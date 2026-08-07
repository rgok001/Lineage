"""Trace worker: turns approved trace_requests into finished genealogies.

Polls Postgres for rows with status='approved' (and ONLY approved — a request
a stranger submitted sits at 'requested' until the owner promotes it), claims
one atomically, then runs the pipeline stages as subprocesses in order:

    corpus_select -> fetch_papers -> extract_text
        -> stage_b_extract -> stage_c_cluster -> stage_d_edges
        -> stage_b_extract --reground -> stage_e_ground
        -> enrich_authors -> stage_f_magnitude -> stage_g_threads
        -> stage_h_claims

Everything after grounding is what the reader actually meets: the authors its
citations need, the scores and threads its front door reads, and the checked
quote under each claim. A map without them exists and is correct, and `/g/[id]`
has nothing to open on, so they are part of a finished trace rather than extras.

The pipeline stays CLI-first: the worker adds nothing to the stages, it just
orchestrates them and streams their stdout into trace_requests.progress so the
app can show "Reading paper 47 of 132" live. Postgres is the queue (FOR UPDATE
SKIP LOCKED); there is no other infrastructure.

Usage:
    python worker/run.py            # poll forever
    python worker/run.py --once     # process at most one job, then exit
"""

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from common import REPO_ROOT, data_dir, env  # noqa: E402

POLL_SECONDS = 10
STALE_RUNNING_MINUTES = 10  # 'running' + no heartbeat for this long => worker died

# Progress markers the stages already print; the worker changes no stage code.
COUNTER_RE = re.compile(r"\[(\d+)/(\d+)\]")
# Digits + at most one decimal part: "$0.0093." at a sentence end must not
# capture the trailing period ([0-9.]+ did, and float() choked on it).
SPEND_RE = re.compile(r"[Ss]pend:? \$([0-9]+(?:\.[0-9]+)?)")


def connect() -> psycopg.Connection:
    # Direct (unpooled) endpoint, same as the pipeline: the worker holds one
    # long-lived connection, which is exactly what the pooler is NOT for.
    return psycopg.connect(env("DATABASE_URL"))


def stages_for(concept: str, corpus_limit: int, field: str,
               gloss: str | None) -> list[tuple[str, list[str]]]:
    py = [sys.executable, "-u"]  # -u: unbuffered, so progress streams live
    corpus_json = str(data_dir() / f"corpus_{re.sub(r'[^a-z0-9]+', '_', concept.lower())}.json")
    # The gloss disambiguates a polysemous sense; it steers corpus relevance and
    # Stage B's extraction question. The field scopes the corpus to a discipline.
    gloss_arg = ["--gloss", gloss] if gloss else []
    return [
        ("select corpus", py + ["pipeline/corpus_select.py", concept,
                                "--limit", str(corpus_limit), "--field", field,
                                "--json", corpus_json] + gloss_arg),
        ("fetch papers", py + ["pipeline/fetch_papers.py", corpus_json]),
        ("extract text", py + ["pipeline/extract_text.py"]),
        # What the grounding check is about to rest on. Free, and it runs here
        # rather than at the end because the verdict describes the text, not the
        # map: a paper whose text lost content is worth knowing about while its
        # quotes are being chosen, not after.
        ("audit extracted text", py + ["pipeline/check_extraction.py",
                                       "--only-unchecked", "--write"]),
        # --corpus scopes Stage B to THIS trace's papers; the papers table is
        # shared across concepts, and without it every past trace's corpus
        # would be re-billed against the new concept.
        ("extract definitions", py + ["pipeline/stage_b_extract.py", concept,
                                      "--corpus", corpus_json] + gloss_arg),
        ("cluster concept-states", py + ["pipeline/stage_c_cluster.py", concept]),
        ("classify edges", py + ["pipeline/stage_d_edges.py", concept]),
        # Free, and it runs immediately before grounding for the same reason
        # Stage E re-copies the edge quotes there: a stamp must not be older than
        # the text it describes. A definition's stamp was the one in the system
        # with no recompute path, so it could only be refreshed by paying for a
        # fresh extraction, and on a map whose papers were re-extracted it kept
        # claiming a check that no longer held. No --corpus here on purpose,
        # unlike extraction: this touches only this concept's own definition
        # rows, so there is nothing to re-bill or overwrite, and scoping it to
        # one trace's corpus would leave a stale stamp on any definition of this
        # concept that came in some other way.
        ("re-check definition quotes", py + ["pipeline/stage_b_extract.py", concept,
                                             "--reground"]),
        ("ground & assemble", py + ["pipeline/stage_e_ground.py", concept]),
        # Authors are needed by nothing upstream and by the export absolutely: a
        # citation without them is omitted from the BibTeX rather than guessed,
        # so a corpus that skips this produces a document whose \cite keys do not
        # resolve. It runs scoped to this concept's map (far fewer requests than
        # the whole papers table) and costs no LLM spend, only arXiv politeness.
        ("fill author metadata", py + ["pipeline/enrich_authors.py",
                                       "--concept", concept]),
        ("score magnitude", py + ["pipeline/stage_f_magnitude.py", concept]),
        ("compose threads", py + ["pipeline/stage_g_threads.py", concept]),
        # The most expensive stage after extraction, and the one that decides
        # whether an account can be audited sentence by sentence or only trusted
        # paragraph by paragraph. It roughly doubles what a map costs; that is
        # the price of the product's central claim, so it runs by default rather
        # than being something a curator has to remember.
        ("check each claim", py + ["pipeline/stage_h_claims.py", concept]),
    ]


class Progress:
    """In-memory progress state, flushed to the row at most once per second."""

    def __init__(self, conn: psycopg.Connection, job_id: int, n_stages: int):
        self.conn, self.job_id, self.n_stages = conn, job_id, n_stages
        # **`spend_usd` starts as null, not 0.0** (issue #87). The report view
        # asks `jsonb_typeof(progress -> 'spend_usd') = 'number'` to tell a
        # recorded figure from one nobody took, and minting a 0.0 here made that
        # test true from the first flush: a completed run that never matched a
        # spend line reported "from the record kept of the last completed run"
        # and rendered US$0.00 under what the map cost, which is the
        # stored-and-aged figure the whole report exists to refuse. A cached
        # re-trace is exactly the run that prints no spend line, so it was the
        # common case rather than the corner.
        self.state: dict = {"stages": n_stages, "spend_usd": None}
        self.base_spend = 0.0   # spend from completed stages
        self.stage_spend = 0.0  # cumulative spend the CURRENT stage has printed
        # Whether any stage has printed a spend line at all in this job. It is
        # the only thing that turns spend_usd into a number, and it never goes
        # back to False: once one stage has priced itself, zero from another
        # stage is a measurement.
        self.spend_seen = False
        self._last_flush = 0.0

    def start_stage(self, no: int, name: str) -> None:
        self.base_spend += self.stage_spend
        self.stage_spend = 0.0
        self.state.update(stage=name, stage_no=no, message=f"starting: {name}",
                          current=None, total=None)
        self.flush(force=True)

    def line(self, text: str) -> None:
        self.state["message"] = text.strip()[:300]
        if m := COUNTER_RE.search(text):
            self.state["current"], self.state["total"] = int(m.group(1)), int(m.group(2))
        if m := SPEND_RE.search(text):
            # Stages print spend cumulatively within themselves.
            self.stage_spend = float(m.group(1))
            self.spend_seen = True
        if self.spend_seen:
            self.state["spend_usd"] = round(self.base_spend + self.stage_spend, 4)
        self.flush()

    def flush(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_flush < 1.0:
            return
        self._last_flush = now
        self.conn.execute(
            "UPDATE trace_requests SET progress = %s, updated_at = now() WHERE id = %s",
            (json.dumps(self.state), self.job_id))
        self.conn.commit()


class Heartbeat:
    """Keeps trace_requests.updated_at fresh while a stage runs, so the
    heartbeat means "worker process alive", not "stdout active".

    Progress only flushes updated_at when a stage prints a newline-terminated
    line, but stages go silent for minutes at a time: the Voyage embedding batch
    in Stage C, a slow LLM call, or a network wait during paper fetching can all
    run with nothing on stdout. During those stretches updated_at would freeze —
    tripping the UI's stall warning and eventually the stale-row sweeper on a
    worker that is perfectly healthy. A background thread bumps updated_at on a
    fixed interval regardless of stdout, so the heartbeat only goes cold when
    the worker is genuinely dead.

    It uses its OWN connection: a psycopg connection is not safe to share across
    threads, and the main thread is busy streaming stdout through Progress on
    the job connection.
    """

    def __init__(self, job_id: int, interval: float = 30.0):
        self.job_id, self.interval = job_id, interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Heartbeat":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        conn = None
        try:
            conn = connect()
            # wait() returns True when stopped, False on timeout: tick, then
            # exit promptly the moment the stage loop is done.
            while not self._stop.wait(self.interval):
                try:
                    # Guarded on status so a late tick can never resurrect a row
                    # that already finished or failed on the main connection.
                    conn.execute(
                        "UPDATE trace_requests SET updated_at = now() "
                        "WHERE id = %s AND status = 'running'", (self.job_id,))
                    conn.commit()
                except Exception as e:  # a cold heartbeat should surface, not crash
                    print(f"[heartbeat] job {self.job_id}: {type(e).__name__}: {e}")
        finally:
            if conn is not None:
                conn.close()


def run_job(conn: psycopg.Connection, job_id: int, concept: str, corpus_limit: int,
            field: str, gloss: str | None) -> None:
    stages = stages_for(concept, corpus_limit, field, gloss)
    prog = Progress(conn, job_id, len(stages))
    tail: list[str] = []  # last lines, kept for the error report on failure

    with Heartbeat(job_id):
        for no, (name, cmd) in enumerate(stages, start=1):
            prog.start_stage(no, name)
            print(f"[job {job_id}] stage {no}/{len(stages)}: {name}")
            proc = subprocess.Popen(
                cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            assert proc.stdout is not None
            for line in proc.stdout:
                print(f"    {line.rstrip()}")
                tail.append(line.rstrip())
                del tail[:-30]
                if line.strip():
                    prog.line(line)
            rc = proc.wait()
            if rc != 0:
                raise StageFailed(f"stage '{name}' exited with code {rc}", tail)

    # Stage E created/updated the genealogy row for (concept, prompt_version).
    pv = env("PROMPT_VERSION", "v2")
    row = conn.execute(
        "SELECT id FROM genealogies WHERE concept = %s AND prompt_version = %s "
        "ORDER BY id DESC LIMIT 1", (concept, pv)).fetchone()
    genealogy_id = row[0] if row else None

    prog.state["message"] = "complete"
    conn.execute(
        """UPDATE trace_requests
           SET status = 'complete', genealogy_id = %s, progress = %s,
               finished_at = now(), updated_at = now()
           WHERE id = %s""",
        (genealogy_id, json.dumps(prog.state), job_id))
    conn.commit()
    # spend_usd is None on a run where no stage printed a spend line, and the
    # log must say that rather than "$0.00" — this line is the operator's copy
    # of the same figure the report publishes, and the two disagreeing is how a
    # cost defect stays invisible. Four decimals because that is the precision
    # `Progress.line` keeps, so a 0.4-cent run reads as a cost and not as free.
    spend = prog.state["spend_usd"]
    print(f"[job {job_id}] complete -> genealogy {genealogy_id}, "
          f"spend {'not recorded (no stage printed one)' if spend is None else f'${spend:.4f}'}")


class StageFailed(Exception):
    def __init__(self, msg: str, tail: list[str]):
        super().__init__(msg)
        self.tail = tail


def fail_job(conn: psycopg.Connection, job_id: int, message: str, tail: list[str]) -> None:
    error = message + ("\n\n--- last output ---\n" + "\n".join(tail) if tail else "")
    conn.execute(
        """UPDATE trace_requests
           SET status = 'failed', error = %s, finished_at = now(), updated_at = now()
           WHERE id = %s""", (error, job_id))
    conn.commit()


def requeue_job(conn: psycopg.Connection, job_id: int) -> None:
    # Interrupted, not broken: back to 'approved'. Re-running is cheap — every
    # LLM stage caches its results, so completed work is not re-billed.
    conn.execute(
        """UPDATE trace_requests
           SET status = 'approved', started_at = NULL, updated_at = now(),
               progress = progress || '{"message": "worker interrupted; requeued"}'
           WHERE id = %s""", (job_id,))
    conn.commit()


def sweep_stale(conn: psycopg.Connection) -> None:
    """A 'running' row with a cold heartbeat means a worker died mid-job."""
    rows = conn.execute(
        """UPDATE trace_requests
           SET status = 'failed', finished_at = now(), updated_at = now(),
               error = 'worker stopped mid-run (heartbeat went stale)'
           WHERE status = 'running'
             AND updated_at < now() - make_interval(mins => %s)
           RETURNING id""", (STALE_RUNNING_MINUTES,)).fetchall()
    conn.commit()
    for (jid,) in rows:
        print(f"[sweep] job {jid}: stale 'running' row marked failed")


def claim(conn: psycopg.Connection) -> tuple[int, str, int, str, str | None] | None:
    row = conn.execute(
        """UPDATE trace_requests
           SET status = 'running', started_at = now(), updated_at = now()
           WHERE id = (SELECT id FROM trace_requests WHERE status = 'approved'
                       ORDER BY decided_at NULLS FIRST, created_at
                       LIMIT 1 FOR UPDATE SKIP LOCKED)
           RETURNING id, concept, corpus_limit, field_id, gloss""").fetchone()
    conn.commit()
    return row


def startup_task(name: str, cmd: list[str]) -> None:
    """Run a housekeeping step at boot, and never let it stop the worker starting.

    A failure here is worth shouting about and not worth dying over: a worker
    that will not boot processes no traces, which is a worse outcome than an
    unapplied migration or an unaudited paper. Both steps are safe to retry, and
    the next restart retries them.
    """
    print(f"[startup] {name}…")
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=900)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"[startup] {name} did not finish ({e}). Continuing.")
        return
    for line in (proc.stdout or "").splitlines():
        print(f"[startup]   {line}")
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        print(f"[startup] {name} FAILED (exit {proc.returncode}). Continuing anyway.")
        for line in tail:
            print(f"[startup]   {line}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run approved trace requests.")
    ap.add_argument("--once", action="store_true", help="process at most one job, then exit")
    ap.add_argument("--poll", type=int, default=POLL_SECONDS, help="poll interval seconds")
    args = ap.parse_args()

    # Two things that used to wait on somebody running a command by hand, on a
    # machine that does not exist. Neither is optional, both are idempotent, and
    # the worker is the only process that has the disk, the database and the repo
    # in one place, so it is the only honest home for them.
    #
    # Migrations first: a deploy that adds a column and a query that reads it ship
    # in the same commit, and the gap between them was a broken page waiting to
    # happen. migrate.py records what it applied, so a second run does nothing.
    startup_task("apply database migrations",
                 [sys.executable, "-u", "pipeline/db/migrate.py"])
    # Then the extraction audit, scoped to papers nobody has looked at yet. Free
    # (no model, no network, disk reads only) and self-limiting: the first run
    # backfills the corpora already on the disk, later runs find little to do.
    startup_task("audit extracted text",
                 [sys.executable, "-u", "pipeline/check_extraction.py",
                  "--only-unchecked", "--write"])

    conn = connect()
    print(f"Worker up. Polling every {args.poll}s for approved trace requests…")
    while True:
        sweep_stale(conn)
        job = claim(conn)
        if job is None:
            if args.once:
                print("No approved jobs. Exiting (--once).")
                return
            time.sleep(args.poll)
            continue

        job_id, concept, corpus_limit, field, gloss = job
        print(f'[job {job_id}] claimed: "{concept}" (field {field}, corpus limit {corpus_limit}'
              f'{", glossed" if gloss else ""})')
        try:
            run_job(conn, job_id, concept, corpus_limit, field, gloss)
        except StageFailed as e:
            print(f"[job {job_id}] FAILED: {e}")
            fail_job(conn, job_id, str(e), e.tail)
        except KeyboardInterrupt:
            print(f"\n[job {job_id}] interrupted — requeueing as 'approved'")
            requeue_job(conn, job_id)
            return
        except Exception as e:  # worker bug or DB hiccup: fail loud, keep living
            print(f"[job {job_id}] ERROR: {type(e).__name__}: {e}")
            fail_job(conn, job_id, f"{type(e).__name__}: {e}", [])

        if args.once:
            return


if __name__ == "__main__":
    main()

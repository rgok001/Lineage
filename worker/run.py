"""Trace worker: turns approved trace_requests into finished genealogies.

Polls Postgres for rows with status='approved' (and ONLY approved — a request
a stranger submitted sits at 'requested' until the owner promotes it), claims
one atomically, then runs the pipeline stages as subprocesses in order:

    corpus_select -> fetch_papers -> extract_text
        -> stage_b_extract -> stage_c_cluster -> stage_d_edges -> stage_e_ground

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
        # --corpus scopes Stage B to THIS trace's papers; the papers table is
        # shared across concepts, and without it every past trace's corpus
        # would be re-billed against the new concept.
        ("extract definitions", py + ["pipeline/stage_b_extract.py", concept,
                                      "--corpus", corpus_json] + gloss_arg),
        ("cluster concept-states", py + ["pipeline/stage_c_cluster.py", concept]),
        ("classify edges", py + ["pipeline/stage_d_edges.py", concept]),
        ("ground & assemble", py + ["pipeline/stage_e_ground.py", concept]),
    ]


class Progress:
    """In-memory progress state, flushed to the row at most once per second."""

    def __init__(self, conn: psycopg.Connection, job_id: int, n_stages: int):
        self.conn, self.job_id, self.n_stages = conn, job_id, n_stages
        self.state: dict = {"stages": n_stages, "spend_usd": 0.0}
        self.base_spend = 0.0   # spend from completed stages
        self.stage_spend = 0.0  # cumulative spend the CURRENT stage has printed
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


def run_job(conn: psycopg.Connection, job_id: int, concept: str, corpus_limit: int,
            field: str, gloss: str | None) -> None:
    stages = stages_for(concept, corpus_limit, field, gloss)
    prog = Progress(conn, job_id, len(stages))
    tail: list[str] = []  # last lines, kept for the error report on failure

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
    print(f"[job {job_id}] complete -> genealogy {genealogy_id}, "
          f"spend ${prog.state['spend_usd']:.2f}")


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


def main() -> None:
    ap = argparse.ArgumentParser(description="Run approved trace requests.")
    ap.add_argument("--once", action="store_true", help="process at most one job, then exit")
    ap.add_argument("--poll", type=int, default=POLL_SECONDS, help="poll interval seconds")
    args = ap.parse_args()

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

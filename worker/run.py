"""Trace worker: turns approved trace_requests into finished genealogies.

Polls Postgres for rows with status='approved' (and ONLY approved — a request
a stranger submitted sits at 'requested' until the owner promotes it), claims
one atomically, then runs the pipeline stages as subprocesses.

**A build runs in two passes** (#192, the design on #184). Pass one selects a
corpus the way it always did and assembles a map from it; pass two then asks that
map which of its papers were the turning points, reads the recent work that cites
them, and re-clusters over both passes together. Only then is the map published.

    BEFORE    save the current map, if this concept already has one
    PASS ONE  select corpus -> fetch -> extract -> audit -> B -> C -> D
                  -> reground -> E --no-publish -> record pass one
                  -> record the papers a person named
    PASS TWO  pass_two_select -> fetch -> extract -> audit -> B --dry-run
                  -> [the spend gate] -> B -> union -> C -> D
                  -> reground -> E --no-publish -> record pass two
    FINISH    record the build -> enrich authors -> F -> G -> H
                  -> record what each step spent -> E (the one publish)

Four things carry that shape and each has a reason that would be expensive to
rediscover.

**Nothing is destroyed before the old map is saved.** A trace against a concept
that already has a map is a rebuild, and Stage C's first write is where the old
one starts disappearing. The build's first act is therefore `snapshot_map.py`,
which writes the whole row and everything hanging off it — the threads and the
curatorial edits Stage E's export does not hold — to a timestamped file under
DATA_DIR. It runs ahead of corpus selection rather than beside Stage C because a
snapshot that cannot be taken should cost the build nothing, and because fetching
and extraction rewrite the text on disk the live map's quotes were checked
against. A failure, or a success that leaves no record of itself, fails the job
while the map is still untouched (#173).

**Publication happens once, at the very end.** Every assembly before it runs
`--no-publish`, so `status` never reaches 'complete' while the map is still being
re-clustered underneath it — which since #168 is the same thing as saying no
reader can see a half-built map. It is last rather than at the end of pass two
because Stage G writes the threads clause 6 of the publish invariant reads
(#171's residue): publishing at Stage E means the invariant judges the PREVIOUS
build's threads over the new concept-states, and refuses a re-trace after every
paid step. Recomposing the threads before the gate reads them is the repair, and
it is free.

**Pass two is bounded and abandonable.** It gets a seat count, not a second
spend cap — the per-trace cap is the one number protecting the owner from a
runaway, and a cap beside it is a way to exceed it. Before pass two buys
anything the cost is estimated and checked against what is left of that one cap;
if it does not fit, pass one's map is published and the reason is written into
the progress feed and the map's own record. Pass one is a complete, coherent,
publishable map by construction, which is what converts the spend cap from a
build-killer into a degradation.

**A pass-two failure degrades to pass one rather than failing the build.** The
same fallback covers all of them: re-cluster over the pass-one corpus, re-classify
(free, #172), re-assemble, publish. A build that read 150 papers should not be
thrown away because the optional second pass broke — but it never happens
silently: the outcome sentence names the stage that failed, and it is on the
report, in the log and in the feed.

Everything after grounding is what the reader actually meets: the authors its
citations need, the scores and threads its front door reads, and the checked
quote under each claim. A map without them exists and is correct, and `/g/[id]`
has nothing to open on, so they are part of a finished trace rather than extras.

The pipeline stays CLI-first: the worker adds nothing to the stages, it just
orchestrates them and streams their stdout into trace_requests.progress so the
app can show "Reading paper 47 of 132" live. What the worker does decide is which
phases run, and every one of those decisions is taken from a file a stage wrote —
the pass-two funnel counts and the pre-flight estimate — rather than from a regex
over a stage's prose. Postgres is the queue (FOR UPDATE SKIP LOCKED); there is no
other infrastructure.

Interruption is a first-class outcome here, and it is not failure: every deploy
of this repo restarts the worker, so a build that is killed mid-run is normal
operating weather rather than a defect (#178). A killed job goes back on the
queue and re-runs; a stage that exits nonzero on its own still fails. The line
between those two is drawn in `classify_stage_exit` and nowhere else.

Usage:
    python worker/run.py            # poll forever
    python worker/run.py --once     # process at most one job, then exit
"""

import argparse
import contextlib
import json
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from common import REPO_ROOT, data_dir, env  # noqa: E402
# The seat count's divisor has one home, in the stage that owns the flag, and the
# worker reads it rather than restating it: a constant restated in a second file
# is a constant with two values as soon as one of them moves.
from pass_two_select import PASS_TWO_SEATS_DIVISOR  # noqa: E402

POLL_SECONDS = 10
STALE_RUNNING_MINUTES = 10  # 'running' + no heartbeat for this long => worker died
# How many times the sweep will put a job back on the queue after finding it
# abandoned, before it gives up and fails it. Three, because two consecutive
# deploys landing on one build has already happened (#178: pushes 4 minutes
# apart killed two builds) and three is comfortably past that, while a job that
# has died four times is not going to survive the fifth attempt either. The cap
# is the only thing standing between a crash-looping worker and unbounded spend:
# restarts are cheap for B, C, D and H, which cache, and merely cheap-ish for F
# and G, which do not (decision 39 corrects decision 38's "every LLM stage caches
# per paper", which was false when it was written). Cheap either way is not free,
# and the spend cap in CLAUDE.md is per trace, not per job-lifetime.
MAX_AUTO_REQUEUES = 3

# Progress markers the stages already print; the worker changes no stage code.
COUNTER_RE = re.compile(r"\[(\d+)/(\d+)\]")
# Digits + at most one decimal part: "$0.0093." at a sentence end must not
# capture the trailing period ([0-9.]+ did, and float() choked on it).
SPEND_RE = re.compile(r"[Ss]pend:? \$([0-9]+(?:\.[0-9]+)?)")


class Shutdown(Exception):
    """Something outside this process asked it to stop: a deploy's SIGTERM, or
    an operator's Ctrl-C. Interrupted, not broken."""


# Set by the signal handler and read by classify_stage_exit. A module-level bool
# because a signal handler may only touch what is safe to touch mid-instruction:
# assigning a global is, and anything that takes a lock or a database connection
# is not.
_shutting_down = False


def _on_shutdown_signal(signum: int, _frame) -> None:
    global _shutting_down
    _shutting_down = True
    # Raising here is what makes the requeue happen at all. The main thread
    # spends a build blocked on a read of the stage's stdout; PEP 475 has the
    # interpreter run this handler when that read is interrupted and propagate
    # whatever it raises, so the exception lands in main()'s handler with the
    # job id still in hand. The flag matters too: the deploy's SIGTERM goes to
    # the whole process group, so the stage subprocess dies of the same signal
    # and its nonzero exit must not be read as a stage failure. Whichever of the
    # two arrives at the top first, the job requeues.
    raise Shutdown(f"received signal {signum}")


def install_shutdown_handler() -> None:
    """Make SIGTERM behave like Ctrl-C.

    Render's deploy stops the old worker with SIGTERM and waits before SIGKILL,
    so there is a window in which this process can put its job back on the queue
    (docs/RUNBOOK.md, deploying the worker). Before #178 nothing caught SIGTERM:
    KeyboardInterrupt covers SIGINT only, so every deploy killed its in-flight
    build with the row still marked 'running' and the sweep later failed it.

    Windows accepts the registration but does not deliver SIGTERM the way POSIX
    does (a process there is terminated, not signalled), so this is a no-op for
    `python worker/run.py` on the dev machine rather than a behaviour to test
    locally. It is wrapped anyway: a worker that will not boot processes no
    traces, which is the same reasoning startup_task is built on.
    """
    for name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _on_shutdown_signal)
        except (ValueError, OSError) as e:
            # ValueError: not the main thread, or the platform refuses this one.
            print(f"[worker] could not install a {name} handler: {type(e).__name__}: {e}")


def classify_stage_exit(rc: int, shutting_down: bool) -> str:
    """What a finished stage subprocess means: 'ok', 'interrupted' or 'failed'.

    The whole of #178 turns on this being two different things rather than one,
    so it is a function with no I/O that can be exercised without a worker, a
    database or a signal.

    **Interrupted is infrastructure and requeues.** The signal that stopped us
    stopped the stage too (same process group), so its exit code is evidence
    about the deploy and not about the stage. It is checked first for that
    reason: a stage killed by SIGTERM reports a nonzero rc and is not a failure.

    **Failed is a defect and stays failed.** A stage that chose to exit nonzero
    while nobody was shutting us down has diagnostics attached and will exit the
    same way next time. Restarting it automatically would re-bill for a
    deterministic failure and bury the error under repeat attempts, which is
    exactly what the owner did NOT ask for.
    """
    if shutting_down:
        return "interrupted"
    return "ok" if rc == 0 else "failed"


def connect() -> psycopg.Connection:
    # Direct (unpooled) endpoint, same as the pipeline: the worker holds one
    # long-lived connection, which is exactly what the pooler is NOT for.
    return psycopg.connect(env("DATABASE_URL"))


def prompt_version() -> str:
    """The prompt version this build's stages will write under.

    One reading, in one place. It was `env("PROMPT_VERSION", "v2")` here and
    `env("PROMPT_VERSION", "v1")` in every stage, so on a machine with the
    variable unset the worker looked up a map at a version nothing had written
    and reported the finished trace with no genealogy_id. Both real environments
    set it, so the divergence never bit; it is corrected here because #192 adds
    three more places in this file that have to agree with the stages about which
    map is being built.
    """
    return env("PROMPT_VERSION", "v1")


def pass_two_seats(corpus_limit: int) -> int:
    """R: how many papers pass two may add.

    `corpus_limit // 10` by default, which is 15 of 150 — the divisor rather than
    a literal for #181's reason, because the seat count has to follow the corpus
    cap or a 50-paper build gets a 15-paper second pass and is a different
    product. PASS_TWO_SEATS overrides it, and **0 disables the second pass
    entirely**: that is the one way to ask this worker for a genuinely one-pass
    build, and such a build writes no build record at all, so its report says "this
    map was built in one pass" and draws no pass figures (#193's seam semantics).
    """
    override = env("PASS_TWO_SEATS", "").strip()
    if override:
        try:
            return max(0, int(override))
        except ValueError:
            # Not fatal: a mistyped seat count should not stop a build that has an
            # obvious right answer, but it must not be read as 0 either, which
            # would silently turn every build one-pass.
            print(f"[worker] PASS_TWO_SEATS={override!r} is not a whole number; "
                  f"using the default instead")
    return max(0, corpus_limit // PASS_TWO_SEATS_DIVISOR)


def trace_paths(concept: str) -> dict[str, str]:
    """Every file this build hands from one stage to another, named once.

    The pass-one corpus keeps the name it has always had, so a requeued build
    (#178) finds the file its killed predecessor wrote and re-reads it rather than
    re-selecting a corpus from an OpenAlex that has moved since.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", concept.lower())
    d = data_dir()
    return {
        "corpus_one": str(d / f"corpus_{slug}.json"),
        "corpus_two": str(d / f"corpus_{slug}_pass2.json"),
        "corpus_union": str(d / f"corpus_{slug}_union.json"),
        "pass_two_stats": str(d / f"pass2_stats_{slug}.json"),
        "pass_two_estimate": str(d / f"pass2_estimate_{slug}.json"),
        # Not the snapshot itself — that is timestamped and kept forever under
        # DATA_DIR/snapshots/. This is the note saying where the last one went,
        # and it is overwritten every build on purpose.
        "snapshot_result": str(d / f"snapshot_{slug}.json"),
        # What each step of this build spent and how long it took (#47). Written
        # by the worker after every step rather than once at the end, so a build
        # that dies mid-run leaves on disk what it had spent by then — the file is
        # the only place that survives a failure, since the database record is
        # written by a step near the end. Overwritten every build, like the
        # snapshot note above.
        "stage_ledger": str(d / f"stages_{slug}.json"),
    }


def plan_for(concept: str, corpus_limit: int, field: str, gloss: str | None,
             anchors: list[str] | None = None,
             named_by: str | None = None) -> dict[str, list[tuple[str, list[str]]]]:
    """Every phase of a two-pass build, as (name, argv) pairs.

    Phases rather than one flat list, because which of them run is decided while
    the build runs: pass two may be skipped before it is selected, abandoned at
    the spend gate, or fall back after a stage of it fails. The names are what the
    progress feed shows a requester, so they say what is happening in the register
    the feed already uses — a count of something done, never a claim about the
    field.
    """
    py = [sys.executable, "-u"]  # -u: unbuffered, so progress streams live
    paths = trace_paths(concept)
    corpus_json = paths["corpus_one"]
    # The gloss disambiguates a polysemous sense; it steers corpus relevance and
    # Stage B's extraction question. The field scopes the corpus to a discipline.
    gloss_arg = ["--gloss", gloss] if gloss else []
    # The papers the requester named (#198). Pass-through and nothing more: the
    # worker adds no rule of its own about them, and every one of the design's
    # five conditions is enforced where it belongs — the cap and the shape at the
    # form, existence and the additive seat in `corpus_select.py`, the reading in
    # Stage B, the citation link in Stage D, the disclosure in `record_anchors.py`.
    # A named id that resolves to nothing fails corpus selection by name, which is
    # the first step of pass one and has spent nothing when it does.
    anchor_args = [a for aid in (anchors or []) for a in ("--anchor", aid)]
    named_by_arg = ["--named-by", named_by] if named_by else []
    seats = pass_two_seats(corpus_limit)

    # ── before anything ─────────────────────────────────────────────────────
    #
    # The first step of every build, ahead of even corpus selection, and a phase
    # of its own so that the worker can read what it wrote before the next stage
    # starts (#173).
    #
    # **Why first rather than immediately before Stage C**, which is where the
    # design put it and which is the actual moment of destruction (`UPSERT_GENEALOGY`
    # rewrites `nodes` and sets `status = 'running'`; `CLEAR_STALE_EDGES` takes the
    # relationships whose meaning moved). Two reasons, and neither is tidiness.
    # Between here and Stage C sit `fetch_papers.py` and `extract_text.py`, which
    # rewrite the extracted text on disk that the live map's verified quotes were
    # checked against — so a step of this build damages the snapshot's usefulness
    # before Stage C is reached. And a snapshot that fails should cost the build
    # nothing: here it costs no arXiv politeness and no money, and the refusal is
    # unambiguously upstream of every write, which is the property this step is for.
    #
    # Once per job, not once per pass. Pass two re-clusters the same map, and by
    # then pass one has already overwritten it: there is nothing left to save that
    # this snapshot does not hold.
    snapshot = [
        ("save the current map", py + ["pipeline/snapshot_map.py", concept,
                                       "--allow-missing",
                                       "--result-json", paths["snapshot_result"]]),
    ]

    pass_one = [
        ("select corpus", py + ["pipeline/corpus_select.py", concept,
                                "--limit", str(corpus_limit), "--field", field,
                                "--json", corpus_json] + gloss_arg + anchor_args),
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
        # --corpus again, and for the second half of the same reason: without it
        # a map's membership is whatever is in the definitions table for this
        # concept, so any row arriving by any other route joins the map at the
        # next clustering (#190). Stage B's flag stops a past trace's corpus
        # being re-billed; this one stops it being clustered in.
        ("cluster concept-states", py + ["pipeline/stage_c_cluster.py", concept,
                                         "--corpus", corpus_json]),
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
        # --no-publish: pass one's map is complete and coherent and nobody may see
        # it yet (#192). It is assembled anyway, rather than left at Stage D,
        # because the export is the de-facto backup (incident 4) and because pass
        # two nominates from a map whose edges have been swept of orphans.
        ("ground & assemble pass one", py + ["pipeline/stage_e_ground.py", concept,
                                             "--no-publish"]),
        ("record what pass one read", py + ["pipeline/record_pass.py", concept,
                                            "--pass", "1", "--corpus", corpus_json]),
        # On EVERY build, anchored or not, because the step also clears what a
        # previous build of this map recorded: a map anchored once and rebuilt
        # with nobody named must come back saying nobody named a paper. It is
        # here rather than in `finish` because the corpus it reads is pass one's
        # and because it needs the genealogy row Stage C has just written; pass
        # two adds papers and cannot add named ones.
        ("record the papers a person named",
         py + ["pipeline/record_anchors.py", concept,
               "--corpus", corpus_json] + named_by_arg),
    ]

    # ── pass two ────────────────────────────────────────────────────────────
    #
    # Split into three phases because two decisions sit between them, and each
    # decision is taken from a file rather than from a stage's prose: the funnel
    # counts `pass_two_select.py --stats-json` writes, and the estimate
    # `stage_b_extract.py --dry-run --estimate-json` writes.
    pass_two_select_phase = [
        ("pass two: ask the map what came next",
         py + ["pipeline/pass_two_select.py", concept, "--field", field,
               "--pass-two-seats", str(seats), "--pass-one-limit", str(corpus_limit),
               "--json", paths["corpus_two"],
               "--stats-json", paths["pass_two_stats"]] + gloss_arg),
    ]
    # Fetching and extracting cost time and arXiv politeness and no money, and the
    # estimate is a token count over the text on disk — so the text has to exist
    # before there is anything to estimate. The spend gate therefore sits AFTER
    # this phase and before the one below it, which is the first that can bill
    # anything. The design says the estimate comes before pass two spends
    # anything, and it does: what is spent before it is patience.
    pass_two_fetch_phase = [
        ("pass two: fetch the nominated papers",
         py + ["pipeline/fetch_papers.py", paths["corpus_two"]]),
        ("pass two: extract text", py + ["pipeline/extract_text.py"]),
        ("pass two: audit extracted text",
         py + ["pipeline/check_extraction.py", "--only-unchecked", "--write"]),
        ("pass two: estimate what reading them costs",
         py + ["pipeline/stage_b_extract.py", concept, "--corpus", paths["corpus_two"],
               "--dry-run", "--estimate-json", paths["pass_two_estimate"]] + gloss_arg),
    ]
    pass_two_read_phase = [
        ("pass two: read the nominated papers",
         py + ["pipeline/stage_b_extract.py", concept,
               "--corpus", paths["corpus_two"]] + gloss_arg),
        ("pass two: join both passes' corpora",
         py + ["pipeline/corpus_union.py", "--json", paths["corpus_union"],
               corpus_json, paths["corpus_two"]]),
        # Stage C re-clusters EVERYTHING rather than assigning the new papers
        # incrementally. Incremental assignment is cheaper and wrong: it is a
        # different algorithm, so a two-stage map would not be the map a one-stage
        # build over the same papers produces, and `meanings` on the report would
        # quietly mean something else on two-stage maps. Pre-publish, decision
        # 20's edge-clearing costs money and nothing else.
        ("pass two: re-cluster over both passes",
         py + ["pipeline/stage_c_cluster.py", concept, "--corpus", paths["corpus_union"]]),
        # Nearly free: #172 caches a classification on the two papers' definitions
        # and citation contexts, and #189 makes a cluster's label a function of its
        # membership, so an unchanged pair comes back from disk for $0. That pair
        # of tickets is what makes this design affordable at all.
        ("pass two: classify edges", py + ["pipeline/stage_d_edges.py", concept]),
        ("pass two: re-check definition quotes",
         py + ["pipeline/stage_b_extract.py", concept, "--reground"]),
        ("pass two: ground & assemble", py + ["pipeline/stage_e_ground.py", concept,
                                              "--no-publish"]),
        ("record what pass two read", py + ["pipeline/record_pass.py", concept,
                                            "--pass", "2", "--corpus", paths["corpus_two"]]),
    ]
    # The abandonment fallback, and the same one covers every way pass two can
    # fail after it has touched the map: re-cluster over the pass-one corpus
    # alone, which is what #190 exists to make nameable, then re-classify and
    # re-assemble. With #172 and #189 it costs $0 and a few minutes.
    pass_two_fallback_phase = [
        ("fall back: re-cluster over pass one alone",
         py + ["pipeline/stage_c_cluster.py", concept, "--corpus", corpus_json]),
        ("fall back: classify edges", py + ["pipeline/stage_d_edges.py", concept]),
        ("fall back: re-check definition quotes",
         py + ["pipeline/stage_b_extract.py", concept, "--reground"]),
        ("fall back: ground & assemble", py + ["pipeline/stage_e_ground.py", concept,
                                               "--no-publish"]),
        # Recorded even though the map is pass one's. Pass two DID read these
        # papers — Stage B bought their definitions and the report's population is
        # the definitions rows (#123) — so leaving them unmarked would put them in
        # `papers_read_pass_unmarked`, which the report calls a build that recorded
        # itself incompletely. What separates this from a successful second pass on
        # the report is the outcome sentence and the count of pass-two papers
        # carrying a relationship into a first-pass meaning, which is zero here
        # because none of them is in the map.
        ("record what pass two read", py + ["pipeline/record_pass.py", concept,
                                            "--pass", "2", "--corpus", paths["corpus_two"]]),
    ]

    finish = [
        # Authors are needed by nothing upstream and by the export absolutely: a
        # citation without them is omitted from the BibTeX rather than guessed,
        # so a corpus that skips this produces a document whose \cite keys do not
        # resolve. It runs scoped to this concept's map (far fewer requests than
        # the whole papers table) and costs no LLM spend, only arXiv politeness.
        ("fill author metadata", py + ["pipeline/enrich_authors.py",
                                       "--concept", concept]),
        ("score magnitude", py + ["pipeline/stage_f_magnitude.py", concept]),
        # Before the publish, not after it, and that ordering is the whole repair
        # of #171's residue: clause 6 of the publish invariant compares the stored
        # threads against the map's papers, so a gate that runs before Stage G
        # judges the previous build's threads over this build's concept-states and
        # refuses a re-trace at the last step for a state it is about to fix.
        ("compose threads", py + ["pipeline/stage_g_threads.py", concept]),
        # The most expensive stage after extraction, and the one that decides
        # whether an account can be audited sentence by sentence or only trusted
        # paragraph by paragraph. It roughly doubles what a map costs; that is
        # the price of the product's central claim, so it runs by default rather
        # than being something a curator has to remember. It runs ONCE, after both
        # passes, which is the single largest cost decision in the two-stage
        # design: it has no cross-run cache, so running it inside pass one would
        # buy an account of a map that is about to be re-clustered.
        ("check each claim", py + ["pipeline/stage_h_claims.py", concept]),
        # What every step above spent, from the ledger this worker has been
        # writing as it went (#47). Second to last, and not last, for one reason:
        # a step that exits nonzero fails the build, and every other recording
        # step in this plan does so while the map is still unpublished. Put after
        # the publish it would fail a job whose map is already live, which is a
        # worse thing to be than a build that stopped before publishing.
        #
        # The cost of that placement is that the ledger cannot contain this step
        # or the publish after it. Neither prints a cost line, so the recorded
        # total still equals the run's; what it does mean is that the recorded
        # WALL CLOCK is short by two steps, and every surface calls it the time in
        # the recorded steps rather than the run's time.
        ("record what each step of this build spent",
         py + ["pipeline/record_spend.py", concept,
               "--stages", paths["stage_ledger"]]),
        # The one publish. Grounding again costs nothing — it reads files and
        # compares digests — and this run is the one that asks the publish
        # invariant and moves the status, with the threads Stage G has just
        # written under clause 6.
        ("ground & publish", py + ["pipeline/stage_e_ground.py", concept]),
    ]

    return {"snapshot": snapshot,
            "pass_one": pass_one, "pass_two_select": pass_two_select_phase,
            "pass_two_fetch": pass_two_fetch_phase, "pass_two_read": pass_two_read_phase,
            "pass_two_fallback": pass_two_fallback_phase, "finish": finish,
            "seats": seats, "paths": paths}


def stages_for(concept: str, corpus_limit: int, field: str, gloss: str | None,
               anchors: list[str] | None = None,
               named_by: str | None = None) -> list[tuple[str, list[str]]]:
    """The nominal sequence: both passes run and nothing is skipped.

    What the progress feed's stage count is initialised from, and the one flat
    view of a build for anyone reading this file or driving it from a harness. A
    real build runs a subset of it plus, at most, one build-record step and the
    fallback.
    """
    p = plan_for(concept, corpus_limit, field, gloss, anchors, named_by)
    return (p["snapshot"] + p["pass_one"] + p["pass_two_select"] + p["pass_two_fetch"]
            + p["pass_two_read"] + p["finish"])


# ── what the second pass may say about itself ──────────────────────────────
#
# One author for the sentence a reader meets under "why the second pass ended"
# on the report (#193's rule: `pass_two_outcome` is reader-ready text and never a
# code, because nothing between here and the page translates it).
#
# **Five states, all counts and no adjectives.** The design names four; the fifth
# is a pass that failed and fell back, which cannot be inferred from any count.
# None of them may say the idea moved recently, that the map is current, or
# anything that blends these numbers into a score — `Filled 15 of 15` says we
# filled our seats and nothing more (#184, and decision 15's reason).
def pass_two_outcome_sentence(state: str, *, seats: int = 0, selected: int = 0,
                              since: int | None = None, cleared: int | None = None,
                              estimate: float | None = None, remaining: float | None = None,
                              cap: float | None = None, stage: str | None = None) -> str:
    if state == "filled":
        return (f"The second pass filled all {seats} of its seats and read them.")
    if state == "under_filled":
        return (f"The second pass filled {selected} of its {seats} seats and read them: "
                f"the candidates ran out before the seats did.")
    if state in ("none_found", "none_seated", "map_has_no_openalex_ids"):
        if state == "map_has_no_openalex_ids":
            return ("The second pass could not run: none of this map's papers carries an "
                    "OpenAlex id, so the citation graph could not be asked what cites them.")
        if state == "none_seated":
            return (f"The second pass seated nobody: {cleared} recent paper(s) cleared both "
                    f"signals of the gate and none of them could be seated.")
        return (f"The second pass found nobody to read: no arXiv paper from "
                f"{since if since is not None else 'the recency window'} or later cites "
                f"two or more of this map's papers. That is a fact about the citation "
                f"graph, not about the field.")
    if state == "abandoned_spend_cap":
        return (f"The second pass was not run: reading its papers was estimated at "
                f"US${estimate:.2f} and US${remaining:.2f} of the US${cap:.2f} spend cap "
                f"was left. Pass one's map was published as it stood.")
    if state == "abandoned_no_estimate":
        return ("The second pass was not run: the estimate of what it would cost could "
                "not be read, and nothing here spends on an unmeasured basis. Pass one's "
                "map was published as it stood.")
    if state == "failed":
        return (f"The second pass failed while '{stage}' was running and the build fell "
                f"back to pass one's map, which was published as it stood.")
    # A state nobody has taught this function about is still a sentence rather
    # than a code on the page, and it says plainly that it cannot account for
    # itself — the alternative is a page reading `unknown`.
    return (f"The second pass ended in a state this build could not account for "
            f"({state}). Pass one's map was published as it stood.")


def read_json_file(path: str, what: str) -> dict | None:
    """A file one stage wrote and the next decision depends on.

    Returns None rather than raising: every caller here has a defined answer for
    "the file is not there or is not readable", and it is never "carry on as if it
    said yes". The reason is printed, because a build that quietly abandoned its
    second pass over an unreadable file is indistinguishable in a log from one
    whose field had no recent work.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[worker] could not read the {what} at {path}: {type(exc).__name__}: {exc}")
        return None
    if not isinstance(data, dict):
        print(f"[worker] the {what} at {path} is not an object; it holds "
              f"{type(data).__name__}")
        return None
    return data


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
        # How many spend lines the CURRENT stage has printed. It is what tells a
        # stage that priced itself at zero from a stage that priced itself not at
        # all, per stage rather than per job, and it is the only thing #47's
        # record has that `spend_seen` below does not (#87 is the same
        # distinction one level up). Reset on every stage, like stage_spend.
        self.stage_spend_lines = 0
        # Whether any stage has printed a spend line at all in this job. It is
        # the only thing that turns spend_usd into a number, and it never goes
        # back to False: once one stage has priced itself, zero from another
        # stage is a measurement.
        self.spend_seen = False
        self._last_flush = 0.0

    def start_stage(self, no: int, name: str) -> None:
        self.base_spend += self.stage_spend
        self.stage_spend = 0.0
        self.stage_spend_lines = 0
        self.state.update(stage=name, stage_no=no, message=f"starting: {name}",
                          current=None, total=None)
        self.flush(force=True)

    def set_total(self, n_stages: int) -> None:
        """How many stages this build will actually run.

        It moves, because a two-stage build decides while it is running whether
        its second pass happens (#192). It is initialised from the nominal plan —
        both passes, nothing skipped — and corrected downward the moment a pass is
        skipped or abandoned, with the reason going into the feed as a message on
        the same flush. A total that silently stayed at 28 while the build ran 16
        stages would leave a requester's progress bar stuck at 57% on a finished
        map.
        """
        self.n_stages = n_stages
        self.state["stages"] = n_stages
        self.flush(force=True)

    def note(self, text: str) -> None:
        """A line the WORKER says, in the same feed the stages write to.

        The pass boundaries are the only things in a build that no single stage
        can narrate, because they are about the build's shape rather than about
        any stage's work. Same register as the stages: a count of something done,
        never a claim about the field (#184).
        """
        print(f"    [feed] {text}")
        self.state["message"] = text.strip()[:300]
        self.flush(force=True)

    def spent(self) -> float:
        """What the stages have said they spent so far, this job.

        The same figure `spend_usd` publishes, and it carries the same weakness:
        it is a regex over what the stages print (#85), so a stage that stops
        printing its spend drops out of it with no error. Since #47 the same
        scrape is also kept per stage and written to the map's record, which does
        not make the scrape more accurate — it is the same numbers — but it does
        mean a step contributing nothing is a named row with no figure rather than
        an absence inside a total. It is what the pre-flight gate has to decide
        on, so the gate prints it and names its basis rather than implying a
        precision it does not have.
        """
        return round(self.base_spend + self.stage_spend, 4)

    def line(self, text: str) -> None:
        self.state["message"] = text.strip()[:300]
        if m := COUNTER_RE.search(text):
            self.state["current"], self.state["total"] = int(m.group(1)), int(m.group(2))
        if m := SPEND_RE.search(text):
            # Stages print spend cumulatively within themselves.
            self.stage_spend = float(m.group(1))
            self.stage_spend_lines += 1
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
                    # Sweep from here too, and bump first so this job's own row
                    # can never be the one swept (#178). The main loop sweeps
                    # once per poll, but it only polls when it is NOT running a
                    # job: a job abandoned by a worker instance that died stayed
                    # visibly 'running' with a frozen progress feed for as long
                    # as this worker's current build lasted, which is up to
                    # twenty minutes. This thread wakes every 30s regardless of
                    # what the main thread is doing, so the correction is
                    # seconds late instead of a build late.
                    sweep_stale(conn)
                except Exception as e:  # a cold heartbeat should surface, not crash
                    print(f"[heartbeat] job {self.job_id}: {type(e).__name__}: {e}")
        finally:
            if conn is not None:
                conn.close()


class StageRunner:
    """Runs one stage as a subprocess and decides what its ending meant.

    Lifted out of `run_job` when the build stopped being one flat list (#192).
    The body is unchanged: same Popen, same line streaming into Progress, same
    `classify_stage_exit` deciding between interrupted and failed, and it is
    still the only place that decision is taken. What it adds is a running stage
    number, so phases that are decided while the build runs still number
    continuously in the feed.

    **And, since #47, the ledger of what each step spent.** Nothing new is
    measured for it: `Progress` has parsed every stage's spend line since the feed
    existed and has always reset its per-stage total on `start_stage`, so all this
    does is keep that number when the stage ends instead of folding it into a
    running sum. The ledger is written to disk after every step — including a step
    that failed, whose money was spent all the same — because the database record
    of it is written by a step near the end of the build and a build that dies
    before that would otherwise leave nothing behind.
    """

    def __init__(self, prog: "Progress", job_id: int,
                 ledger_path: str | None = None, run_id: int | None = None):
        self.prog, self.job_id = prog, job_id
        self.no = 0
        self.tail: list[str] = []  # last lines, kept for the error report on failure
        self.ledger_path, self.run_id = ledger_path, run_id
        self.ledger: list[dict] = []
        # Which pass the steps being run now belong to. NULL for the snapshot and
        # for the finishing stages, which run once and belong to neither.
        self.build_pass: int | None = None

    @contextlib.contextmanager
    def in_pass(self, n: int | None):
        """Mark every step run inside this block as belonging to pass `n`.

        A context manager rather than two assignments because `run_pass_two`
        returns from seven places, and a restore written after the call would be
        skipped by six of them — leaving the finishing stages recorded as
        second-pass work on every build that skipped its second pass.
        """
        previous = self.build_pass
        self.build_pass = n
        try:
            yield
        finally:
            self.build_pass = previous

    def _remember(self, name: str, started: float) -> None:
        self.ledger.append({
            "stage_no": self.no,
            "stage": name,
            "build_pass": self.build_pass,
            # **The absent form is null and never 0.0** (#87, and migration 024's
            # CHECK). A step that printed no cost line spent nothing this system
            # can testify to, which is not the same claim as a step that priced
            # itself at zero — Stage C with every label cached prints `$0.0000`
            # deliberately and is the second kind.
            "spend_usd": (round(self.prog.stage_spend, 4)
                          if self.prog.stage_spend_lines else None),
            "spend_lines": self.prog.stage_spend_lines,
            "seconds": round(time.monotonic() - started, 3),
        })
        if self.ledger_path is None:
            return
        try:
            Path(self.ledger_path).write_text(
                json.dumps({"job_id": self.job_id, "run_id": self.run_id,
                            "stages": self.ledger}, indent=1),
                encoding="utf-8")
        except OSError as exc:
            # Never fatal. Losing the breakdown of what a build spent is worth a
            # line in the log; losing the build over it is not, and the figure the
            # feed and the report already publish is untouched by this failing.
            print(f"[job {self.job_id}] could not write the step ledger to "
                  f"{self.ledger_path}: {type(exc).__name__}: {exc}")

    def run(self, name: str, cmd: list[str]) -> None:
        self.no += 1
        self.prog.start_stage(self.no, name)
        print(f"[job {self.job_id}] stage {self.no}/{self.prog.n_stages}: {name}")
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            assert proc.stdout is not None
            for line in proc.stdout:
                print(f"    {line.rstrip()}")
                self.tail.append(line.rstrip())
                del self.tail[:-30]
                if line.strip():
                    self.prog.line(line)
            rc = proc.wait()
        finally:
            # In a finally, so a stage killed by a deploy or one that exits
            # nonzero still leaves what it had spent on disk. The database record
            # is unaffected either way: the step that writes it runs near the end
            # of a build that got that far.
            self._remember(name, started)
        # The one place the two kinds of ending are told apart. Read
        # classify_stage_exit before changing either arm.
        outcome = classify_stage_exit(rc, _shutting_down)
        if outcome == "interrupted":
            raise Shutdown(f"stopped during stage '{name}'")
        if outcome == "failed":
            raise StageFailed(f"stage '{name}' exited with code {rc}", self.tail)

    def run_all(self, stages: list[tuple[str, list[str]]]) -> None:
        for name, cmd in stages:
            self.run(name, cmd)


def map_summary(conn: psycopg.Connection, concept: str, pv: str) -> tuple | None:
    """(genealogy_id, papers, meanings, relationships) for the map being built.

    Read from the database rather than scraped off Stage E's summary line,
    because the feed's pass-one sentence is the requester's only view of a map
    nobody may look at yet, and a count taken from prose is a count that moves
    when the prose does (#85 is the standing example).
    """
    row = conn.execute(
        """SELECT g.id,
                  (SELECT count(*) FROM definitions d
                    WHERE d.concept = g.concept AND d.prompt_version = g.prompt_version),
                  CASE WHEN jsonb_typeof(g.nodes) = 'array'
                       THEN jsonb_array_length(g.nodes) ELSE 0 END,
                  (SELECT count(*) FROM edges e WHERE e.genealogy_id = g.id)
             FROM genealogies g
            WHERE g.concept = %s AND g.prompt_version = %s
            ORDER BY g.id DESC LIMIT 1""", (concept, pv)).fetchone()
    return row


def run_pass_two(conn: psycopg.Connection, job_id: int, runner: "StageRunner",
                 plan: dict, concept: str) -> tuple[int, str, dict]:
    """The second pass, and every way it can decline to happen.

    Returns `(passes, outcome, counts)`: how many passes actually read papers,
    the sentence a reader meets under "why the second pass ended", and the three
    citation-graph counts the record keeps beside it. It raises nothing a caller
    has to handle except `Shutdown`, which must always travel: a deploy's SIGTERM
    during pass two is an interruption to be requeued (#178) and never an outcome
    to record on a map.

    **Every exit from here is narrated and recorded.** The design's own risk list
    has "the pre-flight gate is wrong and pass two is abandoned when it would have
    fitted", and its control is that the estimate and the remaining cap are
    printed on every abandonment, so the decision is auditable rather than a
    silent branch.
    """
    prog, paths, seats = runner.prog, plan["paths"], plan["seats"]
    cap = float(env("TRACE_SPEND_CAP_USD", "10"))

    # The three counts the record keeps beside the sentence, and NULL until a run
    # has actually taken them: `020` prints a NULL as "not recorded" rather than
    # as a zero, which would claim the citation graph was asked and said nothing.
    counts: dict = {"seats": seats, "candidates": None, "cleared": None}

    # ── does the map nominate anybody? ──────────────────────────────────────
    runner.run_all(plan["pass_two_select"])
    stats = read_json_file(paths["pass_two_stats"], "pass-two funnel counts")
    if stats is None:
        prog.note("pass two: the selection wrote no counts this build could read; "
                  "publishing pass one")
        return 1, pass_two_outcome_sentence("abandoned_no_estimate"), counts
    state = str(stats.get("state") or "unknown")
    selected = int(stats.get("selected") or 0)
    counts["candidates"] = stats.get("fetched")
    counts["cleared"] = stats.get("cleared")
    if not selected:
        # Not a failure and never reported as one. For a mature term "nobody
        # recent cites two of this map's papers" is worth knowing; for a young one
        # it is expected. The sentence names the citation graph and stops.
        prog.note(f"pass two nominated nobody to read: {stats.get('fetched') or 0} recent "
                  f"paper(s) cite this map, {stats.get('cite_min_seeds') or 0} cite two or "
                  f"more. Publishing pass one.")
        return 1, pass_two_outcome_sentence(
            state, seats=seats, selected=selected, since=stats.get("since"),
            cleared=stats.get("cleared")), counts
    prog.note(f"pass two: {stats.get('fetched') or 0} recent paper(s) cite this map, "
              f"{stats.get('cite_min_seeds') or 0} cite two or more of it, "
              f"{stats.get('cleared') or 0} cleared both signals. Reading the top "
              f"{selected}.")

    # ── the pre-flight spend gate ───────────────────────────────────────────
    runner.run_all(plan["pass_two_fetch"])
    est = read_json_file(paths["pass_two_estimate"], "pass-two cost estimate")
    if est is None or not isinstance(est.get("estimate_usd"), (int, float)):
        prog.note("pass two: the estimate of what it would cost could not be read, so "
                  "nothing was bought. Publishing pass one.")
        return 1, pass_two_outcome_sentence("abandoned_no_estimate"), counts
    estimate = float(est["estimate_usd"])
    spent = prog.spent()
    remaining = cap - spent
    basis = ("nothing measurable has been spent yet: no stage has printed a spend line"
             if prog.state.get("spend_usd") is None else f"US${spent:.2f} spent so far")
    print(f"[job {job_id}] pass-two spend gate: estimate US${estimate:.2f} for "
          f"{est.get('papers')} paper(s) on {est.get('model')}; {basis}; "
          f"US${remaining:.2f} of the US${cap:.2f} cap remains.")
    if estimate > remaining:
        prog.note(f"pass two skipped: reading its {selected} paper(s) was estimated at "
                  f"US${estimate:.2f} and US${remaining:.2f} of the US${cap:.2f} cap is "
                  f"left. Publishing pass one.")
        return 1, pass_two_outcome_sentence(
            "abandoned_spend_cap", seats=seats, selected=selected, estimate=estimate,
            remaining=remaining, cap=cap), counts

    # ── read them, re-cluster over both passes, re-assemble ─────────────────
    try:
        runner.run_all(plan["pass_two_read"])
    except StageFailed as exc:
        # Pass one is a complete, publishable map and this is the whole value of
        # the staging: a second pass that broke costs the build its second pass
        # and not its map. It is never silent — the sentence names the stage, and
        # it lands on the report, in this log and in the requester's feed.
        stage = str(exc).split("'")[1] if "'" in str(exc) else "an unnamed stage"
        print(f"[job {job_id}] pass two FAILED ({exc}); falling back to pass one's "
              f"corpus and publishing that map.")
        prog.note(f"pass two failed at '{stage}'; re-clustering over pass one alone and "
                  f"publishing that map.")
        runner.run_all(plan["pass_two_fallback"])
        # Two passes RAN, and the record says so; what the map holds is pass one's
        # papers, and the outcome sentence is what says that. `passes` counts the
        # passes the build ran rather than the passes that survived, because the
        # figures beside it are counts of what was read.
        return 2, pass_two_outcome_sentence("failed", stage=stage), counts

    return 2, pass_two_outcome_sentence(state, seats=seats, selected=selected,
                                        since=stats.get("since"),
                                        cleared=stats.get("cleared")), counts


def run_snapshot(runner: "StageRunner", plan: dict, concept: str) -> None:
    """Save whatever map this concept already has, before the build replaces it.

    Decision 12 refuses a second map for a concept, so a trace against a term that
    already has one is a rebuild: Stage C writes over `nodes`, sets the status back
    to `running` and clears the relationships whose meaning moved. Until #173 the
    only thing standing behind that was Stage E's export, which holds `nodes` and
    `edges` and does not hold the threads, the curatorial audit trail, or the
    definitions the quotes come from. Incident 4 was recovered from it with the
    audit trail lost. `snapshot_map.py` holds all of it and existed for this.

    **A failure here fails the build, and the build has destroyed nothing yet.**
    That is the reason this runs first rather than beside Stage C. There are two
    ways to fail and both refuse: the stage exits non-zero (StageRunner raises), or
    it exits zero having written no record this worker can read, which is the same
    situation as far as anyone asking "is the old map saved" is concerned. Neither
    is a place to carry on and hope.
    """
    runner.run_all(plan["snapshot"])
    result = read_json_file(plan["paths"]["snapshot_result"], "record of the saved map")
    if result is None:
        raise StageFailed(
            "the step that saves the existing map exited cleanly but left no record "
            "of what it saved, so nothing here can say whether there is a copy to go "
            "back to. Stopping before the build overwrites anything; the map is "
            "exactly as it was.", runner.tail)
    if not result.get("existed"):
        # A first build of a term. Said out loud rather than passed over, because
        # "no snapshot was taken" has two causes and only one of them is fine.
        runner.prog.note("no existing map for this term to save: this is its first build.")
        return
    runner.prog.note(
        f"saved the current map before rebuilding it: {result.get('nodes')} meaning(s), "
        f"{result.get('edges')} relationship(s), {result.get('user_edits')} curatorial "
        f"edit(s) -> {result.get('path')}")


def run_job(conn: psycopg.Connection, job_id: int, concept: str, corpus_limit: int,
            field: str, gloss: str | None, anchors: list[str] | None = None,
            named_by: str | None = None) -> None:
    plan = plan_for(concept, corpus_limit, field, gloss, anchors, named_by)
    seats = plan["seats"]
    nominal = (plan["snapshot"] + plan["pass_one"] + plan["pass_two_select"]
               + plan["pass_two_fetch"] + plan["pass_two_read"] + plan["finish"])
    one_pass_only = seats <= 0
    # Initialised from the plan that is expected to run, and corrected the moment
    # a phase is skipped (Progress.set_total says why).
    prog = Progress(conn, job_id,
                    (len(plan["snapshot"]) + len(plan["pass_one"]) + len(plan["finish"]))
                    if one_pass_only else len(nominal))
    # `job_id` is both the log's name for this build and the request row the step
    # record is stamped with (#47), so an Operator can tell whether the recorded
    # steps and the report's own cost figure describe the same run.
    runner = StageRunner(prog, job_id, plan["paths"]["stage_ledger"], job_id)
    pv = prompt_version()

    with Heartbeat(job_id):
        # The snapshot belongs to neither pass and the runner starts there, so
        # nothing is asserted here; pass one is marked, and everything after the
        # two passes goes back to neither.
        run_snapshot(runner, plan, concept)
        with runner.in_pass(1):
            runner.run_all(plan["pass_one"])

        summary = map_summary(conn, concept, pv)
        if summary:
            _gid, papers, meanings, rels = summary
            prog.note(f"pass one complete: {papers} paper(s) read, {meanings} meaning(s), "
                      f"{rels} relationship(s). Not yet published.")

        if one_pass_only:
            # A build asked for one pass writes NO build record, so its report
            # reads "this map was built in one pass" and draws no pass figures.
            # A row saying `passes = 1` would draw five rows of zeroes about a
            # pass that was never attempted (#193, and #30's defect before it).
            print(f"[job {job_id}] pass two is disabled (PASS_TWO_SEATS=0): one pass, "
                  f"and no build record will be written.")
            passes, outcome, counts = 1, None, {}
        else:
            # Marked here rather than inside `run_pass_two`, which returns from
            # seven places: a restore written after any one of them would leave
            # the finishing stages recorded as second-pass work on every build
            # that skipped or abandoned its second pass. Everything the call runs
            # is pass-two work, the fallback included — those steps ran because
            # pass two ran, and their names say what they did.
            with runner.in_pass(2):
                passes, outcome, counts = run_pass_two(conn, job_id, runner, plan,
                                                       concept)

        if outcome is not None:
            record_cmd = [sys.executable, "-u", "pipeline/record_pass.py", concept,
                          "--build", "--passes", str(passes), "--outcome", outcome]
            # Only counts a run actually took are passed. An absent flag leaves the
            # column NULL, which `020` prints as "not recorded"; passing 0 would
            # say the citation graph was asked and answered nothing.
            for flag, value in (("--seats", counts.get("seats")),
                                ("--candidates", counts.get("candidates")),
                                ("--cleared", counts.get("cleared"))):
                if isinstance(value, int):
                    record_cmd += [flag, str(value)]
            runner.run("record how this build's second pass ended", record_cmd)

        # Now that every phase that was going to run has, the total is knowable.
        prog.set_total(runner.no + len(plan["finish"]))
        runner.run_all(plan["finish"])

    # Stage E created/updated the genealogy row for (concept, prompt_version).
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
    #
    # `requeues` is deliberately NOT incremented here (#178). This path runs only
    # when something deliberate stopped the worker — a deploy, an operator's
    # Ctrl-C — which always leaves a log line on both sides and cannot repeat
    # without a person acting again. The counter exists to bound the unattended
    # loop, where the process dies with nothing to say and the platform restarts
    # it; spending its budget on deploys would mean four pushes during one long
    # build permanently failing a job that nothing is wrong with, which is the
    # complaint this ticket exists to answer rather than a defence against it.
    conn.execute(
        """UPDATE trace_requests
           SET status = 'approved', started_at = NULL, updated_at = now(),
               progress = progress || '{"message": "run interrupted by a restart; back in the queue"}'
           WHERE id = %s""", (job_id,))
    conn.commit()


def sweep_stale(conn: psycopg.Connection) -> None:
    """A 'running' row with a cold heartbeat means a worker died mid-job.

    It used to mean the job was marked failed and left there, and a failed row
    has no way back: the app promotes a request into the queue only from
    'requested', so the requester's only recovery was submitting the concept
    again by hand. The owner's instruction on #178, after a deploy killed two
    builds in six minutes: "can you fix it so if they fail they automatically
    requeue. It not reasonable to expect someone to observe and retry upon
    failure."

    So a job that died without saying anything goes back on the queue, up to
    MAX_AUTO_REQUEUES times, and only then fails. **This is not the same as a
    stage failing.** A stage that exits nonzero has written diagnostics and will
    write them again; that path still fails on the first try and is decided in
    classify_stage_exit. What lands here is silence — a process that stopped
    heartbeating — which carries no diagnosis and is nearly always the platform's
    doing rather than the pipeline's.
    """
    rows = conn.execute(
        # Every branch keys off `requeues`, which in an UPDATE reads the row's
        # value from BEFORE this statement — so `requeues + 1` in the message is
        # the attempt number this restart is, and the cap compares the count of
        # restarts already spent.
        """UPDATE trace_requests
           SET status      = CASE WHEN requeues < %(cap)s THEN 'approved' ELSE 'failed' END,
               requeues    = CASE WHEN requeues < %(cap)s THEN requeues + 1 ELSE requeues END,
               started_at  = CASE WHEN requeues < %(cap)s THEN NULL ELSE started_at END,
               finished_at = CASE WHEN requeues < %(cap)s THEN finished_at ELSE now() END,
               error       = CASE WHEN requeues < %(cap)s THEN NULL ELSE
                   format('This run was restarted automatically %%s times and the worker '
                          'died mid-run every time, always without printing an error: the '
                          'heartbeat simply went cold. Stopping rather than restarting it '
                          'again, because a run that never survives costs money without '
                          'finishing. Nothing here says the pipeline is broken. Check the '
                          'worker''s deploy and restart history first.', requeues) END,
               progress    = CASE WHEN requeues < %(cap)s THEN
                   progress || jsonb_build_object('message',
                       format('run interrupted; restarting automatically (attempt %%s of %%s)',
                              requeues + 1, %(cap)s::int))
                   ELSE progress END,
               updated_at  = now()
           WHERE status = 'running'
             AND updated_at < now() - make_interval(mins => %(mins)s)
           RETURNING id, status, requeues""",
        {"cap": MAX_AUTO_REQUEUES, "mins": STALE_RUNNING_MINUTES}).fetchall()
    conn.commit()
    for jid, status, n in rows:
        if status == "approved":
            print(f"[sweep] job {jid}: heartbeat went stale; requeued automatically "
                  f"(attempt {n} of {MAX_AUTO_REQUEUES})")
        else:
            print(f"[sweep] job {jid}: died mid-run {n} times without an error; "
                  f"marked failed rather than restarted again")


def claim(conn: psycopg.Connection) -> tuple | None:
    """Take the oldest approved request, or None.

    `anchors` (migration 023, #198) is selected here rather than looked up later
    so the whole job description arrives in one statement, and `requested_by`
    comes with it: the login is what `record_anchors.py` writes as the
    authenticated actor, and this worker only relays what the app obtained from a
    session.

    **Selected through a fallback, because the worker can be one migration
    behind.** A push deploys the app and the worker at once and Render's
    pre-deploy is what applies migrations, so between a rollback and a redeploy
    this process can meet a `trace_requests` with no such column. Naming it
    unconditionally would leave every queued build unclaimable with an
    `UndefinedColumn` on the poll, which is a worse failure than a build that
    reads no names; `to_jsonb(t)` costs one row's serialisation and asks the
    question the row itself can answer.
    """
    row = conn.execute(
        """UPDATE trace_requests t
           SET status = 'running', started_at = now(), updated_at = now()
           WHERE id = (SELECT id FROM trace_requests WHERE status = 'approved'
                       ORDER BY decided_at NULLS FIRST, created_at
                       LIMIT 1 FOR UPDATE SKIP LOCKED)
           RETURNING id, concept, corpus_limit, field_id, gloss, requested_by,
                     to_jsonb(t) -> 'anchors'""").fetchone()
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

    # Before anything that can be interrupted, including the startup migration.
    install_shutdown_handler()

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
    # The outer arm is for a signal that arrives with no job in hand — while
    # polling, while claiming, or during the startup tasks above. There is
    # nothing to requeue then, and the point of catching it is that the log says
    # the worker was stopped rather than showing a traceback that reads like a
    # crash. A signal arriving mid-job is caught by the inner arm, which has the
    # job id.
    try:
        while True:
            sweep_stale(conn)
            job = claim(conn)
            if job is None:
                if args.once:
                    print("No approved jobs. Exiting (--once).")
                    return
                time.sleep(args.poll)
                continue

            job_id, concept, corpus_limit, field, gloss, requested_by, anchors = job
            # A row from before migration 023, or one whose requester named
            # nobody, both arrive as an empty list here; only the corpus file
            # written by the build can tell those apart, and only the report
            # needs to.
            anchors = [a for a in (anchors or []) if isinstance(a, str) and a.strip()]
            print(f'[job {job_id}] claimed: "{concept}" (field {field}, corpus limit {corpus_limit}'
                  f'{", glossed" if gloss else ""}'
                  f'{f", {len(anchors)} paper(s) named" if anchors else ""})')
            try:
                run_job(conn, job_id, concept, corpus_limit, field, gloss,
                        anchors, requested_by)
            except StageFailed as e:
                print(f"[job {job_id}] FAILED: {e}")
                fail_job(conn, job_id, str(e), e.tail)
            # Shutdown is SIGTERM (a deploy) and KeyboardInterrupt is SIGINT
            # (Ctrl-C); both mean the same thing to the job, and both must be
            # caught above the generic Exception arm below, which would
            # otherwise mark a deploy's victim failed. This arm is the whole
            # deploy path: it has a grace window measured in tens of seconds and
            # spends it on one UPDATE.
            except (Shutdown, KeyboardInterrupt) as e:
                # str(e), not e: an exception object is always truthy, so
                # `e or 'Ctrl-C'` prints an empty pair of brackets for a bare
                # KeyboardInterrupt, which carries no message.
                print(f"\n[job {job_id}] interrupted ({str(e) or 'Ctrl-C'}) — "
                      f"requeueing as 'approved'")
                requeue_job(conn, job_id)
                return
            except Exception as e:  # worker bug or DB hiccup: fail loud, keep living
                print(f"[job {job_id}] ERROR: {type(e).__name__}: {e}")
                fail_job(conn, job_id, f"{type(e).__name__}: {e}", [])

            if args.once:
                return
    except (Shutdown, KeyboardInterrupt) as e:
        print(f"\n[worker] stopping ({str(e) or 'Ctrl-C'}). No job in hand to requeue.")


if __name__ == "__main__":
    main()

"""Record what each step of a build spent, from what the run's own steps printed.

Ticket #47 ([B29]). Until now a build's cost existed as exactly one number: the
worker scrapes the stages' spend lines into `trace_requests.progress.spend_usd`
for the progress feed, and `map_report.run_cost_usd` publishes that total. Which
step spent it was never a stored fact, so "extraction costs four times as much on
one corpus as on another" could be observed and not located, and the fraction of a
map's cost that the shared extraction cache avoids was unknowable (decision 27,
ROADMAP open question 6). This command is the instrument, and it lands before the
cost-reduction work whose before-and-after claims need it.

**It records, it does not measure.** Every figure comes from the worker's ledger
file, which holds what `Progress` already parsed out of each stage's own stdout
while the feed was being written. No stage was taught to account for itself and
no arithmetic was added anywhere: the per-step figures sum to the same scrape the
report already publishes. That is deliberate — a second, independent accounting
would be a second number to keep in agreement with the first (#190's lesson), and
the one we have is the one the requester watched.

**A step that printed no cost line is recorded with no cost, never with zero.**
Most steps of a build spend nothing at all — fetching, extraction, the audit,
grounding, the recorders — and a step that stopped printing its spend looks
exactly the same from here. Neither may be published as US$0.00 (#85, #87). What
this record adds is that such a step is now a named row with no figure rather
than a silent absence inside a total. A stage that DID print `$0.0000` is a real
zero and is stored as one; migration `024`'s CHECK is what keeps the two apart.

**It clears the map's whole step record before writing**, for the reason
`record_pass.py --pass 1` does: a requeued or re-run build is re-stating what it
spent, not adding to it, so a re-run converges on the record a first run would
have written. The clear and the insert are one transaction, so a map is never
left holding half a build.

**What is NOT in the record, on every build, by construction**: this step itself
and everything after it. The worker writes the ledger before launching this
command, so the last thing in it is the step before this one. The steps that
follow are the final grounding and publish, which print no cost line, so the
recorded total still matches the run's — but `stage_wall_clock` is short by them
and both surfaces call it the time in the recorded steps rather than the run's.

Usage:
  python pipeline/record_spend.py "attention" --stages data/stages_attention.json
  python pipeline/record_spend.py "attention" --show
"""

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import build_row, current_row, env, version_note  # noqa: E402

INSERT_STAGE = """
INSERT INTO map_build_stages (genealogy_id, stage_no, stage, build_pass,
                              spend_usd, spend_lines, seconds, run_id)
VALUES (%(gid)s, %(stage_no)s, %(stage)s, %(build_pass)s,
        %(spend_usd)s, %(spend_lines)s, %(seconds)s, %(run_id)s)
"""

# Read back through the view the report reads, not the table, so an Operator
# checking a build by hand and the report page cannot disagree — the same
# reasoning `record_pass.py --show` and `check_map.py` follow.
SHOW_MAP = """
SELECT stages_recorded, stages_with_a_cost, stages_with_no_cost_line,
       stage_spend_usd, stage_wall_clock, stages_pass_one, stages_pass_two,
       stages_outside_passes, pass_one_spend_usd, pass_two_spend_usd,
       spend_outside_passes, costliest_stage, costliest_stage_usd,
       stage_record_basis, stage_record_run_id, stages
FROM map_report_stages WHERE genealogy_id = %s
"""


def map_id(conn, concept: str, prompt_version: str,
           genealogy_id: int | None = None, *, live: bool = False) -> int:
    """The version this record attaches to.

    Two questions, not one (#207b). A record WRITE belongs to the build in
    flight, which owns the newest unpublished version — recording onto the live
    map would attach this build's figures to the map a reader is looking at,
    which is the previous version. `--show` is a reader and asks the other
    question: the live map, the one whose record the operator means when they
    name a concept. `--genealogy-id` answers both by naming a row.
    """
    resolve = current_row if live else build_row
    row = resolve(conn, concept, prompt_version, "id", genealogy_id=genealogy_id)
    if not row:
        if live:
            sys.exit(f'No live map for "{concept}" at prompt {prompt_version}.\n'
                     f"  {version_note(conn, concept, prompt_version)}")
        # Stage C creates the genealogy row, so this means the build has not
        # clustered yet: recording a build's steps before there is a map to
        # attach them to is a caller ordering error, not a missing map.
        sys.exit(f'No unpublished version of "{concept}" at prompt {prompt_version}. '
                 f"The step record attaches to a genealogy row, which Stage C creates; "
                 f"record a build's steps after the clustering they fed, not before it.\n"
                 f"  {version_note(conn, concept, prompt_version)}")
    return row[0]


def money(v) -> str:
    """The four decimals the worker keeps, or the words for a step that printed
    nothing. Never `US$0.00` for an absence (#87)."""
    return "no cost line" if v is None else f"US${Decimal(v):.4f}"


def read_ledger(path: str) -> dict:
    """The worker's ledger, or a refusal naming what is wrong with it.

    Strict, unlike `worker.read_json_file`, and for the opposite reason: the
    worker has a defined answer for "the file is not readable" and it is to
    publish pass one anyway, whereas there is no useful thing this command can do
    with a ledger it cannot parse. A build that silently recorded nothing about
    its own spend is the state this ticket exists to end.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.exit(f"Could not read the step ledger at {path}: "
                 f"{type(exc).__name__}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("stages"), list):
        sys.exit(f"The step ledger at {path} is not an object carrying a 'stages' "
                 f"list. The worker writes it; nothing else does.")
    return data


def clean_stage(entry, i: int) -> dict:
    """One ledger entry, checked into the shape the table accepts.

    Every refusal names the entry and what was wrong with it. The alternative is
    letting migration `024`'s CHECK speak, and a constraint's message is about the
    constraint: this one is about the build.
    """
    where = f"step {i} of the ledger"
    if not isinstance(entry, dict):
        sys.exit(f"{where} is a {type(entry).__name__}, not an object.")
    try:
        stage_no = int(entry["stage_no"])
    except (KeyError, TypeError, ValueError):
        sys.exit(f"{where} has no readable 'stage_no'; it is the step's position in "
                 f"the build and it is what the record is keyed on.")
    stage = str(entry.get("stage") or "").strip()
    if not stage:
        sys.exit(f"{where} has no name. The name is the worker's own feed name for "
                 f"the step, so the breakdown and the progress a requester watched "
                 f"use one vocabulary.")
    build_pass = entry.get("build_pass")
    if build_pass is not None:
        try:
            build_pass = int(build_pass)
        except (TypeError, ValueError):
            sys.exit(f"{where} ({stage}) has a 'build_pass' that is not a whole "
                     f"number: {entry.get('build_pass')!r}.")
    spend_lines = int(entry.get("spend_lines") or 0)
    spend = entry.get("spend_usd")
    if spend is not None:
        try:
            spend = Decimal(str(spend))
        except (InvalidOperation, TypeError, ValueError):
            sys.exit(f"{where} ({stage}) has a 'spend_usd' that is not a number: "
                     f"{entry.get('spend_usd')!r}.")
    # The zero-versus-absence rule, refused here in the build's words before the
    # CHECK refuses it in the constraint's. A cost with no line behind it would be
    # a figure nothing printed; a line with no cost would be a measurement thrown
    # away between the parse and the write.
    if (spend is None) != (spend_lines == 0):
        sys.exit(f"{where} ({stage}) says spend {spend!r} with {spend_lines} cost "
                 f"line(s). A step either printed a cost line and has a figure, or "
                 f"printed none and has no figure; nothing in between is a thing "
                 f"this record can mean.")
    seconds = entry.get("seconds")
    if seconds is not None:
        try:
            seconds = Decimal(str(seconds))
        except (InvalidOperation, TypeError, ValueError):
            sys.exit(f"{where} ({stage}) has a 'seconds' that is not a number: "
                     f"{entry.get('seconds')!r}.")
    return {"stage_no": stage_no, "stage": stage, "build_pass": build_pass,
            "spend_usd": spend, "spend_lines": spend_lines, "seconds": seconds}


def record(conn, gid: int, ledger: dict) -> None:
    stages = [clean_stage(e, i) for i, e in enumerate(ledger["stages"], start=1)]
    seen = {s["stage_no"] for s in stages}
    if len(seen) != len(stages):
        sys.exit(f"The ledger names {len(stages)} steps under {len(seen)} distinct "
                 f"positions. The position is the key, so two steps sharing one "
                 f"would overwrite each other and the breakdown would be short.")
    run_id = ledger.get("run_id")
    run_id = int(run_id) if isinstance(run_id, int) else None

    # One transaction: the clear and the write are the same act, and a map holding
    # half of one build's steps and half of another's is worse than a map holding
    # the previous build's whole record.
    gone = conn.execute(
        "DELETE FROM map_build_stages WHERE genealogy_id = %s", (gid,)).rowcount
    for s in stages:
        conn.execute(INSERT_STAGE, {"gid": gid, "run_id": run_id, **s})
    conn.commit()

    if gone:
        print(f"  cleared {gone} step(s) from this map's previous build record — "
              f"this build is re-stating what it spent, not adding to it")
    if not stages:
        # A finding rather than an error: it is what a build whose ledger was
        # never written looks like, and it must not read as a build that spent
        # nothing.
        print("The ledger names no steps, so this map's record says nothing about "
              "what its build spent. That is an absence and not a cost of zero.")
        return

    priced = [s for s in stages if s["spend_usd"] is not None]
    total = sum((s["spend_usd"] for s in priced), Decimal(0)) if priced else None
    print(f"Recorded {len(stages)} step(s) of this build"
          f"{f' from request {run_id}' if run_id is not None else ''}.")
    print(f"  {len(priced)} printed a cost line, {len(stages) - len(priced)} printed "
          f"none; what the priced steps spent: {money(total)}")
    for label, pass_no in (("first pass", 1), ("second pass", 2), ("neither pass", None)):
        mine = [s for s in stages
                if (s["build_pass"] == pass_no if pass_no is not None
                    else s["build_pass"] not in (1, 2))]
        if not mine:
            continue
        sub = [s["spend_usd"] for s in mine if s["spend_usd"] is not None]
        print(f"  {label}: {len(mine)} step(s), "
              f"{money(sum(sub, Decimal(0)) if sub else None)}")


def show(conn, gid: int) -> None:
    row = conn.execute(SHOW_MAP, (gid,)).fetchone()
    if row is None:
        # The view LEFT JOINs from `genealogies`, so this is a map that does not
        # exist rather than one with no record — worth saying differently.
        print(f"Map {gid} is not on map_report_stages at all, which means no such map.")
        return
    (recorded, priced, unpriced, total, wall, n1, n2, n0, s1, s2, s0,
     costliest, costliest_usd, basis, run_id, stages) = row
    if recorded is None:
        print(f"Map {gid}: {basis}. Nothing here is a cost of zero; nothing recorded "
              f"what this build's steps spent.")
        return
    print(f"Map {gid}: {recorded} step(s) recorded, {basis}"
          f"{f' (request {run_id})' if run_id is not None else ''}")
    print(f"  {priced} printed a cost line, {unpriced} printed none")
    print(f"  what the recorded steps spent: {money(total)}")
    print(f"  time in the recorded steps: "
          f"{'not recorded' if wall is None else f'{float(wall):.1f} s'}")
    print(f"  first pass: {n1} step(s), {money(s1)}")
    print(f"  second pass: {n2} step(s), {money(s2)}")
    print(f"  neither pass: {n0} step(s), {money(s0)}")
    print(f"  most expensive step: "
          f"{'no step printed a cost line' if costliest is None else costliest}"
          f"{'' if costliest is None else f'  {money(costliest_usd)}'}")
    print(f"  {'step':<44}{'pass':>5}{'cost':>16}{'seconds':>10}")
    for s in stages or []:
        spend = s.get("spend_usd")
        secs = s.get("seconds")
        # Built outside the f-string: the absent forms are prose and the present
        # forms are numbers, and a nested format spec inside a nested quote is how
        # this line was wrong the first time.
        name = str(s.get("stage") or "?")[:43]
        pass_no = s.get("build_pass")
        pass_cell = "-" if pass_no is None else str(pass_no)
        cost_cell = money(None if spend is None else Decimal(str(spend)))
        secs_cell = "-" if secs is None else f"{float(secs):.1f}"
        print(f"  {name:<44}{pass_cell:>5}{cost_cell:>16}{secs_cell:>10}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Record what each step of a build spent (issue #47).")
    ap.add_argument("concept")
    ap.add_argument("--prompt-version", default=None,
                    help="default: PROMPT_VERSION from the environment, or v1")
    ap.add_argument("--stages", metavar="JSON",
                    help="the ledger the worker wrote while it ran the build")
    ap.add_argument("--genealogy-id", type=int, metavar="ID",
                    help="the exact version to record onto (or, with --show, to read\n"
                         "back) instead of the one the build in flight owns")
    ap.add_argument("--show", action="store_true",
                    help="print what is recorded for this map and write nothing")
    args = ap.parse_args()

    if not (args.stages or args.show):
        sys.exit("Nothing to do: pass --stages PATH to record a build, or --show.")

    prompt_version = args.prompt_version or env("PROMPT_VERSION", "v1")
    # Not autocommit: the clear and the write below are one act.
    conn = psycopg.connect(env("DATABASE_URL"))
    try:
        gid = map_id(conn, args.concept, prompt_version, args.genealogy_id,
                     live=args.show)
        if args.show:
            show(conn, gid)
            return
        record(conn, gid, read_ledger(args.stages))
    finally:
        conn.close()


if __name__ == "__main__":
    main()

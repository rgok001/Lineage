"""Ask a map whether it still satisfies the rules of the stages that built it.

Ticket #168, which is the missing piece named in #149 and the publish half of
#2. The six clauses are migration `021_map_invariant.sql`; this command computes
nothing of its own, so it and Stage E's publish gate (#171) read one expression
and cannot hold a different opinion about the same map.

**It reads LINEAGE_READ_URL and never DATABASE_URL, and it issues no statement
but SELECT**, modelled on `map_report.py` and `recheck_stamp.py` for the same
reason: it is a tool whose whole value is that an Operator can point it at
production, and that is only safe if it structurally cannot write. It repairs
nothing. Like those two it does COMMIT on the way out of the `with` block --
psycopg's connection context manager does that and nothing here suppresses it --
and the transaction contains two SELECTs, so the commit carries no change. What
makes this safe to point at production is the read-only role and the statements
it issues, not the shape of the transaction.

**A violation is not a score.** Each clause is an existence test or an equality
and every finding names the concept-state, the relationship or the thread it is
about, because the reader of this command is whoever has to repair it. There is
no threshold, no grade and no percentage here, and there must never be one.

**The exit status is the verdict**: 0 when every map asked about satisfies the
invariant, 1 when any of them does not. That makes it usable as a gate in a
procedure; the gate that matters is inside Stage E, where it can roll a publish
back, and this is the same question asked from outside.

`--all --json` is **always** a JSON array -- of one element against a database
holding one map, and empty against a database holding none (issue #93, and the
degenerate case that lesson names). A named concept is always a JSON object.

Usage:
  python pipeline/check_map.py "attention"
  python pipeline/check_map.py "attention" --prompt-version v2
  python pipeline/check_map.py --all
  python pipeline/check_map.py --all --json
"""

import argparse
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env  # noqa: E402

# Only the read-only role. Named deliberately unlike DATABASE_URL so that no
# existing code path can route through it by accident (CLAUDE.md), and read here
# rather than through any helper that knows the writable one.
READ_URL = "LINEAGE_READ_URL"

# Every column named, never `SELECT *`. `CREATE OR REPLACE VIEW` cannot change a
# column's type, drop a column or reorder columns, so a later change to the
# invariant is a DROP and a CREATE; naming them means such a redefinition breaks
# this command loudly instead of silently changing a verdict. Its twin is
# `INVARIANT_COLUMNS` in pipeline/stage_e_ground.py.
CLAUSE_COLUMNS = [
    (1, "definitions_not_admissible"),
    (2, "nodes_whose_members_and_definitions_differ"),
    (3, "nodes_unreadable_or_duplicated"),
    (4, "relationships_with_a_bad_concept_state"),
    (5, "relationships_not_evidenced_by_their_nodes"),
    (6, "thread_papers_the_map_does_not_hold"),
]

MAPS = f"""
SELECT genealogy_id, concept, prompt_version, status,
       {', '.join(c for _n, c in CLAUSE_COLUMNS)},
       findings_total, satisfies_publish_invariant
FROM map_invariant
ORDER BY concept, prompt_version
"""

# The clause names come from the view, so the six sentences live in the
# migration and nowhere else. A map with no findings contributes no rows here,
# which is why the header below prints the counts from `map_invariant` and this
# only supplies the detail.
FINDINGS = """
SELECT genealogy_id, clause, clause_name, subject_kind, subject, detail
FROM map_invariant_findings
ORDER BY genealogy_id, clause, subject_kind, subject
"""


def render(row: dict, findings: list[dict]) -> list[str]:
    mine = [f for f in findings if f["genealogy_id"] == row["genealogy_id"]]
    out = [f'Does "{row["concept"]}" still satisfy the rules that built it?  '
           f'(prompt {row["prompt_version"]}, map {row["genealogy_id"]}, '
           f'{row["status"]})', ""]
    out.append("Six clauses, each an existence test or an equality, computed from this map's")
    out.append("own rows just now. Nothing is stored, so a change to the map changes this")
    out.append("answer immediately, and the honest answer to \"when was this last checked\"")
    out.append("is \"when you asked\". No figure here is a score and none has a threshold")
    out.append("behind it: a map either satisfies every clause or it names what it violates.")
    out.append("")

    # The clause name is taken from a finding when there is one and printed as
    # the column name when there is not, rather than being written down here: the
    # six sentences belong to the migration, and a copy in this file would be a
    # second home for them that ages the first time one is reworded.
    named = {f["clause"]: f["clause_name"] for f in mine}
    for number, column in CLAUSE_COLUMNS:
        count = int(row[column])
        title = named.get(number, column.replace("_", " "))
        out.append(f"  clause {number}  {count:>4}  {title}")
        for f in [f for f in mine if f["clause"] == number]:
            out.append(f"            {f['subject_kind']} {f['subject']}: {f['detail']}")

    out.append("")
    if row["satisfies_publish_invariant"]:
        out.append("Every clause holds. This map is publishable as far as these six questions")
        out.append("can say, which is not the same as the map being right: whether its account")
        out.append("of the term is correct needs the papers.")
    else:
        out.append(f"{int(row['findings_total'])} finding(s). Stage E refuses to publish this "
                   f"map while any clause fails")
        out.append("(issue #171). Each line above names what to repair.")
    return out


def as_json(row: dict, findings: list[dict]) -> dict:
    return {
        **row,
        "findings": [{k: v for k, v in f.items() if k != "genealogy_id"}
                     for f in findings if f["genealogy_id"] == row["genealogy_id"]],
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Whether a map still satisfies the six clauses of the publish "
                    "invariant (read-only; SELECT and nothing else, and it stores "
                    "nothing). Exits 1 if any map asked about violates a clause.")
    ap.add_argument("concept", nargs="?", help="the concept to check")
    ap.add_argument("--prompt-version", default=None,
                    help="defaults to PROMPT_VERSION from the environment")
    ap.add_argument("--all", action="store_true", help="check every map in the database")
    ap.add_argument("--json", action="store_true",
                    help="JSON on stdout and to no file: an object for a named "
                         "concept, an array for --all however many maps exist, "
                         "including none")
    args = ap.parse_args()
    if not args.concept and not args.all:
        ap.error("name a concept, or pass --all")

    with psycopg.connect(env(READ_URL)) as conn:
        cur = conn.execute(MAPS)
        names = [d.name for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
        cur = conn.execute(FINDINGS)
        fnames = [d.name for d in cur.description]
        findings = [dict(zip(fnames, r)) for r in cur.fetchall()]

    if args.all:
        chosen = rows
    else:
        pv = args.prompt_version or env("PROMPT_VERSION", "v1")
        chosen = [r for r in rows
                  if r["concept"] == args.concept and r["prompt_version"] == pv]
        if not chosen:
            have = ", ".join(f'{r["concept"]} ({r["prompt_version"]})' for r in rows) \
                   or "no maps at all"
            sys.exit(f'No map for "{args.concept}" at prompt {pv}. '
                     f"This database holds: {have}.")

    # **The flag decides the shape, never the row count** (issue #93). An empty
    # database prints `[]` here rather than a message, because the promise
    # "--all --json is always an array" is only as strong as its behaviour on the
    # empty input, and a caller parsing this output has not handled a sentence.
    if args.json:
        if args.all:
            print(json.dumps([as_json(r, findings) for r in chosen], indent=2, default=str))
        else:
            print(json.dumps(as_json(chosen[0], findings), indent=2, default=str))
    elif not chosen:
        print("No maps in this database, so there is nothing to check.")
    else:
        for i, row in enumerate(chosen):
            if i:
                print("\n" + "=" * 78)
            print("\n".join(render(row, findings)))

    # The verdict is the exit status, and it is a function of the view's own
    # boolean rather than of anything computed here: a checker whose answer comes
    # from a value it derived itself is a reporter wearing a checker's name.
    failed = [r for r in chosen if not r["satisfies_publish_invariant"]]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

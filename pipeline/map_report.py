"""Print what a map is made of, from the map's own rows, storing nothing.

Ticket #30 ([F2]); the design is docs/design/f2-map-report.md. The figures come
from migration 016's two views and are computed nowhere else, so this command and
`/g/<id>/report` read one expression and cannot disagree about the same map.

**It reads LINEAGE_READ_URL and never DATABASE_URL, and it issues no statement
but SELECT**, modelled on `recheck_stamp.py` for the same reason: it is a tool
whose whole value is that an Operator can run it against production and paste the
answer into a report, and that is only safe if it structurally cannot write. It
does not repair, it does not refresh anything, and there is nothing to refresh --
a view holds no data.

It does, however, COMMIT. `with psycopg.connect(...)` commits on the way out of
the block -- that is what psycopg's connection context manager does, and nothing
here suppresses it -- so a statement counter watching this command sees two
SELECTs and one commit, not two SELECTs and nothing (issue #93). The commit
carries no change, because the only statements in the transaction are those two
SELECTs, and it is left alone rather than turned into a rollback: what makes this
command safe to point at production is the read-only role and the statements it
issues, and rearranging the transaction to make a sentence true would be
decorating the guarantee rather than strengthening it. Inherited from
`recheck_stamp.py`, which does the same.

**--json writes to stdout and to no file.** A report written to disk is a stored
quality figure with a different spelling: it would survive the curatorial edit
that invalidates it, which is the one thing this ticket exists to prevent. If you
want it in a file, redirect it, and then it is your file and dated by your shell
rather than ours.

**--json's shape follows the flag and not the data**: `--all` is always a JSON
array, of one element if the database holds one map, and a named concept is
always a JSON object.

There is no threshold in this file and there must never be one. No cut-off, no
grade, no colour, no composite score, and no constant that decides how anything
prints. Beside each figure it prints the same figure for every other map, and the
sample size, which is the number of rows the view returned rather than a number
written in here.

Usage:
  python pipeline/map_report.py "attention"
  python pipeline/map_report.py "attention" --prompt-version v2
  python pipeline/map_report.py --all
  python pipeline/map_report.py "attention" --json      # one JSON object
  python pipeline/map_report.py --all --json            # a JSON array, always
"""

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env  # noqa: E402

# Only the read-only role. Named deliberately unlike DATABASE_URL so that no
# existing code path can route through it by accident (CLAUDE.md), and read here
# rather than through any helper that knows the writable one.
READ_URL = "LINEAGE_READ_URL"

# Every column named, never `SELECT *`. `CREATE OR REPLACE VIEW` cannot change a
# column's type, drop a column or reorder columns, so a later change to the report
# is a DROP and a CREATE; naming them means such a redefinition breaks this
# command loudly instead of silently changing what it prints. Its twin is
# `COLUMNS` in app/lib/report.ts and the two hold the same names.
COLUMNS = """genealogy_id, concept, prompt_version, status,
  papers_with_a_reading, papers_defining, papers_not_defining,
  definitions_verified, definitions_inferred, definitions_stale,
  edges_total, edges_verified, edges_inferred, edges_stale,
  definitions_verified_share, edges_verified_share,
  quote_slots, quote_slots_empty, distinct_quote_strings,
  distinct_papers_on_edges, most_repeated_quote_uses,
  nodes_total, nodes_unreadable, nodes_with_one_member,
  nodes_with_no_edge_to_another_node, nodes_with_one_member_share,
  largest_node_id, largest_node_members, largest_node_edges,
  largest_node_edges_share, node_pairs, node_pairs_disagreeing,
  edges_on_disagreeing_pairs, edges_on_disagreeing_pairs_share,
  edges_within_one_node,
  year_min, year_p25, year_median, year_p75, year_max, year_counts,
  papers_with_no_year,
  runs_recorded, run_cost_usd, run_cost_basis, run_wall_clock, requester_wait"""

REPORTS = f"SELECT {COLUMNS} FROM map_report ORDER BY concept, prompt_version"

BUCKETS = """
SELECT genealogy_id, unit, source, total, verified, inferred, stale
FROM map_report_by_source
ORDER BY genealogy_id, unit, source
"""


# ── how a figure prints ─────────────────────────────────────────────────────
#
# None is never printed as 0 and never as a blank. The two reasons a figure can
# be missing are different claims -- nothing recorded it, or the population is
# empty -- and each figure below carries the words for its own case.

def count(v) -> str | None:
    return None if v is None else f"{int(v):,}"


def share(v) -> str | None:
    return None if v is None else f"{float(v) * 100:.1f}%"


def money(v) -> str | None:
    """Money, under one rule: a cost that is not zero never renders as a zero one.

    Cents are the readable form and stay the default, but a cached re-trace can
    genuinely cost US$0.004 and `:.2f` printed that as "US$0.00" under what the
    run cost -- a figure that reads as free about a run that was not (issue
    #87). So: print cents; if cents would round a non-zero amount away to
    nothing, print four decimals, which is the precision the worker actually
    keeps; and if even that is all zeros, say so in words. A recorded zero is a
    real zero and keeps US$0.00.

    `money()` in app/app/g/[id]/report/page.tsx is these same branches in the
    same order and the two must stay identical: the page and this command
    publish one number, and a reader who saw both would have no way to tell
    which of them had been rounded.
    """
    if v is None:
        return None
    f = float(v)
    cents = _fixed(f, 2)
    if f == 0 or float(cents) != 0:
        return f"US${cents}"
    fine = _fixed(f, 4)
    return f"US${fine}" if float(fine) != 0 else "less than US$0.0001"


def _fixed(f: float, places: int) -> str:
    """`f` to `places` decimals, rounding a half away from zero.

    Not `f"{f:.2f}"`, which rounds a half to even: US$0.125 printed US$0.12 here
    and US$0.13 on the page, because JavaScript's `toFixed` rounds the half up.
    Found by running the two functions side by side over a sweep of values while
    fixing issue #87, not by reading them. One number published twice under two
    different roundings is the same two-surfaces-disagree defect as #79, in a
    place nobody would think to look.

    `Decimal(f)` is deliberately the exact double rather than `Decimal(str(f))`:
    the page is handed this same double by `Number()`, so quantizing the decimal
    literal instead would round 0.145 to 0.15 here and 0.14 there, which is this
    defect the other way round. Measured over 25 values including both traps;
    they now agree on all of them. Costs are never negative (the worker's spend
    regex has no sign), so the two roundings are untested below zero.
    """
    return str(Decimal(f).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def year(v) -> str | None:
    if v is None:
        return None
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:.1f}"


def duration(v) -> str | None:
    """The same words the page prints for the same number of seconds."""
    if v is None:
        return None
    s = round(float(v))
    if s < 60:
        return f"{s} s"
    m, rem = divmod(s, 60)
    return f"{m} min {rem} s" if rem else f"{m} min"


# The figures, under the page's labels, with the page's words for an absent
# value. `m30_cli.py` in the scratchpad compares this list with the labels in
# app/app/g/[id]/report/page.tsx, because agreement between the two surfaces is a
# claim and not a hope.
#
# **This command prints every figure; the page prints a reader's tier of them**
# (the UX review, #104 and #107 to #113). The page merged each count with its
# share onto one row, cut the figures that only the team reads, and re-ordered
# two sections; this list did not, because the Operator is this command's reader
# and the full account is the point of it. So the claim the comparison enforces
# is that the page's labels are a *subset* of this list, with identical wording
# wherever both surfaces print a figure. It is deliberately weaker than the
# equality it replaces: a figure dropped from this list is still a defect.
SECTIONS: list[tuple[str, list[tuple[str, str, object, str]]]] = [
    ("How much was read", [
        ("papers read", "papers_with_a_reading", count, "not recorded"),
        ("papers that define the term", "papers_defining", count, "not recorded"),
        ("papers that do not define the term", "papers_not_defining", count, "not recorded"),
    ]),
    ("Evidence", [
        ("definitions verified", "definitions_verified", count, "not recorded"),
        ("definitions verified, as a share", "definitions_verified_share", share,
         "no papers define the term"),
        ("definitions inferred", "definitions_inferred", count, "not recorded"),
        ("definitions not re-checked", "definitions_stale", count, "not recorded"),
        ("typed relationships", "edges_total", count, "not recorded"),
        ("relationships verified", "edges_verified", count, "not recorded"),
        ("relationships verified, as a share", "edges_verified_share", share,
         "no relationships"),
        ("relationships inferred", "edges_inferred", count, "not recorded"),
        ("relationships not re-checked", "edges_stale", count, "not recorded"),
    ]),
    ("The evidence behind the map", [
        ("quote slots", "quote_slots", count, "no relationships"),
        ("quote slots holding no text", "quote_slots_empty", count, "no relationships"),
        ("different quotes the map stands on", "distinct_quote_strings", count,
         "no quotes"),
        ("different papers on relationships", "distinct_papers_on_edges", count,
         "no relationships"),
        ("times the most reused quote appears", "most_repeated_quote_uses", count,
         "no quotes"),
    ]),
    ("Shape", [
        ("meanings", "nodes_total", count, "not recorded"),
        ("meanings that could not be read", "nodes_unreadable", count, "not recorded"),
        ("meanings holding one paper", "nodes_with_one_member", count, "not recorded"),
        ("meanings holding one paper, as a share", "nodes_with_one_member_share", share,
         "no meanings"),
        ("meanings with no link to another meaning", "nodes_with_no_edge_to_another_node",
         count, "not recorded"),
        ("largest meaning, papers in it", "largest_node_members", count, "no meanings"),
        ("relationships touching the largest meaning", "largest_node_edges", count,
         "not recorded"),
        ("relationships touching the largest meaning, as a share",
         "largest_node_edges_share", share, "no relationships"),
        ("pairs of meanings that are linked", "node_pairs", count, "not recorded"),
        ("pairs carrying more than one kind of link", "node_pairs_disagreeing", count,
         "not recorded"),
        # Renamed with the page (issue #134): the page merged this count, its
        # share and the pair count onto one row led by what it means, and a
        # label the page rewrites is rewritten here in the same words. "Pairs of
        # meanings that are linked" and "pairs carrying more than one kind of
        # link" are now command-only, like "quote slots" since #108.
        ("relationships between meanings linked in more than one way",
         "edges_on_disagreeing_pairs", count, "not recorded"),
        ("relationships between meanings linked in more than one way, as a share",
         "edges_on_disagreeing_pairs_share", share, "no relationships"),
        ("relationships inside one meaning", "edges_within_one_node", count, "not recorded"),
    ]),
    ("When the papers were written", [
        ("earliest year", "year_min", year, "no years recorded"),
        ("lower quartile", "year_p25", year, "no years recorded"),
        ("median year", "year_median", year, "no years recorded"),
        ("upper quartile", "year_p75", year, "no years recorded"),
        ("latest year", "year_max", year, "no years recorded"),
        ("papers with no year", "papers_with_no_year", count, "not recorded"),
    ]),
    ("The run", [
        ("runs recorded", "runs_recorded", count, "not recorded"),
        ("time the run took", "run_wall_clock", duration, "not recorded"),
        ("time from asking to finished", "requester_wait", duration, "not recorded"),
        # The page shows this to the owner only, pending the owner's answer to
        # open question 1. Here it always prints: this command needs the
        # read-only role's connection string to run at all, so its reader is the
        # Operator and never a visitor.
        ("what the run cost", "run_cost_usd", money, "not recorded"),
    ]),
]

LABEL_WIDTH = max(len(label) for _s, figs in SECTIONS for label, *_ in figs)


def render(row: dict, others: list[dict], buckets: list[dict], n: int) -> list[str]:
    out = [f'What "{row["concept"]}" is made of  (prompt {row["prompt_version"]}, '
           f'map {row["genealogy_id"]}, {row["status"]})', ""]
    out.append("Counted from this map's own rows just now. Nothing here is stored, so a")
    out.append("change to the map changes these figures immediately. A verified quote has")
    out.append("been string-matched against that paper's own extracted text; the shape --")
    out.append("the grouping, the relationships and their direction -- is this tool's")
    out.append("reading, so none of it is the history of the term. No figure here is a")
    out.append(f"score and none has a threshold behind it. Reference points are the other")
    out.append(f"maps in this system, n={n}.")

    for title, figures in SECTIONS:
        out += ["", title, "-" * len(title)]
        for label, col, fmt, absent in figures:
            value = fmt(row[col]) or absent
            line = f"  {label:<{LABEL_WIDTH}}  {value}"
            if others:
                ref = " · ".join(f"{o['concept']} {fmt(o[col]) or absent}" for o in others)
                line += f"\n  {'':<{LABEL_WIDTH}}  the other maps in this system: {ref}"
            out.append(line)
        if title == "Evidence":
            out += ["", "  By source", "  ---------"]
            mine = [b for b in buckets if b["genealogy_id"] == row["genealogy_id"]]
            if not mine:
                out.append("  nothing to split: this map holds no definitions and no "
                           "relationships")
            else:
                out.append(f"  {'unit':<12}{'source':<36}{'total':>8}{'verified':>10}"
                           f"{'inferred':>10}{'not re-checked':>16}")
                for b in mine:
                    unit = "definitions" if b["unit"] == "definition" else "relationships"
                    out.append(f"  {unit:<12}{b['source']:<36}{int(b['total']):>8}"
                               f"{int(b['verified']):>10}{int(b['inferred']):>10}"
                               f"{int(b['stale']):>16}")
        # Two section titles are load-bearing here and nothing else reads them:
        # rename one in SECTIONS without renaming it below and the By source
        # table or the year histogram silently stops printing. Issue #124
        # renamed three of the six.
        if title == "When the papers were written":
            out += ["", "  papers per year"]
            counts = row["year_counts"] or {}
            if not counts:
                out.append("  no years recorded")
            else:
                for y in sorted(counts, key=int):
                    out.append(f"  {y}  {'#' * min(60, int(counts[y]))} {counts[y]}")

    out += ["", "What this cannot tell you:",
            "  How many candidate links were considered and dropped, and why: the",
            "  classification counts none of its discards, so the evidence that did not",
            "  reach the map is not knowable from here (issue #86).",
            "  What a map cost and how long it took, when it was not built from a",
            "  request: those cells read \"not recorded\" rather than zero, and",
            "  genealogies.spend_usd is written by nothing and is never read here",
            "  (issues #85, #47).",
            "  Whether the map is right. Every number above comes from the map's own",
            "  rows; deciding whether its account is correct needs the papers."]
    return out


def as_json(row: dict, buckets: list[dict]) -> str:
    """The row and its buckets, to stdout, in the view's own column names.

    `Decimal` is serialised as a string rather than a float: these are exact
    values out of Postgres and turning a count or a spend into a binary float on
    the way out would be this command inventing a number.
    """
    def plain(v):
        return str(v) if isinstance(v, Decimal) else v

    return json.dumps({
        **{k: plain(v) for k, v in row.items()},
        "by_source": [{k: plain(v) for k, v in b.items()}
                      for b in buckets if b["genealogy_id"] == row["genealogy_id"]],
    }, indent=2, default=str)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="What a map is made of, from the map's own rows "
                    "(read-only; SELECT and nothing else, and it stores nothing).")
    ap.add_argument("concept", nargs="?", help="the concept to report on")
    ap.add_argument("--prompt-version", default=None,
                    help="defaults to PROMPT_VERSION from the environment")
    ap.add_argument("--all", action="store_true",
                    help="report on every map, so the reference points can be read here")
    ap.add_argument("--json", action="store_true",
                    help="JSON on stdout and to no file: an object for a named "
                         "concept, an array for --all however many maps exist")
    args = ap.parse_args()
    if not args.concept and not args.all:
        ap.error("name a concept, or pass --all")

    dsn = env(READ_URL)
    with psycopg.connect(dsn) as conn:
        cur = conn.execute(REPORTS)
        names = [d.name for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
        cur = conn.execute(BUCKETS)
        bnames = [d.name for d in cur.description]
        buckets = [dict(zip(bnames, r)) for r in cur.fetchall()]

    if not rows:
        sys.exit("No maps in this database, so there is nothing to report on.")

    # The sample size is what came back, never a literal: a number written here
    # would be wrong the first time somebody maps a third concept.
    n = len(rows)

    if args.all:
        chosen = rows
    else:
        pv = args.prompt_version or env("PROMPT_VERSION", "v1")
        chosen = [r for r in rows
                  if r["concept"] == args.concept and r["prompt_version"] == pv]
        if not chosen:
            have = ", ".join(f'{r["concept"]} ({r["prompt_version"]})' for r in rows)
            sys.exit(f'No map for "{args.concept}" at prompt {pv}. '
                     f"This database holds: {have}.")

    if args.json:
        # **The flag decides the shape, never the row count** (issue #93). This
        # used to switch on `len(chosen) > 1`, so `--all --json` emitted an
        # object against a database holding one map and an array against a
        # database holding six. A script parsing it worked until somebody mapped
        # a second concept or deleted the second-to-last, and then broke on data
        # rather than on a change anyone made to this file. `--all` is always an
        # array, of one if that is all there is; a named concept is always an
        # object.
        if args.all:
            print(json.dumps([json.loads(as_json(r, buckets)) for r in chosen], indent=2))
        else:
            print(as_json(chosen[0], buckets))
        return

    for i, row in enumerate(chosen):
        if i:
            print("\n" + "=" * 78)
        others = [r for r in rows if r["genealogy_id"] != row["genealogy_id"]]
        print("\n".join(render(row, others, buckets, n)))


if __name__ == "__main__":
    main()

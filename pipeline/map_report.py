"""Print what a map is made of, from the map's own rows, storing nothing.

Ticket #30 ([F2]); the design is docs/design/f2-map-report.md. The figures come
from migration 016's two views, migration 017's third (the mix of kinds of
link, issue #162), migration 019's fourth (what the map read, by year, issue
#182), migration 020's fifth (which pass of the build read a paper, issue
#193), migration 023's sixth (papers a person named, issue #198) and migration
024's seventh (what each step of the build spent, issue #47) and are
computed nowhere else, so this command and
`/g/<id>/report` read one expression and cannot disagree about the same map.
Which version of its concept a map is comes from migration 025's columns on
`genealogies` rather than from an eighth view (issue #209): those are stored
facts, not figures anything computes, so there is nothing for a view to hold on
behalf of two surfaces. `app/lib/report.ts` carries the argument in full.

**It reads LINEAGE_READ_URL and never DATABASE_URL, and it issues no statement
but SELECT**, modelled on `recheck_stamp.py` for the same reason: it is a tool
whose whole value is that an Operator can run it against production and paste the
answer into a report, and that is only safe if it structurally cannot write. It
does not repair, it does not refresh anything, and there is nothing to refresh --
a view holds no data.

It does, however, COMMIT. `with psycopg.connect(...)` commits on the way out of
the block -- that is what psycopg's connection context manager does, and nothing
here suppresses it -- so a statement counter watching this command sees four
SELECTs and one commit, not four SELECTs and nothing (issue #93; it was two
before #162 added the kinds of link and three before #209 added the versions).
The commit carries no change, because the only statements in the transaction are
those four
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

A concept can name more than one map since #209, because a rebuild adds a version
rather than replacing one. Naming a concept reports every version of it, in
version order; `--version N` picks one. `--json` still emits exactly one object
for a named concept -- the current version, with a note on stderr saying so --
because the flag decides the shape and the data never does.

Usage:
  python pipeline/map_report.py "attention"
  python pipeline/map_report.py "attention" --prompt-version v2
  python pipeline/map_report.py "attention" --version 2  # one version of it
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
from common import curatorial_edits, edit_actor, env  # noqa: E402

# What publication is, spelled here because this command has no access to
# `app/lib/genealogy.ts`'s `PUBLISHED_STATUS` and the two must agree. It is
# Stage E's own word (`UPDATE genealogies SET status='complete'`), it is what
# every read path in the app tests, and it is what migration 025's backfill used
# to decide which rows became version 1 and current.
PUBLISHED_STATUS = "complete"

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

# What the map READ, by year (migration 019, issue #182). Named the same way and
# for the same reason, and joined into the report row rather than fetched as a
# second table, because the grain is the same: one row per map.
#
# **LEFT JOIN, and unguarded on purpose.** LEFT so that a map absent from the
# view -- which the view's own LEFT JOINs make impossible, and which is therefore
# worth being able to see -- prints "not recorded" for these figures rather than
# vanishing out of the report entirely. Unguarded because this command is run by
# the Operator against a database whose migrations have been applied, so a
# missing view should stop it loudly; the app carries the `to_regclass` fallback
# instead, because it is live to strangers during the few minutes between the
# Vercel deploy and Render's pre-deploy migration.
READ_YEAR_COLUMNS = """r.read_year_min, r.read_year_max, r.read_year_counts,
  r.papers_read_with_no_year, r.recent_window_start, r.recent_window_end,
  r.papers_read_recent, r.papers_defining_recent"""

# Which pass of the build read a paper (migration 020, issue #193). Same grain
# again — one row per map — so it joins into the report row rather than arriving
# as a fourth table, and LEFT and unguarded for the reasons above.
#
# **Every one of these is NULL on every map in this database today**, and that is
# the design rather than a gap: nothing in the schema records a paper's pass
# until #192's orchestration lands, migration 020 ships the question over an
# empty seam, and `pass_two_outcome` carries the words for it. Printing zeros
# here would report four maps as having run a second pass that read nothing.
PASS_COLUMNS = """q.passes_recorded, q.pass_two_outcome, q.pass_two_seats,
  q.pass_two_candidates, q.pass_two_candidates_cleared, q.papers_read_pass_one,
  q.papers_read_pass_two, q.papers_read_pass_unmarked, q.papers_defining_pass_two,
  q.papers_linking_into_pass_one, q.pass_two_rank_bands,
  q.pass_two_rank_band_width"""

# Papers a person named at request time (migration 023, issue #198). Same grain
# again — one row per map — so it joins into the report row, and LEFT and
# unguarded for the reasons above.
#
# **Unlike `PASS_COLUMNS`, every count here is a real zero on every map in this
# database**, and no `COALESCE` fabricates it: the view counts rows in
# `map_anchor_papers`, and a map with none had no paper named by a person. That
# is equally true of a map built before the feature shipped and of one built
# after it with the field left empty, so there is no state to distinguish and no
# absent word to invent. `named_papers` is the exception and is NULL when nobody
# was named, so the list can be skipped without inspecting the count.
#
# `named_by` and `named_by_asserted` print HERE and on no other surface: the
# page's sentence is about "the person who requested it" and needs no login to be
# true, while this command's reader is the Operator, who needs the read-only
# connection string to run it at all. Resolved with decision 18's precedence.
ANCHOR_COLUMNS = """n.papers_named, n.papers_named_read, n.papers_named_defining,
  n.papers_named_linked, n.named_by, n.named_by_asserted, n.named_papers"""

# What each step of the build spent (migration 024, issue #47). Same grain again
# — one row per map — so it joins into the report row, and LEFT and unguarded for
# the reasons above.
#
# **Every count here is NULL on every map built before #47 shipped**, like
# `PASS_COLUMNS` and unlike `ANCHOR_COLUMNS`: a build that ran no steps does not
# exist, so a zero could only ever mean nothing recorded it, and
# `stage_record_basis` carries the words. Within a recorded build the zeros are
# real — `stages_with_no_cost_line` counts steps that ran and printed nothing.
#
# `stage_record_run_id` prints HERE and on no other surface: it says which queued
# request the steps were recorded from, which is what tells an Operator whether
# this breakdown and `run_cost_usd` above describe the same run. A reader of a map
# is owed neither the id nor the queue behind it.
STAGE_COLUMNS = """p.stages_recorded, p.stages_with_a_cost, p.stages_with_no_cost_line,
  p.stage_spend_usd, p.stage_wall_clock, p.stages_pass_one, p.stages_pass_two,
  p.stages_outside_passes, p.pass_one_spend_usd, p.pass_two_spend_usd,
  p.spend_outside_passes, p.costliest_stage, p.costliest_stage_usd,
  p.costliest_stage_share, p.stage_record_basis, p.stage_record_run_id, p.stages"""

# Which version of its concept a map is (migration 025, issue #209). These are
# columns of `genealogies` and not of a report view, because they are stored
# facts rather than figures anything computes -- `app/lib/report.ts` carries the
# argument for why no eighth view was added for them.
#
# The join is back to the table `map_report` is built from, keyed on the map's
# own id, so it cannot multiply a row. LEFT for the reason the others are: a
# report row with no `genealogies` row is impossible and therefore worth being
# able to see, and it prints as an absence rather than dropping the map.
#
# **It joins a subquery exposing four columns and not the table.** `genealogies`
# carries `concept`, `prompt_version` and `status` too, and `COLUMNS` above names
# those bare -- so joining the table makes every one of them ambiguous and the
# whole statement raises `AmbiguousColumn` (found by running it, not by reading
# it). Qualifying `COLUMNS` with `m.` would have fixed it too and would have
# broken the thing that list exists for: it is compared name for name with its
# twin in `app/lib/report.ts`.
#
# **Unguarded, like every other join here**: the Operator runs this against a
# database whose migrations have been applied, so a missing column should stop it
# loudly. The app carries the `to_regclass` probe instead, because it is live to
# strangers during the few minutes between the Vercel deploy and Render's
# pre-deploy migration.
VERSION_COLUMNS = """g.version, g.is_current, g.superseded_at"""

REPORTS = (f"SELECT {COLUMNS},\n  {READ_YEAR_COLUMNS},\n  {PASS_COLUMNS},\n"
           f"  {ANCHOR_COLUMNS},\n  {STAGE_COLUMNS},\n  {VERSION_COLUMNS}\n"
           "FROM map_report m\n"
           "LEFT JOIN map_report_read_years r USING (genealogy_id)\n"
           "LEFT JOIN map_report_passes q USING (genealogy_id)\n"
           "LEFT JOIN map_report_anchors n USING (genealogy_id)\n"
           "LEFT JOIN map_report_stages p USING (genealogy_id)\n"
           "LEFT JOIN (SELECT id, version, is_current, superseded_at\n"
           "             FROM genealogies) g ON g.id = m.genealogy_id\n"
           "ORDER BY concept, prompt_version, version")

BUCKETS = """
SELECT genealogy_id, unit, source, total, verified, inferred, stale
FROM map_report_by_source
ORDER BY genealogy_id, unit, source
"""

# The mix of kinds of link (migration 017, issue #162). Unguarded on purpose,
# unlike the app's read of the same view: this command is run by the Operator
# against a database whose migrations have been applied, and a missing view here
# should stop the command loudly rather than quietly print a report with a grain
# missing. The app carries a fallback because it is live to strangers during the
# few minutes between the Vercel deploy and Render's pre-deploy migration.
#
# Ordered by the view's own rank, so the order of the six lives in the migration
# and nowhere else; NULLS LAST puts a kind the taxonomy does not contain after
# the ones it does.
TYPES = """
SELECT genealogy_id, edge_type, taxonomy_rank, edges, edges_share
FROM map_report_by_type
ORDER BY genealogy_id, taxonomy_rank NULLS LAST, edge_type
"""

# Every version of every concept (migration 025, issue #209), so each map's
# report can list the siblings a reader can open and say which of them carries
# somebody's hand edits. #212 rules that an edit stays on the version it was made
# against, so the count is per version and is never added up across them.
#
# **Every row, whatever its status, unlike the page.** `/g/<id>/report` lists
# published versions only, because an unpublished one is not a version a reader
# can open; this command's reader is the Operator, for whom a build that took
# version 4 and never published it is exactly the thing worth seeing, and it is
# the number #211 will count. So the table below prints `status` and the page has
# no such column.
#
# `user_edits` comes over the wire and is counted in Python by
# `common.curatorial_edits`, not by `jsonb_array_length` here: what counts as
# curation has one definition per language, and the SQL form would count a
# recovery script's `restore` as somebody's editorial work (incident 12).
VERSIONS = """
SELECT id AS genealogy_id, concept, prompt_version, version, is_current,
       superseded_at, status,
       COALESCE(user_edits, '[]'::jsonb) AS user_edits
FROM genealogies
ORDER BY concept, version, id
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


def text(v) -> str | None:
    """A figure the view publishes as words rather than as a number.

    `pass_two_outcome` is the only one today and it is never NULL, but this is
    written to return None for one anyway: the absent branch is what every other
    formatter here has, and a figure that cannot be absent today is one migration
    from being able to be.
    """
    return None if v is None else str(v)


def year(v) -> str | None:
    if v is None:
        return None
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:.1f}"


def flag(v) -> str | None:
    """A stored boolean, as a word. None stays None so the row prints its own
    absent words rather than reporting false about a column nothing answered."""
    return None if v is None else ("yes" if v else "no")


def when(v) -> str | None:
    """A calendar day: "12 August 2026", the same three parts in the same order
    as `longDate` on `/g/<id>/report`.

    Spelled and never numeric, because 12/08/2026 is two different days on two
    sides of the Atlantic and this one is the date a version of a map stopped
    being the live one. Not `strftime("%-d")`, which is not portable to Windows,
    where this command is also run.

    The page renders its date in UTC so that every reader of one map sees one
    string; this prints whatever zone psycopg hands back, which is the Operator's,
    and the two can therefore differ by a day for a replacement that happened near
    midnight. That is deliberate and is the same split as `edit_when`: this
    command's reader is one person looking at their own database, the page's
    readers are strangers who must all see the same thing.
    """
    return None if v is None else f"{v.day} {v:%B %Y}"


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
        # Papers a person named at request time (migration 023, issue #198). In
        # this section rather than one of its own, where the page puts it, and
        # for the page's reason: these figures say how much was read, and the
        # difference between a paper this system found and a paper somebody
        # handed it belongs inside one glance of the totals. The list itself
        # prints under the section, like the by-source and kinds-of-link tables.
        #
        # The absent words are never reached today and are written anyway: the
        # view counts rows, so these are zeroes rather than absences on every map.
        # Every label here is unique across this whole list and is spelled the
        # same way on the page. "of those, papers that define the term" was the
        # obvious wording for the third and is already taken, by the recency
        # block below, over a different population — the exact one-noun-two-
        # populations trap #123 was about.
        ("papers named by the person who asked for this map", "papers_named", count,
         "not recorded"),
        ("named papers this map read", "papers_named_read", count, "not recorded"),
        ("named papers that define the term", "papers_named_defining", count,
         "not recorded"),
        ("named papers carrying a relationship", "papers_named_linked", count,
         "not recorded"),
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
        # Everything above is over the papers that DEFINE the term; everything
        # below is over every paper the map read (migration 019, issue #182).
        # The labels say which, because two populations under one noun is how
        # four surfaces of this product came to print four different counts of
        # "papers" (#123). "papers read" is already the first figure of the
        # report and these use the same word for the same population.
        ("oldest paper read", "read_year_min", year, "no years recorded"),
        ("newest paper read", "read_year_max", year, "no years recorded"),
        ("papers read with no year", "papers_read_with_no_year", count, "not recorded"),
        ("recent window, first year", "recent_window_start", year, "not recorded"),
        ("recent window, last year", "recent_window_end", year, "not recorded"),
        # This one moves by construction the moment the selection reserves seats
        # for recent work: a figure counting papers in a window cannot fail when
        # something puts papers in the window. It is instrumentation and the
        # evidence is the line below it, which an independent judge -- reading
        # the paper -- can still answer no to.
        ("papers read from the last five years", "papers_read_recent", count,
         "not recorded"),
        ("of those, papers that define the term", "papers_defining_recent", count,
         "not recorded"),
    ]),
    # Which pass of the build read a paper (migration 020, issue #193). Its own
    # section here, where the page puts it in a block at the foot of "When the
    # papers were written": the page's question is "did this map read recent
    # work, and did it go looking or was it given the seats", which is one
    # glance; this command's reader is the Operator and the ladder below needs a
    # heading to sit under.
    #
    # **"built in one pass" is the absent word for every count, and it is not a
    # zero.** Nothing records a paper's pass yet, so every one of these reads it
    # on every map in this database. Once a build IS recorded, a zero is a real
    # zero and `why the second pass ended` says which of the four states produced
    # it.
    ("The two passes", [
        ("why the second pass ended", "pass_two_outcome", text, "not recorded"),
        # Its own absent words, and deliberately not the others': this figure is
        # literally "what the build wrote down about itself", so "built in one
        # pass" would be this row answering with the conclusion drawn from its
        # own absence. The row above it says the conclusion.
        ("passes the build recorded", "passes_recorded", count,
         "nothing recorded how this map was built"),
        ("papers read in the first pass", "papers_read_pass_one", count,
         "built in one pass"),
        ("papers read in the second pass", "papers_read_pass_two", count,
         "built in one pass"),
        # Above zero means the build's own record of itself is incomplete. It
        # exists so the three counts sum to `papers read` whatever the build
        # wrote, and `render` marks it when it does not.
        ("papers the record puts in neither pass", "papers_read_pass_unmarked",
         count, "built in one pass"),
        ("second-pass papers that define the term", "papers_defining_pass_two",
         count, "built in one pass"),
        # The tool's reading, not a checked fact: an edge is a judgement about
        # direction and kind. The closest honest figure to "the idea moved
        # recently" and not that claim.
        ("second-pass papers linked to a first-pass meaning",
         "papers_linking_into_pass_one", count, "built in one pass"),
        ("seats the second pass reserved", "pass_two_seats", count,
         "built in one pass"),
        ("recent papers that cite this map", "pass_two_candidates", count,
         "built in one pass"),
        ("of those, papers the second pass could have read",
         "pass_two_candidates_cleared", count, "built in one pass"),
    ]),
    # Which version of its concept this map is (migration 025, issue #209). Its
    # own section here, immediately before the run whose record produced it,
    # where the page puts the same figures in a block at the head of "The run":
    # the build behind a version and the version's standing are one question, and
    # the table below needs a heading to sit under.
    #
    # **Every count here is a real count and none of them is an absence**, like
    # the named-paper figures and unlike the pass ones: migration 025's columns
    # are NOT NULL with defaults and its backfill made every published map version
    # 1, so a NULL could only mean the LEFT JOIN found no `genealogies` row, which
    # is a state this database cannot be in. The absent words are written anyway,
    # because a figure that cannot be absent today is one migration from being
    # able to be.
    ("Which version this is", [
        ("which version this is", "version_label", text, "not recorded"),
        ("is it the current version", "is_current", flag, "not recorded"),
        # Its own absent words and deliberately not "not recorded": a current
        # version has not been replaced, which is a fact and not a silence.
        # `replaced_on` is composed in `version_figures` precisely so that a
        # version replaced without a date being written says THAT instead, rather
        # than sharing these words and reading as though it were still live.
        ("replaced on", "replaced_on", text,
         "not replaced: this is the current version"),
        ("changes made to this version by hand", "curatorial_edits_this_version",
         count, "not counted"),
        ("published versions of this map", "versions_published", count,
         "not counted"),
        # Command-only, like `named_by` and `stage_record_run_id`. A build that
        # took a version number and never published is invisible to a reader and
        # is exactly what an Operator wants to see; the gap between these two
        # counts is the abandoned rows #211 will read.
        ("versions of this map recorded, published or not", "versions_recorded",
         count, "not counted"),
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
    # What each step of the build spent (migration 024, issue #47). Its own
    # section, after the run whose total it opens up, because the table below
    # needs a heading to sit under and because the reading order is total first
    # and parts second.
    #
    # **"no step-by-step record of this build" is the absent word for every count
    # and it is not a zero.** Every map built before #47 reads it. A build that
    # ran no steps does not exist, so a zero here could only ever mean absence,
    # and `where these figures came from` says which state this map is in.
    ("What each step of the build spent", [
        ("where these figures came from", "stage_record_basis", text, "not recorded"),
        ("steps of the build recorded", "stages_recorded", count,
         "no step-by-step record of this build"),
        ("steps that reported a cost", "stages_with_a_cost", count,
         "no step-by-step record of this build"),
        # Most steps of a build spend nothing, and a step that stopped printing
        # its spend looks the same from here. Neither is a cost of zero, and this
        # count is what makes the second one visible at all rather than silently
        # absent from a total (#85's complaint, and the half of it that was
        # fixable).
        ("steps that reported no cost line", "stages_with_no_cost_line", count,
         "no step-by-step record of this build"),
        ("what the recorded steps spent", "stage_spend_usd", money,
         "no step reported a cost"),
        # NOT the run's time, and the label says so: the step that writes this
        # record runs inside the build and cannot time itself or the publish after
        # it, so this is always short of `time the run took` by those two steps.
        ("time in the recorded steps", "stage_wall_clock", duration,
         "no step-by-step record of this build"),
        ("steps in the first pass", "stages_pass_one", count,
         "no step-by-step record of this build"),
        ("steps in the second pass", "stages_pass_two", count,
         "no step-by-step record of this build"),
        ("steps in neither pass", "stages_outside_passes", count,
         "no step-by-step record of this build"),
        ("what the first pass spent", "pass_one_spend_usd", money,
         "no first-pass step reported a cost"),
        ("what the second pass spent", "pass_two_spend_usd", money,
         "no second-pass step reported a cost"),
        ("what the steps in neither pass spent", "spend_outside_passes", money,
         "no such step reported a cost"),
        ("the most expensive step", "costliest_stage", text,
         "no step reported a cost"),
        ("what the most expensive step cost", "costliest_stage_usd", money,
         "no step reported a cost"),
        ("what the most expensive step cost, as a share", "costliest_stage_share",
         share, "no step reported a cost"),
        # Command-only, like `named_by`: it says which queued request these steps
        # came from, which is how an Operator tells whether this breakdown and
        # "what the run cost" describe the same run.
        ("the request these steps were recorded from", "stage_record_run_id", count,
         "not recorded"),
    ]),
]

LABEL_WIDTH = max(len(label) for _s, figs in SECTIONS for label, *_ in figs)


def attach_version_figures(rows: list[dict], versions: list[dict]) -> None:
    """Compose each map's version figures onto its report row, in place.

    **Every row gets every key, not only the map being printed.** The comparison
    line beside each figure reads `o[col]` for every other map, so a key present
    on one row and missing on another is a KeyError in the middle of a report --
    the same reason the joins above are LEFT.

    `versions` is every row of `genealogies`, whatever its status, so this can
    report the published count a reader sees and the recorded count only an
    Operator does. The two differ by builds that took a version number and never
    published, which is #211's reading.
    """
    # How a map is named on somebody else's reference line. It was the concept
    # alone until versions existed, and on this command -- which reports every
    # map, not one per concept -- three versions of one term then printed as
    # "dark energy 4 · dark energy 4 · dark energy 4", three identical labels for
    # three different maps. The version is added only where the term appears more
    # than once, so a database of one map per term prints exactly what it printed
    # before. Display only; the map's identity is its id, which the header prints.
    seen: dict[str, int] = {}
    for row in rows:
        seen[row["concept"]] = seen.get(row["concept"], 0) + 1

    for row in rows:
        mine = [v for v in versions if v["concept"] == row["concept"]]
        me = next((v for v in mine if v["genealogy_id"] == row["genealogy_id"]), None)
        # The map's id and not its version number: the first draft said
        # "dark energy version 2" and the version row then read "dark energy
        # version 2 version 2", because that row's value is itself "version 2".
        # The id is the map's identity anyway, and the header prints it.
        row["ref_label"] = (row["concept"] if seen[row["concept"]] < 2
                            else f'{row["concept"]} #{row["genealogy_id"]}')
        row["versions"] = mine
        row["versions_recorded"] = len(mine)
        row["versions_published"] = len([v for v in mine
                                         if v["status"] == PUBLISHED_STATUS])
        row["curatorial_edits_this_version"] = (
            None if me is None else len(curatorial_edits(me["user_edits"])))
        if row["version"] is None:
            # No `genealogies` row behind this report row, which the views cannot
            # produce. Every version figure reads as an absence, and `replaced on`
            # gets words of its own rather than falling through to "not replaced",
            # which would be this command asserting the map is live.
            row["version_label"] = None
            row["replaced_on"] = "not recorded: no map row to read a version from"
            continue
        row["version_label"] = f"version {row['version']}"
        # **Not current does NOT mean replaced**, and the first draft of this said
        # it did: it printed "replaced, and the date was not recorded" over a
        # build that died halfway and over a map nobody has ever published, both
        # of which were never current and so were never replaced either.
        # Migration 025's header states exactly that about these two columns, and
        # the bug was written anyway; running it over a fixture holding both rows
        # is what showed it. Four states, four sentences, and only the current one
        # returns None so that the absent branch has exactly one meaning.
        row["replaced_on"] = (
            None if row["is_current"]
            else when(row["superseded_at"]) or
            ("nothing records this version being replaced"
             if row["status"] == PUBLISHED_STATUS
             else "never published, so never replaced"))


def render(row: dict, others: list[dict], buckets: list[dict], types: list[dict],
           n: int) -> list[str]:
    # The version rides in the header beside the status, because both say what
    # the reader is looking at rather than what is in it (issue #209). Absent
    # rather than guessed where the join found nothing.
    # "not current" and never "superseded" where no date says so: a build that
    # died is not current and was not replaced by anything.
    standing = (f', {row["version_label"]}, ' + (
        "current" if row["is_current"]
        else f'superseded {when(row["superseded_at"])}' if row["superseded_at"]
        else "not current")) if row.get("version_label") else ""
    out = [f'What "{row["concept"]}" is made of  (prompt {row["prompt_version"]}, '
           f'map {row["genealogy_id"]}, {row["status"]}{standing})', ""]
    out.append("Counted from this map's own rows just now. Nothing here is stored, so a")
    out.append("change to the map changes these figures immediately. A verified quote has")
    out.append("been string-matched against that paper's own extracted text; the shape --")
    out.append("the grouping, the relationships and their direction -- is this tool's")
    out.append("reading, so none of it is the history of the term. No figure here is a")
    out.append(f"score and none has a threshold behind it. Reference points are every")
    out.append(f"other map in this database, published or not and current or superseded,")
    out.append(f"n={n}. That is deliberately a wider set than /g/<id>/report compares")
    out.append(f"against, which is one map per term, the current version of each; so the")
    out.append(f"two surfaces print the same figures for a map and can print a different")
    out.append(f"n beside them.")

    for title, figures in SECTIONS:
        out += ["", title, "-" * len(title)]
        for label, col, fmt, absent in figures:
            value = fmt(row[col]) or absent
            line = f"  {label:<{LABEL_WIDTH}}  {value}"
            if others:
                ref = " · ".join(f"{o['ref_label']} {fmt(o[col]) or absent}"
                                 for o in others)
                line += f"\n  {'':<{LABEL_WIDTH}}  the other maps in this system: {ref}"
            out.append(line)
        # Which papers a person named (issue #198), under the section whose
        # totals they are part of, where the page puts them. A count alone cannot
        # tell a reader WHICH paper somebody supplied, and being able to is the
        # design's second integrity condition; the honest failure it exists to
        # expose — named, read, defines nothing, connected to nothing — is a line
        # of this table and not a sentence anybody has to write.
        if title == "How much was read":
            named = row["named_papers"]
            if named:
                who, basis = edit_actor({"by": row["named_by"],
                                         "by_asserted": row["named_by_asserted"]})
                out += ["", f"  Named by {who} ({basis})" if who
                        else "  Named, actor not recorded",
                        "  " + "-" * 30]
                out.append(f"  {'arXiv ID':<14}{'Year':>5}  {'Read':<20}"
                           f"{'Defines':<10}{'Links':>6}  Title")
                for p in named:
                    # "not read" rather than "no" where the paper never arrived:
                    # Stage B gave no verdict on it, and printing "no" would
                    # report a reading that never happened.
                    defines = ("yes" if p.get("defines")
                               else "no" if p.get("read") else "not read")
                    out.append(
                        f"  {str(p.get('arxiv_id') or '?'):<14}"
                        f"{p.get('year') or '?':>5}  "
                        f"{('yes' if p.get('read') else 'COULD NOT BE READ'):<20}"
                        f"{defines:<10}"
                        f"{int(p.get('relationships') or 0):>6}  "
                        f"{(p.get('title') or '?')[:44]}")
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
        # The mix of kinds of link (issue #162), under Shape, where the page puts
        # it. Every kind the view returns is printed in the view's own order, so
        # the six names are not written down in this file either and a seventh
        # would print as a seventh line rather than going missing.
        if title == "Shape":
            out += ["", "  Kinds of link", "  -------------"]
            mine = [t for t in types if t["genealogy_id"] == row["genealogy_id"]]
            # The zero branch is on the map's relationship count and not on
            # `mine`, because the view emits all six kinds for every map: a map
            # with no relationships has six rows, each reading 0 with an absent
            # share, and printing them gave six lines of "0no relationships"
            # where the absent words overran a ten-column field. The page says
            # one sentence in that state and so does this. `not mine` stays as
            # its own branch: it means the view returned nothing for this map,
            # which is a different claim from the map having no relationships.
            if not mine:
                out.append("  nothing to count: this map has no rows on the view")
            elif int(row["edges_total"]) == 0:
                out.append("  this map holds no relationships, so there is no mix "
                           "of kinds to count")
            else:
                out.append(f"  {'kind':<14}{'relationships':>14}{'share':>10}"
                           f"   {'in the taxonomy':<16}")
                for t in mine:
                    out.append(f"  {t['edge_type']:<14}{count(t['edges']):>14}"
                               f"{share(t['edges_share']) or 'no relationships':>10}"
                               f"   {'yes' if t['taxonomy_rank'] is not None else 'NO':<16}")
                # The falsifier, printed rather than assumed: these must add up to
                # `typed relationships` above, and a reader of this command should
                # not have to add six numbers to find out that they do not.
                total = sum(int(t["edges"]) for t in mine)
                line = f"  {'total':<14}{count(total):>14}"
                if total != int(row["edges_total"]):
                    line += "   <- DOES NOT MATCH typed relationships above"
                out.append(line)
        # #188's free half, and it prints here and on no other surface (issue
        # #193). The defining rate over what the second pass actually read, in
        # bands of ten by selection rank, so a falling rate says the seat count
        # is larger than the map had papers worth reading. It costs nothing,
        # because it counts work the build already did.
        #
        # **It bounds R from above and cannot bound it from below**: past the
        # point where the rate falls off the seats are certainly wasted, and
        # nothing here can say whether a seat below that point earned its place.
        # That needs one deliberate over-read to twice the seat count, on the
        # first two-stage map, which is the paid half of #188 and is not this.
        # And it measures whether a reserved paper DEFINES the term, never
        # whether it MOVED it.
        #
        # Off the page deliberately, like "quote slots" since #108: it answers a
        # question for whoever sets the seat count, not for somebody reading a
        # map.
        if title == "The two passes":
            heading = "  The second pass's ranking, by band of selection rank"
            out += ["", heading, "  " + "-" * (len(heading) - 2)]
            bands = row["pass_two_rank_bands"]
            read2 = row["papers_read_pass_two"]
            if row["passes_recorded"] is None:
                out.append("  this map was built in one pass, so there is no second "
                           "pass to rank")
            elif not bands:
                # Two different findings and they must not print the same words:
                # nothing was read, or things were read and the build recorded no
                # ranking for them. The second is a defect in the build's record.
                out.append("  the second pass read nothing, so there is nothing to rank"
                           if read2 == 0 else
                           "  the second pass read papers and recorded no selection "
                           "ranking for them")
            else:
                width = row["pass_two_rank_band_width"]
                out.append(f"  bands are {width} ranks wide")
                out.append(f"  {'ranks':<12}{'read':>8}{'define':>8}")
                for b in bands:
                    span = f"{b['from']}-{b['to']}"
                    out.append(f"  {span:<12}"
                               f"{int(b['read']):>8}{int(b['defining']):>8}")
                # The falsifier, printed rather than assumed: the bands are the
                # ranked papers, which can be fewer than the papers read if the
                # build ranked only some of them, and never more.
                ranked = sum(int(b["read"]) for b in bands)
                line = f"  {'ranked':<12}{ranked:>8}"
                if read2 is not None and ranked > int(read2):
                    line += "   <- MORE THAN papers read in the second pass"
                out.append(line)
            # The other falsifier this section carries: the two passes plus the
            # papers the record places in neither must be the papers read.
            parts = [row["papers_read_pass_one"], row["papers_read_pass_two"],
                     row["papers_read_pass_unmarked"]]
            if all(p is not None for p in parts):
                total = sum(int(p) for p in parts)
                line = (f"  papers read = {count(parts[0])} in the first pass"
                        f" + {count(parts[1])} in the second"
                        f" + {count(parts[2])} in neither = {count(total)}")
                if total != int(row["papers_with_a_reading"]):
                    line += "   <- DOES NOT MATCH papers read above"
                out += ["", line]
        # Every version of this map (issue #209), under the section whose figures
        # describe one of them. A count alone cannot tell a reader WHICH version
        # carries somebody's hand edits, and #212's rule -- an edit stays on the
        # version it was made against -- is only checkable if that is visible.
        #
        # It prints unpublished versions too, where the page cannot: `status` is a
        # column here and the page has no such column, because a build that took a
        # version number and never finished is a fact about our operations rather
        # than about the term.
        if title == "Which version this is":
            heading = "  Every version of this map"
            out += ["", heading, "  " + "-" * (len(heading) - 2)]
            mine = row.get("versions") or []
            if not mine:
                # The report row came out of `genealogies` and this query reads
                # `genealogies`, so an empty list here is not a state a map can be
                # in.
                out.append("  no versions recorded for this term, which cannot be true "
                           "of a map that has a report: read it as a defect.")
            else:
                out.append(f"  {'version':>7}  {'map':>6}  {'prompt':<8}{'status':<12}"
                           f"{'current':<9}{'replaced on':<22}{'by hand':>8}  which")
                for v in mine:
                    # "not replaced" covers both a current version and one that
                    # nothing records replacing, which is what a died build looks
                    # like. The `current` column beside it says which.
                    replaced = ("" if v["is_current"] else when(v["superseded_at"]) or "")
                    out.append(
                        f"  {int(v['version']):>7}  {int(v['genealogy_id']):>6}  "
                        f"{str(v['prompt_version'])[:7]:<8}"
                        f"{str(v['status'])[:11]:<12}"
                        f"{('yes' if v['is_current'] else 'no'):<9}"
                        f"{(replaced or 'not replaced'):<22}"
                        f"{len(curatorial_edits(v['user_edits'])):>8}  "
                        f"{'THIS ONE' if v['genealogy_id'] == row['genealogy_id'] else ''}")
                # The falsifier, printed rather than assumed: migration 025's
                # partial unique index makes two current versions of one concept
                # impossible, so seeing two here means the index is gone.
                live = [v for v in mine if v["is_current"]]
                if len(live) > 1:
                    out.append(f"  <- {len(live)} versions of this term say they are "
                               f"current, which genealogies_one_current_per_concept "
                               f"is supposed to make impossible.")
        # The breakdown itself (issue #47), under the section whose figures it
        # opens up. It prints here and not on the page's reader tier for the
        # reason "quote slots" has been command-only since #108: the page shows
        # the owner the total, the most expensive step and the same table, and the
        # per-pass subtotals and the request id are the Operator's half.
        #
        # A step with no cost line prints the words rather than US$0.00, and the
        # column is wide enough for them — the absent form is the one string in a
        # numeric column that is prose, and sizing a column by its numbers is how
        # `0no relationships` was published six times on #162.
        if title == "What each step of the build spent":
            heading = "  Every step, in the order it ran"
            out += ["", heading, "  " + "-" * (len(heading) - 2)]
            stages = row["stages"]
            if row["stages_recorded"] is None:
                out.append("  no step-by-step record of this build, so there is nothing "
                           "to break down. That is an absence and not a build that "
                           "spent nothing.")
            elif not stages:
                # The counts said something was recorded and the list is empty:
                # the two come out of one set of rows, so this is a defect in the
                # view rather than a state a build can be in.
                out.append("  the record counts steps and lists none, which the view "
                           "cannot produce from one set of rows: read it as a defect "
                           "and not as a build.")
            else:
                out.append(f"  {'#':>3}  {'step':<44}{'pass':>8}{'cost':>16}"
                           f"{'time':>12}")
                for s in stages:
                    spend = s.get("spend_usd")
                    secs = s.get("seconds")
                    pass_no = s.get("build_pass")
                    out.append(
                        f"  {int(s.get('stage_no') or 0):>3}  "
                        f"{str(s.get('stage') or '?')[:43]:<44}"
                        f"{('neither' if pass_no is None else str(pass_no)):>8}"
                        f"{(money(spend) or 'no cost line'):>16}"
                        f"{(duration(secs) or 'not recorded'):>12}")
                # The falsifier, printed rather than assumed: the recorded steps
                # are the same scrape the run's own total is, so the two figures
                # should agree. They can legitimately differ, and the line says
                # how: the run figure describes the last COMPLETED run and the
                # steps describe the last build that got as far as recording
                # itself, which are two different runs when a build recorded its
                # steps and then failed at the publish.
                total, run_total = row["stage_spend_usd"], row["run_cost_usd"]
                line = (f"  the recorded steps spent {money(total) or 'nothing measured'}"
                        f"; the run's own total says "
                        f"{money(run_total) or 'nothing recorded'}")
                if (total is not None and run_total is not None
                        and Decimal(total) != Decimal(run_total)):
                    line += ("\n    <- DOES NOT MATCH. Either a step's spend was "
                             "recorded and not counted into the run, or these two "
                             "figures describe different runs of this map; the "
                             "request id above says which run the steps came from.")
                out += ["", line]
        # Three section titles are load-bearing here and nothing else reads them:
        # rename one in SECTIONS without renaming it below and the By source
        # table, the kinds-of-link table or the year histogram silently stops
        # printing. Issue #124 renamed three of the six.
        if title == "When the papers were written":
            out += ["", "  papers per year"]
            counts = row["year_counts"] or {}
            # Both series in one bar, the way the page draws them in one column
            # (issue #182): '#' is a paper that defines the term, '-' is a paper
            # read that did not, so the tail of the bar IS the gap between the
            # two figures and nobody has to subtract. `read` is falsy on a map
            # that read no dated paper, and then this prints exactly what it
            # printed before the read series existed.
            read = row.get("read_year_counts") or {}
            if not counts and not read:
                out.append("  no years recorded")
            elif not read:
                for y in sorted(counts, key=int):
                    out.append(f"  {y}  {'#' * min(60, int(counts[y]))} {counts[y]}")
            else:
                out.append("  '#' defines the term, '-' read and did not")
                for y in sorted(set(counts) | set(read), key=int):
                    n_def, n_read = int(counts.get(y, 0)), int(read.get(y, 0))
                    bar = ("#" * n_def + "-" * max(0, n_read - n_def))[:60]
                    out.append(f"  {y}  {bar} {n_read} read, {n_def} define")

    out += ["", "What this cannot tell you:",
            "  How many candidate links were considered and dropped, and why: the",
            "  classification counts none of its discards, so the evidence that did not",
            "  reach the map is not knowable from here (issue #86).",
            "  What a map cost and how long it took, when it was not built from a",
            "  request: those cells read \"not recorded\" rather than zero, and",
            "  genealogies.spend_usd is written by nothing and is never read here",
            "  (issue #85). Since #47 a build run from a request also records what",
            "  each of its steps spent; a map built by hand records none, and a",
            "  step that prints no cost line is a step with no figure either way.",
            "  Whether the map is right. Every number above comes from the map's own",
            "  rows; deciding whether its account is correct needs the papers."]
    return out


def as_json(row: dict, buckets: list[dict], types: list[dict]) -> str:
    """The row and its buckets, to stdout, in the view's own column names.

    `Decimal` is serialised as a string rather than a float: these are exact
    values out of Postgres and turning a count or a spend into a binary float on
    the way out would be this command inventing a number.

    Since #209 the row also carries the keys `attach_version_figures` composed --
    `versions`, `versions_recorded`, `versions_published`, `version_label`,
    `replaced_on`, `curatorial_edits_this_version` -- which are the only ones here
    that are not a column of some view. They are named for what they are rather
    than hidden: a consumer that wants the raw facts still has `version`,
    `is_current` and `superseded_at` beside them.
    """
    def plain(v):
        return str(v) if isinstance(v, Decimal) else v

    return json.dumps({
        **{k: plain(v) for k, v in row.items()},
        "by_source": [{k: plain(v) for k, v in b.items()}
                      for b in buckets if b["genealogy_id"] == row["genealogy_id"]],
        "by_type": [{k: plain(v) for k, v in t.items()}
                    for t in types if t["genealogy_id"] == row["genealogy_id"]],
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
    ap.add_argument("--version", type=int, default=None,
                    help="which version of the named concept; defaults to every "
                         "version, and to the current one under --json")
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
        cur = conn.execute(TYPES)
        tnames = [d.name for d in cur.description]
        types = [dict(zip(tnames, r)) for r in cur.fetchall()]
        cur = conn.execute(VERSIONS)
        vnames = [d.name for d in cur.description]
        versions = [dict(zip(vnames, r)) for r in cur.fetchall()]

    if not rows:
        sys.exit("No maps in this database, so there is nothing to report on.")

    # Before anything selects or prints, so that a row this command reports and a
    # row it only uses as a reference point carry the same keys (issue #209).
    attach_version_figures(rows, versions)

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
        # A concept can now name several maps (issue #209), where migration 007's
        # UNIQUE (concept, prompt_version) used to make that impossible. Without
        # `--version` every one of them is reported, in version order, each with
        # its own header saying which it is.
        if args.version is not None:
            chosen = [r for r in chosen if r["version"] == args.version]
            if not chosen:
                sys.exit(f'No version {args.version} of "{args.concept}" at prompt '
                         f"{pv}. Run without --version to see the versions there are.")

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
            print(json.dumps([json.loads(as_json(r, buckets, types)) for r in chosen],
                             indent=2))
        else:
            # **Still exactly one object, whatever the data holds** (#93's rule,
            # which versions are the first thing that could have broken it): a
            # concept naming three maps must not turn this into an array on a
            # database where a term has been rebuilt. The current version is what
            # a reader means by "the map for this term"; `chosen` is ordered by
            # version, so the fallback is the newest. The note goes to stderr, so
            # stdout stays one parseable object.
            pick = next((r for r in chosen if r["is_current"]), chosen[-1])
            if len(chosen) > 1:
                print(f'"{args.concept}" has {len(chosen)} versions at prompt '
                      f'{pick["prompt_version"]}; reporting version {pick["version"]} '
                      f'(map {pick["genealogy_id"]}). Pass --version N for another.',
                      file=sys.stderr)
            print(as_json(pick, buckets, types))
        return

    for i, row in enumerate(chosen):
        if i:
            print("\n" + "=" * 78)
        others = [r for r in rows if r["genealogy_id"] != row["genealogy_id"]]
        print("\n".join(render(row, others, buckets, types, n)))


if __name__ == "__main__":
    main()

"""Stage E: grounding check + graph assembly.

The mandatory grounding check (CLAUDE.md rule 2): every edge quote is string-
verified against the extracted source text. An edge is 'verified' (renders solid)
only if BOTH its quotes are found verbatim; otherwise it is 'inferred' (dotted).
Never displays an unverified quote as verified.

Then assembles the final genealogy JSON (nodes + verified edges) that the UI
renders, and marks the genealogy complete — which since #168 is the act that
makes a map public, and since #171 is refused for a map that violates the
publish invariant (migration 021, `pipeline/check_map.py`).

**`--no-publish` assembles without publishing**, which is what a two-stage build
runs on every assembly but the last (#192, designed on #184). A build now grounds
and assembles three times — once at the end of pass one, once at the end of pass
two, once after Stage G — and it must be public exactly once, at the end, because
a map that became `complete` at the end of pass one would be served to readers
and then re-clustered underneath them. That is the live-surgery risk (#149, #169,
#171) the staging exists to avoid.

Usage:
  python pipeline/stage_e_ground.py "attention"
  python pipeline/stage_e_ground.py "attention" --no-publish
"""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (_fold, edge_stamp_state, grounded_span,  # noqa: E402
                    read_grounding_text, REPO_ROOT, STAMP_INFERRED, STAMP_STALE,
                    STAMP_VERIFIED, data_dir, env, node_ids)


# An edge whose source_node or target_node is not in genealogies.nodes has no
# concept-state to be a transition between. `/g/<id>/evidence` does not drop it
# and does not fail on it: `labelOf` falls back to the raw id, so the row is
# drawn in full, with both quotes and whatever stamp grounding gives it, over a
# concept-state that is not there. `computeFamilies` skips it, so it also
# silently stops joining the families it appears to join. Neither is a state to
# publish, and grounding is where every other edge-level truth is settled, so it
# is settled here too.
SELECT_ORPHANS = """
SELECT id, source_node, target_node FROM edges
WHERE genealogy_id = %(gid)s
  AND (NOT (source_node = ANY(%(live)s)) OR NOT (target_node = ANY(%(live)s)))
ORDER BY id
"""
DELETE_ORPHANS = "DELETE FROM edges WHERE id = ANY(%(ids)s)"


# ── the publish gate (issue #171) ──────────────────────────────────────────
#
# Every column named, never `SELECT *`, for the reason migration 021's header
# gives: `CREATE OR REPLACE VIEW` cannot retype, drop or reorder a column, so a
# later change to the invariant is a DROP and a CREATE, and naming them means
# such a redefinition breaks this gate loudly instead of silently changing a
# verdict. Its twin is `CLAUSE_COLUMNS` in pipeline/check_map.py.
INVARIANT_COLUMNS = [
    (1, "definitions_not_admissible"),
    (2, "nodes_whose_members_and_definitions_differ"),
    (3, "nodes_unreadable_or_duplicated"),
    (4, "relationships_with_a_bad_concept_state"),
    (5, "relationships_not_evidenced_by_their_nodes"),
    (6, "thread_papers_the_map_does_not_hold"),
]
SELECT_INVARIANT = (
    "SELECT " + ", ".join(c for _n, c in INVARIANT_COLUMNS)
    + ", findings_total, satisfies_publish_invariant "
    "FROM map_invariant WHERE genealogy_id = %(gid)s")
SELECT_FINDINGS = """
SELECT clause, clause_name, subject_kind, subject, detail
FROM map_invariant_findings
WHERE genealogy_id = %(gid)s
ORDER BY clause, subject_kind, subject
"""
FINDINGS_SHOWN = 20


def refuse_unless_publishable(conn, gen_id: int) -> None:
    """Refuse to mark a map complete while it violates the publish invariant.

    Issue #171, the publish half of #2. This stage used to set
    `status = 'complete'` with no check on what it was completing: #2 is the
    future-tense case, where a truncated rebuild gets ratified, and #149 is the
    past-tense one, where a map today's rules would refuse is marked complete and
    serves traffic.

    **Read inside the caller's transaction, so it judges the map about to be
    published rather than the one that was there before.** The orphan sweep's
    DELETE and the grounding loop's UPDATEs are uncommitted at this point and the
    view sees them, which is the whole reason the query is here rather than in a
    separate command run afterwards.

    **Every caller of `publish_swap` calls this first** (#233): this stage, and
    both restore scripts. For one commit the swap was importable and the gate was
    not, and a restore published a map this function refuses on the identical row
    — the path most likely to be carrying a damaged map, since a restore is run
    when something is already wrong. The pair is the publication rule; either
    half alone is not it. All three callers hold the writes in an uncommitted
    transaction at this point, which is what makes the sentences below true for
    all three.

    **It computes nothing.** Every count and the verdict come from
    `map_invariant`, which `pipeline/check_map.py` also reads, so an Operator
    checking a map by hand and this gate cannot disagree about it. A gate whose
    verdict is a function of something it worked out for itself would be a second
    opinion wearing the invariant's name.

    **The refusal is upstream of the commit and downstream of nothing durable**,
    which is what makes its sentence true: `sys.exit` raises `SystemExit`, the
    caller's `conn.transaction()` rolls back on any exception, and the export is
    not written until after this returns (issues #55, #65, #67).

    A missing view is a refusal too, and it says so. Migration 021 is applied by
    Render's pre-deploy step before the worker starts, so a database without it
    is one nobody migrated; failing closed there is right, and failing closed
    with a raw `UndefinedTable` traceback in the middle of a thirteen-step run is
    not.
    """
    try:
        row = conn.execute(SELECT_INVARIANT, {"gid": gen_id}).fetchone()
    except psycopg.errors.UndefinedTable as exc:
        sys.exit(
            f"\nRefusing to publish this map: the publish invariant cannot be read.\n"
            f"  {exc}\n"
            "  That view is migration 021. Apply the migrations "
            "(python pipeline/db/migrate.py)\n"
            "  and run this command again. Nothing was written and every stamp stands "
            "as\n"
            "  it was.")
    # The view selects FROM genealogies and joins everything else outward, so
    # every map has a row; no row means the genealogy is gone from under this
    # run, which is a different thing from a map that fails a clause and must not
    # be reported as one.
    if row is None:
        sys.exit(
            f"\nRefusing to publish this map: genealogy {gen_id} has no row on "
            f"map_invariant.\n"
            "  The view emits one row per genealogy, so this map was deleted while this\n"
            "  run was in flight. Nothing was written and every stamp stands as it was.")

    *counts, findings_total, satisfies = row
    if satisfies:
        print(f"  publish invariant: all six clauses hold ({findings_total} findings).\n")
        return

    findings = conn.execute(SELECT_FINDINGS, {"gid": gen_id}).fetchall()
    lines = [
        "",
        f"Refusing to publish this map: it violates {sum(1 for c in counts if c)} of the "
        f"six clauses of the publish invariant, with {findings_total} finding(s).",
        "",
    ]
    for (number, _column), count in zip(INVARIANT_COLUMNS, counts):
        lines.append(f"  clause {number}  {count:>4}")
    lines.append("")
    for clause, name, kind, subject, detail in findings[:FINDINGS_SHOWN]:
        lines.append(f"  clause {clause} ({name})")
        lines.append(f"    {kind} {subject}: {detail}")
    if len(findings) > FINDINGS_SHOWN:
        lines.append(f"  … and {len(findings) - FINDINGS_SHOWN} more")
    lines += [
        "",
        "  A map that fails a clause is one this system's own rules would not build",
        "  today, and publishing it is how the last one went unnoticed for a month",
        "  (issue #149). Nothing was written and every stamp stands as it was: this",
        "  map is exactly as it was before this run.",
        "",
        "  The same findings, read-only and from anywhere:",
        "    python pipeline/check_map.py <concept>",
    ]
    sys.exit("\n".join(lines))


def sweep_orphan_edges(conn, gen_id: int, nodes) -> None:
    """Remove edges that point at concept-states this map no longer has.

    Ordered before the quote re-sync and the grounding loop, so nothing is
    repaired, judged, stamped or assembled for an edge that is about to go, and
    so the reported verified count describes the map that will actually be
    published. Nothing later needs these rows: no stage after this one reads
    source_node or target_node at all.
    """
    live = node_ids(nodes)
    total = conn.execute("SELECT count(*) FROM edges WHERE genealogy_id = %s",
                         (gen_id,)).fetchone()[0]
    if not total:
        return
    orphans = conn.execute(SELECT_ORPHANS, {"gid": gen_id, "live": live}).fetchall()
    if not orphans:
        print(f"  {total} edge(s), every one of them between concept-states this map has.\n")
        return

    # Every edge an orphan is not a finding, it is a broken run wearing a
    # result's clothes: an empty or replaced `nodes` blob produces exactly this,
    # and so does pointing this stage at the wrong map. The same shape as the
    # --reground guard (decision 19), down to `total > 1`, which that guard has
    # as `checked > 1` for the same reason: with a single edge there is nothing
    # for "all of them" to mean, and refusing there would abort a trace at step 9
    # of 13, after every paid step, over one removable edge. The boundary is
    # likewise zero rather than a fraction — "not one edge survives" is a
    # degenerate case, not a calibration. Refuse and change nothing; the map
    # keeps its edges and its last honest stamps.
    if total > 1 and len(orphans) == total:
        sys.exit(
            f"\nRefusing to sweep: all {total} edge(s) of this map name concept-states "
            f"that genealogies.nodes does not contain.\n"
            f"  Concept-states present: {len(live)}"
            f"{' (none at all)' if not live else ''}.\n"
            "  That is what an empty or swapped `nodes` blob looks like, not what a\n"
            "  re-clustered map looks like, and this stage cannot tell them apart.\n"
            "  Nothing was deleted and no stamp was moved. Check `nodes` first, and\n"
            "  re-run Stage C then Stage D if the concept-states really are gone.")

    print(f"  {len(orphans)} of {total} edge(s) name a concept-state this map no longer "
          f"has, and were removed before grounding:")
    for eid, sn, tn in orphans[:20]:
        missing = " and ".join(
            f"{side} {nid}" for side, nid in (("source", sn), ("target", tn))
            if nid not in live)
        print(f"    edge {eid}: {missing} not in nodes")
    if len(orphans) > 20:
        print(f"    … and {len(orphans) - 20} more")
    conn.execute(DELETE_ORPHANS, {"ids": [e[0] for e in orphans]})
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage E: ground edge quotes and assemble genealogy.")
    ap.add_argument("concept")
    ap.add_argument("--json", metavar="PATH", help="output path (default DATA_DIR/genealogy_<concept>_<pv>.json)")
    ap.add_argument("--no-publish", action="store_true",
                    help="ground and assemble, but leave the map unpublished: the "
                         "status is not touched and the publish invariant is not "
                         "asked. For the assembly runs inside a two-stage build "
                         "that must not be shown to anyone (#192)")
    args = ap.parse_args()

    prompt_version = env("PROMPT_VERSION", "v1")
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    gen = conn.execute("SELECT id, nodes FROM genealogies WHERE concept=%s AND prompt_version=%s",
                       (args.concept, prompt_version)).fetchone()
    if not gen:
        sys.exit(f'No genealogy for "{args.concept}" at prompt {prompt_version}.')
    gen_id, nodes = gen

    # ── one transaction, because a refusal has to be able to undo everything ──
    #
    # Issue #55. The connection is autocommit, and the whole-run refusal below
    # sits after the grounding loop, so the orphan DELETE and the quote re-sync
    # UPDATE had both committed by the time it printed "Nothing was written and
    # every stamp stands as it was." Both halves of that sentence were false.
    #
    # Worse than a wrong message: the re-sync rewrites source_quote/target_quote
    # and deliberately touches none of the eight stamp columns, because the loop
    # below was going to rewrite them all. When the refusal intervened, the edge
    # was left holding a NEW quote beside the OLD span, the OLD digest and the OLD
    # `verified = true`, and since the paper's digest had not moved either, the
    # page resolved it to VERIFIED. A tick standing behind a quote no check had
    # ever seen, produced by the refusal added to prevent exactly that.
    #
    # So every write this stage makes now happens inside one transaction that is
    # not committed until the refusal question is settled. sys.exit raises
    # SystemExit, the context manager rolls back on any exception, and the
    # sentence becomes true. Deciding the refusal earlier by probing the files
    # first was the alternative and is worse: the set of paths that matters is
    # only known after the sweep has removed the orphans, so the probe would
    # answer for a different set of edges than the one being published.
    # ── and the announcement follows the commit, never predicts it ────────────
    #
    # Issue #65. The first version of this transaction swallowed the JSON export
    # and the whole success summary, which had previously run after the writes
    # were durable. A COMMIT that fails — a dropped connection, a serialization
    # failure, a full server disk — then left the operator having read
    # "Genealogy complete: N edges" for a run that wrote nothing, and, worse, left
    # `data/genealogy_<concept>_<pv>.json` overwritten with a description of a map
    # the database does not hold. That file is the de-facto backup (incident 4),
    # so the failure destroyed the copy of the map as it was at the moment it was
    # most needed.
    #
    # The content is still produced inside the transaction, to a sibling temp
    # path, so a commit still cannot land without the export having been written
    # successfully. Only the atomic rename and the success prose happen after the
    # commit returns. A crash between the two leaves a committed map, the previous
    # backup intact and a `.tmp` file, which is the one residue worth having:
    # **a backup must never describe a state the database did not reach.**
    result = None
    try:
        with conn.transaction():
            result = _ground(conn, args, gen_id, nodes, prompt_version)
    except BaseException:
        if result is not None:
            result["tmp"].unlink(missing_ok=True)
        raise
    finally:
        conn.close()

    # Issue #67. The residue the ordering above cannot remove, only move: between
    # the COMMIT returning and this rename, the database has advanced and the
    # published export has not. The rename stays out here — putting it back inside
    # the transaction would recreate exactly the fault #65 fixed — so the window is
    # real, and all that was missing was a sentence. An uncaught OSError prints a
    # traceback with no success line, and the only reasonable reading of that is
    # "it failed, nothing happened", which is wrong in the direction that decides
    # whether to re-run and whether to trust the file on disk.
    try:
        os.replace(result["tmp"], result["out"])
    except OSError as exc:
        _report_export_stranded(result, exc)
    _report(result)


def _ground(conn, args, gen_id: int, nodes, prompt_version: str) -> dict:
    """Everything this stage writes, inside the caller's transaction.

    Returns what the caller needs to publish the export and narrate the run once
    the commit has actually landed. Nothing in here prints a success line and
    nothing in here puts a file where a reader will find it.
    """
    sweep_orphan_edges(conn, gen_id, nodes)

    # An edge's quotes ARE the two papers' Stage B definition quotes (decision 6):
    # only text we extracted can pass our own grounding check. Stage D copies them
    # onto the edge when it classifies, and a copy can go stale. Re-extracting a
    # corpus and refreshing its definitions did exactly that: the definitions were
    # correct, the edges still held the quotes taken from the text before the fix,
    # and grounding them against the new text failed 77 edges that had nothing
    # wrong with them.
    #
    # So the copy is re-derived here, every run, before anything is judged. A
    # value that is defined as a copy of another value should never be older than
    # what it copies. Empty definitions are left alone: a paper that no longer
    # defines the concept keeps its old quote and fails honestly, rather than
    # being blanked into a pass.
    synced = conn.execute("""
        UPDATE edges e
        SET source_quote = ds.verbatim_quote, target_quote = dt.verbatim_quote
        FROM definitions ds, definitions dt
        WHERE e.genealogy_id = %(gid)s
          AND ds.paper_id = e.source_paper_id
          AND ds.concept = %(c)s AND ds.prompt_version = %(pv)s AND ds.verbatim_quote <> ''
          AND dt.paper_id = e.target_paper_id
          AND dt.concept = %(c)s AND dt.prompt_version = %(pv)s AND dt.verbatim_quote <> ''
          AND (e.source_quote IS DISTINCT FROM ds.verbatim_quote
               OR e.target_quote IS DISTINCT FROM dt.verbatim_quote)
    """, {"gid": gen_id, "c": args.concept, "pv": prompt_version}).rowcount
    if synced:
        print(f"  re-synced {synced} edge quote pair(s) from their definitions "
              f"(the definition is the source of truth; the edge holds a copy)\n")

    edges = conn.execute("""
        SELECT e.id, e.source_node, e.target_node, e.edge_type, e.confidence,
               sp.arxiv_id, tp.arxiv_id, e.source_quote, e.target_quote,
               sp.extracted_text_path, tp.extracted_text_path,
               sp.extracted_text_digest, tp.extracted_text_digest,
               sp.extractor_version, tp.extractor_version
        FROM edges e
        JOIN papers sp ON sp.id = e.source_paper_id
        JOIN papers tp ON tp.id = e.target_paper_id
        WHERE e.genealogy_id = %s
    """, (gen_id,)).fetchall()

    text_cache: dict[str, tuple[str, str] | None] = {}
    reads_attempted: set[str] = set()
    reads_failed: set[str] = set()

    # Why a side could not produce a tick. Issue #58: these were all one value,
    # so a healthy DATA_DIR with no paths recorded and an unmounted one were the
    # same state, and an edge whose file read perfectly printed "text could not be
    # read" because its quote was blank. The refusal below is about the disk, so
    # it may only count the one that is about the disk.
    NO_PATH = "no extracted text recorded for this paper"
    UNREADABLE = "extracted text could not be read on this disk"
    EMPTY_QUOTE = "the stored quote contains no text of the paper"
    NOT_FOUND = "quote not found in the extracted text"

    def match(path: str, quote: str) -> tuple[bool, tuple[int, int] | None, str | None, str | None]:
        """(verdict, span, digest of the bytes it was checked against, why not).

        The digest is None when no bytes were read, and that is the point: since
        migration 015 the schema finally has somewhere to put the difference
        between "we looked and it was not there" and "we could not look". A
        digest-less stamp renders stale, which claims nothing. Before 015 an
        unreadable file crashed this stage and a NULL path was written as a plain
        false, which is a failed verdict from a check that never ran — the thing
        decision 21 and the --reground missing-file branch both refuse to write.

        A file that read fine yields its digest even when the quote fails, empty
        or otherwise: bytes were read and the matcher was run, so the stamp
        honestly says "checked against these, found nothing" and renders inferred
        rather than stale. Only a genuine absence of bytes renders stale.

        Tolerating the per-file failure is also what makes the whole-run refusal
        below reachable: if the first missing file aborted the run, "every read
        failed" could never be observed, and incident 12 is what a total outage
        looks like when only the per-item path can see it.

        Reading and hashing once per path per run, because a paper with twenty
        edges is one file.
        """
        if not path:
            return False, None, None, NO_PATH
        if path not in text_cache:
            reads_attempted.add(path)
            try:
                text_cache[path] = read_grounding_text(path)
            except (OSError, UnicodeDecodeError) as exc:
                text_cache[path] = None
                reads_failed.add(path)
                print(f"  ⚠ could not read {path}: {exc}")
        loaded = text_cache[path]
        if loaded is None:
            return False, None, None, UNREADABLE
        text, digest = loaded
        if not quote:
            return False, None, digest, EMPTY_QUOTE
        span = grounded_span(text, quote)
        if span is None:
            # grounded_span refuses a quote that folds to nothing (issue #57), so
            # a quote of "<cit.>" arrives here rather than matching at (0, 0).
            # Distinguished from a real miss, because "we hold no words of the
            # paper" and "the paper does not contain these words" are different
            # findings and only one of them is about the paper.
            return False, None, digest, (EMPTY_QUOTE if not _fold(quote) else NOT_FOUND)
        return True, span, digest, None

    print(f'Grounding {len(edges)} edges for "{args.concept}" (prompt {prompt_version})…\n')
    assembled_edges = []
    verified_count = stale_count = 0
    checked = 0
    pending: list[tuple] = []
    for (eid, sn, tn, etype, conf, s_arxiv, t_arxiv,
         s_quote, t_quote, s_path, t_path,
         s_now, t_now, s_ever, t_ever) in edges:
        checked += 1
        s_ok, s_span, s_digest, s_why = match(s_path, s_quote)
        t_ok, t_span, t_digest, t_why = match(t_path, t_quote)
        verified = s_ok and t_ok
        verified_count += verified
        # Resolved here against the paper's own current digest, which is written
        # by extract_text and never by this stage, so the two can disagree and
        # the comparison can return false. This is the same resolution the app
        # performs at render time, so the JSON and the page agree by construction.
        state = edge_stamp_state(verified, s_digest, s_now, t_digest, t_now)
        stale_count += state == STAMP_STALE
        pending.append((eid, verified, s_span, s_digest, s_ever, t_span, t_digest, t_ever))

        mark = {"verified": "SOLID  ✓ verified", "inferred": "dotted ◌ inferred",
                "stale": "dotted ◌ stale   "}[state]
        # The true cause per side, not one word covering four states (issue #58).
        # A blank quote against a file that read perfectly used to print "text
        # could not be read", which sends an operator to look at a disk that is
        # fine.
        causes = [f"{side} {why}" for side, why in (("src", s_why), ("tgt", t_why)) if why]
        if state == STAMP_STALE and not causes:
            causes = ["checked against text the papers table no longer describes"]
        reason = ("  [" + "; ".join(causes) + "]") if causes else ""
        print(f"  {mark}  {etype.upper():<9} {s_arxiv} -> {t_arxiv}  conf {conf:.2f}{reason}")

        assembled_edges.append({
            "source_node": sn, "target_node": tn, "edge_type": etype,
            "confidence": conf, "verified": verified, "stamp": state,
            "source_paper": s_arxiv, "target_paper": t_arxiv,
            "source_quote": s_quote, "target_quote": t_quote,
        })

    # Incident 12, and the same refusal Stage B's --reground carries and the
    # orphan sweep above carries. The per-edge tolerance that makes one missing
    # file survivable is exactly what makes a total outage invisible: an unmounted
    # or empty DATA_DIR grounds nothing and would otherwise be published as a map
    # whose every edge went inferred. The boundary is zero, not a fraction — "every
    # read failed" is a state, not a calibration — and, like the sweep, it needs
    # more than one edge for "not one of them" to mean anything.
    #
    # It counts READS, not edges (issue #58). The first version counted paths it
    # had loaded, which never grew for an edge whose paper has no
    # extracted_text_path at all, so a small healthy map built from the ~12 papers
    # that have no text (issue #5) refused and blamed the mount. A map with
    # nothing recorded to read has not proved the disk is broken; it has proved
    # its papers have no text, which is a different finding and is not this
    # stage's to refuse over. Only an attempted read that failed is evidence about
    # the disk.
    if checked > 1 and reads_attempted and reads_failed == reads_attempted:
        sys.exit(
            f"\nRefusing to ground this map: {checked} edges were checked, "
            f"{len(reads_attempted)} extracted text file(s) were opened, and every "
            f"one of them failed to read.\n"
            f"  That is an unmounted or empty DATA_DIR, not a map that failed, and this\n"
            f"  stage cannot tell them apart. Nothing was written and every stamp stands\n"
            f"  as it was.\n"
            f"  Check the extracted text first: {data_dir()}")

    for (eid, verified, s_span, s_digest, s_ever,
         t_span, t_digest, t_ever) in pending:
        conn.execute("""
            UPDATE edges SET verified=%s,
                   source_quote_start=%s, source_quote_end=%s,
                   source_text_digest=%s, source_extractor_version=%s,
                   target_quote_start=%s, target_quote_end=%s,
                   target_text_digest=%s, target_extractor_version=%s
            WHERE id=%s
        """, (verified,
              s_span[0] if s_span else None, s_span[1] if s_span else None,
              s_digest, s_ever,
              t_span[0] if t_span else None, t_span[1] if t_span else None,
              t_digest, t_ever, eid))

    # The last question asked before the map is published, and the last chance to
    # answer no (issue #171). It reads the map this transaction is about to
    # commit, including the edges the sweep removed and the stamps the loop just
    # wrote.
    #
    # **Under --no-publish the gate does not run, because publishing is what it
    # gates** (#192). Two consequences worth stating, since "check anyway, it is
    # free" is the obvious alternative. Clause 6 compares the stored threads
    # against the map's papers, and Stage G runs AFTER this stage — so on the
    # intermediate assemblies of a re-trace the threads are the PREVIOUS build's
    # over the new concept-states, and asking there would refuse a build at step 9
    # of 24 over a state the build is about to repair anyway (#171's own residue,
    # which is why the design moved the publish to the end). And a gate whose
    # verdict changes nothing is a gate that teaches an operator to ignore it.
    # The invariant is asked at every moment it can still answer no, and at no
    # other: this stage's publish run at the end, and — since #233 — the two
    # restore scripts, each immediately before the swap they perform.
    if args.no_publish:
        print("  --no-publish: this map was assembled but NOT published. Its status is\n"
              "  untouched, the publish invariant was not asked, and no reader can see\n"
              "  it until a later run of this stage publishes it.\n")
        return _assemble(args, gen_id, nodes, prompt_version, assembled_edges,
                         edges, verified_count, stale_count, published=False)

    refuse_unless_publishable(conn, gen_id)

    # The swap itself is `publish_swap` below, because since #230 the two restore
    # scripts perform it too and a second copy of it is a second publication
    # rule. This stage still owns it: the caller supplies the transaction, and
    # everything about WHEN a map may be published stays here, in the invariant
    # this line follows — which is why the restore scripts import the pair. They
    # imported the swap alone for one commit and published past the gate (#233).
    publish_swap(conn, args.concept, gen_id)

    return _assemble(args, gen_id, nodes, prompt_version, assembled_edges,
                     edges, verified_count, stale_count, published=True)


def publish_swap(conn, concept: str, gen_id: int) -> list[int]:
    """Make `gen_id` the current map for `concept`. Returns the ids it demoted.

    The caller supplies the connection and the transaction: this is two
    statements that must land together, and it never commits on its own.

    Issue #226, the defect #207a exists to close. Migration 025 gave a map
    `is_current` and backfilled it true on the four published maps, and #208
    landed the readers — `listGenealogies` reads `genealogies_current`,
    `/g/<id>/current` resolves through it, a report draws its comparison set
    from it. But no code in this repository had ever WRITTEN the column. Stage E
    published with `SET status='complete'` alone, so the next map to complete
    would have published `complete` with `is_current = false`: reachable at its
    own address, and invisible to the concepts list for ever. Nothing would have
    errored. It had not happened yet only because no map had completed since
    025 deployed.

    Since #230 the two restore scripts call this too. A recovery that put a map
    back and left it invisible is a recovery that has not finished, and the way
    to make a map current is this swap and never a raw `is_current = true`:
    that write is the one migration 026 refuses on a row that was demoted once,
    and it is not the operator's job to remember which.
    """
    # **Demote before promote, and that order is not ours to choose.** The
    # partial unique index `genealogies_one_current_per_concept` (025) permits
    # one current row per concept, so promoting first raises before the demotion
    # could run. The database enforces the order; this comment only records that
    # we know why. Sequencing a destructive step before its replacement is what
    # this house forbids, so: the demotion destroys nothing. The old row keeps
    # its id, its nodes, its edges, its streams, its user_edits and its address
    # (#208) — one flag moves and one timestamp is written. And both statements
    # are inside the transaction this whole stage runs in, so if the promote
    # fails the demote reverts and the old map is still the live one, which is
    # the property that matters.
    #
    # **`AND id <> %(gid)s` keeps a re-publish from touching its own row.**
    # Without it, re-publishing a map that is already current demotes it, stamps
    # `superseded_at`, and promotes it back in the same transaction. Until #229
    # that ended as a live map its own record said was replaced, and deleting the
    # clause failed the publish on `genealogies_current_not_superseded`. Now that
    # the promote clears the column the two statements cancel, and deleting the
    # clause leaves the same final row — measured, both before and after. The
    # clause stays because a no-op should touch no rows, and because the demote
    # is the statement that would otherwise fire on the concept's live map on
    # every re-publish. The invariant's falsifier moved with the fix: delete the
    # clause AND the promote's `superseded_at = NULL` and the CHECK fires again.
    #
    # **The promote clears `superseded_at`, and that is not tidiness** (issue
    # #229). A row demoted by an earlier publish carries the timestamp for ever;
    # publishing it again — a rollback to the previous version, or re-grounding
    # an older map with `PROMPT_VERSION` pointing at it — would otherwise write
    # `is_current = true` beside a non-NULL `superseded_at`, which is the
    # contradiction 026 forbids. Without the clear it dies on that CHECK as a
    # psycopg traceback at the end of a fully paid grounding run; on a database
    # at 025 the same sequence succeeded silently and stamped the NEWER map
    # superseded. `superseded_at` answers "when was this replaced", so a row
    # that is live again has not been replaced and the column must say so.
    # Latent while a concept has one publishable row, routine from #207b on.
    #
    # This is #207a and only #207a. A rebuild of an existing map still dies
    # earlier, in Stage C, which upserts `status = 'running'` onto the live row
    # and violates 025's `genealogies_current_is_published` (#214). #207b is the
    # commit that inserts a new version row instead.
    demoted = conn.execute("""
        UPDATE genealogies SET is_current = false, superseded_at = now(), updated_at = now()
        WHERE concept = %(concept)s AND is_current AND id <> %(gid)s
        RETURNING id
    """, {"concept": concept, "gid": gen_id}).fetchall()
    conn.execute("""
        UPDATE genealogies SET status = 'complete', is_current = true,
               superseded_at = NULL, updated_at = now()
        WHERE id = %(gid)s
    """, {"gid": gen_id})
    return [r[0] for r in demoted]


def _assemble(args, gen_id: int, nodes, prompt_version: str, assembled_edges: list,
              edges: list, verified_count: int, stale_count: int,
              published: bool) -> dict:
    """The export and the counts, for both endings of the stage.

    Split out when `--no-publish` arrived (#192) rather than duplicated, because
    the export is the de-facto backup (incident 4) and an unpublished assembly
    that wrote a different file from a published one would make the backup say
    which branch ran rather than what the map holds. The only difference between
    the two endings is whether the status moved, and that is the caller's.
    """
    # Counted at the stamp, not at the boolean, and the three are disjoint. An
    # edge whose quotes both matched text the papers table no longer describes
    # is not displayable as verified, and a summary that folds it into the
    # verified count is the same overclaim as the page making it.
    shown_verified = sum(1 for e in assembled_edges if e["stamp"] == STAMP_VERIFIED)
    shown_inferred = sum(1 for e in assembled_edges if e["stamp"] == STAMP_INFERRED)

    genealogy = {
        "concept": args.concept, "prompt_version": prompt_version,
        "nodes": nodes, "edges": assembled_edges,
        # `verified` stays on every edge, so restore_genealogy.py and the exports
        # keep working; `stamp` is the resolved three-state value beside it.
        #
        # The three state counts are disjoint and sum to `edges` (issue #59). They
        # were the boolean, the boolean's complement and the stamp, so an edge
        # that matched text the papers table no longer describes was counted both
        # verified and stale and the three summed to more than the edge count.
        # This file is the CLI's deliverable and the de-facto backup (incident 4);
        # an agent reading `verified_edges` out of it was reading the overclaiming
        # number the console summary two lines below had already stopped printing.
        # The boolean keeps a count under a name that says what it is.
        "stats": {"nodes": len(nodes), "edges": len(assembled_edges),
                  "verified_edges": shown_verified,
                  "inferred_edges": shown_inferred,
                  "stale_edges": stale_count,
                  "both_quotes_matched_this_run": verified_count},
    }
    out = Path(args.json) if args.json else data_dir() / f"genealogy_{args.concept}_{prompt_version}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # A sibling of the real path, so the rename after the commit is atomic: on
    # every platform os.replace is only atomic within one filesystem.
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(genealogy, indent=2), encoding="utf-8")

    return {"out": out, "tmp": tmp, "nodes": len(nodes), "edges": len(edges),
            "verified": shown_verified, "inferred": shown_inferred,
            "stale": stale_count, "matched": verified_count,
            "published": published}


def _stamp_caveats(r: dict) -> list:
    """What the counts do not say on their own, for whichever report is talking.

    These qualify the run, not the branch it ended on, so both post-commit
    reports owe them (issue #76). Only the success report printed them, which
    left the more alarming outcome carrying the less complete account of the same
    numbers: identical data, and the stranded report said neither that some
    matched quotes cannot be shown as verified nor that a first run after
    migration 015 needs extract_text.py before anything will improve.
    """
    out = []
    if r["matched"] != r["verified"]:
        out.append(f"  ({r['matched']} edges have both quotes matching the text this run "
                   f"read; {r['matched'] - r['verified']} of them cannot be shown as "
                   f"verified because that text is not what papers.extracted_text_digest "
                   f"describes.)")
    if r["stale"]:
        out.append(f"  {r['stale']} of them render STALE rather than as either: their stamp "
                   f"names bytes\n  that are not the bytes papers.extracted_text_digest now "
                   f"describes, or no digest\n  was recorded at all. A stale stamp is not a "
                   f"failed check, it is an unrepeated one.")
        out.append("  If this is the first run after migration 015, run "
                   "extract_text.py (no --force) first:\n"
                   "  the papers have no current digest to compare against yet.")
    return out


def _report(r: dict) -> None:
    """The success narrative, after the commit has landed and the export is in
    place. Every sentence here is in the past tense about something that is now
    durable; a line printed before the commit is a prediction (issue #65, and
    issue #21 in `workbench.py` before it).

    The first sentence differs by branch and the counts do not (#192). "Genealogy
    complete" is a claim about publication rather than about assembly: an
    unpublished map is finished in every other sense and is visible to nobody,
    and this is the one line an operator reads to decide whether readers can see
    it."""
    verdict = ("Genealogy complete" if r.get("published", True)
               else "Genealogy assembled and NOT published")
    print(f"\n{verdict}: {r['nodes']} concept-states, {r['edges']} edges "
          f"({r['verified']} solid/verified, {r['inferred']} dotted/inferred, "
          f"{r['stale']} stale).")
    for caveat in _stamp_caveats(r):
        print(caveat)
    print(f"Assembled JSON -> {r['out']}")


def _report_export_stranded(r: dict, exc: OSError) -> None:
    """The other branch that can be reached after the commit (issue #67).

    Both halves have to be said, and they point opposite ways: the run's writes
    are durable, and the file an operator would look at to see them is not the
    file describing them. Names the counts so the state is checkable, both paths
    so the repair is one command, and exits non-zero because a run that did not
    publish is not a success.

    Written to stderr through `sys.exit(msg)`, which is how every other refusal
    in this file reports (issue #75). The first version used `print`, so a
    scripted run that logs stdout and alerts on stderr got exit 1 and not one
    word on the stream it watches: the exact silence this report was written to
    end, and worse than the traceback it replaced, which at least went to stderr.

    The re-run half of the repair advice is conditional for the same reason the
    caveat above it is (issue #76): "grounding costs nothing and writes the same
    result again" is a promise, and before extract_text.py has run after
    migration 015 the same result is the same stale stamps.

    Both file sentences are now questions asked of the filesystem rather than
    assertions (issue #77). They were written for the motivating case, a locked
    destination, where both files do exist, and were false in the other
    directions that reach here: a `.tmp` swept between the write and the rename
    raises FileNotFoundError, which is an OSError, and the report then described
    a complete and correct file that is not there; and on a first-ever export
    there is no previous export to be untouched. A failure report that reads
    fluently and falsely is worse than a traceback, because it is believed.
    """
    caveats = "".join(c + "\n" for c in _stamp_caveats(r))
    tmp_there, out_there = r["tmp"].exists(), r["out"].exists()
    if tmp_there:
        new_map = (f"  The new map is written, complete and correct, at:\n"
                   f"    {r['tmp']}\n")
    else:
        new_map = (f"  This run's export is GONE: it was written to\n"
                   f"    {r['tmp']}\n"
                   f"  and nothing is there now, so no file on disk describes the map "
                   f"the\n  database now holds.\n")
    if out_there:
        previous = (f"  The previous export is untouched at:\n"
                    f"    {r['out']}\n"
                    f"  That file describes the map as it was BEFORE this run. It is no "
                    f"longer\n  what the database holds, so do not read it as the current "
                    f"map.\n")
    else:
        previous = (f"  There is no previous export to fall back on: no file exists "
                    f"at\n    {r['out']}\n")

    # The rename is only on offer if there is something to rename. Where it is
    # not, the re-run is the whole repair rather than the easy half of it, so the
    # #76 caveat on re-running matters more here, not less.
    if tmp_there:
        repair = "  To finish the run, rename the first path above over the second.\n  "
    else:
        repair = "  There is nothing left to rename, so a re-run is the only repair.\n  "
    if r["stale"]:
        repair += ("Re-running this stage is free and writes the same result, but if the "
                   "stale\n  stamps above are the first run after migration 015 the same "
                   "result is the\n  same stale stamps: run extract_text.py first, as "
                   "above.")
    else:
        repair += "Re-running this stage costs nothing and writes the same result again."
    # Under --no-publish the map is emphatically not marked complete, and this
    # report is read by somebody deciding what state the system is in (#192).
    marked = ("this map is marked complete" if r.get("published", True)
              else "this map is NOT published: its status was deliberately left alone")
    sys.exit(
        f"\nThe grounding run was COMMITTED and the database has moved: "
        f"{r['nodes']} concept-states, {r['edges']} edges "
        f"({r['verified']} solid/verified, {r['inferred']} dotted/inferred, "
        f"{r['stale']} stale) are stored now, and {marked}.\n"
        f"{caveats}"
        f"Publishing the export then FAILED: {exc}\n"
        f"{new_map}"
        f"{previous}"
        f"{repair}")


if __name__ == "__main__":
    main()

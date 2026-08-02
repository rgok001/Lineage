"""Stage E: grounding check + graph assembly.

The mandatory grounding check (CLAUDE.md rule 2): every edge quote is string-
verified against the extracted source text. An edge is 'verified' (renders solid)
only if BOTH its quotes are found verbatim; otherwise it is 'inferred' (dotted).
Never displays an unverified quote as verified.

Then assembles the final genealogy JSON (nodes + verified edges) that the UI
renders, and marks the genealogy complete.

Usage:
  python pipeline/stage_e_ground.py "attention"
"""

import argparse
import json
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
    try:
        with conn.transaction():
            _ground(conn, args, gen_id, nodes, prompt_version)
    finally:
        conn.close()


def _ground(conn, args, gen_id: int, nodes, prompt_version: str) -> None:
    """Everything this stage writes, inside the caller's transaction.

    The JSON export is written from here too, after the refusal has passed but
    before the commit. That ordering is deliberate and it is the safe one: a file
    written for a run that then fails to commit is a file describing a map that
    did not change, which a re-run overwrites; a commit with no file is a map
    whose documented backup is missing (incident 4).
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

    conn.execute("UPDATE genealogies SET status='complete', updated_at=now() WHERE id=%s", (gen_id,))

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
    out.write_text(json.dumps(genealogy, indent=2), encoding="utf-8")

    print(f"\nGenealogy complete: {len(nodes)} concept-states, {len(edges)} edges "
          f"({shown_verified} solid/verified, {shown_inferred} dotted/inferred, "
          f"{stale_count} stale).")
    if verified_count != shown_verified:
        print(f"  ({verified_count} edges have both quotes matching the text this run "
              f"read; {verified_count - shown_verified} of them cannot be shown as "
              f"verified because that text is not what papers.extracted_text_digest "
              f"describes.)")
    if stale_count:
        print(f"  {stale_count} of them render STALE rather than as either: their stamp "
              f"names bytes\n  that are not the bytes papers.extracted_text_digest now "
              f"describes, or no digest\n  was recorded at all. A stale stamp is not a "
              f"failed check, it is an unrepeated one.")
        print("  If this is the first run after migration 015, run "
              "extract_text.py (no --force) first:\n"
              "  the papers have no current digest to compare against yet.")
    print(f"Assembled JSON -> {out}")


if __name__ == "__main__":
    main()

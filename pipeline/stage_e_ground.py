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
from common import quote_is_grounded, REPO_ROOT, data_dir, env  # noqa: E402


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
# A map with no concept-states at all makes every edge an orphan, and it needs
# its own statement rather than the one above with an empty array: an empty list
# parameter has no element type Postgres can infer, so `= ANY(%s)` raises rather
# than returning false for every row. This is the branch that walks straight
# into the refusal below, which is where a nodeless map should end up.
SELECT_ALL_EDGES = """
SELECT id, source_node, target_node FROM edges
WHERE genealogy_id = %(gid)s
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
    live = sorted({n["node_id"] for n in (nodes or []) if n.get("node_id")})
    total = conn.execute("SELECT count(*) FROM edges WHERE genealogy_id = %s",
                         (gen_id,)).fetchone()[0]
    if not total:
        return
    orphans = (conn.execute(SELECT_ORPHANS, {"gid": gen_id, "live": live}).fetchall()
               if live else
               conn.execute(SELECT_ALL_EDGES, {"gid": gen_id}).fetchall())
    if not orphans:
        print(f"  {total} edge(s), every one of them between concept-states this map has.\n")
        return

    # Every edge an orphan is not a finding, it is a broken run wearing a
    # result's clothes: an empty or replaced `nodes` blob produces exactly this,
    # and so does pointing this stage at the wrong map. The same shape as the
    # --reground guard (decision 19), and the boundary is likewise zero rather
    # than a fraction — "not one edge survives" is a degenerate case, not a
    # calibration. Refuse and change nothing; the map keeps its edges and its
    # last honest stamps.
    if len(orphans) == total:
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
               sp.extracted_text_path, tp.extracted_text_path
        FROM edges e
        JOIN papers sp ON sp.id = e.source_paper_id
        JOIN papers tp ON tp.id = e.target_paper_id
        WHERE e.genealogy_id = %s
    """, (gen_id,)).fetchall()

    text_cache: dict[str, str] = {}

    def contains(path: str, quote: str) -> bool:
        if not quote or not path:
            return False
        if path not in text_cache:
            text_cache[path] = (data_dir() / path).read_text(encoding="utf-8")
        return quote_is_grounded(text_cache[path], quote)

    print(f'Grounding {len(edges)} edges for "{args.concept}" (prompt {prompt_version})…\n')
    assembled_edges = []
    verified_count = 0
    for (eid, sn, tn, etype, conf, s_arxiv, t_arxiv,
         s_quote, t_quote, s_path, t_path) in edges:
        s_ok = contains(s_path, s_quote)
        t_ok = contains(t_path, t_quote)
        verified = s_ok and t_ok
        verified_count += verified
        conn.execute("UPDATE edges SET verified=%s WHERE id=%s", (verified, eid))

        stamp = "SOLID  ✓ verified" if verified else "dotted ◌ inferred"
        reason = "" if verified else f"  [{'src' if not s_ok else ''}{'+' if not s_ok and not t_ok else ''}{'tgt' if not t_ok else ''} quote not found]"
        print(f"  {stamp}  {etype.upper():<9} {s_arxiv} -> {t_arxiv}  conf {conf:.2f}{reason}")

        assembled_edges.append({
            "source_node": sn, "target_node": tn, "edge_type": etype,
            "confidence": conf, "verified": verified,
            "source_paper": s_arxiv, "target_paper": t_arxiv,
            "source_quote": s_quote, "target_quote": t_quote,
        })

    conn.execute("UPDATE genealogies SET status='complete', updated_at=now() WHERE id=%s", (gen_id,))
    conn.commit()

    genealogy = {
        "concept": args.concept, "prompt_version": prompt_version,
        "nodes": nodes, "edges": assembled_edges,
        "stats": {"nodes": len(nodes), "edges": len(assembled_edges),
                  "verified_edges": verified_count, "inferred_edges": len(edges) - verified_count},
    }
    out = Path(args.json) if args.json else data_dir() / f"genealogy_{args.concept}_{prompt_version}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(genealogy, indent=2), encoding="utf-8")
    conn.close()

    print(f"\nGenealogy complete: {len(nodes)} concept-states, {len(edges)} edges "
          f"({verified_count} solid/verified, {len(edges) - verified_count} dotted/inferred).")
    print(f"Assembled JSON -> {out}")


if __name__ == "__main__":
    main()

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
from common import REPO_ROOT, data_dir, env  # noqa: E402


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
        return quote in text_cache[path]

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

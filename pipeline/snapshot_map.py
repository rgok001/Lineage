"""Snapshot everything about one map, before doing something that rewrites it.

Stage E's export is the documented backup and it holds `nodes` and `edges`. It
does not hold `streams` (the threads and their claims), it does not hold
`user_edits` (the curatorial audit trail), and it does not hold the definitions
the edges quote. Incident 4 cost a curated map and was recovered from that
export with its audit trail lost, which is exactly the shape of the gap.

Repairing a corpus rewrites definitions in place and re-grounds every edge. On
an uncurated map that is cheap to redo. On a curated one the labels, merges and
splits are hand work that exists nowhere else, so this writes the whole row and
everything hanging off it to a timestamped file first.

Restoring is deliberately not automated. A restore is a decision, and the file is
plain JSON: the point of this script is that the decision is still available.

Usage:
  python pipeline/snapshot_map.py "embedding"
  python pipeline/snapshot_map.py "embedding" --out /data/before-repair.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, edit_actor, edit_op, edit_when, env  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Write a full backup of one map before repairing it")
    ap.add_argument("concept")
    ap.add_argument("--prompt-version", default=env("PROMPT_VERSION", "v1"))
    ap.add_argument("--out", help="path to write; defaults to DATA_DIR/snapshots/")
    args = ap.parse_args()

    with psycopg.connect(env("DATABASE_URL")) as conn:
        gen = conn.execute("""
            SELECT id, concept, prompt_version, status, spend_usd, nodes, user_edits,
                   streams, created_at, updated_at
            FROM genealogies WHERE concept = %s AND prompt_version = %s
        """, (args.concept, args.prompt_version)).fetchone()
        if not gen:
            sys.exit(f'No genealogy for "{args.concept}" at prompt {args.prompt_version}.')
        cols = ("id", "concept", "prompt_version", "status", "spend_usd", "nodes",
                "user_edits", "streams", "created_at", "updated_at")
        genealogy = dict(zip(cols, gen))
        gen_id = genealogy["id"]

        # The stamp columns (migration 015) travel with the verdict they qualify.
        # A snapshot that carried `verified` and left them behind would restore a
        # tick with nothing saying what it was checked against, which is the
        # state this whole migration exists to end.
        edges = conn.execute("""
            SELECT e.id, sp.arxiv_id, tp.arxiv_id, e.source_node, e.target_node,
                   e.edge_type, e.confidence, e.verified, e.source_quote, e.target_quote,
                   e.rationale, e.citation_context,
                   e.source_quote_start, e.source_quote_end,
                   e.source_text_digest, e.source_extractor_version,
                   e.target_quote_start, e.target_quote_end,
                   e.target_text_digest, e.target_extractor_version
            FROM edges e
            JOIN papers sp ON sp.id = e.source_paper_id
            JOIN papers tp ON tp.id = e.target_paper_id
            WHERE e.genealogy_id = %s ORDER BY e.id
        """, (gen_id,)).fetchall()
        edge_cols = ("id", "source_arxiv", "target_arxiv", "source_node", "target_node",
                     "edge_type", "confidence", "verified", "source_quote", "target_quote",
                     "rationale", "citation_context",
                     "source_quote_start", "source_quote_end",
                     "source_text_digest", "source_extractor_version",
                     "target_quote_start", "target_quote_end",
                     "target_text_digest", "target_extractor_version")

        # The definitions are what a repair overwrites in place, so the old quotes
        # and their verdicts only exist here once it has run.
        defs = conn.execute("""
            SELECT d.id, p.arxiv_id, d.defines_concept, d.definition, d.verbatim_quote,
                   d.quote_verified, d.section, d.novelty_claims, d.model,
                   d.attention, d.displacement,
                   d.quote_start, d.quote_end, d.quote_text_digest,
                   d.quote_extractor_version
            FROM definitions d JOIN papers p ON p.id = d.paper_id
            WHERE d.concept = %s AND d.prompt_version = %s ORDER BY d.id
        """, (args.concept, args.prompt_version)).fetchall()
        def_cols = ("id", "arxiv_id", "defines_concept", "definition", "verbatim_quote",
                    "quote_verified", "section", "novelty_claims", "model",
                    "attention", "displacement",
                    "quote_start", "quote_end", "quote_text_digest",
                    "quote_extractor_version")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else (
        data_dir() / "snapshots" / f"{args.concept.replace(' ', '_')}_{args.prompt_version}_{stamp}.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "snapshot_at": stamp,
        "genealogy": genealogy,
        "edges": [dict(zip(edge_cols, e)) for e in edges],
        "definitions": [dict(zip(def_cols, d)) for d in defs],
    }
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    verified = sum(1 for e in payload["edges"] if e["verified"])
    threads = len((genealogy["streams"] or {}).get("streams", [])) if genealogy["streams"] else 0
    claims = sum(len(p.get("claims") or [])
                 for s in ((genealogy["streams"] or {}).get("streams", []) if genealogy["streams"] else [])
                 for p in s.get("papers", []))
    print(f'Snapshot of "{args.concept}" (genealogy {gen_id}) -> {out}')
    print(f"  {len(genealogy['nodes'])} concept-states, {len(genealogy['user_edits'])} curatorial edits")
    # Printed, not just counted, and with the actor: this is the forensic tool
    # for "who changed this map", so the answer belongs where the owner is
    # already looking rather than inside the file. The basis is printed beside
    # the name because a signed-in login and a name a process asserted about
    # itself are not the same evidence, and an entry from before either key was
    # written says so instead of being guessed at.
    for e in genealogy["user_edits"] or []:
        name, basis = edit_actor(e)
        who = f"{name} ({basis})" if name else basis
        detail = e.get("detail", "") if isinstance(e, dict) else e
        print(f"    {edit_when(e)}  {edit_op(e)}  {who}  {detail}")
    print(f"  {len(payload['edges'])} edges ({verified} verified)")
    print(f"  {len(payload['definitions'])} definitions with their quotes and verdicts")
    print(f"  {threads} threads carrying {claims} claims")
    print(f"  {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

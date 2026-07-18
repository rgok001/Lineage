"""Restore a genealogy from a Stage-E JSON export.

The inverse of stage_e_ground.py's --json output: reads an exported genealogy
and re-inserts the genealogies row and its edges. Papers and definitions are
never touched by deletion, so a restore only has to rebuild the map itself.

This makes the exports real backups. Deleting a genealogy in the app is
permanent from the app's point of view; this is the recovery path.

Usage:
    python pipeline/restore_genealogy.py data/genealogy_attention_v2.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Restore a genealogy from an exported JSON.")
    ap.add_argument("json_path", help="a genealogy_<concept>_<pv>.json written by stage E")
    args = ap.parse_args()

    doc = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    concept, pv = doc["concept"], doc["prompt_version"]
    nodes, edges = doc["nodes"], doc["edges"]

    with psycopg.connect(env("DATABASE_URL")) as conn:
        existing = conn.execute(
            "SELECT id FROM genealogies WHERE concept = %s AND prompt_version = %s",
            (concept, pv)).fetchone()
        if existing:
            sys.exit(f'A genealogy for "{concept}" ({pv}) already exists (id {existing[0]}). '
                     "Delete it first if you mean to replace it.")

        # The restoration is itself a curatorial event — record it.
        audit = [{"op": "restore", "detail": {"from": Path(args.json_path).name},
                  "at": datetime.now(timezone.utc).isoformat(), "by": "cli"}]
        gid = conn.execute(
            """INSERT INTO genealogies (concept, prompt_version, status, nodes, user_edits)
               VALUES (%s, %s, 'complete', %s, %s) RETURNING id""",
            (concept, pv, Jsonb(nodes), Jsonb(audit))).fetchone()[0]

        paper_ids = dict(conn.execute(
            "SELECT arxiv_id, id FROM papers WHERE arxiv_id = ANY(%s)",
            ([e["source_paper"] for e in edges] + [e["target_paper"] for e in edges],)
        ).fetchall())

        for e in edges:
            sp, tp = paper_ids.get(e["source_paper"]), paper_ids.get(e["target_paper"])
            if sp is None or tp is None:
                sys.exit(f"Missing paper row for edge {e['source_paper']} -> {e['target_paper']} "
                         "— was the papers table pruned?")
            conn.execute(
                """INSERT INTO edges (genealogy_id, source_node, target_node, edge_type,
                                      source_paper_id, target_paper_id, source_quote,
                                      target_quote, confidence, verified)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (gid, e["source_node"], e["target_node"], e["edge_type"], sp, tp,
                 e["source_quote"], e["target_quote"], e["confidence"], e["verified"]))

        conn.commit()
        print(f'Restored "{concept}" ({pv}) as genealogy {gid}: '
              f"{len(nodes)} nodes, {len(edges)} edges.")


if __name__ == "__main__":
    main()

"""Put a map back the way snapshot_map.py found it.

Written on 2026-07-31, when an exhausted API balance left `embedding` with its
concept-states rewritten, all 305 edges deleted, and its uptake scores
overwritten with a uniform neutral value. The snapshot taken twenty minutes
earlier held all of it.

Restores, by id so nothing is orphaned:
  genealogies.nodes         the concept-states, with their labels and members
  genealogies.streams       the threads and their claims, if the snapshot had them
  genealogies.status        the map's publication state, and see below
  edges                     every edge with its type, confidence, quotes and basis
  definitions               quote, verdict, section, claims, model, and the two
                            magnitude scores

**`status` came back into scope with #173**, and without it this script could not
undo the thing it now exists to undo. Stage C's upsert sets `status = 'running'`
at the moment it overwrites a map, and since #168 the app serves only `complete`,
so a build that died after Stage C leaves the map invisible on the site. A
restore that put the concept-states and the edges back and left `running`
standing would return a map nobody can open, under a summary saying it had been
restored. The snapshot records what the status was; this writes that value back,
whatever it is, and prints it — a snapshot taken of a map that was already
`running` restores `running`, because the job is to put the row back rather than
to decide what it ought to say.

Deliberately NOT restored: `user_edits`. The audit trail is append-only by
design, and a restore is an event in a map's history rather than a way to
un-happen one. It is recorded as an edit instead.

What this cannot do is restore the extracted text. If the papers were
re-extracted after the snapshot, the quotes coming back here were matched
against text that no longer exists on disk, so their stored verdicts describe a
document that is gone. Run Stage E afterwards: it is free, it re-grounds every
quote against the text that is actually there, and the verified count it reports
will be the true one, even if it is lower.

Usage:
  python pipeline/restore_snapshot.py /data/snapshots/embedding_v2_...json --dry-run
  python pipeline/restore_snapshot.py /data/snapshots/embedding_v2_...json --confirm
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import actor, env  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Restore a map from a snapshot_map.py file")
    ap.add_argument("snapshot", help="path to the snapshot JSON")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    ap.add_argument("--confirm", action="store_true", help="actually write")
    args = ap.parse_args()
    if not args.dry_run and not args.confirm:
        sys.exit("Refusing to write without --confirm. Use --dry-run first.")

    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    g = snap["genealogy"]
    gen_id, concept, pv = g["id"], g["concept"], g["prompt_version"]

    with psycopg.connect(env("DATABASE_URL")) as conn:
        live = conn.execute("SELECT id, status, nodes FROM genealogies WHERE id = %s",
                            (gen_id,)).fetchone()
        if not live:
            sys.exit(f"Genealogy {gen_id} no longer exists. This script restores content "
                     f"into an existing row; use restore_genealogy.py to recreate one.")
        now_status, now_nodes = live[1], len(live[2])
        now_edges = conn.execute("SELECT count(*) FROM edges WHERE genealogy_id = %s",
                                 (gen_id,)).fetchone()[0]

        print(f'Restoring "{concept}" (genealogy {gen_id}, prompt {pv}) from {snap["snapshot_at"]}')
        print(f"  concept-states: {now_nodes} now -> {len(g['nodes'])} from the snapshot")
        print(f"  edges:          {now_edges} now -> {len(snap['edges'])} from the snapshot")
        print(f"  definitions:    {len(snap['definitions'])} rows to rewrite in place")
        print(f"  status:         {now_status} now -> {g['status']} from the snapshot")
        if args.dry_run:
            print("\n[dry-run] nothing written.")
            return

        # Paper ids by arxiv_id: the snapshot stores arxiv ids because they are
        # stable, while a papers row id is not something a backup should trust.
        pids = {r[0]: r[1] for r in conn.execute("SELECT arxiv_id, id FROM papers").fetchall()}

        conn.execute("UPDATE genealogies SET nodes = %s, streams = %s, status = %s, "
                     "updated_at = now() WHERE id = %s",
                     (json.dumps(g["nodes"]), json.dumps(g["streams"]) if g["streams"] else None,
                      g["status"], gen_id))

        conn.execute("DELETE FROM edges WHERE genealogy_id = %s", (gen_id,))
        restored = skipped = pre_015 = 0
        for e in snap["edges"]:
            src, dst = pids.get(e["source_arxiv"]), pids.get(e["target_arxiv"])
            if not src or not dst:
                skipped += 1
                continue
            # The stamp columns come back with the verdict they qualify
            # (migration 015). `.get` rather than `[...]`: a snapshot taken before
            # 015 does not have them, and restoring None there leaves the stamp
            # rendering stale, which is safe and lossy rather than a claim. A
            # snapshot carrying a *stale* digest is safe too, because the
            # comparison is against the paper's current digest either way.
            conn.execute("""
                INSERT INTO edges (genealogy_id, source_node, target_node, edge_type,
                                   confidence, verified, source_paper_id, target_paper_id,
                                   source_quote, target_quote, rationale, citation_context,
                                   source_quote_start, source_quote_end,
                                   source_text_digest, source_extractor_version,
                                   target_quote_start, target_quote_end,
                                   target_text_digest, target_extractor_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s)
            """, (gen_id, e["source_node"], e["target_node"], e["edge_type"], e["confidence"],
                  e["verified"], src, dst, e["source_quote"], e["target_quote"],
                  e["rationale"], e["citation_context"],
                  e.get("source_quote_start"), e.get("source_quote_end"),
                  e.get("source_text_digest"), e.get("source_extractor_version"),
                  e.get("target_quote_start"), e.get("target_quote_end"),
                  e.get("target_text_digest"), e.get("target_extractor_version")))
            restored += 1
            if e.get("source_text_digest") is None or e.get("target_text_digest") is None:
                pre_015 += 1

        for d in snap["definitions"]:
            conn.execute("""
                UPDATE definitions SET defines_concept = %s, definition = %s,
                       verbatim_quote = %s, quote_verified = %s, section = %s,
                       novelty_claims = %s, model = %s, attention = %s, displacement = %s,
                       quote_start = %s, quote_end = %s, quote_text_digest = %s,
                       quote_extractor_version = %s
                WHERE id = %s
            """, (d["defines_concept"], d["definition"], d["verbatim_quote"], d["quote_verified"],
                  d["section"], json.dumps(d["novelty_claims"]), d["model"],
                  d["attention"], d["displacement"],
                  d.get("quote_start"), d.get("quote_end"), d.get("quote_text_digest"),
                  d.get("quote_extractor_version"), d["id"]))

        # The restore is itself an event in the map's history, not an erasure of
        # one. user_edits is append-only and is the one thing not overwritten —
        # appended with `||` in the database rather than read, extended and
        # written back, because the read-modify-write silently dropped any web
        # edit that landed in between.
        entry = [{"op": "restore", "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "detail": f"restored from snapshot {snap['snapshot_at']} "
                            f"({restored} edges, {len(g['nodes'])} concept-states)",
                  "by_asserted": actor()}]
        conn.execute("UPDATE genealogies SET user_edits = "
                     "COALESCE(user_edits, '[]'::jsonb) || %s WHERE id = %s",
                     (Jsonb(entry), gen_id))
        conn.commit()

    print(f"\n  {restored} edges restored" + (f", {skipped} skipped (paper gone)" if skipped else ""))
    print(f"  {len(snap['definitions'])} definitions rewritten, {len(g['nodes'])} concept-states")
    print(f"  status is {g['status']}" + ("" if g["status"] == "complete" else
          " — the site serves only 'complete', so this map is not visible to a reader"))
    print("\n  The quotes are back, and their verdicts are the ones the snapshot held.")
    if pre_015:
        print(f"  {pre_015} of the restored edges came from a snapshot taken before "
              f"migration 015 and\n  carry no stamp digest, so they render as not "
              f"re-checked until the re-ground below.")
    print("  If the papers were re-extracted since, those verdicts describe text that is")
    print("  no longer on disk. Run Stage E to re-ground them honestly (it costs nothing):")
    print(f'    python pipeline/stage_e_ground.py "{concept}"')


if __name__ == "__main__":
    main()

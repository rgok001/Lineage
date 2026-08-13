"""Restore a genealogy from a Stage-E JSON export.

The inverse of stage_e_ground.py's --json output: reads an exported genealogy
and re-inserts the genealogies row and its edges. Papers and definitions are
never touched by deletion, so a restore only has to rebuild the map itself.

It restores as a NEW version of the concept's map (#207b) and publishes it,
which is also the rollback path: restore an older export and the swap demotes
whatever was live. Nothing existing is deleted or written over.

This makes the exports real backups. Deleting a genealogy in the app is
permanent from the app's point of view; this is the recovery path.

Usage:
    python pipeline/restore_genealogy.py data/genealogy_attention_v1_v2.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import NEXT_VERSION, actor, current_row, env, lock_version_mint  # noqa: E402
# The publication rule lives in the stage that owns it, and a restore performs
# the same swap rather than its own version of it (#230) — behind the same gate,
# because the pair is the rule and half of it is not (#233).
from stage_e_ground import publish_swap, refuse_unless_publishable  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Restore a genealogy from an exported JSON.")
    ap.add_argument("json_path",
                    help="a genealogy_<concept>_<pv>_v<N>.json written by stage E")
    ap.add_argument("--no-publish", action="store_true",
                    help="restore the map without making it the current one for its "
                         "concept (it will be reachable at /g/<id> and absent from the "
                         "concepts list)")
    args = ap.parse_args()

    doc = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    concept, pv = doc["concept"], doc["prompt_version"]
    nodes, edges = doc["nodes"], doc["edges"]

    with psycopg.connect(env("DATABASE_URL")) as conn:
        # There was a refusal here: "a genealogy for this concept already exists,
        # delete it first if you mean to replace it." That was migration 007's
        # world, where a concept had exactly one row and restoring over it meant
        # destroying it — decision 12's destroy-before-replace, on the only copy,
        # in the recovery script. #207b removes both halves: this restores as a
        # NEW version beside whatever is there, and the publish swap below is
        # what moves readers onto it. Nothing is deleted to make room, so there
        # is nothing left to refuse.
        #
        # The version is minted per CONCEPT across prompt versions, and it is
        # literally the same expression Stage C uses: `common.NEXT_VERSION`, taken
        # under `lock_version_mint` (#241). It was a second copy of
        # `coalesce(max(version), 0) + 1` here, which is how two minters drift —
        # this one was not in #241's finding because nobody ran a restore beside a
        # build, and it would have re-issued a deleted version's number the day the
        # ledger shipped, since only the copy in Stage C would have read it.
        # Letting the column's DEFAULT of 1 stand would collide with the existing
        # v1 on `genealogies_concept_pv_version_key` (025) — a raw constraint error
        # at the end of a recovery, which is the worst moment to meet one.
        #
        # The lock is held to the `conn.commit()` below: this connection is not
        # autocommit, so the INSERT, the edges, the gate and the swap are all one
        # transaction, and a build minting at the same moment waits for it.
        #
        # The restoration is itself a curatorial event — record it. The actor
        # goes in `by_asserted`: this used to write {"by": "cli"} into the same
        # key that holds authenticated GitHub logins, so the audit trail
        # rendered "by cli" beside "by rgok001" with nothing to tell them apart.
        audit = [{"op": "restore", "detail": {"from": Path(args.json_path).name},
                  "at": datetime.now(timezone.utc).isoformat(),
                  "by_asserted": actor()}]
        lock_version_mint(conn, concept)
        gid, version = conn.execute(
            f"""INSERT INTO genealogies (concept, prompt_version, status, nodes,
                                         user_edits, version, is_current)
                VALUES (%(concept)s, %(pv)s, 'complete', %(nodes)s, %(audit)s,
                        {NEXT_VERSION},
                        false)
                RETURNING id, version""",
            {"concept": concept, "pv": pv, "nodes": Jsonb(nodes),
             "audit": Jsonb(audit)}).fetchone()

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

        # A restore that leaves the map invisible has not restored it (#230).
        # The INSERT above writes `status = 'complete'` and lets `is_current`
        # default false, which is `('complete', false, NULL)`: reachable at
        # /g/<id>, absent from `genealogies_current`, so absent from the concepts
        # list and from every report's comparison set, and a 404 at
        # /g/<id>/current. That is the state this script recovers FROM, and it
        # was producing it. The promotion is Stage E's own swap and never a raw
        # `is_current = true`, because a raw write is what migration 026 refuses
        # on a row that has been demoted once, and because the concept may
        # already have a live map that has to be demoted first.
        # **The gate travels with the swap** (#233). #230 moved `publish_swap`
        # out of Stage E and left `refuse_unless_publishable` behind, so this
        # path published a map Stage E's own rules refuse — #149's case reopened
        # on the route most likely to be carrying a damaged map, because a
        # restore is what you run when something is already wrong. It is asked
        # here rather than before the INSERTs because the invariant is a question
        # about the map being published, and until the rows above exist there is
        # no map to ask about; the view reads them uncommitted. Refusing exits
        # before `conn.commit()` below, so the row and its edges roll back and
        # the concept's live map is untouched.
        demoted = []
        if not args.no_publish:
            refuse_unless_publishable(conn, gid)
            demoted = publish_swap(conn, concept, gid)

        # Read before the commit and inside the same transaction as the swap, so
        # the sentence below describes the row rather than the flag that was
        # passed (#237): under --no-publish the live map is whatever it was, and
        # naming it is the difference between "yours is not live" and telling the
        # operator which version readers are still on.
        live = current_row(conn, concept, pv, "id, version")

        conn.commit()
        print(f'Restored "{concept}" ({pv}) as genealogy {gid}, version {version}: '
              f"{len(nodes)} nodes, {len(edges)} edges.")
        if args.no_publish:
            print("  --no-publish: it is NOT the current map for this concept, so it is "
                  f"reachable at /g/{gid} and absent from the concepts list.")
            print(f"  Readers are still on version {live[1]} (genealogy {live[0]})."
                  if live else
                  "  This concept has no live map at all at this prompt version.")
        elif demoted:
            print(f"  It is now the current map for \"{concept}\". The version that was "
                  f"live (genealogy {', '.join(str(d) for d in demoted)}) is marked "
                  f"superseded and keeps its id, its edges and its address.")
        else:
            print(f"  It is now the current map for \"{concept}\": on the concepts list, "
                  f"in every report's comparison set, and at /g/{gid}/current.")


if __name__ == "__main__":
    main()

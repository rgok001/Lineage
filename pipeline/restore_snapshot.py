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

A snapshot taken since #230 records whether the map was the live one, and this
obeys it. One taken before #230 cannot say, and rather than infer it this refuses
until told: `--publish` or `--no-publish` (#237).

Usage:
  python pipeline/restore_snapshot.py /data/snapshots/embedding_v2_...json --dry-run
  python pipeline/restore_snapshot.py /data/snapshots/embedding_v2_...json --confirm
  python pipeline/restore_snapshot.py /data/snapshots/old_...json --confirm --no-publish
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
# The publication rule lives in the stage that owns it, and a restore performs
# the same swap rather than its own version of it (#230) — behind the same gate,
# because the pair is the rule and half of it is not (#233).
from stage_e_ground import publish_swap, refuse_unless_publishable  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Restore a map from a snapshot_map.py file")
    ap.add_argument("snapshot", help="path to the snapshot JSON")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    ap.add_argument("--confirm", action="store_true", help="actually write")
    ap.add_argument("--no-publish", action="store_true",
                    help="restore the content without making the map current again")
    ap.add_argument("--publish", action="store_true",
                    help="make the restored map the current one for its concept, "
                         "demoting whatever is live. Required for a snapshot too old "
                         "to record which map was live")
    args = ap.parse_args()
    if not args.dry_run and not args.confirm:
        sys.exit("Refusing to write without --confirm. Use --dry-run first.")
    if args.publish and args.no_publish:
        sys.exit("--publish and --no-publish say opposite things. Give one of them.")

    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    g = snap["genealogy"]
    gen_id, concept, pv = g["id"], g["concept"], g["prompt_version"]

    # Whether this map should be the current one after the restore (#230).
    # A snapshot taken since #230 records `is_current` and is believed exactly;
    # `--publish` overrides it, which is the deliberate rollback #229 made
    # legitimate, and says so when it does. Currency also requires publication —
    # 025's `genealogies_current_is_published` — so a snapshot of a mid-build map
    # never promotes anything, and asking it to is an error rather than a
    # silently ignored flag.
    #
    # **A snapshot too old to have the field is not guessed at** (#237). This
    # inferred "yes if it is published", on the premise that every map in those
    # snapshots was the live one — true when 025's backfill ran and no concept
    # had a second version, false for a map restored before #230 or published in
    # the 025 window (both states the runbook names), and false for every concept
    # from #207b on. Measured on the premise's own terms: a fieldless snapshot of
    # v1 restored while v2 was live made v1 current and demoted v2. The inference
    # was disclosed both before and after the write, and disclosure is not
    # consent: the operator is the only one here who knows which map should be
    # live, so the refusal below asks them.
    snap_current = g.get("is_current")
    if args.publish and g["status"] != "complete":
        sys.exit(f"--publish was given, but this snapshot's status is '{g['status']}'. "
                 f"Only a\n'complete' map can be the current one (migration 025's "
                 f"genealogies_current_is_published),\nso there is nothing to publish "
                 f"here. Restore it, finish the build, then publish.")
    if snap_current is None and g["status"] == "complete" and not (args.publish
                                                                  or args.no_publish):
        sys.exit(
            f"\nRefusing to guess whether this map should be the live one.\n"
            f"  This snapshot was taken before #230 and does not record `is_current`, so\n"
            f"  it cannot say whether readers were seeing this map when it was taken. It\n"
            f"  used to be treated as the live one, which was true of every map in those\n"
            f"  snapshots when they were taken and is not true now: restoring a fieldless\n"
            f"  snapshot of a superseded version makes it current and demotes the version\n"
            f"  that is live.\n"
            f"  Say which you mean:\n"
            f"    --publish     make this the current map for \"{concept}\", superseding "
            f"whatever is live\n"
            f"    --no-publish  put the content back and leave the concepts list alone\n"
            f"  Nothing was written, and this refusal is the same in --dry-run: the\n"
            f"  question is about the snapshot, not about the database.")
    publish = (g["status"] == "complete"
               and (args.publish or bool(snap_current))
               and not args.no_publish)

    with psycopg.connect(env("DATABASE_URL")) as conn:
        live = conn.execute(
            "SELECT id, status, nodes, is_current FROM genealogies WHERE id = %s",
            (gen_id,)).fetchone()
        if not live:
            sys.exit(f"Genealogy {gen_id} no longer exists. This script restores content "
                     f"into an existing row; use restore_genealogy.py to recreate one.")
        now_status, now_nodes, now_current = live[1], len(live[2]), live[3]
        now_edges = conn.execute("SELECT count(*) FROM edges WHERE genealogy_id = %s",
                                 (gen_id,)).fetchone()[0]

        print(f'Restoring "{concept}" (genealogy {gen_id}, prompt {pv}) from {snap["snapshot_at"]}')
        print(f"  concept-states: {now_nodes} now -> {len(g['nodes'])} from the snapshot")
        print(f"  edges:          {now_edges} now -> {len(snap['edges'])} from the snapshot")
        print(f"  definitions:    {len(snap['definitions'])} rows to rewrite in place")
        print(f"  status:         {now_status} now -> {g['status']} from the snapshot")
        print(f"  on the site:    {'yes' if now_current else 'no'} now -> "
              + ("yes, and any other live version of this concept is superseded" if publish
                 else f"unchanged ({'yes' if now_current else 'no'})")
              + ("" if snap_current is not None else
                 f"  [this snapshot predates the column and cannot say; "
                 f"{'--publish' if args.publish else '--no-publish'} decides it]")
              + ("" if not (args.publish and snap_current is False) else
                 "  [--publish overrides the snapshot, which recorded this version as "
                 "not the live one]"))
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

        # Published last, as Stage E does: the map becomes the live one only once
        # everything it is made of is back (#230). Before this, a map restored to
        # `complete` stayed `is_current = false` — off the concepts list and a
        # 404 at /g/<id>/current — while this script printed that it was visible.
        #
        # **And gated first, because the gate is half of the rule** (#233). #230
        # took `publish_swap` from Stage E and left `refuse_unless_publishable`
        # there, so this script could publish a map Stage E would refuse: a
        # snapshot restored after a `--refresh` demoted one of its definitions
        # violates clause 1, and that is a routine event, not a contrived one.
        # Asked after the edges and definitions are written and before the
        # commit, so it judges the restored map rather than the damaged one, and
        # so a refusal rolls the whole restore back and leaves the live map alone.
        demoted = []
        if publish:
            refuse_unless_publishable(conn, gen_id)
            demoted = publish_swap(conn, concept, gen_id)

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
    if publish:
        print("  it is the current map for this concept again: on the concepts list, in "
              "every\n  report's comparison set, and at /g/<id>/current"
              + (f" (superseding genealogy {', '.join(str(d) for d in demoted)})"
                 if demoted else ""))
    elif g["status"] == "complete":
        # Said out loud rather than left to be discovered on the site — and read
        # from the row rather than deduced from the flags (#234). Not publishing
        # is not the same fact as not being current: `now_current` is the row's
        # own standing, read above, and this run changed it only by calling
        # `publish_swap`, which it did not. Two reachable inputs printed the
        # opposite of the truth here, and both are routine: `--no-publish` on the
        # live map, and a snapshot that honestly recorded `is_current = false`
        # restored onto a row that #229's rollback made current again. The
        # dry-run line four prints above ("on the site: yes now -> unchanged
        # (yes)") had the value right in the same run, which is the shape #228
        # removed from Stage D's aborts.
        why = ("--no-publish was given" if args.no_publish
               else "the snapshot recorded this version as not the live one")
        if now_current:
            print(f"  it is STILL the current map for this concept — {why}, so nothing "
                  f"was\n  promoted or demoted and the restored content is what a reader "
                  f"sees now, on\n  the concepts list and at /g/{gen_id}/current.")
        else:
            print(f"  it is NOT the current map for this concept, because {why}. A reader "
                  f"reaches it\n  at /g/{gen_id} and does not see it on the concepts list. "
                  f"Re-running Stage E on the\n  concept publishes it.")
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

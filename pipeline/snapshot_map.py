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
`restore_snapshot.py` is the decision's hands, and `docs/RUNBOOK.md` holds the
procedure.

**Since #173 the worker runs this as the first step of every build**, before
anything the build does can touch an existing map, so the export under `data/` is
a deliverable again rather than incident 4's improvised backup. Two flags exist
for that caller and for no other: `--allow-missing`, because a first build of a
term has no map to save and that is not a failure, and `--result-json`, because
the worker decides from files a stage wrote rather than from a stage's prose, and
because the path of the snapshot has to reach the requester's progress feed.

Usage:
  python pipeline/snapshot_map.py "embedding"
  python pipeline/snapshot_map.py "embedding" --out /data/before-repair.json
  python pipeline/snapshot_map.py "embedding" --allow-missing --result-json /tmp/s.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    current_row, data_dir, edit_actor, edit_op, edit_when, env, version_note)


def write_result(path: str | None, payload: dict) -> None:
    """The pointer file the worker reads to learn whether a snapshot exists.

    Its own failure is fatal on purpose. The worker treats an unreadable result
    as a refusal and destroys nothing, so a silent skip here would turn "we
    cannot say whether the map was saved" into "carry on" — which is the one
    reading this whole step exists to forbid.
    """
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Write a full backup of one map before repairing it")
    ap.add_argument("concept")
    ap.add_argument("--prompt-version", default=env("PROMPT_VERSION", "v1"))
    ap.add_argument("--out", help="path to write; defaults to DATA_DIR/snapshots/")
    ap.add_argument("--allow-missing", action="store_true",
                    help="a concept with no map yet is reported and exits 0 "
                         "(what the worker passes: a first build has nothing to save)")
    ap.add_argument("--result-json",
                    help="write {existed, path, counts} here for a caller that has to "
                         "decide on what happened rather than read this output")
    ap.add_argument("--genealogy-id", type=int, metavar="ID",
                    help="save this exact version instead of the live map")
    args = ap.parse_args()

    try:
        conn_ctx = psycopg.connect(env("DATABASE_URL"))
    except psycopg.Error as exc:
        # Named rather than left as a traceback: this runs before a rebuild
        # touches anything, so the operator's question is "what stopped it", and
        # the answer is one line rather than fifteen.
        sys.exit(f"Could not connect to take the snapshot: {type(exc).__name__}: {exc}")

    with conn_ctx as conn:
        # `is_current` travels with `status`, for the reason `status` does
        # (#173, and #230 for this column): a snapshot that records what the map
        # held and not whether anyone could see it cannot restore the map. It is
        # written even when false, so a restore can tell "this version was not
        # the live one" from "this snapshot predates the column".
        #
        # **The LIVE map** (#207b): this runs before a rebuild, and what a
        # rebuild puts at risk is the map readers can see. The new version does
        # not exist yet when this runs, and the previous versions are not at risk
        # because nothing writes to them again.
        gen = current_row(conn, args.concept, args.prompt_version,
                          """id, concept, prompt_version, status, spend_usd, nodes,
                             user_edits, streams, created_at, updated_at, is_current""",
                          genealogy_id=args.genealogy_id)
        if not gen:
            missing = (f'No live map for "{args.concept}" at prompt '
                       f"{args.prompt_version}.")
            if not args.allow_missing:
                sys.exit(missing)
            # Not a failure and not silence: the caller has to be able to tell
            # "there was nothing to save" from "the save did not happen", and
            # they are the same exit code.
            # "This is its first build" was true while a concept had one row;
            # with versions it is one of two causes, and the other — versions
            # exist and none of them is live — is worth telling apart (#207b).
            print(f"{missing} Nothing live to snapshot. "
                  f"{version_note(conn, args.concept, args.prompt_version)}")
            write_result(args.result_json,
                         {"existed": False, "path": None, "concept": args.concept,
                          "prompt_version": args.prompt_version})
            return
        cols = ("id", "concept", "prompt_version", "status", "spend_usd", "nodes",
                "user_edits", "streams", "created_at", "updated_at", "is_current")
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

    payload = {
        "snapshot_at": stamp,
        "genealogy": genealogy,
        "edges": [dict(zip(edge_cols, e)) for e in edges],
        "definitions": [dict(zip(def_cols, d)) for d in defs],
    }
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        # Exit non-zero with the path in the message. The worker's build stops
        # here, before its first destructive write, which is the whole point of
        # running this first; an operator's next move is to look at that path.
        sys.exit(f"Could not write the snapshot to {out}: {type(exc).__name__}: {exc}\n"
                 f"Nothing has been changed. The map is as it was.")

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
    try:
        write_result(args.result_json, {
            "existed": True, "path": str(out), "concept": args.concept,
            "prompt_version": args.prompt_version, "genealogy_id": gen_id,
            "status": genealogy["status"], "nodes": len(genealogy["nodes"]),
            "edges": len(payload["edges"]), "edges_verified": verified,
            "definitions": len(payload["definitions"]),
            "user_edits": len(genealogy["user_edits"] or []),
            "threads": threads, "bytes": out.stat().st_size,
        })
    except OSError as exc:
        sys.exit(f"The snapshot is written and safe at {out}, but the record of it could "
                 f"not be written to {args.result_json}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()

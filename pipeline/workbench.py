"""Workbench: curate a genealogy — merge, rename, split-out, delete, reclassify.

The product is a workbench, not an oracle (CLAUDE.md rule 3). Stages C and D
produce a *draft*: clustering deliberately over-splits (merging is safe, un-merging
a conflated node is not), and weak nodes survive. This is the tool that turns the
draft into a defensible map.

Every edit is appended to genealogies.user_edits, so the curated map always
carries the record of what a human changed and when. Edits mutate the stored
genealogy; re-run Stage E afterwards to re-ground and re-export the JSON.

Usage:
  python pipeline/workbench.py "attention" list
  python pipeline/workbench.py "attention" merge n6 --into n4
  python pipeline/workbench.py "attention" rename n4 "Self-attention as architecture"
  python pipeline/workbench.py "attention" delete-node n5
  python pipeline/workbench.py "attention" delete-edge 12
  python pipeline/workbench.py "attention" reclassify 12 narrows
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env  # noqa: E402

EDGE_TYPES = ("extends", "contests", "narrows", "renames", "merges", "migrates")


def load(conn, concept, pv):
    row = conn.execute(
        "SELECT id, nodes, user_edits FROM genealogies WHERE concept=%s AND prompt_version=%s",
        (concept, pv)).fetchone()
    if not row:
        sys.exit(f'No genealogy for "{concept}" at prompt {pv}. Run Stage C first.')
    return row


def record(conn, gen_id, edits, op, detail):
    edits = list(edits or [])
    edits.append({"op": op, "detail": detail,
                  "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    conn.execute("UPDATE genealogies SET user_edits=%s, updated_at=now() WHERE id=%s",
                 (psycopg.types.json.Json(edits), gen_id))


def save_nodes(conn, gen_id, nodes):
    conn.execute("UPDATE genealogies SET nodes=%s, updated_at=now() WHERE id=%s",
                 (psycopg.types.json.Json(nodes), gen_id))


def cmd_list(conn, gen_id, nodes, concept):
    print(f'Genealogy "{concept}" — {len(nodes)} concept-states\n')
    edges = conn.execute("""
        SELECT e.id, e.source_node, e.target_node, e.edge_type, e.confidence, e.verified,
               sp.arxiv_id, tp.arxiv_id
        FROM edges e JOIN papers sp ON sp.id=e.source_paper_id
                     JOIN papers tp ON tp.id=e.target_paper_id
        WHERE e.genealogy_id=%s ORDER BY e.id
    """, (gen_id,)).fetchall()
    deg = {}
    for _, s, t, *_ in edges:
        deg[s] = deg.get(s, 0) + 1
        deg[t] = deg.get(t, 0) + 1
    for n in sorted(nodes, key=lambda n: n["year_start"]):
        d = deg.get(n["node_id"], 0)
        flag = "  ← isolated (no edges)" if d == 0 else ""
        print(f"  {n['node_id']:<4} {n['year_start']}–{n['year_end']}  {n['label']}")
        print(f"       {len(n['members'])} paper(s), {d} edge(s){flag}")
        for m in n["members"]:
            print(f"         · {m['year']} {m['title'][:62]}")
    print(f"\n{len(edges)} edges:")
    for eid, s, t, et, conf, ver, sa, ta in edges:
        print(f"  [{eid}] {et:<9} {s} -> {t}   {sa} -> {ta}  "
              f"conf {conf:.2f}  {'verified' if ver else 'inferred'}")


def cmd_merge(conn, gen_id, nodes, src, dst):
    if src == dst:
        sys.exit("Cannot merge a node into itself.")
    s = next((n for n in nodes if n["node_id"] == src), None)
    d = next((n for n in nodes if n["node_id"] == dst), None)
    if not s or not d:
        sys.exit(f"Unknown node(s): {src if not s else ''} {dst if not d else ''}".strip())

    d["members"] = sorted(d["members"] + s["members"], key=lambda m: m["year"])
    d["definition_ids"] = sorted(set(d["definition_ids"] + s["definition_ids"]))
    years = [m["year"] for m in d["members"] if m.get("year")]
    d["year_start"], d["year_end"] = min(years), max(years)
    nodes = [n for n in nodes if n["node_id"] != src]

    # rewire edges, then drop any that became self-loops: once two states are one
    # state, a relationship between them is no longer a genealogy transition.
    conn.execute("UPDATE edges SET source_node=%s WHERE genealogy_id=%s AND source_node=%s",
                 (dst, gen_id, src))
    conn.execute("UPDATE edges SET target_node=%s WHERE genealogy_id=%s AND target_node=%s",
                 (dst, gen_id, src))
    dropped = conn.execute(
        "DELETE FROM edges WHERE genealogy_id=%s AND source_node=target_node RETURNING edge_type",
        (gen_id,)).fetchall()

    save_nodes(conn, gen_id, nodes)
    print(f"Merged {src} into {dst}: {dst} now has {len(d['members'])} papers "
          f"({d['year_start']}–{d['year_end']}).")
    if dropped:
        print(f"  Dropped {len(dropped)} edge(s) that became self-loops within {dst}: "
              f"{', '.join(e[0] for e in dropped)}")
        print("  (a relationship between two papers of the SAME concept-state is not a transition)")
    return nodes, {"merged": src, "into": dst, "self_loops_dropped": [e[0] for e in dropped]}


def cmd_rename(conn, gen_id, nodes, node_id, label):
    n = next((x for x in nodes if x["node_id"] == node_id), None)
    if not n:
        sys.exit(f"Unknown node {node_id}")
    old = n["label"]
    n["label"] = label
    save_nodes(conn, gen_id, nodes)
    print(f'Renamed {node_id}:\n  from "{old}"\n  to   "{label}"')
    return nodes, {"node": node_id, "from": old, "to": label}


def cmd_delete_node(conn, gen_id, nodes, node_id):
    n = next((x for x in nodes if x["node_id"] == node_id), None)
    if not n:
        sys.exit(f"Unknown node {node_id}")
    killed = conn.execute(
        "DELETE FROM edges WHERE genealogy_id=%s AND (source_node=%s OR target_node=%s) RETURNING id",
        (gen_id, node_id, node_id)).fetchall()
    nodes = [x for x in nodes if x["node_id"] != node_id]
    save_nodes(conn, gen_id, nodes)
    print(f'Deleted {node_id} ("{n["label"]}") and {len(killed)} attached edge(s).')
    return nodes, {"node": node_id, "label": n["label"], "edges_removed": len(killed)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Curate a genealogy (workbench).")
    ap.add_argument("concept")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    m = sub.add_parser("merge"); m.add_argument("node"); m.add_argument("--into", required=True)
    r = sub.add_parser("rename"); r.add_argument("node"); r.add_argument("label")
    dn = sub.add_parser("delete-node"); dn.add_argument("node")
    de = sub.add_parser("delete-edge"); de.add_argument("edge_id", type=int)
    rc = sub.add_parser("reclassify"); rc.add_argument("edge_id", type=int)
    rc.add_argument("edge_type", choices=EDGE_TYPES)
    args = ap.parse_args()

    pv = env("PROMPT_VERSION", "v1")
    conn = psycopg.connect(env("DATABASE_URL"))
    gen_id, nodes, edits = load(conn, args.concept, pv)

    if args.cmd == "list":
        cmd_list(conn, gen_id, nodes, args.concept)
        return

    if args.cmd == "merge":
        nodes, detail = cmd_merge(conn, gen_id, nodes, args.node, args.into)
    elif args.cmd == "rename":
        nodes, detail = cmd_rename(conn, gen_id, nodes, args.node, args.label)
    elif args.cmd == "delete-node":
        nodes, detail = cmd_delete_node(conn, gen_id, nodes, args.node)
    elif args.cmd == "delete-edge":
        row = conn.execute("DELETE FROM edges WHERE id=%s AND genealogy_id=%s RETURNING edge_type",
                           (args.edge_id, gen_id)).fetchone()
        if not row:
            sys.exit(f"No edge {args.edge_id} in this genealogy.")
        detail = {"edge_id": args.edge_id, "was": row[0]}
        print(f"Deleted edge {args.edge_id} ({row[0]}).")
    elif args.cmd == "reclassify":
        row = conn.execute("UPDATE edges SET edge_type=%s WHERE id=%s AND genealogy_id=%s "
                           "RETURNING edge_type", (args.edge_type, args.edge_id, gen_id)).fetchone()
        if not row:
            sys.exit(f"No edge {args.edge_id} in this genealogy.")
        detail = {"edge_id": args.edge_id, "to": args.edge_type}
        print(f"Reclassified edge {args.edge_id} -> {args.edge_type}.")

    record(conn, gen_id, edits, args.cmd, detail)
    conn.commit()
    conn.close()
    print("\nEdit recorded in genealogies.user_edits. "
          "Re-run Stage E to re-ground and re-export the JSON.")


if __name__ == "__main__":
    main()

"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireOwner } from "./authz";
import { sql } from "./db";
import { EDGE_TYPES, getGenealogy, recordEdit, saveNodes, type Node } from "./genealogy";

async function loadNodes(genealogyId: number): Promise<Node[]> {
  const g = await getGenealogy(genealogyId);
  if (!g) throw new Error(`No genealogy ${genealogyId}`);
  return g.nodes;
}

function refresh(genealogyId: number) {
  revalidatePath(`/g/${genealogyId}`);
  revalidatePath("/");
}

export async function renameNode(formData: FormData) {
  const who = await requireOwner();
  const genealogyId = Number(formData.get("genealogyId"));
  const nodeId = String(formData.get("nodeId"));
  const label = String(formData.get("label") ?? "").trim();
  if (!label) return;

  const nodes = await loadNodes(genealogyId);
  const n = nodes.find((x) => x.node_id === nodeId);
  if (!n) return;
  const from = n.label;
  n.label = label;

  await saveNodes(genealogyId, nodes);
  await recordEdit(genealogyId, "rename", { node: nodeId, from, to: label }, who.login);
  refresh(genealogyId);
}

/**
 * Merge `nodeId` into `intoId`: the two concept-states become one.
 *
 * Edges that become self-loops are dropped — once two states are a single state,
 * a relationship between them is no longer a genealogy transition. Same rule as
 * the CLI workbench; the dropped types are recorded so the edit is auditable.
 */
export async function mergeNode(formData: FormData) {
  const who = await requireOwner();
  const genealogyId = Number(formData.get("genealogyId"));
  const nodeId = String(formData.get("nodeId"));
  const intoId = String(formData.get("intoId") ?? "");
  if (!intoId || intoId === nodeId) return;

  const nodes = await loadNodes(genealogyId);
  const src = nodes.find((x) => x.node_id === nodeId);
  const dst = nodes.find((x) => x.node_id === intoId);
  if (!src || !dst) return;

  dst.members = [...dst.members, ...src.members].sort((a, b) => a.year - b.year);
  dst.definition_ids = Array.from(new Set([...dst.definition_ids, ...src.definition_ids])).sort();
  const years = dst.members.map((m) => m.year).filter(Boolean);
  dst.year_start = Math.min(...years);
  dst.year_end = Math.max(...years);

  await sql`UPDATE edges SET source_node = ${intoId}
            WHERE genealogy_id = ${genealogyId} AND source_node = ${nodeId}`;
  await sql`UPDATE edges SET target_node = ${intoId}
            WHERE genealogy_id = ${genealogyId} AND target_node = ${nodeId}`;
  const dropped = (await sql`
    DELETE FROM edges WHERE genealogy_id = ${genealogyId} AND source_node = target_node
    RETURNING edge_type
  `) as { edge_type: string }[];

  await saveNodes(genealogyId, nodes.filter((x) => x.node_id !== nodeId));
  await recordEdit(genealogyId, "merge", {
    merged: nodeId, into: intoId, self_loops_dropped: dropped.map((d) => d.edge_type),
  }, who.login);
  refresh(genealogyId);
}

export async function deleteNode(formData: FormData) {
  const who = await requireOwner();
  const genealogyId = Number(formData.get("genealogyId"));
  const nodeId = String(formData.get("nodeId"));

  const nodes = await loadNodes(genealogyId);
  const n = nodes.find((x) => x.node_id === nodeId);
  if (!n) return;

  const killed = (await sql`
    DELETE FROM edges
    WHERE genealogy_id = ${genealogyId} AND (source_node = ${nodeId} OR target_node = ${nodeId})
    RETURNING id
  `) as { id: number }[];

  await saveNodes(genealogyId, nodes.filter((x) => x.node_id !== nodeId));
  await recordEdit(genealogyId, "delete-node", {
    node: nodeId, label: n.label, edges_removed: killed.length,
  }, who.login);
  refresh(genealogyId);
}

/**
 * Delete an entire genealogy — the map, its edges (FK cascade), and nothing
 * else. Papers and cached definitions survive, so re-tracing the concept later
 * re-bills almost nothing; and since requestTrace refuses concepts that
 * already have a genealogy, deleting one deliberately re-opens it.
 *
 * Confirmation is server-side: the form asks the owner to type the concept
 * name, and THIS code checks it. A client-side confirm() would be bypassable
 * by anyone invoking the action endpoint directly.
 */
export async function deleteGenealogy(formData: FormData) {
  await requireOwner();
  const genealogyId = Number(formData.get("genealogyId"));
  const typed = String(formData.get("confirm") ?? "").trim().toLowerCase();

  const rows = (await sql`
    SELECT concept FROM genealogies WHERE id = ${genealogyId}
  `) as { concept: string }[];
  if (!rows.length || typed !== rows[0].concept.toLowerCase()) return;

  // Trace history outlives the genealogy it produced (it is the record of who
  // requested what and what it cost); null the link or the FK blocks the delete.
  await sql`UPDATE trace_requests SET genealogy_id = NULL WHERE genealogy_id = ${genealogyId}`;
  await sql`DELETE FROM genealogies WHERE id = ${genealogyId}`;

  revalidatePath("/");
  redirect("/");
}

export async function reclassifyEdge(formData: FormData) {
  const who = await requireOwner();
  const genealogyId = Number(formData.get("genealogyId"));
  const edgeId = Number(formData.get("edgeId"));
  const edgeType = String(formData.get("edgeType") ?? "");
  if (!(EDGE_TYPES as readonly string[]).includes(edgeType)) return;

  await sql`UPDATE edges SET edge_type = ${edgeType}
            WHERE id = ${edgeId} AND genealogy_id = ${genealogyId}`;
  await recordEdit(genealogyId, "reclassify", { edge_id: edgeId, to: edgeType }, who.login);
  refresh(genealogyId);
}

export async function deleteEdge(formData: FormData) {
  const who = await requireOwner();
  const genealogyId = Number(formData.get("genealogyId"));
  const edgeId = Number(formData.get("edgeId"));

  const rows = (await sql`
    DELETE FROM edges WHERE id = ${edgeId} AND genealogy_id = ${genealogyId}
    RETURNING edge_type
  `) as { edge_type: string }[];
  if (!rows.length) return;

  await recordEdit(genealogyId, "delete-edge", { edge_id: edgeId, was: rows[0].edge_type }, who.login);
  refresh(genealogyId);
}

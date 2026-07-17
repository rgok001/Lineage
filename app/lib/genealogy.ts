import { sql } from "./db";

export type Member = { arxiv_id: string; year: number; title: string };
export type Node = {
  node_id: string;
  label: string;
  year_start: number;
  year_end: number;
  members: Member[];
  definition_ids: number[];
  representative_arxiv_id?: string;
};
export type Edge = {
  id: number;
  source_node: string;
  target_node: string;
  edge_type: string;
  confidence: number;
  verified: boolean;
  source_paper: string;
  target_paper: string;
  source_quote: string;
  target_quote: string;
};
export type UserEdit = { op: string; detail: unknown; at: string };
export type Genealogy = {
  id: number;
  concept: string;
  prompt_version: string;
  status: string;
  updated_at: string;
  nodes: Node[];
  edges: Edge[];
  user_edits: UserEdit[];
};

export const EDGE_TYPES = [
  "extends",
  "contests",
  "narrows",
  "renames",
  "merges",
  "migrates",
] as const;

export const EDGE_MEANING: Record<string, string> = {
  extends: "builds on / generalises",
  contests: "disputes",
  narrows: "restricts to a special case",
  renames: "same idea, new name",
  merges: "fuses two ideas",
  migrates: "carries into a new field",
};

export async function listGenealogies() {
  return (await sql`
    SELECT g.id, g.concept, g.prompt_version, g.status, g.updated_at,
           jsonb_array_length(g.nodes)      AS node_count,
           jsonb_array_length(g.user_edits) AS edit_count,
           (SELECT count(*) FROM edges e WHERE e.genealogy_id = g.id)                    AS edge_count,
           (SELECT count(*) FROM edges e WHERE e.genealogy_id = g.id AND e.verified)     AS verified_count
    FROM genealogies g
    ORDER BY g.updated_at DESC
  `) as {
    id: number; concept: string; prompt_version: string; status: string;
    updated_at: string; node_count: number; edit_count: number;
    edge_count: number; verified_count: number;
  }[];
}

export async function getGenealogy(id: number): Promise<Genealogy | null> {
  const rows = (await sql`
    SELECT id, concept, prompt_version, status, updated_at, nodes, user_edits
    FROM genealogies WHERE id = ${id}
  `) as any[];
  if (!rows.length) return null;

  const edges = (await sql`
    SELECT e.id, e.source_node, e.target_node, e.edge_type, e.confidence, e.verified,
           sp.arxiv_id AS source_paper, tp.arxiv_id AS target_paper,
           e.source_quote, e.target_quote
    FROM edges e
    JOIN papers sp ON sp.id = e.source_paper_id
    JOIN papers tp ON tp.id = e.target_paper_id
    WHERE e.genealogy_id = ${id}
    ORDER BY e.id
  `) as Edge[];

  const g = rows[0];
  return {
    id: g.id,
    concept: g.concept,
    prompt_version: g.prompt_version,
    status: g.status,
    updated_at: g.updated_at,
    nodes: (g.nodes as Node[]).slice().sort((a, b) => a.year_start - b.year_start),
    user_edits: (g.user_edits ?? []) as UserEdit[],
    edges: edges.map((e) => ({ ...e, confidence: Number(e.confidence) })),
  };
}

/** Every workbench edit is appended here, so a curated map always carries the
 *  record of what a human changed — same contract as the CLI workbench. */
export async function recordEdit(genealogyId: number, op: string, detail: unknown) {
  const entry = JSON.stringify([{ op, detail, at: new Date().toISOString() }]);
  await sql`
    UPDATE genealogies
    SET user_edits = COALESCE(user_edits, '[]'::jsonb) || ${entry}::jsonb,
        updated_at = now()
    WHERE id = ${genealogyId}
  `;
}

export async function saveNodes(genealogyId: number, nodes: Node[]) {
  await sql`
    UPDATE genealogies SET nodes = ${JSON.stringify(nodes)}::jsonb, updated_at = now()
    WHERE id = ${genealogyId}
  `;
}

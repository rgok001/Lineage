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
  rationale: string | null;
  citation_context: string | null;
  source_novelty: string[] | null;
  target_novelty: string[] | null;
  source_section: string | null;
  target_section: string | null;
};
export type UserEdit = { op: string; detail: unknown; at: string; by?: string };
/** A paper ranked for the spine. attention = on-term weighted uptake (who built
 *  on it for this term); displacement = how far it moved the term's meaning.
 *  Both drive ordering only — never shown as numbers (see product guardrail). */
export type RankedPaper = {
  arxiv: string;
  year: number;
  title: string;
  node_id: string;
  attention: number | null;
  displacement: number | null;
  novelty: string[] | null;
};
export type Genealogy = {
  id: number;
  concept: string;
  prompt_version: string;
  status: string;
  updated_at: string;
  nodes: Node[];
  edges: Edge[];
  papers: RankedPaper[];
  user_edits: UserEdit[];
  has_river: boolean;
};

/* ── the influence map (the front door) ─────────────────────────── */

export type MapPaper = {
  arxiv: string; year: number; title: string;
  attention: number; displacement: number;
  turning: boolean;                 // see TURNING_QUANTILE
  contrib: string | null;           // first novelty claim, the one-liner
  stream_id: string; stream_name: string; color: string;
};

/**
 * A paper is a turning point if it sits in the top slice of its own corpus by
 * displacement. Relative, not absolute: displacement is a distance from the
 * centroid of earlier definitions, so its scale depends on how far a corpus
 * spreads. A fixed `>= 0.25` ringed 9% of embedding's papers and 44% of
 * attention's, which made the same legend mean two different things on two
 * pages (section 10, incident 9 is the same fault in the mover rule).
 */
export const TURNING_QUANTILE = 0.85; // the top 15% moved this term most

export function turningCutoff(values: number[]): number {
  const xs = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!xs.length) return Infinity;
  return xs[Math.min(xs.length - 1, Math.floor(TURNING_QUANTILE * xs.length))];
}
export type MapEdge = { from: string; to: string; type: string; verified: boolean };
export type InfluenceMapData = {
  concept: string;
  through_line: string;
  papers: MapPaper[];
  edges: MapEdge[];
  streams: { id: string; name: string; color: string; count: number }[];
  total_papers: number;
};

/** The pivotal papers and the typed links among them: top-N by on-term uptake
 *  plus the strongest movers (displacement, gated by uptake so outliers stay
 *  out). The magnitude scores select and size; they are never displayed. */
export async function getInfluenceMap(id: number): Promise<InfluenceMapData | null> {
  const riverData = await getRiver(id);
  if (!riverData) return null;
  const { concept, river } = riverData;

  const g = (await sql`SELECT concept, prompt_version FROM genealogies WHERE id = ${id}`) as
    { concept: string; prompt_version: string }[];
  if (!g.length) return null;

  const rows = (await sql`
    SELECT p.arxiv_id AS arxiv, p.year, p.title, d.attention, d.displacement, d.novelty_claims AS novelty
    FROM definitions d JOIN papers p ON p.id = d.paper_id
    WHERE d.concept = ${g[0].concept} AND d.prompt_version = ${g[0].prompt_version}
      AND d.defines_concept = true AND d.attention IS NOT NULL
  `) as { arxiv: string; year: number; title: string; attention: number; displacement: number | null; novelty: string[] | null }[];

  const streamOf = new Map<string, { id: string; name: string; color: string }>();
  for (const s of river.streams)
    for (const p of s.papers)
      if (!streamOf.has(p.arxiv)) streamOf.set(p.arxiv, { id: s.id, name: s.name, color: s.color });

  const byAtt = [...rows].sort((a, b) => Number(b.attention) - Number(a.attention));
  const picked = new Map<string, typeof rows[number]>();
  for (const r of byAtt.slice(0, 20)) picked.set(r.arxiv, r);

  // Movers are ranked, never thresholded. An `attention >= 1` gate used to stand
  // here and it silenced the very signal it was guarding: displacement exists to
  // catch papers the citation graph misses, so gating it behind a citation score
  // means a sparse corpus loses its turning points. On /g/13 exactly 20 papers
  // cleared that bar and all 20 were already picked, so no mover was ever added.
  // Same lesson as the Stage A cosine cutoff (decision 3): rank, do not threshold,
  // because an absolute cut on a density-dependent score travels badly.
  const byDisp = (a: typeof rows[number], b: typeof rows[number]) =>
    Number(b.displacement) - Number(a.displacement);
  const candidates = rows.filter((r) => r.displacement !== null && !picked.has(r.arxiv));
  const withUptake = candidates.filter((r) => Number(r.attention) > 0).sort(byDisp);
  const without = candidates.filter((r) => !(Number(r.attention) > 0)).sort(byDisp);
  for (const r of [...withUptake, ...without].slice(0, 8)) picked.set(r.arxiv, r);

  // Every thread gets at least its strongest paper. The channels are drawn from
  // what the map selected, so a thread with nothing above the cut vanished from
  // the map while still being listed below it, which reads as a bug to anyone
  // who counts.
  for (const s of river.streams) {
    const members = s.papers.map((p) => p.arxiv);
    if (members.some((a) => picked.has(a))) continue;
    const best = rows
      .filter((r) => members.includes(r.arxiv))
      .sort((a, b) => Number(b.attention) - Number(a.attention) ||
                      Number(b.displacement ?? 0) - Number(a.displacement ?? 0))[0];
    if (best) picked.set(best.arxiv, best);
  }

  const arxivs = [...picked.keys()];
  const rawEdges = (await sql`
    SELECT sp.arxiv_id AS from, tp.arxiv_id AS to, e.edge_type AS type, e.verified,
           sp.year AS from_year, tp.year AS to_year
    FROM edges e JOIN papers sp ON sp.id = e.source_paper_id
                 JOIN papers tp ON tp.id = e.target_paper_id
    WHERE e.genealogy_id = ${id} AND sp.arxiv_id = ANY(${arxivs}) AND tp.arxiv_id = ANY(${arxivs})
  `) as (MapEdge & { from_year: number; to_year: number })[];

  // An edge means "the newer paper did X to the older one's concept", so a link
  // pointing backwards in time is a data error: arXiv revisions let two papers
  // cite each other, and the stored year is the v1 date. Drop the reverse leg
  // rather than draw a lineage the data cannot support.
  const edges: MapEdge[] = rawEdges
    .filter((e) => e.to_year >= e.from_year)
    .map(({ from, to, type, verified }) => ({ from, to, type, verified }));

  // Judged against the whole scored corpus, not against the handful that reached
  // the map, so being a turning point is a property of the paper rather than of
  // who else got drawn.
  const cutoff = turningCutoff(rows.map((r) => Number(r.displacement)).filter((v) => v > 0));

  const papers: MapPaper[] = arxivs.map((a) => {
    const r = picked.get(a)!;
    const st = streamOf.get(a) ?? { id: "other", name: "Other", color: "#7f8c94" };
    return {
      arxiv: a, year: r.year, title: r.title,
      attention: Number(r.attention), displacement: Number(r.displacement ?? 0),
      turning: Number(r.displacement ?? 0) >= cutoff,
      contrib: r.novelty?.find((c) => c && c.trim()) ?? null,
      stream_id: st.id, stream_name: st.name, color: st.color,
    };
  });

  return {
    concept,
    through_line: river.through_line,
    papers,
    edges,
    streams: river.streams.map((s) => ({ id: s.id, name: s.name, color: s.color, count: s.papers.length })),
    total_papers: rows.length,
  };
}

/**
 * Our LaTeX extractor leaves `<cit.>` where the paper had a \cite{...}, and
 * `<ref>` for a cross-reference. They are genuinely in the text the quote was
 * string-matched against, so the verification claim is untouched, but they are
 * our machinery showing in public and they travel into a reader's draft. Shown
 * as an elision, which is what a scholar already writes for a citation dropped
 * from a quotation. Display only: the stored span stays byte-identical to the
 * one Stage E matched.
 */
export const readableQuote = (s: string) =>
  s.replace(/\s*<(?:cit\.?|ref)>/g, " […]").replace(/(\s*\[…\])+/g, " […]").trim();

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
           jsonb_array_length(g.user_edits) AS edit_count,
           CASE WHEN g.streams IS NOT NULL
                THEN jsonb_array_length(g.streams->'streams') END                        AS stream_count,
           (SELECT count(*) FROM definitions d
             WHERE d.concept = g.concept AND d.prompt_version = g.prompt_version
               AND d.defines_concept = true)                                             AS paper_count,
           (SELECT count(*) FROM edges e WHERE e.genealogy_id = g.id)                    AS edge_count,
           (SELECT count(*) FROM edges e WHERE e.genealogy_id = g.id AND e.verified)     AS verified_count
    FROM genealogies g
    ORDER BY g.updated_at DESC
  `) as {
    id: number; concept: string; prompt_version: string; status: string;
    updated_at: string; edit_count: number; stream_count: number | null;
    paper_count: number; edge_count: number; verified_count: number;
  }[];
}

export type RiverPaper = { arxiv: string; year: number; title: string; move: string; prose: string; quote: string };
export type RiverStream = {
  id: string; name: string; tagline: string; arc: string; color: string;
  origin_year: number | null; papers: RiverPaper[];
};
export type RiverCross = { from: string; to: string; year: number | null; label: string };
export type River = { through_line: string; streams: RiverStream[]; cross_currents: RiverCross[] };

/** The generated river for a map: conceptual streams + per-stream grounded dive
 *  accounts. Read-only render artifact (migration 012); null until the streams
 *  job has run for this genealogy. */
export async function getRiver(id: number): Promise<{ concept: string; river: River } | null> {
  const rows = (await sql`SELECT concept, streams FROM genealogies WHERE id = ${id}`) as
    { concept: string; streams: River | null }[];
  if (!rows.length || !rows[0].streams) return null;
  return { concept: rows[0].concept, river: rows[0].streams };
}

export async function getGenealogy(id: number): Promise<Genealogy | null> {
  const rows = (await sql`
    SELECT id, concept, prompt_version, status, updated_at, nodes, user_edits,
           (streams IS NOT NULL) AS has_river
    FROM genealogies WHERE id = ${id}
  `) as any[];
  if (!rows.length) return null;
  const g = rows[0];

  const edges = (await sql`
    SELECT e.id, e.source_node, e.target_node, e.edge_type, e.confidence, e.verified,
           sp.arxiv_id AS source_paper, tp.arxiv_id AS target_paper,
           e.source_quote, e.target_quote, e.rationale, e.citation_context,
           ds.novelty_claims AS source_novelty, dt.novelty_claims AS target_novelty,
           ds.section AS source_section, dt.section AS target_section
    FROM edges e
    JOIN papers sp ON sp.id = e.source_paper_id
    JOIN papers tp ON tp.id = e.target_paper_id
    LEFT JOIN definitions ds ON ds.paper_id = e.source_paper_id
      AND ds.concept = ${g.concept} AND ds.prompt_version = ${g.prompt_version} AND ds.defines_concept = true
    LEFT JOIN definitions dt ON dt.paper_id = e.target_paper_id
      AND dt.concept = ${g.concept} AND dt.prompt_version = ${g.prompt_version} AND dt.defines_concept = true
    WHERE e.genealogy_id = ${id}
    ORDER BY e.id
  `) as Edge[];

  const paperRows = (await sql`
    SELECT p.arxiv_id AS arxiv, p.year, p.title, d.attention, d.displacement, d.novelty_claims AS novelty
    FROM definitions d JOIN papers p ON p.id = d.paper_id
    WHERE d.concept = ${g.concept} AND d.prompt_version = ${g.prompt_version} AND d.defines_concept = true
    ORDER BY d.attention DESC NULLS LAST
  `) as Omit<RankedPaper, "node_id">[];

  const nodeOf = new Map<string, string>();
  for (const n of g.nodes as Node[]) for (const m of n.members) nodeOf.set(m.arxiv_id, n.node_id);

  return {
    id: g.id,
    concept: g.concept,
    prompt_version: g.prompt_version,
    status: g.status,
    updated_at: g.updated_at,
    nodes: (g.nodes as Node[]).slice().sort((a, b) => a.year_start - b.year_start),
    user_edits: (g.user_edits ?? []) as UserEdit[],
    has_river: Boolean(g.has_river),
    edges: edges.map((e) => ({ ...e, confidence: Number(e.confidence) })),
    papers: paperRows.map((p) => ({
      ...p,
      attention: p.attention === null ? null : Number(p.attention),
      displacement: p.displacement === null ? null : Number(p.displacement),
      node_id: nodeOf.get(p.arxiv) ?? "",
    })),
  };
}

/**
 * Partition a genealogy's meanings into connected families.
 *
 * A polysemous term ("kernel": operating systems, SVMs, GPUs) produces
 * unrelated lineages that share nothing but the word — no citation ever
 * crosses between them, so they form disjoint components in the edge graph.
 * Rendering them interleaved in one timeline silently implies one story.
 * This computes the truth so the page can disclose it: families (components
 * with at least one edge, largest first) and unconnected singletons.
 */
export function computeFamilies(nodes: Node[], edges: Edge[]) {
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    let root = x;
    while (parent.get(root) !== root) root = parent.get(root)!;
    let cur = x;
    while (parent.get(cur) !== cur) {
      const next = parent.get(cur)!;
      parent.set(cur, root);
      cur = next;
    }
    return root;
  };
  for (const n of nodes) parent.set(n.node_id, n.node_id);
  for (const e of edges) {
    if (!parent.has(e.source_node) || !parent.has(e.target_node)) continue;
    parent.set(find(e.source_node), find(e.target_node));
  }

  const groups = new Map<string, Node[]>();
  for (const n of nodes) {
    const root = find(n.node_id);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root)!.push(n); // nodes arrive year-sorted; order is preserved
  }

  const families: Node[][] = [];
  const unconnected: Node[] = [];
  for (const g of groups.values()) {
    if (g.length === 1) unconnected.push(g[0]);
    else families.push(g);
  }
  families.sort((a, b) => b.length - a.length || a[0].year_start - b[0].year_start);
  unconnected.sort((a, b) => a.year_start - b.year_start);
  return { families, unconnected };
}

/** Every workbench edit is appended here, so a curated map always carries the
 *  record of what a human changed, when, and who — same contract as the CLI
 *  workbench (which has no session, hence `by` is optional). */
export async function recordEdit(genealogyId: number, op: string, detail: unknown, by?: string) {
  const entry = JSON.stringify([{ op, detail, at: new Date().toISOString(), ...(by ? { by } : {}) }]);
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

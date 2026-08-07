import type { Viewer } from "./authz";
import { sql } from "./db";
import { edgeStampOf, type StampState } from "./stamp";

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
  /** Resolved server-side from the two stamp digests and the two papers' current
   *  digests (migration 015). `verified` stays beside it because it is still the
   *  stored verdict; `stamp` is what may be shown, and it is never more than
   *  `verified` claims. */
  stamp: StampState;
  /** Nullable because the join that fetches them is a LEFT JOIN (issue #79):
   *  `edges.source_paper_id` and `target_paper_id` are nullable and may name a
   *  row that is gone, and such an edge is shown rather than dropped. Every
   *  reader of these must be ready for null and must say "we do not have this
   *  paper" rather than inventing one (CLAUDE.md rule 4). */
  source_paper: string | null;
  target_paper: string | null;
  source_quote: string;
  target_quote: string;
  rationale: string | null;
  citation_context: string | null;
  source_novelty: string[] | null;
  target_novelty: string[] | null;
  source_section: string | null;
  target_section: string | null;
};
/** `by` is a GitHub login this app got from a session, so a third party
 *  authenticated it. `by_asserted` is a name a process asserted about itself
 *  (the CLI scripts, which authenticate nobody). An entry carries one, or the
 *  other, or — if it was written before either key existed — neither. Never
 *  both, and nothing but a session may ever write `by`. */
export type UserEdit = {
  op: string; detail: unknown; at: string;
  by?: string; by_asserted?: string;
};

const ACTOR_MAX = 64;

/**
 * Make a stored name safe to render, in markdown as well as in React.
 *
 * `by_asserted` can hold anything `LINEAGE_ACTOR` held, and an interior newline
 * escapes the `> ` blockquote in the export and lands as body prose in a
 * researcher's paper. React escapes, markdown does not, so the folding happens
 * on the way out and not only on the way in — that covers rows already stored
 * and rows a future writer stores. Parentheses and the middle dot go too:
 * those are the delimiters this product uses to print the *basis*, and a label
 * must not be able to spell a trust level it does not have. That is a rule
 * about our own syntax rather than a blocklist of phrases, which is the
 * distinction incidents 10 and 11 were about.
 */
function tidyActorName(raw: string): string {
  return raw
    .replace(/[\u0000-\u001f\u007f-\u009f\uFEFF]/g, " ")
    .replace(/[()·]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, ACTOR_MAX);
}

/** `user_edits` is JSONB, so a field the types call a string can hold a number,
 *  a boolean, an array or null. Anything that is not a usable string is absent:
 *  junk degrades to "actor not recorded" and can never be upgraded into an
 *  authenticated claim. It must not throw either — `app/` has no error.tsx, so
 *  one TypeError inside a server component turns the evidence page and the
 *  export into a 500 for that map until the row is edited by hand. */
const actorName = (v: unknown): string => (typeof v === "string" ? tidyActorName(v) : "");

/**
 * How one audit entry names its actor, in one place because the evidence page
 * and the export both say it and must say the same thing. Its twin is
 * `edit_actor` in pipeline/common.py and the two must agree on every input.
 *
 * The absence of an actor is reported as an absence. The page used to print
 * "(cli)" there, which manufactured a positive claim about origin out of a
 * silence: every entry predating this change would have asserted that the
 * command line made it, which nobody knows.
 */
export function editActor(e: UserEdit): { name: string | null; basis: string } {
  if (!e || typeof e !== "object") return { name: null, basis: "actor not recorded" };
  const by = actorName(e.by);
  if (by) return { name: by, basis: "signed in" };
  const asserted = actorName(e.by_asserted);
  if (asserted) return { name: asserted, basis: "from the command line, name not verified" };
  return { name: null, basis: "actor not recorded" };
}

/** Same contract for `op` and `at`: a stored entry may be missing either, or
 *  hold something that is not a string, and neither may crash a page. */
export function editOp(e: UserEdit): string {
  const op = e && typeof e === "object" ? e.op : undefined;
  return typeof op === "string" && op.trim() ? op.trim() : "unrecorded change";
}

/** Its Python twin `edit_when` does NOT agree with this on every input, by
 *  design: this formats for a viewer's locale and so must parse, so an
 *  unparseable string reads "date not recorded" here and is echoed there.
 *  Neither invents a date. Any other divergence between the twins is a bug. */
export function editWhen(e: UserEdit): string {
  const at = e && typeof e === "object" ? e.at : undefined;
  const d = typeof at === "string" ? new Date(at) : new Date(NaN);
  return Number.isNaN(d.getTime()) ? "date not recorded" : d.toLocaleString();
}

/**
 * What counts as curation, in one place, because four surfaces claim it.
 *
 * Exactly the operations the workbench performs: `lib/actions.ts`'s Server
 * Actions and `workbench.py`'s subcommands write no other op. `restore` is
 * absent on purpose. It is written by the two recovery scripts, and putting a
 * map back after an incident is not somebody curating it — `/g/10` carries one
 * restore from incident 12 and nothing else, and announcing that as "1
 * curatorial change" is the false curation claim this change exists to remove,
 * with a number attached to make it worse.
 *
 * A closed list fails by undercounting, which is the direction this product is
 * allowed to be wrong in. Twin of `CURATORIAL_OPS` in pipeline/common.py.
 */
export const CURATORIAL_OPS = ["rename", "merge", "delete-node", "delete-edge", "reclassify"] as const;

export const isCuratorial = (e: UserEdit): boolean =>
  (CURATORIAL_OPS as readonly string[]).includes(editOp(e));

export function curatorialEdits(edits: unknown): UserEdit[] {
  return Array.isArray(edits) ? (edits as UserEdit[]).filter(isCuratorial) : [];
}

/**
 * Who made these edits, counted per actor, highest evidence first, plus whether
 * any actor is known at all. Twin of `actor_tally` in pipeline/common.py.
 *
 * One implementation because the map page, the home page and both exports all
 * make this statement, and a claim about attribution said four ways drifts.
 */
export function actorTally(edits: UserEdit[]): { parts: string[]; anyKnown: boolean } {
  const rank: Record<string, number> = {
    "signed in": 0, "from the command line, name not verified": 1,
  };
  const tally = new Map<string, { name: string; basis: string; count: number }>();
  let unattributed = 0;
  for (const e of edits) {
    const { name, basis } = editActor(e);
    if (!name) { unattributed++; continue; }
    const key = JSON.stringify([basis, name]);
    const seen = tally.get(key);
    if (seen) seen.count++;
    else tally.set(key, { name, basis, count: 1 });
  }
  const known = [...tally.values()].sort(
    (a, b) => (rank[a.basis] ?? 9) - (rank[b.basis] ?? 9) ||
              b.count - a.count || a.name.localeCompare(b.name),
  );
  const parts = known.map((k) => `${k.count} by ${k.name} (${k.basis})`);
  if (unattributed) parts.push(`${unattributed} with no actor recorded`);
  return { parts, anyKnown: known.length > 0 };
}

/** The sentence the two pages use: how many curatorial changes, and who by,
 *  with the same tally the exports print. Never asserts attribution the entries
 *  have not established, which is decision 18 applied to its own copy. */
export function curationSentence(edits: unknown): string {
  const curated = curatorialEdits(edits);
  if (!curated.length)
    return "No curatorial changes have been made to it since; any that are will be recorded with who made them.";
  const { parts, anyKnown } = actorTally(curated);
  const head = `${curated.length} curatorial change(s) have been made to it since`;
  return anyKnown ? `${head}: ${parts.join(", ")}.`
                  : `${head}. No actor is recorded for any of them.`;
}

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
export type MapEdge = {
  from: string; to: string; type: string; verified: boolean;
  /** Same resolution as `Edge.stamp`. The map draws a stale edge dotted, like an
   *  inferred one: it is not entitled to a solid line, because nothing has
   *  checked its quotes against the text that is there now. */
  stamp: StampState;
};
export type InfluenceMapData = {
  concept: string;
  through_line: string;
  papers: MapPaper[];
  edges: MapEdge[];
  streams: { id: string; name: string; color: string; count: number }[];
  total_papers: number;
  /** The footer's whole claim, already resolved server-side: how many
   *  CURATORIAL edits this map carries and who by. The footer used to say
   *  "curated by hand" on every map unconditionally, then said "1 curatorial
   *  change ... recorded with who made it" about `/g/10`, whose one entry is
   *  incident 12's restore and names nobody. Both were false; both are now
   *  counted. A string rather than the array because this object is serialised
   *  into the client bundle for InfluenceMap. */
  curation: string;
};

/** The pivotal papers and the typed links among them: top-N by on-term uptake
 *  plus the strongest movers (displacement, gated by uptake so outliers stay
 *  out). The magnitude scores select and size; they are never displayed. */
export async function getInfluenceMap(id: number): Promise<InfluenceMapData | null> {
  const riverData = await getRiver(id);
  if (!riverData) return null;
  const { concept, river } = riverData;

  const g = (await sql`
    SELECT concept, prompt_version,
           COALESCE(user_edits, '[]'::jsonb) AS user_edits
    FROM genealogies WHERE id = ${id}
  `) as { concept: string; prompt_version: string; user_edits: UserEdit[] }[];
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
  // LEFT JOIN for the same reason as everywhere else (issue #79), and here it is
  // uniformity rather than a behaviour change: measured, the result set is
  // identical either way. The predicate below asks for two arXiv ids drawn from
  // the papers this map selected, and a missing paper row has no arXiv id, so
  // `NULL = ANY(...)` is NULL and the edge is excluded by the WHERE clause
  // instead of by the join. It has to be: this canvas draws edges BETWEEN two
  // drawn papers, and there is no node to hang a missing one from. What the
  // LEFT JOIN buys is that removing or widening that predicate later cannot
  // silently reintroduce the join deciding the question.
  const rawEdges = (await sql`
    SELECT sp.arxiv_id AS from, tp.arxiv_id AS to, e.edge_type AS type, e.verified,
           e.source_text_digest, e.target_text_digest,
           sp.extracted_text_digest AS source_current_digest,
           tp.extracted_text_digest AS target_current_digest,
           sp.year AS from_year, tp.year AS to_year
    FROM edges e LEFT JOIN papers sp ON sp.id = e.source_paper_id
                 LEFT JOIN papers tp ON tp.id = e.target_paper_id
    WHERE e.genealogy_id = ${id} AND sp.arxiv_id = ANY(${arxivs}) AND tp.arxiv_id = ANY(${arxivs})
  `) as (MapEdge & {
    from_year: number; to_year: number;
    source_text_digest: string | null; target_text_digest: string | null;
    source_current_digest: string | null; target_current_digest: string | null;
  })[];

  // An edge means "the newer paper did X to the older one's concept", so a link
  // pointing backwards in time is a data error: arXiv revisions let two papers
  // cite each other, and the stored year is the v1 date. Drop the reverse leg
  // rather than draw a lineage the data cannot support.
  const edges: MapEdge[] = rawEdges
    .filter((e) => e.to_year >= e.from_year)
    .map((e) => ({
      from: e.from, to: e.to, type: e.type, verified: e.verified,
      stamp: edgeStampOf(e.verified, e.source_text_digest, e.source_current_digest,
                         e.target_text_digest, e.target_current_digest),
    }));

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
    curation: curationSentence(g[0].user_edits),
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

/** `edit_count` is the count of CURATORIAL edits, computed here rather than in
 *  SQL so that what counts as curation has one definition (`CURATORIAL_OPS`)
 *  instead of a second one in a query. `jsonb_array_length` used to stand here
 *  and it counted incident 12's restore as somebody's editorial work.
 *
 *  `verified_count` and `stale_count` are `stampOf`'s rule in SQL, and they used
 *  to be written out here as two subqueries — the third implementation of a
 *  three-line rule, and the one that disagreed with the other two on an
 *  empty-string digest and put a wrong number on the front page (issue #60).
 *  **They now come from `map_report`** (migration 016, issue #30): the rule's SQL
 *  form is one `CASE` producing one label per row, in one place, and this page and
 *  `pipeline/map_report.py` read that one expression instead of two. The count of
 *  implementations is unchanged at three — `stamp_state` in `pipeline/common.py`,
 *  `stampOf` in `app/lib/stamp.ts`, and the view — which is the whole argument
 *  for a view: two surfaces that must agree now read one expression.
 *
 *  It stays in SQL rather than moving to TypeScript because these are one
 *  aggregate per map on the front page, and resolving them here would mean
 *  fetching every edge of every map to count them.
 *
 *  Everything the old subqueries were careful about is carried by the view and
 *  is commented there: the `COALESCE(..., '') = ''` tests that stop a pair of
 *  empty digests satisfying `'' = ''` and reading verified (#60), and the two
 *  `LEFT JOIN`s to `papers` that stop the join deciding whether an edge exists,
 *  so that a missing paper row counts as not-re-checked here exactly as it
 *  resolves stale on the page this card links to (#60's residue, then #79, #83).
 *
 *  `paper_count` and `edge_count` are deliberately still counted here. The view
 *  publishes `papers_defining` and `edges_total` and they must equal these; that
 *  equality is a check the report is meant to be able to fail, and taking all
 *  four numbers from one expression would make it true by construction and
 *  therefore worth nothing.
 *
 *  LEFT JOIN to the view, not JOIN. Every genealogies row has a `map_report` row
 *  because the view selects `FROM genealogies` and joins everything else outward,
 *  so this changes no result today; it is written this way because a JOIN here
 *  would be the join deciding whether a map appears on the front page, which is
 *  the fault this file has now paid for three times. */
export async function listGenealogies() {
  const rows = (await sql`
    SELECT g.id, g.concept, g.prompt_version, g.status, g.updated_at,
           COALESCE(g.user_edits, '[]'::jsonb) AS user_edits,
           CASE WHEN g.streams IS NOT NULL
                THEN jsonb_array_length(g.streams->'streams') END                        AS stream_count,
           (SELECT count(*) FROM definitions d
             WHERE d.concept = g.concept AND d.prompt_version = g.prompt_version
               AND d.defines_concept = true)                                             AS paper_count,
           (SELECT count(*) FROM edges e WHERE e.genealogy_id = g.id)                    AS edge_count,
           r.edges_verified                                                              AS verified_count,
           r.edges_stale                                                                 AS stale_count
    FROM genealogies g
    LEFT JOIN map_report r ON r.genealogy_id = g.id
    ORDER BY g.updated_at DESC
  `) as {
    id: number; concept: string; prompt_version: string; status: string;
    updated_at: string; user_edits: UserEdit[]; stream_count: number | null;
    paper_count: number; edge_count: number; verified_count: number;
    stale_count: number;
  }[];
  return rows.map((g) => ({ ...g, edit_count: curatorialEdits(g.user_edits).length }));
}

/** A claim carries its own evidence: the passage from the paper that shows it,
 *  checked by the same comparison Stage E uses, or null when nothing in the
 *  paper's text supported it. Written by Stage H; absent on maps built before
 *  it, which fall back to the paragraph. */
export type RiverClaim = { text: string; quote: string | null; verified: boolean };
export type RiverPaper = {
  arxiv: string; year: number; title: string; move: string; prose: string;
  quote?: string; claims?: RiverClaim[];
};
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

  // The four digest columns are the whole staleness test (migration 015): two
  // stamp digests written by the code that performed each match, and the two
  // papers' current digests written by the code that wrote each file. They are
  // read together here so the page never has to ask a second question.
  //
  // LEFT JOIN on both papers, for the reason listGenealogies gives at length
  // (issue #60, then #79): the join must not decide whether an edge exists. An
  // INNER JOIN here dropped an edge whose paper row is missing, while the home
  // card counted it, so the card said "3 relationships" and the page it links to
  // listed 2 — the two surfaces disagreeing about one map. Now the row arrives
  // with NULL digests, which is exactly what `edgeStampOf` is handed for a paper
  // with no digest, so it resolves stale on the page as it counts stale on the
  // card. `source_paper` and `target_paper` arrive NULL with it; see the type.
  const edges = (await sql`
    SELECT e.id, e.source_node, e.target_node, e.edge_type, e.confidence, e.verified,
           sp.arxiv_id AS source_paper, tp.arxiv_id AS target_paper,
           e.source_quote, e.target_quote, e.rationale, e.citation_context,
           e.source_text_digest, e.target_text_digest,
           sp.extracted_text_digest AS source_current_digest,
           tp.extracted_text_digest AS target_current_digest,
           ds.novelty_claims AS source_novelty, dt.novelty_claims AS target_novelty,
           ds.section AS source_section, dt.section AS target_section
    FROM edges e
    LEFT JOIN papers sp ON sp.id = e.source_paper_id
    LEFT JOIN papers tp ON tp.id = e.target_paper_id
    LEFT JOIN definitions ds ON ds.paper_id = e.source_paper_id
      AND ds.concept = ${g.concept} AND ds.prompt_version = ${g.prompt_version} AND ds.defines_concept = true
    LEFT JOIN definitions dt ON dt.paper_id = e.target_paper_id
      AND dt.concept = ${g.concept} AND dt.prompt_version = ${g.prompt_version} AND dt.defines_concept = true
    WHERE e.genealogy_id = ${id}
    ORDER BY e.id
  `) as (Edge & {
    source_text_digest: string | null; target_text_digest: string | null;
    source_current_digest: string | null; target_current_digest: string | null;
  })[];

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
    // Array.isArray, not `?? []`: a JSONB string has a `.length` and no `.map`,
    // so it satisfies the page's `user_edits.length > 0` guard and then throws
    // inside AuditTrail. There is still no error.tsx, so that is a 500 on the
    // whole evidence page. Nothing writes a non-array today; the guard costs a
    // call.
    user_edits: (Array.isArray(g.user_edits) ? g.user_edits : []) as UserEdit[],
    has_river: Boolean(g.has_river),
    edges: edges.map((e) => ({
      ...e,
      confidence: Number(e.confidence),
      stamp: edgeStampOf(e.verified, e.source_text_digest, e.source_current_digest,
                         e.target_text_digest, e.target_current_digest),
    })),
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

/**
 * Every workbench edit is appended here, so a curated map always carries the
 * record of what a human changed, when, and who.
 *
 * The actor is a `Viewer`, not a string, and that is the load-bearing part: a
 * string is a convention any caller can satisfy with any text, while a Viewer
 * can only be obtained from getViewer() or requireOwner(). So the compiler,
 * rather than a comment, keeps unauthenticated text out of `by`. The CLI has no
 * session and writes `by_asserted` instead; this function is the only writer of
 * `by` in the system.
 */
export async function recordEdit(genealogyId: number, op: string, detail: unknown, by: Viewer) {
  const entry = JSON.stringify([{ op, detail, at: new Date().toISOString(), by: by.login }]);
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

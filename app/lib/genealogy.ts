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
 * What it means for a map to be published, in one place, because every read of
 * `genealogies` in this file has to ask it (issue #168).
 *
 * **Until this shipped, publication did not exist as a state.** Nothing in the
 * app filtered on `status`: `listGenealogies` selected every row and ordered by
 * `updated_at`, `getGenealogy` and `getMapRow` selected by id with no predicate,
 * and no page added one. The row is written by Stage C, roughly halfway through
 * a build — `INSERT_GENEALOGY` in `stage_c_cluster.py` writes `status =
 * 'running'` — so a half-built map, concept-states and no relationships, was
 * publicly listed and loadable on every build, for the whole second half of it.
 * That has been true for months and nobody saw it, because the maps in this
 * database were built before anyone was watching the home page.
 *
 * `'complete'` is Stage E's own word (`UPDATE genealogies SET status='complete'`
 * at the end of its one transaction), so this needs no column and no migration,
 * which is what lets it ship in the same push as one: the app is live against a
 * schema one migration behind for the minutes between the Vercel deploy and
 * Render's pre-deploy (decision 31), and this predicate reads a column that has
 * been in `genealogies` since migration 001.
 *
 * **An allow-list, not a deny-list.** `status = 'complete'` rather than `status
 * <> 'running'`: the CHECK on that column already permits `pending`, `failed`
 * and `aborted_spend_cap`, none of which is a map anybody should be reading, and
 * a status invented tomorrow is unpublished until somebody decides otherwise.
 * The direction this can be wrong in is hiding a map, which is visible; the
 * other direction is showing half of one, which is not.
 *
 * **The refusal lives here and never in a page conditional**, which is the
 * control the two-stage build design (#184) names for this risk: three surfaces
 * read a `genealogies` row and a fourth would be added by the next feature, so a
 * guard per page is a guard that the next page forgets. An unpublished map is
 * therefore indistinguishable from a map that does not exist, on every surface —
 * `/g/<id>` redirects to the evidence view and that 404s, exactly as it already
 * does for an id nobody ever minted — and that is deliberate: leaking the
 * existence of a map that is not ready is most of what leaking the map is.
 *
 * **No exception for the owner**, on the design's reasoning: "visible to them,
 * not to others" is a second visibility rule to keep in agreement with the
 * first. A requester watching their own build sees it in the live trace panel,
 * which only offers a link to the map once the run is complete.
 *
 * `/g/<id>/report` is the fourth read path, and it is covered as of issue #194:
 * `listMapReports` in `lib/report.ts` imports this constant and tests
 * `map_report.status`, which migration 016's view selects straight through from
 * `genealogies`. It is imported and not respelled there because publication is
 * one fact — see that function for why it leaked twice.
 */
export const PUBLISHED_STATUS = "complete";

/**
 * One published version of a concept's map: the id it lives at for ever, the
 * number it calls itself, and whether it is the one the concept currently points
 * at (migration 025, issue #206; read here for issue #208).
 *
 * **Published versions only.** An unpublished row is also a not-current row, and
 * both facts have to hold independently: listing a `running` build here as
 * "version 3" would leak the existence of a map that is not ready through a
 * strip on a page that is, which is most of what leaking a map is (#168). So the
 * predicate on the sibling list is `PUBLISHED_STATUS`, exactly as everywhere
 * else, and currency is a second test layered on it rather than a replacement.
 */
export type MapVersion = { id: number; version: number; is_current: boolean };

/**
 * What one map page knows about being a version (issue #208).
 *
 * **The rule this exists to serve: an id names a version, permanently.** A
 * reader who cites a map in a literature review is citing a set of claims, so
 * `/g/17` is version 1 of dark energy for ever and renders in full whether or
 * not it is still current. These are the facts the page needs to say so: which
 * version this is, whether it is the live one, when it stopped being the live
 * one, and where its siblings are.
 *
 * **Null on the whole object means the schema has not got there yet**, not
 * "this map has one version". Migration 025's columns are read behind a
 * try/catch (see `getMapRow`), because a push deploys Vercel minutes before
 * Render applies the migration and a missing *column* cannot be probed for
 * (#182). A page handed null renders no version line at all, which is exactly
 * what it renders today.
 */
export type MapVersions = {
  version: number;
  is_current: boolean;
  /** When the swap demoted this version (#207 writes it). Null on a version
   *  that is current, and also on one that is not current and was never
   *  recorded as replaced: "when was this replaced" has no answer derivable
   *  from "this is not current", and the page says the weaker thing rather than
   *  inventing a date. The driver may hand this back as a `Date` rather than a
   *  string depending on its type parsers, so anything formatting it takes
   *  both — see `supersededOn` in `app/g/[id]/version-note.tsx`. */
  superseded_at: string | null;
  /** Every published version of this concept, oldest first, this one included.
   *  Empty is impossible for a row that was itself found published; an empty
   *  array would mean the sibling query disagreed with the row query. */
  published: MapVersion[];
};

/** The version facts, or null, off a row that may not have the columns at all.
 *  Written once because `getMapRow` and `getGenealogy` both read them and a
 *  second spelling is a second thing to keep in agreement. */
function versionsOf(r: Record<string, unknown>): MapVersions | null {
  if (r.version === undefined || r.version === null) return null;
  const list = Array.isArray(r.versions) ? (r.versions as MapVersion[]) : [];
  return {
    version: Number(r.version),
    is_current: r.is_current === true,
    superseded_at: (r.superseded_at ?? null) as string | null,
    published: list.map((v) => ({
      id: Number(v.id), version: Number(v.version), is_current: v.is_current === true,
    })),
  };
}

/**
 * Why the version columns are read behind a `try` and not behind a probe.
 *
 * The guarded thing here is three *columns*, and #182 established that a missing
 * column cannot be probed for the way a missing relation can: `to_regclass`
 * answers about a relation name, and `genealogies` is present either way. What
 * can be done is to ask the real question and catch the failure (#44's pattern
 * in `edgeTotalAndReading` below), which costs nothing on every deployment that
 * has run migration 025 and costs one extra round trip only in the minutes
 * between the Vercel deploy and Render's pre-deploy.
 *
 * **The condition on doing it this way is that the fallback still answers the
 * page's primary question**, and here it plainly does: the fallback is the same
 * statement without the version facts, so the reader gets the map and loses a
 * line naming which version it is. Before migration 025 there is exactly one
 * published row per concept, so that line would have said nothing anyway.
 *
 * The driver's own message is logged rather than the class name, because "the
 * version line is missing" with no cause in the log is how a transient network
 * failure gets read as a schema state.
 */
function noVersionColumns(fn: string, id: number, exc: unknown) {
  console.error(
    `${fn}(${id}): could not read the version columns from genealogies, ` +
      `falling back to the map without them: ${String(exc)}`,
  );
}

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
 *  authenticated claim. It must not throw either: one TypeError inside a server
 *  component loses the evidence page and the export for that map until the row
 *  is edited by hand. Since #159 that is a styled apology rather than the raw
 *  global-error shell, which is a better failure and still a failure. */
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

/** The sentence the two pages use: how many changes made by hand, and who by,
 *  with the same tally the exports print. Never asserts attribution the entries
 *  have not established, which is decision 18 applied to its own copy.
 *
 *  Says it in the reader's words rather than the team's (issue #126): this read
 *  "No curatorial changes have been made to it since" on the front door's
 *  footnote, where "curatorial" is a word the reader meets nowhere else, and
 *  "change(s)" is the machine talking in the same place #120 removed it from the
 *  home card. The count and what counts as curation are untouched. */
export function curationSentence(edits: unknown): string {
  const curated = curatorialEdits(edits);
  if (!curated.length)
    return "Nobody has edited this map by hand since. If anyone does, the change will be recorded, along with who made it.";
  const { parts, anyKnown } = actorTally(curated);
  const one = curated.length === 1;
  const head = `${curated.length} change${one ? "" : "s"} ${one ? "has" : "have"} been made to it by hand since`;
  return anyKnown ? `${head}: ${parts.join(", ")}.`
                  : `${head}. Who made ${one ? "it" : "them"} was not recorded.`;
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
  /** The paper's own defining passage and the two digests its stamp resolves
   *  from, so the evidence page can show each passage once at the head of that
   *  paper's relationships (issue #146) instead of only inside closed rows.
   *  They ride on the paper query `getGenealogy` already issues, which is why
   *  this costs no round trip. Nullable throughout: a paper can define the
   *  concept with no quote recorded, and a digest is absent on anything checked
   *  before migration 015. `stampOf` is handed all three and answers stale. */
  verbatim_quote: string | null;
  quote_verified: boolean | null;
  quote_text_digest: string | null;
  extracted_text_digest: string | null;
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
  /** Which version this is and where its siblings are, or null when the schema
   *  does not carry versions yet (issue #208; see `MapVersions`). */
  versions: MapVersions | null;
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
  /** The papers that define the term AND carry an uptake score: `rows.length`
   *  from the query above, which is the pool the canvas picks its dots from. It
   *  is NOT the map's paper count and must never be labelled as one (issue
   *  #123). Four surfaces print a count under the word "papers" and all four
   *  count different sets — every definitions row for the map (the report's
   *  "papers read"), the defining ones (`paper_count` on the home card and
   *  `papers_defining` on the report), the membership of the stored grouping
   *  (the evidence page header), and this. Reproduced on one constructed map:
   *  20 / 12 / 11 / 10, each moved only by its own input. */
  total_papers: number;
  /** Every typed relationship in the map, not just the ones the canvas draws.
   *  The badge needs both counts to name both populations (issue #114): a reader
   *  went home card 320, front door "39 of 39", evidence 320, with the single
   *  word "shown" to explain the drop, and the careful reader concluded the map
   *  had lost 281 relationships. This is the same quantity the evidence page
   *  prints as "N typed relationships", counted the same way: `getGenealogy`
   *  selects every edge of the map and its LEFT JOINs cannot multiply a row,
   *  because `definitions` is UNIQUE on (paper_id, concept, prompt_version). */
  total_edges: number;
  /** The footer's whole claim, already resolved server-side: how many
   *  CURATORIAL edits this map carries and who by. The footer used to say
   *  "curated by hand" on every map unconditionally, then said "1 curatorial
   *  change ... recorded with who made it" about `/g/10`, whose one entry is
   *  incident 12's restore and names nobody. Both were false; both are now
   *  counted. A string rather than the array because this object is serialised
   *  into the client bundle for InfluenceMap. */
  curation: string;
  /** The two ends of what this map read: the oldest and the newest year among
   *  the map's DEFINING papers (issue #44, `[Q7]`). A fifth
   *  population on this page, so it is named here and labelled everywhere it is
   *  printed (#123's rule): it is wider than `total_papers`, which is the
   *  defining papers that also carry an uptake score, and wider again than the
   *  dots the canvas draws.
   *
   *  Read from `map_report` rather than computed here, so this and the report
   *  page's "earliest year"/"latest year" are one expression and cannot disagree
   *  about one map. NULL means the years could not be read at all (see
   *  `edgeTotalAndReading`), never "the map has no years": the marker and the
   *  sentence are then both absent, because a horizon nobody can place is worse
   *  than no horizon. What is drawn and said from them is in
   *  `lib/reading-window.ts`, which is a separate module because the canvas is a
   *  client component and must not import this one for a value. */
  reading_from: number | null;
  reading_to: number | null;
  /** Which version this map is and where its siblings are (issue #208), carried
   *  from the row `getMapRow` already read, so the front door pays no round trip
   *  for the line that names it.
   *
   *  It rides on this object knowing this object is serialised into the client
   *  bundle for `InfluenceMap`, which is why `curation` beside it is a string
   *  rather than an array. The cost is bounded by the number of published
   *  versions of one concept at three small fields each, against a payload that
   *  already carries every drawn paper's title; and it is null, not an empty
   *  array, on a deployment whose schema has no versions. */
  versions: MapVersions | null;
};

type MapTotals = { total: number | string; year_min: unknown; year_max: unknown };

/**
 * The map's relationship count and the two ends of its reading, in one
 * statement (issue #44).
 *
 * The count was already a statement of its own and the horizon rides on it, so
 * the front door pays no extra round trip for the caption: #140 spent a ticket
 * getting this page's serial queries down and a second question about one map is
 * exactly what it removed. `map_report` is read here, rather than `min`/`max`
 * being written out again, so this page and the report page print one figure
 * (report.ts explains why nothing on that page computes anything).
 *
 * **A fallback, not a probe.** `listGenealogies` and `typesFor` guard the same
 * view with `to_regclass`, and both pay a round trip to ask about a *name* while
 * the query that follows resolves that name against a search path — the two are
 * the same question only under the deployment we tested (issue #92). Asking the
 * real query and catching the failure has neither problem: it costs nothing when
 * the view is there, which is every deployment that has run migration 016, and
 * when it is not there the page loses a caption instead of the map. The reason
 * is logged with the driver's own message, because "the horizon is missing" with
 * no cause in the log is how a transient failure gets read as a schema state.
 */
async function edgeTotalAndReading(id: number): Promise<MapTotals[]> {
  try {
    return (await sql`
      SELECT (SELECT count(*) FROM edges WHERE genealogy_id = ${id}) AS total,
             r.year_min, r.year_max
      FROM (SELECT 1) AS one
      LEFT JOIN map_report r ON r.genealogy_id = ${id}
    `) as MapTotals[];
  } catch (exc) {
    console.error(
      `getInfluenceMap(${id}): could not read the reading horizon from map_report, ` +
        `falling back to the relationship count alone: ${String(exc)}`,
    );
    return (await sql`
      SELECT count(*) AS total, NULL AS year_min, NULL AS year_max
      FROM edges WHERE genealogy_id = ${id}
    `) as MapTotals[];
  }
}

/** The driver hands `bigint` back as a string and may hand back nothing at all,
 *  and this page distinguishes "no year recorded" from a year: same boundary
 *  rule as `num` in lib/report.ts, and for the same reason — a silent 0 here
 *  would rule a line off the canvas at the year nought. */
const yearOrNull = (v: unknown): number | null => {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** The pivotal papers and the typed links among them: top-N by on-term uptake
 *  plus the strongest movers (displacement, gated by uptake so outliers stay
 *  out). The magnitude scores select and size; they are never displayed. */
export async function getInfluenceMap(id: number): Promise<InfluenceMapData | null> {
  // Was two statements against the same `genealogies` row — `getRiver` for the
  // streams, then a second SELECT for `prompt_version` and `user_edits`. One
  // now (issue #140). The null test is unchanged: a map with no generated
  // river has no front door and the page redirects to the evidence view.
  const g = await getMapRow(id);
  if (!g?.river) return null;
  const { concept, river } = g;

  // Independent, so asked together. `rows` is keyed on the concept and prompt
  // version; `total_edges` is keyed on the genealogy id alone and needs nothing
  // this function computes. It used to be asked last, after the edge query,
  // purely because that is where the number is used — a serial round trip for a
  // question that could have been in flight the whole time.
  const [rows, totals] = (await Promise.all([
    sql`
      SELECT p.arxiv_id AS arxiv, p.year, p.title, d.attention, d.displacement, d.novelty_claims AS novelty
      FROM definitions d JOIN papers p ON p.id = d.paper_id
      WHERE d.concept = ${g.concept} AND d.prompt_version = ${g.prompt_version}
        AND d.defines_concept = true AND d.attention IS NOT NULL
    `,
    // Counted, never inferred from what the canvas drew. `COUNT(*)` on the map's
    // edges is exactly the population the evidence page lists, so the badge's
    // "the full N are in the evidence" is a promise the next page keeps. It
    // carries the reading horizon with it (issue #44); see the function.
    edgeTotalAndReading(id),
  ])) as [
    { arxiv: string; year: number; title: string; attention: number; displacement: number | null; novelty: string[] | null }[],
    MapTotals[],
  ];
  const total_edges = Number(totals[0]?.total ?? 0);

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
    total_edges,
    curation: curationSentence(g.user_edits),
    reading_from: yearOrNull(totals[0]?.year_min),
    reading_to: yearOrNull(totals[0]?.year_max),
    versions: g.versions,
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
 *  the fault this file has now paid for three times.
 *
 *  And the view may not be there at all: see the `to_regclass` probe below
 *  (issue #92).
 *
 *  **Published maps only** (issue #168; see `PUBLISHED_STATUS`). This is the
 *  front page's list, so it was the surface a map appeared on the moment Stage C
 *  wrote its row, halfway through the build.
 *
 *  **And current versions only** (issue #208): one card per concept. This is the
 *  one of the four read functions that gains a currency test, and the asymmetry
 *  is the design — `getGenealogy` and `getMapRow` serve any published version
 *  for ever, because an id names a version, while this list answers "which
 *  concepts have been mapped", which has one answer per concept. Without it, a
 *  concept rebuilt three times would put three cards on the front page, all
 *  titled the same word.
 *
 *  Currency is a second test layered on publication and never a replacement for
 *  it: `status = ${PUBLISHED_STATUS}` stays below even though migration 025's
 *  CHECK makes a current row published by construction, because a build that is
 *  `running` must be invisible whether or not anyone remembered the currency
 *  filter. */
export async function listGenealogies() {
  // **Does the view exist?** Reading the two counts from `map_report` gave the
  // home page a hard dependency on migration 016, and an app that deploys before
  // the migration lands does not lose two numbers, it loses the front page:
  // Postgres raises `UndefinedTable` for the whole statement and `/` returns a
  // 500 (issue #92). `to_regclass` answers NULL instead of raising for a
  // relation that is not there, and it has to be its own statement, because
  // every relation named in a statement is resolved before any expression in it
  // runs — a guard inside the query would be parsed by the thing it guards
  // against. The runbook says migration before deploy; this is what happens when
  // that is not what happened.
  //
  // **The currency filter is probed in the same statement** (issue #208), so
  // this page still pays exactly one round trip to ask what its schema holds.
  // It is a probe rather than a catch, unlike the version facts on `getMapRow`:
  // what is guarded there is three display columns, and losing them costs a
  // line, while what is guarded here is a FILTER, and a silent fallback would
  // put every superseded version back on the front page. A probe can only
  // fall back when the relation is genuinely absent — the minutes before
  // Render's pre-deploy — and there the fallback is exact rather than degraded,
  // because before migration 025 there is one published row per concept and
  // `status = 'complete'` returns precisely the set the view would.
  //
  // Probed unqualified, matching `FROM genealogies_current` below, which is #92's
  // own correction: a probe that qualifies where its query does not is asking
  // about a different name under any schema arrangement it does not spell. Its
  // neighbour on this line still asks about `public.map_report` while the query
  // says `FROM map_report`; that is the residue #92 recorded, left as it was
  // rather than changed under a ticket about versions.
  const [probe] = (await sql`
    SELECT to_regclass('public.map_report')   IS NOT NULL AS reported,
           to_regclass('genealogies_current') IS NOT NULL AS versioned
  `) as { reported: boolean; versioned: boolean }[];
  const reported = probe?.reported === true;
  // A view, so `SELECT *` on it gives back every column of `genealogies` this
  // query already reads — including `streams` and `user_edits` — and no column
  // list here has to know about migration 025 at all.
  const from = probe?.versioned === true
    ? sql.unsafe("FROM genealogies_current g")
    : sql.unsafe("FROM genealogies g");

  // Absence is reported as absence. `NULL` here, and the card prints words for
  // it, because 0 verified relationships is a claim about the map and this is a
  // claim about the schema: a page that renders "0 verified relationships" over
  // a map with 287 of them is worse than the 500 it replaced.
  const counts = reported
    ? sql.unsafe(`r.edges_verified AS verified_count,
                  r.edges_stale    AS stale_count`)
    : sql.unsafe(`NULL::bigint AS verified_count,
                  NULL::bigint AS stale_count`);
  const join = reported
    ? sql.unsafe("LEFT JOIN map_report r ON r.genealogy_id = g.id")
    : sql.unsafe("");

  const rows = (await sql`
    SELECT g.id, g.concept, g.prompt_version, g.status, g.updated_at,
           COALESCE(g.user_edits, '[]'::jsonb) AS user_edits,
           CASE WHEN g.streams IS NOT NULL
                THEN jsonb_array_length(g.streams->'streams') END                        AS stream_count,
           (SELECT count(*) FROM definitions d
             WHERE d.concept = g.concept AND d.prompt_version = g.prompt_version
               AND d.defines_concept = true)                                             AS paper_count,
           (SELECT count(*) FROM edges e WHERE e.genealogy_id = g.id)                    AS edge_count,
           ${counts}
    ${from}
    ${join}
    WHERE g.status = ${PUBLISHED_STATUS}
    ORDER BY g.updated_at DESC
  `) as {
    id: number; concept: string; prompt_version: string; status: string;
    updated_at: string; user_edits: UserEdit[]; stream_count: number | null;
    paper_count: number; edge_count: number; verified_count: number | null;
    stale_count: number | null;
  }[];
  return rows.map((g) => ({ ...g, edit_count: curatorialEdits(g.user_edits).length }));
}

/** A claim carries its own evidence: the passage from the paper that shows it,
 *  checked by the same comparison Stage E uses, or null when nothing in the
 *  paper's text supported it. Written by Stage H; absent on maps built before
 *  it, which fall back to the paragraph. `checked_against` is the digest of the
 *  exact bytes the grounding check read (#215), written by the check itself and
 *  never copied from `papers.extracted_text_digest`; the thread page resolves
 *  the two through `stampOf`, so a claim stamped before the digest existed —
 *  every legacy claim — resolves stale by the same rule a NULL digest always
 *  has, and the raw boolean alone can no longer put a green stamp on a quote. */
export type RiverClaim = {
  text: string; quote: string | null; verified: boolean;
  checked_against?: string | null;
};
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

/** A map's identity row: the two keys every other query about this map needs,
 *  its generated river, and its edit log. `river` is null until the streams job
 *  has run for this genealogy (migration 012), which is a real state — /g/10
 *  had none — so callers that can live without it must not treat null as "no
 *  such map". */
export type MapRow = {
  concept: string;
  prompt_version: string;
  river: River | null;
  user_edits: UserEdit[];
  /** Which version this is and where its siblings are, or null when the schema
   *  does not carry versions yet (issue #208; see `MapVersions`). */
  versions: MapVersions | null;
};

/**
 * One SELECT for the four columns of `genealogies` the app ever wants.
 *
 * This replaced `getRiver`, which selected `concept, streams` and left every
 * caller to fetch `prompt_version` — the key it needs to look up anything else
 * about the map — in a second statement against the same row. Four call sites
 * did exactly that: the influence map, the export builder, the thread page and
 * the paper dossier. The Neon HTTP driver makes every query a separate fetch
 * (see lib/db.ts), and the functions run in `iad1`, so asking one row twice
 * bought a whole network round trip for columns that were already on the wire.
 * Measured from the map's front door before and after, issue #140.
 *
 * **Null for a map that is not published as well as for one that is not there**
 * (issue #168; see `PUBLISHED_STATUS`). The design named two read functions and
 * there are three: this one serves the map's front door, the paper dossier, the
 * thread page and the export, so guarding only the other two would have left the
 * front door open.
 *
 * **Any published version, current or not** (issue #208). This is the function
 * that must NOT gain a currency test: `/g/17` is version 1 of dark energy for
 * ever, and a cited version that cannot be opened is no better than one that
 * changed. What it gains instead is the facts a page needs to say which version
 * the reader is looking at, on the same round trip — the three columns migration
 * 025 added, plus the concept's other published versions, as a correlated
 * subquery rather than a second statement, because #140 spent a ticket taking
 * round trips out of exactly these pages.
 */
export async function getMapRow(id: number): Promise<MapRow | null> {
  type Row = {
    concept: string; prompt_version: string; streams: River | null; user_edits: unknown;
    version?: number; is_current?: boolean; superseded_at?: string | null;
    versions?: MapVersion[];
  };
  // See `noVersionColumns` for why this is a catch and not a probe.
  let rows: Row[];
  try {
    rows = (await sql`
      SELECT g.concept, g.prompt_version, g.streams,
             COALESCE(g.user_edits, '[]'::jsonb) AS user_edits,
             g.version, g.is_current, g.superseded_at,
             (SELECT jsonb_agg(jsonb_build_object('id', v.id, 'version', v.version,
                                                  'is_current', v.is_current)
                               ORDER BY v.version)
                FROM genealogies v
               WHERE v.concept = g.concept AND v.status = ${PUBLISHED_STATUS}) AS versions
      FROM genealogies g WHERE g.id = ${id} AND g.status = ${PUBLISHED_STATUS}
    `) as Row[];
  } catch (exc) {
    noVersionColumns("getMapRow", id, exc);
    rows = (await sql`
      SELECT concept, prompt_version, streams,
             COALESCE(user_edits, '[]'::jsonb) AS user_edits
      FROM genealogies WHERE id = ${id} AND status = ${PUBLISHED_STATUS}
    `) as Row[];
  }
  if (!rows.length) return null;
  const r = rows[0];
  // Same guard `getGenealogy` gives at length: `user_edits` is JSONB and a
  // stored string has a `.length` but no `.map`, which throws inside AuditTrail
  // and loses the page: `app/error.tsx` catches it as of #159, so the reader
  // gets an apology instead of a digest, but they still do not get the map.
  return {
    concept: r.concept,
    prompt_version: r.prompt_version,
    river: r.streams,
    user_edits: (Array.isArray(r.user_edits) ? r.user_edits : []) as UserEdit[],
    versions: versionsOf(r as unknown as Record<string, unknown>),
  };
}

/**
 * The id of the concept's current version, for `/g/<id>/current` (issue #208).
 *
 * **The concept's address, not a second id space.** A reader who wants "the dark
 * energy map, whatever version that is now" needs a target that follows the
 * concept, and this is it: no slug to escape, no collisions, no new table. What
 * it must never do is make `/g/<id>` itself follow the concept, which is the
 * whole rule this ticket exists to hold.
 *
 * **The publication refusal is in the same statement as the lookup**, so an
 * unpublished id resolves to nothing here exactly as it does on the map itself
 * (#168): `/g/<id>/current` 404s for an id nobody minted, an id that is still
 * building, and an id whose build failed, and those are indistinguishable, which
 * is deliberate.
 *
 * The join is to `genealogies_current` rather than to `genealogies WHERE
 * is_current`, so the app names a relation it can be missing — and when it is
 * missing the fallback is correct rather than degraded, on the design's own
 * arithmetic: before migration 025 there is exactly one published row per
 * concept, so "the current version of this concept" and "this published row"
 * are the same row, and the fallback answers with the id it was given. A
 * transient failure lands in the same branch and answers the same way; the
 * reader then arrives at the version they named, which still says on its own
 * page whether it is current, so the failure is visible rather than silent.
 */
export async function currentVersionId(id: number): Promise<number | null> {
  let rows: { id: number }[];
  try {
    rows = (await sql`
      SELECT c.id
      FROM genealogies g JOIN genealogies_current c ON c.concept = g.concept
      WHERE g.id = ${id} AND g.status = ${PUBLISHED_STATUS}
    `) as { id: number }[];
  } catch (exc) {
    console.error(
      `currentVersionId(${id}): could not read genealogies_current, falling back to ` +
        `the published row itself, which is the same row until a second version exists: ${String(exc)}`,
    );
    rows = (await sql`
      SELECT id FROM genealogies WHERE id = ${id} AND status = ${PUBLISHED_STATUS}
    `) as { id: number }[];
  }
  return rows.length ? Number(rows[0].id) : null;
}

/** The evidence page's whole map, and null for a map that is not published as
 *  well as for one that is not there (issue #168; see `PUBLISHED_STATUS`). The
 *  workbench Server Actions resolve the map through this function, so an
 *  unpublished map cannot be edited either.
 *
 *  **Any published version, current or not** (issue #208), for the reason
 *  `getMapRow` gives at length: a superseded version is fully readable at its
 *  own address, evidence included, because a citation that cannot be opened is
 *  no better than one that changed. The version facts ride on the statement this
 *  page was already issuing; the catch around it is `noVersionColumns`.
 *
 *  **The workbench follows the evidence, deliberately.** `lib/actions.ts`
 *  resolves the map through this function, so a superseded version can be
 *  edited by the owner exactly as a current one can. That is the design's rule
 *  that edits do not carry ACROSS versions (#212), not a rule that a version
 *  stops being editable once it is replaced; what must not exist is a version
 *  *selector* in the workbench, and none does. */
export async function getGenealogy(id: number): Promise<Genealogy | null> {
  let rows: any[];
  try {
    rows = (await sql`
      SELECT g.id, g.concept, g.prompt_version, g.status, g.updated_at, g.nodes, g.user_edits,
             (g.streams IS NOT NULL) AS has_river,
             g.version, g.is_current, g.superseded_at,
             (SELECT jsonb_agg(jsonb_build_object('id', v.id, 'version', v.version,
                                                  'is_current', v.is_current)
                               ORDER BY v.version)
                FROM genealogies v
               WHERE v.concept = g.concept AND v.status = ${PUBLISHED_STATUS}) AS versions
      FROM genealogies g WHERE g.id = ${id} AND g.status = ${PUBLISHED_STATUS}
    `) as any[];
  } catch (exc) {
    noVersionColumns("getGenealogy", id, exc);
    rows = (await sql`
      SELECT id, concept, prompt_version, status, updated_at, nodes, user_edits,
             (streams IS NOT NULL) AS has_river
      FROM genealogies WHERE id = ${id} AND status = ${PUBLISHED_STATUS}
    `) as any[];
  }
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
  //
  // Asked alongside the paper query below, not before it (issue #140). Both are
  // keyed on nothing but `g`, neither reads the other's result, and this is the
  // evidence page's whole cost: two large statements that were serialised for no
  // reason beyond the order they were written in.
  const [edges, paperRows] = (await Promise.all([
    sql`
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
  `,
    // Four columns more than this asked for a week ago, and no extra statement:
    // the evidence page's paper groups need each paper's own passage and the
    // digests its stamp resolves from (issue #146), and they are columns of the
    // two tables this join already reads.
    sql`
    SELECT p.arxiv_id AS arxiv, p.year, p.title, d.attention, d.displacement, d.novelty_claims AS novelty,
           d.verbatim_quote, d.quote_verified, d.quote_text_digest, p.extracted_text_digest
    FROM definitions d JOIN papers p ON p.id = d.paper_id
    WHERE d.concept = ${g.concept} AND d.prompt_version = ${g.prompt_version} AND d.defines_concept = true
    ORDER BY d.attention DESC NULLS LAST
  `,
  ])) as [
    (Edge & {
      source_text_digest: string | null; target_text_digest: string | null;
      source_current_digest: string | null; target_current_digest: string | null;
    })[],
    Omit<RankedPaper, "node_id">[],
  ];

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
    // inside AuditTrail, which loses the whole evidence page — since #159 into
    // `app/error.tsx` rather than into Next's unstyled shell, which changes what
    // the reader sees and not whether they see the map. Nothing writes a
    // non-array today; the guard costs a call.
    user_edits: (Array.isArray(g.user_edits) ? g.user_edits : []) as UserEdit[],
    has_river: Boolean(g.has_river),
    versions: versionsOf(g as Record<string, unknown>),
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

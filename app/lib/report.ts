import { sql } from "./db";
import { curatorialEdits, PUBLISHED_STATUS } from "./genealogy";

/**
 * The map report (issue #30, `[F2]`), read from migration 016's two views,
 * migration 017's third (`map_report_by_type`, issue #162), migration 019's
 * fourth (`map_report_read_years`, issue #182), migration 020's fifth
 * (`map_report_passes`, issue #193), migration 023's sixth
 * (`map_report_anchors`, issue #198) and migration 024's seventh
 * (`map_report_stages`, issue #47).
 *
 * Nothing here computes a figure. Every number is selected from `map_report`,
 * `map_report_by_source`, `map_report_by_type`, `map_report_read_years`,
 * `map_report_passes`, `map_report_anchors` or `map_report_stages`, which is the
 * whole point of the ticket: the app and
 * `pipeline/map_report.py` read one expression, so the page and the shell cannot
 * disagree about the same map, and nothing is stored, so a figure cannot survive
 * the curatorial edit that invalidates it.
 *
 * **`versionsFor` is the one read that does not come from a report view, and
 * that is deliberate** (issue #209). A version's number, its currency and the
 * date it was replaced are stored columns on `genealogies` (migration 025), not
 * figures anything computes, so there is nothing for a view to hold in one place
 * on behalf of two surfaces; a `map_report_versions` view would be a probe target
 * and nothing else. The one figure that IS computed there — how many changes a
 * person made by hand to a version — is counted in TypeScript by
 * `curatorialEdits`, for the reason `listGenealogies` counts it that way rather
 * than in SQL: `jsonb_array_length` would count incident 12's restore as
 * somebody's editorial work, and what counts as curation has exactly one
 * definition per language (`CURATORIAL_OPS` here, its twin in
 * `pipeline/common.py`).
 *
 * **Every column is named.** `CREATE OR REPLACE VIEW` cannot change a column's
 * type, drop a column or reorder columns, so a later change to the report is a
 * `DROP VIEW` and a `CREATE VIEW`; a `SELECT *` here would let that redefinition
 * silently change what the page renders.
 *
 * **NULL is never coalesced to zero on the way through.** The view returns NULL
 * for a figure nothing recorded and for a share whose denominator is zero, and
 * the page prints words for each. A `?? 0` anywhere in this file would print
 * $0.00 under "what this map cost" about a map whose cost nobody knows, which is
 * the derived-value-stored-and-allowed-to-age defect the whole ticket is a
 * reaction to (issue #85).
 */

/** The Neon HTTP driver leaves `bigint` and `numeric` as strings (it does not
 *  set `parseInt8`, and `numeric` has no lossless JS type), so every figure is
 *  converted once, here, at the boundary. `null` stays `null` and an
 *  unparseable value becomes `null` rather than `0`: this page's entire job is
 *  to distinguish "none" from "not recorded", and a silent zero would collapse
 *  them. */
const num = (v: unknown): number | null => {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
};

export type ReportBucket = {
  unit: "definition" | "edge";
  source: string;
  total: number;
  verified: number;
  inferred: number;
  stale: number;
};

/** One kind of link and how many of the map's relationships were given it
 *  (migration 017, issue #162).
 *
 *  `taxonomy_rank` is the kind's position in the six CLAUDE.md names, and
 *  **NULL means the taxonomy does not contain this kind**. The view emits a row
 *  for every one of the six even when a map has none of it, plus a row for any
 *  kind actually present that is not among them, so the rows always sum to the
 *  map's relationship count. The app therefore never writes the six names down:
 *  it renders whatever rows it is handed, in the order it is handed them. */
export type ReportTypeCount = {
  edge_type: string;
  taxonomy_rank: number | null;
  edges: number;
  edges_share: number | null;
};

/** What the map READ, by year (migration 019, issue #182, designing #33).
 *
 *  Every figure `map_report` publishes about years is over the papers that
 *  **define** the term; these are the same shape over every paper the map read,
 *  defining or not. The pair is the point: `year_max` alone cannot separate "no
 *  recent paper was ever selected" from "recent papers were read and none of
 *  them defined the term", and those two need opposite fixes.
 *
 *  `read_year_max >= year_max` and `papers_defining_recent <=
 *  papers_read_recent` hold by construction, because the view carries
 *  `defines_concept` as a column rather than as a filter and both series come
 *  out of one set of rows. A map where either fails has a join defect.
 *
 *  **`papers_read_recent` is instrumentation, not evidence.** It counts papers
 *  in a window, so a change to how papers are selected for a map moves it by
 *  construction and it cannot report failure. The page's copy says so. */
export type ReadYears = {
  read_year_min: number | null;
  read_year_max: number | null;
  read_year_counts: Record<string, number> | null;
  papers_read_with_no_year: number;
  /** Both ends of the window, published so the page prints the years it used
   *  rather than the word "recent". They move with the calendar: the view reads
   *  `current_date` when the page loads. */
  recent_window_start: number | null;
  recent_window_end: number | null;
  papers_read_recent: number;
  papers_defining_recent: number;
};

/** Which pass of the build read a paper (migration 020, issue #193, designing
 *  #184).
 *
 *  **Every count here is null on every map today, and that is the design.**
 *  Nothing in the schema records a paper's pass yet: the orchestration that runs
 *  the two passes is #192, and migration 020 ships the question with an empty
 *  seam so that the figures light up when #192 replaces it. Until then
 *  `pass_two_outcome` reads "this map was built in one pass" and the counts are
 *  absent.
 *
 *  **Absent, not zero.** A `?? 0` on any of these would report a map as having
 *  run a second pass that read no papers, which is a measurement of something
 *  that never happened. Once a build IS recorded a zero is a real zero — a
 *  second pass that ran and found nothing — and `pass_two_outcome` says which of
 *  those two it was.
 *
 *  `papers_read_pass_one + papers_read_pass_two + papers_read_pass_unmarked`
 *  equals `papers_with_a_reading` by construction, because the view carries the
 *  pass as a column rather than as a filter over one set of rows; and
 *  `papers_defining_pass_two <= papers_read_pass_two` for the same reason. A map
 *  where either fails has a join defect. */
export type PassFigures = {
  /** How many passes the build recorded. Null means nothing recorded it, which
   *  is not the same as one. */
  passes_recorded: number | null;
  /** Never blank and never a code: the view emits the reader's sentence, the way
   *  `run_cost_basis` does. */
  pass_two_outcome: string;
  pass_two_seats: number | null;
  pass_two_candidates: number | null;
  pass_two_candidates_cleared: number | null;
  papers_read_pass_one: number | null;
  papers_read_pass_two: number | null;
  /** Papers a recorded build marked as neither the first nor the second pass,
   *  including papers it marked not at all. Anything above zero is a defect in
   *  the build's own record; it exists so that the three counts sum to the
   *  papers read whatever the build wrote. */
  papers_read_pass_unmarked: number | null;
  papers_defining_pass_two: number | null;
  /** The tool's reading, and labelled as such wherever it prints: an edge is a
   *  judgement about direction and kind, unlike Stage B's verdict on whether a
   *  paper defines the term. */
  papers_linking_into_pass_one: number | null;
};

/** One paper a person named at request time (migration 023, issue #198).
 *
 *  `read` is whether this map holds a reading of it, which is not the same as
 *  having been named: an id that named a paper nothing could fetch stays in this
 *  list with `read` false, because a silently dropped name is a requester
 *  believing their paper is in a map that does not contain it.
 *
 *  `defines` is Stage B's verdict, taken the same way it is taken for every other
 *  paper. `relationships` is how many of the map's relationships touch it, and it
 *  is **the tool's reading** rather than a checked fact, like every other edge
 *  count on this page. Both may be false and zero on a named paper, and that is
 *  the honest failure the whole feature rests on being visible. */
export type AnchorPaper = {
  arxiv_id: string;
  title: string | null;
  year: number | null;
  read: boolean;
  defines: boolean;
  relationships: number;
};

/** How many of a map's papers a person named (migration 023, issue #198).
 *
 *  **Zero here is a real zero on every map, and there is no absent case.** A map
 *  with no rows in `map_anchor_papers` had no paper named by a person, and that
 *  is equally true of a map built before this shipped and of one built after it
 *  with the field left empty. That is why these are plain counts while the pass
 *  figures beside them are all nullable: "no second pass ran" and "a second pass
 *  ran and read nothing" are different facts with identical counts, and nothing
 *  like that exists here.
 *
 *  `named_papers` is null rather than empty when nobody was named, so the page
 *  can print a sentence without inspecting the count. The actor is deliberately
 *  NOT selected: the view publishes it for `pipeline/map_report.py`, whose reader
 *  is the Operator, and a login has no business travelling to a public page to
 *  support a sentence that says "the person who requested it". */
export type AnchorFigures = {
  papers_named: number;
  papers_named_read: number;
  papers_named_defining: number;
  papers_named_linked: number;
  named_papers: AnchorPaper[] | null;
};

/** One step of the build that produced a map, and what it spent (migration 024,
 *  issue #47).
 *
 *  `spend_usd` is null when the step printed no cost line at all, which is what
 *  most steps of a build do — fetching, text extraction, the audit, grounding —
 *  and is also what a step that stopped reporting its spend looks like. **Neither
 *  may be rendered as US$0.00.** A step that did print a figure of zero (Stage C
 *  with every label already cached prints one deliberately) carries
 *  `spend_lines >= 1` and a real zero, and the pair is what separates them. */
export type StageSpend = {
  stage_no: number;
  stage: string;
  /** 1, 2, or null for a step belonging to neither pass. */
  build_pass: number | null;
  spend_usd: number | null;
  spend_lines: number;
  seconds: number | null;
};

/** What each step of the build spent (migration 024, issue #47).
 *
 *  **Every count is nullable and none of them is ever coalesced**, for the pass
 *  figures' reason rather than the anchor figures' one: a map with no step record
 *  is a map built before this record existed, and "this build spent nothing" is
 *  the wrong reading of it by the widest possible margin. There is no such thing
 *  as a build that ran zero steps, so a zero here could only ever mean absence,
 *  and the view returns null instead. `stage_record_basis` is the words for it
 *  and is never blank, the way `run_cost_basis` is.
 *
 *  Within a recorded build the zeros are real: `stages_with_no_cost_line` counts
 *  steps that ran and printed nothing, which is a measurement of how much of the
 *  build the cost figure can see at all.
 *
 *  `stages_pass_one + stages_pass_two + stages_outside_passes = stages_recorded`
 *  and the three spend subtotals sum to `stage_spend_usd`, both by construction:
 *  the view carries the pass as a column rather than as a filter over separate
 *  scans. A map where either fails has a join defect.
 *
 *  **`stage_wall_clock` is the time in the recorded steps and not the run's
 *  time.** The step that writes this record runs inside the build, so it cannot
 *  time itself or the publish that follows it; `run_wall_clock` is the run. */
export type StageFigures = {
  stages_recorded: number | null;
  stages_with_a_cost: number | null;
  stages_with_no_cost_line: number | null;
  stage_spend_usd: number | null;
  stage_wall_clock: number | null;
  stages_pass_one: number | null;
  stages_pass_two: number | null;
  stages_outside_passes: number | null;
  pass_one_spend_usd: number | null;
  pass_two_spend_usd: number | null;
  spend_outside_passes: number | null;
  costliest_stage: string | null;
  costliest_stage_usd: number | null;
  costliest_stage_share: number | null;
  /** Never blank: either the sentence saying there is no step record, or the one
   *  saying where these figures came from. */
  stage_record_basis: string;
  /** Null only when nothing is recorded, so the page can print a sentence
   *  without inspecting the counts. */
  stages: StageSpend[] | null;
};

/** One published version of a map's concept (migration 025, issue #209).
 *
 *  `curatorial_edits` is a count of THIS version's own hand edits and is never
 *  added to another version's. #212 rules that an edit stays on the version it
 *  was made against, because Stage C names concept-states positionally
 *  (decision 20) and `n3` in two versions need not denote the same meaning, so a
 *  total across versions would be a number about nothing. Zero is a real zero on
 *  every version, like the named-paper counts and unlike the pass counts: the
 *  count is over `user_edits`, which is an array that is there or empty. */
export type VersionSibling = {
  genealogy_id: number;
  version: number;
  prompt_version: string;
  is_current: boolean;
  /** ISO, normalised at the boundary; see `isoOrNull`. Null on a version that
   *  has not been replaced AND on one that was replaced without the date being
   *  written, which are different facts. `is_current` is what separates them and
   *  neither is ever inferred from the other — migration 025's header carries the
   *  argument. */
  superseded_at: string | null;
  curatorial_edits: number;
};

/** Which version of its concept a map is, and where it stands (migration 025,
 *  issue #209, designing F4/#32).
 *
 *  `siblings` is every PUBLISHED version of this concept, oldest first, and
 *  always contains this map. A build that died leaves a `running` row holding a
 *  version number and it is absent from here, so `version` can exceed
 *  `siblings.length` and the page must never print "version 3 of 2": what is
 *  published and what was numbered are two counts, and the page names the one it
 *  is showing. Abandoned rows are #211's reading, not this page's.
 *
 *  **The whole of this is absent, not zeroed, when migration 025 has not landed
 *  on this deployment** — see `versionsFor`. "Version 1 of 1" is a claim, and a
 *  page that cannot read the columns must not make it.
 *
 *  **Not `MapVersions` in `lib/genealogy.ts`, and the difference is the set of
 *  rows rather than a second opinion about the facts.** That one hangs off
 *  `getMapRow` and answers about the map a page is showing, so its siblings carry
 *  an id, a number and a flag — everything the version line needs. This one has
 *  to answer for every map on the report at once, including each comparison
 *  map's own standing, and its siblings additionally carry the date, the prompt
 *  version and the count of hand edits, because the report prints a row per
 *  version and says which of them somebody curated. Reusing the other would cost
 *  a round trip per map and still not answer. The two agree on the underlying
 *  facts by reading the same three columns of the same table. */
export type VersionFigures = {
  version: number;
  is_current: boolean;
  superseded_at: string | null;
  curatorial_edits: number;
  siblings: VersionSibling[];
};

export type MapReport = {
  genealogy_id: number;
  concept: string;
  prompt_version: string;
  status: string;

  papers_with_a_reading: number;
  papers_defining: number;
  papers_not_defining: number;

  definitions_verified: number;
  definitions_inferred: number;
  definitions_stale: number;
  definitions_verified_share: number | null;
  edges_total: number;
  edges_verified: number;
  edges_inferred: number;
  edges_stale: number;
  edges_verified_share: number | null;

  quote_slots: number;
  quote_slots_empty: number;
  distinct_quote_strings: number;
  distinct_papers_on_edges: number;
  most_repeated_quote_uses: number | null;

  nodes_total: number;
  nodes_unreadable: number;
  nodes_with_one_member: number;
  nodes_with_one_member_share: number | null;
  nodes_with_no_edge_to_another_node: number;
  largest_node_id: string | null;
  largest_node_members: number | null;
  largest_node_edges: number;
  largest_node_edges_share: number | null;
  node_pairs: number;
  node_pairs_disagreeing: number;
  edges_on_disagreeing_pairs: number;
  edges_on_disagreeing_pairs_share: number | null;
  edges_within_one_node: number;

  year_min: number | null;
  year_p25: number | null;
  year_median: number | null;
  year_p75: number | null;
  year_max: number | null;
  year_counts: Record<string, number> | null;
  papers_with_no_year: number;

  runs_recorded: number;
  run_cost_usd: number | null;
  run_cost_basis: string;
  run_wall_clock: number | null;
  requester_wait: number | null;

  buckets: ReportBucket[];
  /** **NULL is not an empty mix.** It means migration 017 has not landed on this
   *  deployment yet and the counts could not be read at all; an empty array
   *  would be a map with no kinds of link, which is a different claim and one
   *  the view never makes (it emits six rows for a map with no relationships,
   *  each reading zero). The page prints words for the NULL and never a zero. */
  types: ReportTypeCount[] | null;
  /** **NULL is not a map that read nothing.** Same rule as `types` above: it
   *  means migration 019 has not landed on this deployment yet and the year
   *  series over the papers read could not be read at all. The view emits a row
   *  for every map, including one that has read nothing, so a missing row means
   *  the read did not happen and the page prints words rather than a zero. */
  reading: ReadYears | null;
  /** **NULL is not a map built in one pass.** Same rule again: it means
   *  migration 020 has not landed on this deployment yet. The view emits a row
   *  for every map, and a map built in one pass carries a row saying so in
   *  words, so a missing row means the read did not happen. */
  passes: PassFigures | null;
  /** **NULL is not a map nobody named a paper for.** Same rule again: it means
   *  migration 023 has not landed on this deployment yet. The view emits a row
   *  for every map, and a map nobody named a paper for carries a row of zeroes,
   *  so a missing row means the read did not happen and the page says that
   *  rather than claiming nobody was named. */
  anchors: AnchorFigures | null;
  /** **NULL is not a build that spent nothing.** Same rule again: it means
   *  migration 024 has not landed on this deployment yet. The view emits a row
   *  for every map, and a map with no step record carries a row whose counts are
   *  null and whose basis says so in words, so a missing row means the read did
   *  not happen. */
  stages: StageFigures | null;
  /** **NULL is not a map with one version.** Same rule again, with a different
   *  relation behind it: it means migration 025 has not landed on this
   *  deployment yet, so `genealogies.version` could not be read at all. Every
   *  published map has a version once the migration is applied — the backfill
   *  made the four existing maps version 1, current — so a null here is the
   *  deploy window and never a fact about the map. */
  versions: VersionFigures | null;
};

/** Named, in the view's own order, so the shape of this list and the shape of
 *  `COLUMNS` in `pipeline/map_report.py` can be compared without running either. */
const COLUMNS = `genealogy_id, concept, prompt_version, status,
  papers_with_a_reading, papers_defining, papers_not_defining,
  definitions_verified, definitions_inferred, definitions_stale,
  edges_total, edges_verified, edges_inferred, edges_stale,
  definitions_verified_share, edges_verified_share,
  quote_slots, quote_slots_empty, distinct_quote_strings,
  distinct_papers_on_edges, most_repeated_quote_uses,
  nodes_total, nodes_unreadable, nodes_with_one_member,
  nodes_with_no_edge_to_another_node, nodes_with_one_member_share,
  largest_node_id, largest_node_members, largest_node_edges,
  largest_node_edges_share, node_pairs, node_pairs_disagreeing,
  edges_on_disagreeing_pairs, edges_on_disagreeing_pairs_share,
  edges_within_one_node,
  year_min, year_p25, year_median, year_p75, year_max, year_counts,
  papers_with_no_year,
  runs_recorded, run_cost_usd, run_cost_basis, run_wall_clock, requester_wait`;

function shape(r: Record<string, unknown>, buckets: ReportBucket[],
               types: ReportTypeCount[] | null,
               reading: ReadYears | null,
               passes: PassFigures | null,
               anchors: AnchorFigures | null,
               stages: StageFigures | null,
               versions: VersionFigures | null): MapReport {
  const n = (k: string) => num(r[k]) ?? 0;      // counts: the view coalesces these
  const m = (k: string) => num(r[k]);           // measurements: absence is meaningful
  return {
    genealogy_id: Number(r.genealogy_id),
    concept: String(r.concept),
    prompt_version: String(r.prompt_version),
    status: String(r.status),
    papers_with_a_reading: n("papers_with_a_reading"),
    papers_defining: n("papers_defining"),
    papers_not_defining: n("papers_not_defining"),
    definitions_verified: n("definitions_verified"),
    definitions_inferred: n("definitions_inferred"),
    definitions_stale: n("definitions_stale"),
    definitions_verified_share: m("definitions_verified_share"),
    edges_total: n("edges_total"),
    edges_verified: n("edges_verified"),
    edges_inferred: n("edges_inferred"),
    edges_stale: n("edges_stale"),
    edges_verified_share: m("edges_verified_share"),
    quote_slots: n("quote_slots"),
    quote_slots_empty: n("quote_slots_empty"),
    distinct_quote_strings: n("distinct_quote_strings"),
    distinct_papers_on_edges: n("distinct_papers_on_edges"),
    most_repeated_quote_uses: m("most_repeated_quote_uses"),
    nodes_total: n("nodes_total"),
    nodes_unreadable: n("nodes_unreadable"),
    nodes_with_one_member: n("nodes_with_one_member"),
    nodes_with_one_member_share: m("nodes_with_one_member_share"),
    nodes_with_no_edge_to_another_node: n("nodes_with_no_edge_to_another_node"),
    largest_node_id: r.largest_node_id === null ? null : String(r.largest_node_id),
    largest_node_members: m("largest_node_members"),
    largest_node_edges: n("largest_node_edges"),
    largest_node_edges_share: m("largest_node_edges_share"),
    node_pairs: n("node_pairs"),
    node_pairs_disagreeing: n("node_pairs_disagreeing"),
    edges_on_disagreeing_pairs: n("edges_on_disagreeing_pairs"),
    edges_on_disagreeing_pairs_share: m("edges_on_disagreeing_pairs_share"),
    edges_within_one_node: n("edges_within_one_node"),
    year_min: m("year_min"),
    year_p25: m("year_p25"),
    year_median: m("year_median"),
    year_p75: m("year_p75"),
    year_max: m("year_max"),
    year_counts: (r.year_counts ?? null) as Record<string, number> | null,
    papers_with_no_year: n("papers_with_no_year"),
    runs_recorded: n("runs_recorded"),
    // Not `n()`. A cost nobody recorded must arrive here as null and be printed
    // as words, never as 0.
    run_cost_usd: m("run_cost_usd"),
    run_cost_basis: String(r.run_cost_basis),
    run_wall_clock: m("run_wall_clock"),
    requester_wait: m("requester_wait"),
    buckets,
    types,
    reading,
    passes,
    anchors,
    stages,
    versions,
  };
}

async function bucketsFor(ids: number[]): Promise<Map<number, ReportBucket[]>> {
  if (!ids.length) return new Map();
  const rows = (await sql`
    SELECT genealogy_id, unit, source, total, verified, inferred, stale
    FROM map_report_by_source
    WHERE genealogy_id = ANY(${ids})
    ORDER BY unit, source
  `) as Record<string, unknown>[];
  const out = new Map<number, ReportBucket[]>();
  for (const r of rows) {
    const id = Number(r.genealogy_id);
    if (!out.has(id)) out.set(id, []);
    out.get(id)!.push({
      unit: r.unit as "definition" | "edge",
      source: String(r.source),
      total: num(r.total) ?? 0,
      verified: num(r.verified) ?? 0,
      inferred: num(r.inferred) ?? 0,
      stale: num(r.stale) ?? 0,
    });
  }
  return out;
}

/**
 * The mix of kinds of link, per map (migration 017, issue #162).
 *
 * **Guarded, because this migration lands after the app that reads it.** A push
 * to `master` deploys Vercel and Render at once and Render's pre-deploy is what
 * runs the migration, so for a few minutes the app is live against a schema one
 * migration behind — which CLAUDE.md requires it to tolerate and RUNBOOK.md says
 * to handle with #92's fallback. Without the probe, Postgres raises
 * `UndefinedTable` for a statement naming a relation that is not there and the
 * whole report page 500s, taking every figure with it to add one.
 *
 * **The probe is unqualified, and that is the correction #92 earned.**
 * `listGenealogies` asks `to_regclass('public.map_report')` while its query says
 * `FROM map_report`, so the probe is more specific than the thing it guards: any
 * schema arrangement it does not name reads as absence, and the page would then
 * print words about a view that is right there. Written unqualified, the probe
 * resolves the name against the same `search_path` the next statement does, so
 * the two agree by construction rather than under the deployment we happened to
 * test.
 *
 * **Its answer is a snapshot and the race is a known residue, not an oversight.**
 * Two statements on an HTTP driver are two transactions, so a view dropped
 * between them still raises. That is acceptable here for the same reason it was
 * in #92: the alternative is a hard 500 on the ordinary path, and dropping a view
 * under a running deployment is not something this system does to itself.
 */
async function typesFor(ids: number[]): Promise<Map<number, ReportTypeCount[]> | null> {
  const [probe] = (await sql`
    SELECT to_regclass('map_report_by_type') IS NOT NULL AS reported
  `) as { reported: boolean }[];
  if (!probe?.reported) return null;
  if (!ids.length) return new Map();
  // Ordered by the view's own rank, so the order of the six lives in the
  // migration and nowhere else. NULLS LAST puts a kind the taxonomy does not
  // contain after the ones it does, which is where a reader expects it.
  const rows = (await sql`
    SELECT genealogy_id, edge_type, taxonomy_rank, edges, edges_share
    FROM map_report_by_type
    WHERE genealogy_id = ANY(${ids})
    ORDER BY genealogy_id, taxonomy_rank NULLS LAST, edge_type
  `) as Record<string, unknown>[];
  const out = new Map<number, ReportTypeCount[]>();
  for (const r of rows) {
    const id = Number(r.genealogy_id);
    if (!out.has(id)) out.set(id, []);
    out.get(id)!.push({
      edge_type: String(r.edge_type),
      taxonomy_rank: num(r.taxonomy_rank),
      edges: num(r.edges) ?? 0,
      // A measurement, not a count: the view returns NULL when the map has no
      // relationships to be a share of, and the page prints words for it.
      edges_share: num(r.edges_share),
    });
  }
  return out;
}

/**
 * The year series over every paper the map read (migration 019, issue #182).
 *
 * **Guarded exactly like `typesFor` above, and for the same reason**: this
 * migration lands after the app that reads it, because a push deploys Vercel and
 * Render at once and Render's pre-deploy is what applies it. Without the probe,
 * Postgres raises `UndefinedTable` for a statement naming a relation that is not
 * there and the whole report page 500s to add two figures. The probe is
 * unqualified so that it resolves the name against the same `search_path` the
 * next statement does (#92's correction), and its answer is a snapshot, so a
 * view dropped between the two statements still raises — a known residue, not an
 * oversight.
 *
 * **This one is a fourth view rather than four columns on `map_report`
 * precisely so that it can be guarded.** A missing column cannot be: `COLUMNS`
 * above names every one in a single statement, so the report page would 500 for
 * the minutes between the two deploys. Migration 019's header carries the whole
 * argument.
 */
async function readYearsFor(ids: number[]): Promise<Map<number, ReadYears> | null> {
  const [probe] = (await sql`
    SELECT to_regclass('map_report_read_years') IS NOT NULL AS reported
  `) as { reported: boolean }[];
  if (!probe?.reported) return null;
  if (!ids.length) return new Map();
  const rows = (await sql`
    SELECT genealogy_id, read_year_min, read_year_max, read_year_counts,
           papers_read_with_no_year, recent_window_start, recent_window_end,
           papers_read_recent, papers_defining_recent
    FROM map_report_read_years
    WHERE genealogy_id = ANY(${ids})
  `) as Record<string, unknown>[];
  const out = new Map<number, ReadYears>();
  for (const r of rows) {
    out.set(Number(r.genealogy_id), {
      // Measurements: a map that read no dated paper has no earliest and no
      // latest year, and the page prints words for that rather than a year.
      read_year_min: num(r.read_year_min),
      read_year_max: num(r.read_year_max),
      read_year_counts: (r.read_year_counts ?? null) as Record<string, number> | null,
      papers_read_with_no_year: num(r.papers_read_with_no_year) ?? 0,
      recent_window_start: num(r.recent_window_start),
      recent_window_end: num(r.recent_window_end),
      papers_read_recent: num(r.papers_read_recent) ?? 0,
      papers_defining_recent: num(r.papers_defining_recent) ?? 0,
    });
  }
  return out;
}

/**
 * Which pass of the build read each paper (migration 020, issue #193).
 *
 * **Guarded exactly like `typesFor` and `readYearsFor` above, and for the same
 * reason**: the migration lands after the app that reads it, because a push
 * deploys Vercel and Render at once and Render's pre-deploy is what applies it.
 * The probe is unqualified so it resolves the name against the same
 * `search_path` the next statement does (#92's correction), and its answer is a
 * snapshot, so a view dropped between the two statements still raises — a known
 * residue, not an oversight.
 *
 * **One probe covers three new relations, and that is a decision.** Migration
 * 020 creates `map_pass_papers`, `map_pass_build` and `map_report_passes`, and
 * only the last is read here; `migrate.py` applies each file in one transaction,
 * so a half-applied migration is impossible and probing the one name this
 * statement uses is exact rather than approximate.
 *
 * **`pass_two_rank_bands` is not read here.** It is the ladder that says whether
 * pass two reserved more seats than it had papers worth reading, which is a
 * question for whoever sets the seat count and not for someone reading a map.
 * It prints in `pipeline/map_report.py`, which is the same page/command subset
 * "quote slots" has sat in since #108.
 */
async function passesFor(ids: number[]): Promise<Map<number, PassFigures> | null> {
  const [probe] = (await sql`
    SELECT to_regclass('map_report_passes') IS NOT NULL AS reported
  `) as { reported: boolean }[];
  if (!probe?.reported) return null;
  if (!ids.length) return new Map();
  const rows = (await sql`
    SELECT genealogy_id, passes_recorded, pass_two_outcome, pass_two_seats,
           pass_two_candidates, pass_two_candidates_cleared,
           papers_read_pass_one, papers_read_pass_two, papers_read_pass_unmarked,
           papers_defining_pass_two, papers_linking_into_pass_one
    FROM map_report_passes
    WHERE genealogy_id = ANY(${ids})
  `) as Record<string, unknown>[];
  const out = new Map<number, PassFigures>();
  for (const r of rows) {
    out.set(Number(r.genealogy_id), {
      // Every one of these is `num()` and never `?? 0`: on every map that
      // exists today they are null, and a zero here would say a second pass ran
      // and read nothing.
      passes_recorded: num(r.passes_recorded),
      pass_two_outcome: String(r.pass_two_outcome),
      pass_two_seats: num(r.pass_two_seats),
      pass_two_candidates: num(r.pass_two_candidates),
      pass_two_candidates_cleared: num(r.pass_two_candidates_cleared),
      papers_read_pass_one: num(r.papers_read_pass_one),
      papers_read_pass_two: num(r.papers_read_pass_two),
      papers_read_pass_unmarked: num(r.papers_read_pass_unmarked),
      papers_defining_pass_two: num(r.papers_defining_pass_two),
      papers_linking_into_pass_one: num(r.papers_linking_into_pass_one),
    });
  }
  return out;
}

/**
 * How many of each map's papers a person named (migration 023, issue #198).
 *
 * **Guarded exactly like `typesFor`, `readYearsFor` and `passesFor` above, and
 * for the same reason**: the migration lands after the app that reads it, because
 * a push deploys Vercel and Render at once and Render's pre-deploy is what
 * applies it. The probe is unqualified so it resolves the name against the same
 * `search_path` the next statement does (#92's correction), and its answer is a
 * snapshot, so a view dropped between the two statements still raises — a known
 * residue, not an oversight.
 *
 * **`named_by` and `named_by_asserted` are on the view and are not selected
 * here.** The disclosure a reader is owed is "N of this map's papers were named
 * by the person who requested it", which needs no login to be true, and a login
 * selected here would be shipped to every browser that opens the page to support
 * a sentence that does not use it. The Operator reads it through
 * `pipeline/map_report.py`, which needs the read-only connection string to run at
 * all.
 */
async function anchorsFor(ids: number[]): Promise<Map<number, AnchorFigures> | null> {
  const [probe] = (await sql`
    SELECT to_regclass('map_report_anchors') IS NOT NULL AS reported
  `) as { reported: boolean }[];
  if (!probe?.reported) return null;
  if (!ids.length) return new Map();
  const rows = (await sql`
    SELECT genealogy_id, papers_named, papers_named_read, papers_named_defining,
           papers_named_linked, named_papers
    FROM map_report_anchors
    WHERE genealogy_id = ANY(${ids})
  `) as Record<string, unknown>[];
  const out = new Map<number, AnchorFigures>();
  for (const r of rows) {
    out.set(Number(r.genealogy_id), {
      // `?? 0` is right here and wrong on the pass figures four functions up,
      // and the difference is the whole reason this block exists: the view
      // counts rows, so every one of these is a genuine zero on a map nobody
      // named a paper for. There is no "nothing recorded it" state to collapse.
      papers_named: num(r.papers_named) ?? 0,
      papers_named_read: num(r.papers_named_read) ?? 0,
      papers_named_defining: num(r.papers_named_defining) ?? 0,
      papers_named_linked: num(r.papers_named_linked) ?? 0,
      named_papers: (r.named_papers ?? null) as AnchorPaper[] | null,
    });
  }
  return out;
}

/**
 * What each step of each map's build spent (migration 024, issue #47).
 *
 * **Guarded exactly like the four functions above, and for the same reason**: the
 * migration lands after the app that reads it, because a push deploys Vercel and
 * Render at once and Render's pre-deploy is what applies it. The probe is
 * unqualified so it resolves the name against the same `search_path` the next
 * statement does (#92's correction), and its answer is a snapshot, so a view
 * dropped between the two statements still raises — a known residue, not an
 * oversight.
 *
 * **`stage_record_run_id` is on the view and is not selected here.** It says
 * which queued request these steps were recorded from, which is what an Operator
 * needs to tell whether the breakdown and `run_cost_usd` describe the same run;
 * a reader of a map is owed neither the id nor the queue it came from.
 * `pipeline/map_report.py` reads it, the way it reads `named_by`.
 */
async function stagesFor(ids: number[]): Promise<Map<number, StageFigures> | null> {
  const [probe] = (await sql`
    SELECT to_regclass('map_report_stages') IS NOT NULL AS reported
  `) as { reported: boolean }[];
  if (!probe?.reported) return null;
  if (!ids.length) return new Map();
  const rows = (await sql`
    SELECT genealogy_id, stages_recorded, stages_with_a_cost,
           stages_with_no_cost_line, stage_spend_usd, stage_wall_clock,
           stages_pass_one, stages_pass_two, stages_outside_passes,
           pass_one_spend_usd, pass_two_spend_usd, spend_outside_passes,
           costliest_stage, costliest_stage_usd, costliest_stage_share,
           stage_record_basis, stages
    FROM map_report_stages
    WHERE genealogy_id = ANY(${ids})
  `) as Record<string, unknown>[];
  const out = new Map<number, StageFigures>();
  for (const r of rows) {
    out.set(Number(r.genealogy_id), {
      // `num()` throughout and never `?? 0`, like the pass figures and unlike
      // the anchor figures: every one of these is null on a map built before
      // this record existed, and a zero would report a build that ran no steps
      // and spent nothing.
      stages_recorded: num(r.stages_recorded),
      stages_with_a_cost: num(r.stages_with_a_cost),
      stages_with_no_cost_line: num(r.stages_with_no_cost_line),
      stage_spend_usd: num(r.stage_spend_usd),
      stage_wall_clock: num(r.stage_wall_clock),
      stages_pass_one: num(r.stages_pass_one),
      stages_pass_two: num(r.stages_pass_two),
      stages_outside_passes: num(r.stages_outside_passes),
      pass_one_spend_usd: num(r.pass_one_spend_usd),
      pass_two_spend_usd: num(r.pass_two_spend_usd),
      spend_outside_passes: num(r.spend_outside_passes),
      costliest_stage: r.costliest_stage === null || r.costliest_stage === undefined
        ? null : String(r.costliest_stage),
      costliest_stage_usd: num(r.costliest_stage_usd),
      costliest_stage_share: num(r.costliest_stage_share),
      stage_record_basis: String(r.stage_record_basis),
      stages: (r.stages ?? null) as StageSpend[] | null,
    });
  }
  return out;
}

/** `timestamptz` arrives as a `Date` from the driver's type parsers and as a
 *  string from anything that does not apply them, and this page prints a date, so
 *  the two are normalised to one ISO string here at the boundary — the rule
 *  `num()` follows for numbers, and for the same reason. Anything else, including
 *  an unparseable string, becomes null and the page prints words: a date this
 *  file could not read must not reach the reader as a wrong date. */
const isoOrNull = (v: unknown): string | null => {
  if (v === null || v === undefined) return null;
  const d = v instanceof Date ? v : new Date(String(v));
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
};

/**
 * Which version of its concept each map is (migration 025, issue #209).
 *
 * **Guarded like the five functions above, and the probe is the same one that
 * decided the comparison set** — see `listMapReports`, which asks it once and
 * hands the answer down. That is the departure from the pattern and it is the
 * point: if the two asked separately they could answer differently across the
 * seconds between them, and the page would then name its comparison population
 * one way and print version figures the other way, about one map, on one screen.
 *
 * **The probe names `genealogies_current` and the query names three columns of
 * `genealogies`**, which is a wider claim than the probe makes on its face.
 * `migrate.py` applies each migration file in one transaction, so `025` either
 * added the columns AND created the view or did neither; there is no state where
 * the view exists and `version` does not. That is the same argument `passesFor`
 * makes for probing one of migration 020's three relations, and it is what makes
 * probing a relation on behalf of a column a decision rather than an oversight —
 * a missing column cannot be guarded at all (#182), which is why the view exists.
 *
 * **`getMapRow` reads the same columns behind a `try` instead, and that is not an
 * inconsistency** (#208). It has no probe available: its statement is the map's
 * own row and there is no relation whose absence stands in for the columns'. Here
 * the probe is already being paid for, because the comparison set needs the view
 * itself, so the same answer guards both and one round trip covers them.
 *
 * **It reads every published version of the concepts on the page**, not only the
 * maps being reported, because "version 2 of 3" and "version 1 carried edits and
 * this one does not" are both claims about the siblings. `user_edits` comes over
 * the wire for each of them: `listGenealogies` already fetches every published
 * map's whole edit log for the front page, so this is the same cost against a set
 * bounded by the number of concepts, and counting in SQL would put a second
 * definition of curation in the system.
 */
async function versionsFor(versioned: boolean, ids: number[]):
    Promise<Map<number, VersionFigures> | null> {
  if (!versioned) return null;
  if (!ids.length) return new Map();
  const rows = (await sql`
    SELECT g.id AS genealogy_id, g.concept, g.version, g.prompt_version,
           g.is_current, g.superseded_at,
           COALESCE(g.user_edits, '[]'::jsonb) AS user_edits
    FROM genealogies g
    WHERE g.status = ${PUBLISHED_STATUS}
      AND g.concept IN (SELECT concept FROM genealogies WHERE id = ANY(${ids}))
    ORDER BY g.concept, g.version, g.id
  `) as Record<string, unknown>[];

  const byConcept = new Map<string, VersionSibling[]>();
  const conceptOf = new Map<number, string>();
  for (const r of rows) {
    const concept = String(r.concept);
    const id = Number(r.genealogy_id);
    conceptOf.set(id, concept);
    if (!byConcept.has(concept)) byConcept.set(concept, []);
    byConcept.get(concept)!.push({
      genealogy_id: id,
      // `?? 0` would be a version nobody issued. The column is NOT NULL with a
      // default, so this can only fail if the driver hands back something
      // unparseable, and 0 is at least visibly not a version number.
      version: num(r.version) ?? 0,
      prompt_version: String(r.prompt_version),
      is_current: r.is_current === true,
      superseded_at: isoOrNull(r.superseded_at),
      curatorial_edits: curatorialEdits(r.user_edits).length,
    });
  }

  const out = new Map<number, VersionFigures>();
  for (const [id, concept] of conceptOf) {
    const siblings = byConcept.get(concept)!;
    const mine = siblings.find((s) => s.genealogy_id === id)!;
    out.set(id, {
      version: mine.version,
      is_current: mine.is_current,
      superseded_at: mine.superseded_at,
      curatorial_edits: mine.curatorial_edits,
      siblings,
    });
  }
  return out;
}

/**
 * Every map's report, newest map first.
 *
 * The page needs all of them rather than one, because each figure is published
 * beside the same figure for the other maps: with two maps there is no
 * distribution to take a quantile from, so the only honest reference points are
 * the other maps themselves, and the sample size is the length of this array —
 * `count(*)` over the view — never a literal written into a page that would age
 * the moment a third map exists.
 *
 * **Published maps only** (issue #194, completing #168). This was the fourth
 * read path and the one #168 left open, and it leaked an unpublished map twice
 * over, because this one function answers both questions the report page asks.
 * The map named in the URL is found in this array — so an unfinished map's own
 * report rendered — and every *other* map on the page is the rest of this same
 * array, so an unfinished map appeared with its half-built figures as a
 * reference point on every other map's report, on every build, from the moment
 * Stage C wrote its row. The page needs no conditional for either: it already
 * 404s when the id is not in what this returns, which is how it has always
 * handled an id nobody minted.
 *
 * The predicate is `PUBLISHED_STATUS` imported from `lib/genealogy.ts` rather
 * than the string spelled again here. Publication is one fact; a second copy is
 * a second thing to change when the word does, and a page that disagreed with
 * `/` about which maps exist is precisely the defect. `map_report.status` is
 * `genealogies.status` selected straight through by migration 016's view, so
 * this is the same column the other three read functions test.
 *
 * **And current maps only, as of issue #208, which is the same lesson one turn
 * on.** #194's finding was that a leak is always in two places — the map's own
 * report, and the map as everybody else's reference point — and versions make
 * the second one arrive without the first. "The other maps in this system" has
 * to mean current maps: if superseded versions join the set, a concept rebuilt
 * three times contributes three points, `n` inflates, and every comparison on
 * the page silently weights concepts by how often we happened to rebuild them.
 * That is a figure moving for a reason that is about our operations rather than
 * about the literature.
 *
 * **The subject and the comparison set part company here, and #209 is where
 * that landed.** A superseded version renders in full at its own address
 * (#208), report included, so the map named in the URL must be fetchable by id
 * whether or not it is current, while the maps it is compared against must not
 * be. #208 shipped one filter standing in for both, which would have kept a
 * superseded version's own report out of what this returns; the split below
 * replaces it.
 *
 * **`n` therefore counts published maps**, which is what the page's "N of the M
 * maps in this system" should always have meant. `pipeline/map_report.py` still
 * reads every map, unfiltered and with each map's status printed in its own
 * header: it is the Operator's instrument and being able to see a map that is
 * mid-build is most of its job. The two commands can still not disagree about a
 * figure for a map they both show; the command shows more maps, deliberately,
 * the same way `check_map.py` does.
 *
 * ── One subject, one point per concept beside it (issue #209) ───────────────
 *
 * **This function answers two questions and they now have two different rules**,
 * which is the whole of #209. The page finds the map named in the URL inside what
 * this returns, and it takes every OTHER element of the same array as that map's
 * reference points. Under versioned maps (#206, #207) those two need opposite
 * predicates:
 *
 * - **the subject** is fetched by id and may be any PUBLISHED version, current or
 *   superseded, because #208 keeps a cited version readable at its own address
 *   for ever and a version whose report 404s is a version nobody can check;
 * - **the comparison set is one map per concept: the current version of each**,
 *   and it excludes the subject's concept entirely rather than only the subject's
 *   row.
 *
 * **Excluding the concept and not just the row is the load-bearing part.** If a
 * concept rebuilt three times contributed three points, `n` would inflate and
 * every figure on every other map's report would silently weight concepts by how
 * often they were rebuilt. And if only the subject's own row were excluded, a
 * superseded version's report would carry the current version of ITSELF under the
 * heading "the other maps in this system", which is both a false population and a
 * different comparison set from the one the current version sees — where the
 * design requires the two to be identical. So: `n` is the number of concepts, on
 * every version's report, for ever.
 *
 * `status = ${PUBLISHED_STATUS}` stays exactly where #194 put it and governs
 * both halves. Currency is a second, narrower test layered on it for the
 * comparison half only, never a replacement, so a `running` build stays
 * invisible whether or not anyone remembered the currency filter.
 *
 * **A superseded version therefore compares against today's maps and not against
 * the maps that existed when it was built**, and the page says so in a line,
 * because the alternative reading would be false: nothing stores what those
 * figures were on a past date, and reconstructing them would be a derived value
 * with no recomputer.
 *
 * **The probe, and what the fallback is and is not.** Vercel deploys the app
 * minutes before Render's pre-deploy applies the migration (decision 31), so
 * `genealogies_current` may not be there yet; the app then reads `status =
 * ${PUBLISHED_STATUS}` alone, which before migration 025 returns precisely the
 * same set, because there is exactly one published row per concept. The probe is
 * unqualified so it resolves the name against the same `search_path` the next
 * statement does (#92's correction), and its answer is a snapshot, so a view
 * dropped between the two statements still raises — a known residue.
 *
 * **"Correct rather than degraded" is a claim about that window and not about
 * the branch.** Driven against a fixture holding three versions of one concept
 * with the view dropped, this fallback returns all six published rows and the
 * page reads `n = 6` with one term counted three times — the exact inflation the
 * ticket exists to prevent. That state is unreachable in the deploy window,
 * because no second version can exist until the worker that mints them has
 * deployed with the migration that creates the view; it is written down because
 * the fallback's correctness rests on that and not on anything this function
 * does, and a later change that lets the two come apart would be silent.
 *
 * **A probe here and not `edgeTotalAndReading`'s try/catch**, which is the other
 * shape this repository uses for the same window. That one asks the exact
 * question and costs no round trip, and the condition on it is that the fallback
 * still answers the page's primary question. It does not here: the fallback
 * changes the POPULATION, and a transient failure caught by a `catch` would
 * quietly widen `n` from one point per concept to one per version — the precise
 * defect this ticket exists to prevent, arriving silently, with a logged message
 * nobody reads. A probe answers false only for a relation that is genuinely
 * absent, which is the state the fallback is correct in.
 */
export async function listMapReports(subjectId: number): Promise<MapReport[]> {
  // **Does the currency view exist?** The probe #208 added, asked once and
  // handed down to `versionsFor`, so the page cannot name its comparison
  // population one way and print version figures the other.
  //
  // Unqualified, like the five probes above it, so it resolves the name against
  // the same `search_path` the next statement does (#92's correction).
  const [probe] = (await sql`
    SELECT to_regclass('genealogies_current') IS NOT NULL AS versioned
  `) as { versioned: boolean }[];
  const versioned = probe?.versioned === true;

  // `sql.unsafe` is the driver's documented escape for a raw fragment, and what
  // it is handed here is a compile-time constant in this file with no value from
  // anywhere else in it. Naming the columns in one place is what lets
  // `pipeline/map_report.py`'s list be compared with this one.
  //
  // `IS DISTINCT FROM`, not `<>`: an id nobody minted makes that subquery NULL,
  // and `concept <> NULL` is NULL, which would exclude every map and 404 a page
  // that should 404 for having no subject — the right answer by the wrong route,
  // and the wrong answer the moment anything else reads this function.
  const rows = (versioned
    ? await sql`
        SELECT ${sql.unsafe(COLUMNS)} FROM map_report m
        WHERE m.status = ${PUBLISHED_STATUS}
          AND (m.genealogy_id = ${subjectId}
               OR (EXISTS (SELECT 1 FROM genealogies_current c
                            WHERE c.id = m.genealogy_id)
                   AND m.concept IS DISTINCT FROM
                       (SELECT concept FROM genealogies WHERE id = ${subjectId})))
        ORDER BY m.genealogy_id DESC
      `
    : await sql`
        SELECT ${sql.unsafe(COLUMNS)} FROM map_report m
        WHERE m.status = ${PUBLISHED_STATUS}
        ORDER BY m.genealogy_id DESC
      `) as Record<string, unknown>[];
  const ids = rows.map((r) => Number(r.genealogy_id));
  // In parallel, so #162's two extra round trips, #182's two, #193's two,
  // #198's two, #47's two and #209's one cost one wait rather than eleven on a
  // page already taking most of a second. The probe above cannot join them: the
  // statement that decides `ids` depends on its answer.
  const [buckets, types, reading, passes, anchors, stages, versions] =
    await Promise.all([
      bucketsFor(ids), typesFor(ids), readYearsFor(ids), passesFor(ids),
      anchorsFor(ids), stagesFor(ids), versionsFor(versioned, ids),
    ]);
  return rows.map((r) => {
    const id = Number(r.genealogy_id);
    // `?? []` for the buckets and `?? null` for the types, and the difference is
    // the point: a map with no definitions and no relationships genuinely has no
    // bucket rows, while the view emits six type rows for every map that exists,
    // so a map missing from `types` means the read did not happen. The year
    // series over the papers read follows the types: one row per map that
    // exists, so absence means the read did not happen. The pass figures follow
    // both.
    // The version figures follow the types too: once migration 025 is applied
    // every published map has a row, because the columns are NOT NULL with
    // defaults and the backfill made the existing maps version 1. So a map
    // missing from `versions` means the read did not happen.
    return shape(r, buckets.get(id) ?? [],
                 types === null ? null : types.get(id) ?? null,
                 reading === null ? null : reading.get(id) ?? null,
                 passes === null ? null : passes.get(id) ?? null,
                 anchors === null ? null : anchors.get(id) ?? null,
                 stages === null ? null : stages.get(id) ?? null,
                 versions === null ? null : versions.get(id) ?? null);
  });
}

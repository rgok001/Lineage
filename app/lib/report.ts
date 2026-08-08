import { sql } from "./db";

/**
 * The map report (issue #30, `[F2]`), read from migration 016's two views and
 * migration 017's third (`map_report_by_type`, issue #162).
 *
 * Nothing here computes a figure. Every number is selected from `map_report`,
 * `map_report_by_source` or `map_report_by_type`, which is the whole point of
 * the ticket: the app and
 * `pipeline/map_report.py` read one expression, so the page and the shell cannot
 * disagree about the same map, and nothing is stored, so a figure cannot survive
 * the curatorial edit that invalidates it.
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
               reading: ReadYears | null): MapReport {
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
 * Every map's report, newest map first.
 *
 * The page needs all of them rather than one, because each figure is published
 * beside the same figure for the other maps: with two maps there is no
 * distribution to take a quantile from, so the only honest reference points are
 * the other maps themselves, and the sample size is the length of this array —
 * `count(*)` over the view — never a literal written into a page that would age
 * the moment a third map exists.
 */
export async function listMapReports(): Promise<MapReport[]> {
  // `sql.unsafe` is the driver's documented escape for a raw fragment, and what
  // it is handed here is a compile-time constant in this file with no value from
  // anywhere else in it. Naming the columns in one place is what lets
  // `pipeline/map_report.py`'s list be compared with this one.
  const rows = (await sql`
    SELECT ${sql.unsafe(COLUMNS)} FROM map_report ORDER BY genealogy_id DESC
  `) as Record<string, unknown>[];
  const ids = rows.map((r) => Number(r.genealogy_id));
  // In parallel, so #162's two extra round trips and #182's two cost one wait
  // rather than four on a page already taking most of a second.
  const [buckets, types, reading] = await Promise.all([
    bucketsFor(ids), typesFor(ids), readYearsFor(ids),
  ]);
  return rows.map((r) => {
    const id = Number(r.genealogy_id);
    // `?? []` for the buckets and `?? null` for the types, and the difference is
    // the point: a map with no definitions and no relationships genuinely has no
    // bucket rows, while the view emits six type rows for every map that exists,
    // so a map missing from `types` means the read did not happen. The year
    // series over the papers read follows the types: one row per map that
    // exists, so absence means the read did not happen.
    return shape(r, buckets.get(id) ?? [],
                 types === null ? null : types.get(id) ?? null,
                 reading === null ? null : reading.get(id) ?? null);
  });
}

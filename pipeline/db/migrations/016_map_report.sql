-- 016: the map report — one row per map, computed on read, stored nowhere.
--
-- Ticket #30 ([F2]); the design is docs/design/f2-map-report.md.
--
-- A map arrives today with no account of itself. A reader is shown 287 typed
-- relationships and 88 definitions and cannot ask how much of that is
-- quote-verified, how lopsided the shape came out, how old the sources are or
-- what the run cost. Those answers are all in the map's own rows; nothing put
-- them in one place.
--
-- Two constraints from the ticket shape everything below and neither is
-- stylistic.
--
-- **Nothing is stored.** No table, no column, no MATERIALIZED, no job, no
-- backfill. A quality figure written to a column survives the curatorial edit
-- that invalidates it and is then a lie with a timestamp. `CREATE VIEW` writes
-- no row, takes no rewrite lock and is reversed by
--   DROP VIEW map_report; DROP VIEW map_report_by_source;
--
-- **No threshold.** The only numeric literals in this file are 0.25, 0.5 and
-- 0.75 — the quantiles that define the quartiles and the median — and 2, the
-- number of quote slots an edge has. Each of those defines a statistic; none of
-- them decides anything. With two maps there is no distribution to take a
-- quantile from, and this project has paid four times for a threshold moved
-- because a rate looked wrong (decisions 24, 25, 29). A severity colour, a
-- grade, a badge or a composite score is a threshold with the evidence removed,
-- and none of them belongs here either.
--
-- Two views, because a per-source total and a map total computed by two separate
-- expressions are two homes for one fact, and this record has already paid for
-- that pattern. `map_report`'s per-unit counts are SUMs over
-- `map_report_by_source`, so "the per-source figures add up to the map figure"
-- is true by construction rather than by test. A view on a view is inlined by
-- Postgres and both tables are in the low hundreds of rows.
--
-- **`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or
-- reorder columns**, so any later change beyond appending trailing columns is
-- `DROP VIEW ... CASCADE` then `CREATE VIEW`. Consequently no consumer may
-- `SELECT *`: `app/lib/genealogy.ts` and `pipeline/map_report.py` name every
-- column they read, so a redefinition cannot silently change what a page
-- renders.


-- ── the base: one row per (genealogy, unit, source) ────────────────────────
--
-- `unit` is 'definition' or 'edge'. Discard counts arrive as a third unit when
-- Stage D can count them (#86); a view holds no data, so that extension is a
-- DROP and a CREATE and costs nothing. That is why designing the grain in now is
-- not scaffolding.

CREATE VIEW map_report_by_source AS
WITH definition_rows AS (
    SELECT g.id AS genealogy_id,

           -- The per-source label is MEASURED FROM THE ROW, not asserted.
           -- `papers.source` does not exist yet; F7's migration adds it and
           -- **replaces this expression with `p.source` in the same migration
           -- that creates the column**. Today `papers.arxiv_id` is UNIQUE NOT
           -- NULL, so every row genuinely reports 'arxiv' and the report can
           -- truthfully say "arXiv: 88 of 88". A literal 'arxiv' would have been
           -- an assertion that cannot fail; this one can, and when F7 drops the
           -- NOT NULL a paper from another source falls into 'source not
           -- recorded' — visibly wrong rather than silently counted as arXiv.
           CASE WHEN p.id IS NULL           THEN 'no paper row'
                WHEN p.arxiv_id IS NOT NULL THEN 'arxiv'
                ELSE 'source not recorded' END AS source,

           -- THE STAMP RULE, definition side. This is not a fourth copy of the
           -- rule: it REPLACES the one that used to live in
           -- `listGenealogies`. The implementations are `stamp_state` in
           -- pipeline/common.py, `stampOf` in app/lib/stamp.ts, and this — three,
           -- exactly as before, and the SQL one is now in one place that both the
           -- app and the CLI read.
           --
           -- **One CASE producing one label per row, never three independent
           -- predicates.** That is what makes verified, inferred and stale
           -- disjoint and summing to the row count BY CONSTRUCTION. Stage E's
           -- `stats` block was the boolean, the boolean's complement and the
           -- stamp, and its three counts summed to more than the edge count
           -- (issue #59). That arithmetic must not be reproduced here.
           --
           -- The `COALESCE(..., '') = ''` tests are not decoration (issue #60).
           -- `IS NOT NULL` alone let a pair of empty-string digests satisfy
           -- `'' = ''` and counted the row **verified** on the front page, where
           -- both `stamp_state` and `stampOf` treat "" as falsy and return stale.
           -- Nothing writes an empty digest today, so it was latent, and the
           -- polarity was wrong in the one copy whose answer is a number a
           -- stranger reads.
           CASE
             WHEN COALESCE(d.quote_text_digest, '') = ''
               OR COALESCE(p.extracted_text_digest, '') = ''
               OR d.quote_text_digest IS DISTINCT FROM p.extracted_text_digest
                  THEN 'stale'
             WHEN d.quote_verified THEN 'verified'
             ELSE 'inferred'
           END AS state

    FROM genealogies g
    -- A map is (concept, prompt_version), UNIQUE since migration 007, and
    -- (paper_id, concept, prompt_version) is UNIQUE on definitions, so this join
    -- is provably single-valued per paper.
    JOIN definitions d
      ON d.concept = g.concept
     AND d.prompt_version = g.prompt_version
     AND d.defines_concept = true
    -- `definitions.paper_id` is NOT NULL with a cascading foreign key and cannot
    -- dangle, so LEFT here is uniformity rather than behaviour — measured, the
    -- result set is identical either way. It is written this way so that
    -- widening the predicate later cannot silently reintroduce the join deciding
    -- the question, which is the note `getInfluenceMap` already carries.
    LEFT JOIN papers p ON p.id = d.paper_id
),

-- Only defining papers. A negative verdict ("this paper does not define the
-- concept") is a finding and is reported beside this rather than folded in
-- (migration 003), but it carries an empty quote and is not evidence, so
-- counting it here would make the verified fraction read as a fraction of the
-- corpus while being a fraction of the definers.

edge_rows AS (
    SELECT g.id AS genealogy_id,

           -- Same measured label, once per endpoint. See the note above.
           CASE WHEN sp.id IS NULL           THEN 'no paper row'
                WHEN sp.arxiv_id IS NOT NULL THEN 'arxiv'
                ELSE 'source not recorded' END AS source_label,
           CASE WHEN tp.id IS NULL           THEN 'no paper row'
                WHEN tp.arxiv_id IS NOT NULL THEN 'arxiv'
                ELSE 'source not recorded' END AS target_label,

           -- THE STAMP RULE, edge side. The same shape over the two stamps an
           -- edge carries: either side stale makes the edge stale, because half
           -- a re-checkable edge is not a re-checkable edge. Twin of
           -- `edge_stamp_state` / `edgeStampOf`, and pinned to them by the same
           -- truth table (docs/design/recheckable-stamp.md, section 7,
           -- falsifier 5).
           CASE
             WHEN COALESCE(e.source_text_digest, '') = ''
               OR COALESCE(sp.extracted_text_digest, '') = ''
               OR e.source_text_digest IS DISTINCT FROM sp.extracted_text_digest
               OR COALESCE(e.target_text_digest, '') = ''
               OR COALESCE(tp.extracted_text_digest, '') = ''
               OR e.target_text_digest IS DISTINCT FROM tp.extracted_text_digest
                  THEN 'stale'
             WHEN e.verified THEN 'verified'
             ELSE 'inferred'
           END AS state

    FROM genealogies g
    JOIN edges e ON e.genealogy_id = g.id
    -- **Both joins to `papers` are LEFT.** `edges.source_paper_id` and
    -- `target_paper_id` are nullable and may name a row that is gone. Issues
    -- #60, #79 and #83 are three rounds of one defect: an inner join lets the
    -- join decide whether an edge exists, silently, and in the one direction
    -- that is not available — an edge whose paper is missing is certainly not
    -- verified, but it is also not nothing. A LEFT JOIN hands the CASE a NULL
    -- digest, which is exactly what `stampOf` is handed for a paper with no
    -- digest, and both call it stale. The report must not inherit the
    -- assumptions of the five inner joins #83 lists in pipeline/.
    --
    -- Neither join can drop or duplicate a row either, because both are on the
    -- papers primary key. That is what makes the bucket sums below equal
    -- `count(*)` over `edges` rather than merely resembling it.
    LEFT JOIN papers sp ON sp.id = e.source_paper_id
    LEFT JOIN papers tp ON tp.id = e.target_paper_id
),

unit_rows AS (
    SELECT genealogy_id, 'definition' AS unit, source, state
    FROM definition_rows
    UNION ALL
    -- An edge has two endpoints and may, after F7, span two sources, so grouping
    -- it by a single source is not defined. Its key is the PAIR of endpoint
    -- labels, sorted and joined: 'arxiv' today, and after F7 also 'pmc' and
    -- 'arxiv + pmc', with 'no paper row' participating like any other label.
    -- Every edge therefore lands in exactly one bucket and the buckets sum to
    -- the edge count, which is the global check that stops a per-endpoint
    -- fallback quietly swallowing a whole class of edge.
    SELECT genealogy_id, 'edge' AS unit,
           CASE WHEN source_label = target_label THEN source_label
                WHEN source_label <  target_label
                     THEN source_label || ' + ' || target_label
                ELSE target_label || ' + ' || source_label END AS source,
           state
    FROM edge_rows
)

SELECT genealogy_id,
       unit,
       source,
       count(*)                                   AS total,
       count(*) FILTER (WHERE state = 'verified') AS verified,
       count(*) FILTER (WHERE state = 'inferred') AS inferred,
       count(*) FILTER (WHERE state = 'stale')    AS stale
FROM unit_rows
GROUP BY genealogy_id, unit, source;


-- ── the report: one row per map ────────────────────────────────────────────

CREATE VIEW map_report AS

-- The verification counts, and only these, are SUMs over the base view. Every
-- other figure is computed directly from edges, definitions, papers,
-- genealogies.nodes and trace_requests.
WITH verification AS (
    SELECT genealogy_id,
           COALESCE(SUM(total)    FILTER (WHERE unit = 'definition'), 0) AS definitions_total,
           COALESCE(SUM(verified) FILTER (WHERE unit = 'definition'), 0) AS definitions_verified,
           COALESCE(SUM(inferred) FILTER (WHERE unit = 'definition'), 0) AS definitions_inferred,
           COALESCE(SUM(stale)    FILTER (WHERE unit = 'definition'), 0) AS definitions_stale,
           COALESCE(SUM(total)    FILTER (WHERE unit = 'edge'), 0)       AS edges_total,
           COALESCE(SUM(verified) FILTER (WHERE unit = 'edge'), 0)       AS edges_verified,
           COALESCE(SUM(inferred) FILTER (WHERE unit = 'edge'), 0)       AS edges_inferred,
           COALESCE(SUM(stale)    FILTER (WHERE unit = 'edge'), 0)       AS edges_stale
    FROM map_report_by_source
    GROUP BY genealogy_id
),

-- COALESCE to 0 above is a count with no population, not a measurement with no
-- value: a map with no edges has zero of them, and SUM over no rows is NULL.
-- Nothing below coalesces a MEASUREMENT — see run_cost_usd.
--
-- It is applied a SECOND time where these columns are selected, and the second
-- one is the one that matters. A map with no edges and no definitions has no row
-- in `map_report_by_source` at all, so the LEFT JOIN to this CTE yields NULL for
-- every column above and the COALESCE inside it never runs — measured, a fresh
-- map reported `edges_total` NULL, which the page would print as "not recorded"
-- about a map we know has none. Coalescing inside an aggregate protects against
-- an empty group; it does nothing about a missing group.

-- Coverage of the reading. `papers_defining` has one home, the base view, and is
-- not re-counted here; `papers_with_a_reading = papers_defining +
-- papers_not_defining` is then an identity a reader can check on the page.
--
-- **What none of these is: the corpus.** A paper selected in Stage A but never
-- fetched, or fetched but never extracted, leaves no `definitions` row at all,
-- so every figure here under-reports what the run set out to read. The page says
-- so rather than leaving it in this comment.
coverage AS (
    SELECT g.id AS genealogy_id,
           count(d.id)                                          AS papers_with_a_reading,
           count(d.id) FILTER (WHERE d.defines_concept = false)  AS papers_not_defining
    FROM genealogies g
    LEFT JOIN definitions d
      ON d.concept = g.concept AND d.prompt_version = g.prompt_version
    GROUP BY g.id
),

-- Quote reuse. An edge's two quotes ARE the two papers' Stage B definition
-- quotes by design (decision 6), so a paper appearing on 43 edges contributes
-- its one quote 43 times, and `distinct_quote_strings` far below `edges_total`
-- is structural rather than a defect. Publishing it beside
-- `distinct_papers_on_edges` is what makes it informative: the two should be
-- close, and `distinct_quote_strings` materially LOWER than
-- `distinct_papers_on_edges` means two different papers carry the same quote
-- string, which is a real finding this system currently cannot see.
quote_slot_rows AS (
    SELECT e.genealogy_id, q.quote
    FROM edges e
    -- 2: the number of quote slots an edge has. `quote_slots` is then count(*)
    -- over these rows rather than a multiplication, so it cannot disagree with
    -- what is actually counted below it.
    CROSS JOIN LATERAL (VALUES (e.source_quote), (e.target_quote)) AS q(quote)
),
quote_uses AS (
    SELECT genealogy_id, quote, count(*) AS uses
    FROM quote_slot_rows
    WHERE trim(COALESCE(quote, '')) <> ''
    GROUP BY genealogy_id, quote
),
quotes AS (
    SELECT s.genealogy_id,
           count(*)                                                    AS quote_slots,
           count(*) FILTER (WHERE trim(COALESCE(s.quote, '')) = '')     AS quote_slots_empty,
           -- Empty strings are excluded from the distinct count deliberately: a
           -- quote holding no text of the paper is not evidence (issue #57), and
           -- counting '' as a distinct quote string would manufacture
           -- distinctness out of an absence.
           count(DISTINCT s.quote) FILTER (WHERE trim(COALESCE(s.quote, '')) <> '')
                                                                       AS distinct_quote_strings
    FROM quote_slot_rows s
    GROUP BY s.genealogy_id
),
quote_max AS (
    SELECT genealogy_id, max(uses) AS most_repeated_quote_uses
    FROM quote_uses GROUP BY genealogy_id
),
endpoint_rows AS (
    SELECT e.genealogy_id, x.paper_id
    FROM edges e
    CROSS JOIN LATERAL (VALUES (e.source_paper_id), (e.target_paper_id)) AS x(paper_id)
),
endpoints AS (
    SELECT genealogy_id, count(DISTINCT paper_id) AS distinct_papers_on_edges
    FROM endpoint_rows GROUP BY genealogy_id
),

-- Shape. All of this reads `genealogies.nodes`, which is JSONB written by Stage
-- C and rewritten by the workbench and both restore scripts, so a shape change
-- breaks these figures without breaking anything else. `nodes_unreadable` is the
-- detector for that and it is on the page rather than in a log.
--
-- **Malformed nodes are dropped and counted, never guessed at and never raised
-- on.** That is the posture `node_denotation` already takes in common.py, and
-- the counting is what stops it being silent: a map whose blob is half
-- unreadable must say so rather than reporting a small, confident
-- `nodes_total`. A blob that is not an array at all is wrapped into a
-- one-element array so it lands in `nodes_unreadable` as one thing that could
-- not be read, rather than raising out of the view and taking every other figure
-- with it.
node_rows AS (
    SELECT g.id AS genealogy_id, n.value AS node
    FROM genealogies g
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(g.nodes) = 'array' THEN g.nodes
             ELSE jsonb_build_array(g.nodes) END) AS n(value)
),
node_shape AS (
    SELECT genealogy_id,
           COALESCE(jsonb_typeof(node) = 'object'
                    AND jsonb_typeof(node -> 'node_id') = 'string'
                    AND jsonb_typeof(node -> 'members') = 'array', false) AS readable,
           node ->> 'node_id' AS node_id,
           CASE WHEN jsonb_typeof(node -> 'members') = 'array'
                THEN jsonb_array_length(node -> 'members') END AS members
    FROM node_rows
),
node_stats AS (
    SELECT ns.genealogy_id,
           count(*) FILTER (WHERE ns.readable)              AS nodes_total,
           count(*) FILTER (WHERE NOT ns.readable)          AS nodes_unreadable,
           count(*) FILTER (WHERE ns.readable AND ns.members = 1)
                                                            AS nodes_with_one_member
    FROM node_shape ns
    GROUP BY ns.genealogy_id
),
-- "appears on no edge whose two node_ids differ". A self-loop does not connect a
-- node to anything, so it does not count as a link here. Equal to
-- `computeFamilies`' "Unconnected meanings" whenever every edge names two nodes
-- the map still has, which is what Stage C and the workbench maintain; the two
-- are computed differently (degree zero here, singleton union-find component
-- there) and falsifier 3 is the reading that says they have come apart. Its own
-- CTE rather than a FILTER over the aggregate above, because a correlated
-- NOT EXISTS belongs in a WHERE clause where it is plainly readable.
node_islands AS (
    SELECT ns.genealogy_id, count(*) AS nodes_with_no_edge_to_another_node
    FROM node_shape ns
    WHERE ns.readable
      AND NOT EXISTS (
          SELECT 1 FROM edges e
          WHERE e.genealogy_id = ns.genealogy_id
            AND e.source_node IS DISTINCT FROM e.target_node
            AND (e.source_node = ns.node_id OR e.target_node = ns.node_id))
    GROUP BY ns.genealogy_id
),
largest_node AS (
    SELECT DISTINCT ON (genealogy_id)
           genealogy_id, node_id AS largest_node_id, members AS largest_node_members
    FROM node_shape
    WHERE readable
    ORDER BY genealogy_id, members DESC NULLS LAST, node_id
),

-- Node pairs. **The pair is ORDERED**, because an edge means "the later paper
-- did X to the earlier one's concept" and the reverse is a different claim;
-- folding them makes agreement look like disagreement. The pair counts are
-- published beside the share for the reason decision 24 exists: a rate says
-- something is wrong and cannot say what, while "two enormous pairs carry
-- everything" and "fifty small pairs each disagree once" are different findings
-- implying different actions.
pairs AS (
    SELECT genealogy_id, source_node, target_node,
           count(*)                  AS edges_here,
           count(DISTINCT edge_type) AS types_here
    FROM edges
    GROUP BY genealogy_id, source_node, target_node
),
pair_stats AS (
    SELECT genealogy_id,
           count(*)                                        AS node_pairs,
           count(*) FILTER (WHERE types_here > 1)          AS node_pairs_disagreeing,
           COALESCE(SUM(edges_here) FILTER (WHERE types_here > 1), 0)
                                                           AS edges_on_disagreeing_pairs
    FROM pairs GROUP BY genealogy_id
),
edge_shape AS (
    SELECT e.genealogy_id,
           -- 0 by construction today: stage_d_edges.py drops every same-cluster
           -- candidate pair, so no edge can have source_node = target_node. After
           -- F3 it must be non-zero, and that is one of the four lines of this
           -- report F3's before-and-after is read from.
           count(*) FILTER (WHERE e.source_node = e.target_node) AS edges_within_one_node,
           count(*) FILTER (WHERE ln.largest_node_id IS NOT NULL
                              AND (e.source_node = ln.largest_node_id
                                OR e.target_node = ln.largest_node_id))
                                                                 AS largest_node_edges
    FROM edges e
    LEFT JOIN largest_node ln ON ln.genealogy_id = e.genealogy_id
    GROUP BY e.genealogy_id
),

-- Corpus age, over the map's defining papers. `papers.year` is the EARLIEST
-- CREDIBLE DATE — the minimum of the OpenAlex year and the year encoded in the
-- arXiv id (migration 009, after OpenAlex dated "Attention Is All You Need" to
-- 2025) — and the page says so where it prints these, because a reader will
-- otherwise read them as publication dates.
year_rows AS (
    SELECT g.id AS genealogy_id, p.year
    FROM genealogies g
    JOIN definitions d
      ON d.concept = g.concept AND d.prompt_version = g.prompt_version
     AND d.defines_concept = true
    LEFT JOIN papers p ON p.id = d.paper_id
),
year_stats AS (
    SELECT genealogy_id,
           min(year) AS year_min,
           max(year) AS year_max,
           -- 0.25, 0.5, 0.75: the quantiles that define the quartiles and the
           -- median. percentile_cont ignores NULL years, which is why the count
           -- of them is published beside these and never imputed into them.
           percentile_cont(0.25) WITHIN GROUP (ORDER BY year::double precision) AS year_p25,
           percentile_cont(0.5)  WITHIN GROUP (ORDER BY year::double precision) AS year_median,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY year::double precision) AS year_p75,
           count(*) FILTER (WHERE year IS NULL) AS papers_with_no_year
    FROM year_rows GROUP BY genealogy_id
),
year_hist AS (
    SELECT genealogy_id, jsonb_object_agg(y::text, n ORDER BY y) AS year_counts
    FROM (SELECT genealogy_id, year AS y, count(*) AS n
          FROM year_rows WHERE year IS NOT NULL
          GROUP BY genealogy_id, year) t
    GROUP BY genealogy_id
),

-- Which run. A genealogy may have several `trace_requests` rows over its life;
-- the figures below describe the most recent COMPLETE one, and `runs_recorded`
-- is published so a reader knows they describe one run out of N rather than the
-- map's whole history. With runs_recorded = 0 every cost and time cell reads
-- "not recorded", which is the state both live maps are in: `attention` and
-- `embedding` were built from the CLI and have no `trace_requests` row at all.
run_count AS (
    SELECT genealogy_id, count(*) AS runs_recorded
    FROM trace_requests
    WHERE status = 'complete' AND genealogy_id IS NOT NULL
    GROUP BY genealogy_id
),
last_run AS (
    SELECT DISTINCT ON (genealogy_id)
           genealogy_id, created_at, started_at, finished_at, progress
    FROM trace_requests
    WHERE status = 'complete' AND genealogy_id IS NOT NULL
    ORDER BY genealogy_id, finished_at DESC NULLS LAST, id DESC
)

SELECT g.id                        AS genealogy_id,
       g.concept,
       g.prompt_version,
       g.status,
       g.updated_at,

       -- coverage
       COALESCE(c.papers_with_a_reading, 0)     AS papers_with_a_reading,
       COALESCE(v.definitions_total, 0)         AS papers_defining,
       COALESCE(c.papers_not_defining, 0)       AS papers_not_defining,

       -- evidence
       COALESCE(v.definitions_verified, 0)      AS definitions_verified,
       COALESCE(v.definitions_inferred, 0)      AS definitions_inferred,
       COALESCE(v.definitions_stale, 0)         AS definitions_stale,
       COALESCE(v.edges_total, 0)               AS edges_total,
       COALESCE(v.edges_verified, 0)            AS edges_verified,
       COALESCE(v.edges_inferred, 0)            AS edges_inferred,
       COALESCE(v.edges_stale, 0)               AS edges_stale,

       -- **Every share is a NULLIF(denominator, 0) division and is absent when
       -- the denominator is zero.** A map with no edges reports its verified
       -- share as "no edges", never as 0%. Zero percent is a claim about a
       -- population; there is no population.
       COALESCE(v.definitions_verified, 0)::numeric / NULLIF(COALESCE(v.definitions_total, 0), 0)
                                                AS definitions_verified_share,
       COALESCE(v.edges_verified, 0)::numeric / NULLIF(COALESCE(v.edges_total, 0), 0)
                                                AS edges_verified_share,

       -- quote reuse
       COALESCE(q.quote_slots, 0)        AS quote_slots,
       COALESCE(q.quote_slots_empty, 0)  AS quote_slots_empty,
       COALESCE(q.distinct_quote_strings, 0) AS distinct_quote_strings,
       COALESCE(ep.distinct_papers_on_edges, 0) AS distinct_papers_on_edges,
       qm.most_repeated_quote_uses,

       -- shape
       COALESCE(ns.nodes_total, 0)             AS nodes_total,
       COALESCE(ns.nodes_unreadable, 0)        AS nodes_unreadable,
       COALESCE(ns.nodes_with_one_member, 0)   AS nodes_with_one_member,
       COALESCE(ni.nodes_with_no_edge_to_another_node, 0)
                                               AS nodes_with_no_edge_to_another_node,
       COALESCE(ns.nodes_with_one_member, 0)::numeric / NULLIF(ns.nodes_total, 0)
                                               AS nodes_with_one_member_share,
       ln.largest_node_id,
       ln.largest_node_members,
       COALESCE(es.largest_node_edges, 0)      AS largest_node_edges,
       COALESCE(es.largest_node_edges, 0)::numeric / NULLIF(COALESCE(v.edges_total, 0), 0)
                                               AS largest_node_edges_share,
       COALESCE(ps.node_pairs, 0)              AS node_pairs,
       COALESCE(ps.node_pairs_disagreeing, 0)  AS node_pairs_disagreeing,
       COALESCE(ps.edges_on_disagreeing_pairs, 0) AS edges_on_disagreeing_pairs,
       COALESCE(ps.edges_on_disagreeing_pairs, 0)::numeric / NULLIF(COALESCE(v.edges_total, 0), 0)
                                               AS edges_on_disagreeing_pairs_share,
       COALESCE(es.edges_within_one_node, 0)   AS edges_within_one_node,

       -- corpus age
       ys.year_min,
       ys.year_p25,
       ys.year_median,
       ys.year_p75,
       ys.year_max,
       yh.year_counts,
       COALESCE(ys.papers_with_no_year, 0)     AS papers_with_no_year,

       -- the run
       COALESCE(rc.runs_recorded, 0)           AS runs_recorded,

       -- **Never COALESCE this to `genealogies.spend_usd` or to 0.** That column
       -- exists and is written by nothing: it reads 0.0000 on both live maps
       -- (decision 26, issue #85). A $0.00 printed under "what this map cost" is
       -- precisely the derived value stored and allowed to age that this whole
       -- ticket is a reaction to, and it would be the single most damaging line
       -- on the page. NULL here means "not recorded" and the page prints those
       -- words.
       --
       -- The real figure is a regex scrape of the stages' stdout, kept by the
       -- worker in `trace_requests.progress`. The design's literal wording for
       -- `run_cost_basis` named the worker; this says the same thing without it,
       -- because the string is rendered to a reader and "worker" is on the
       -- standing list of internal words the interface may not use. It is only as good as the lines the
       -- stages print, and a stage that stops printing its spend silently drops
       -- out of the total with no error; the caveats are printed beside the
       -- figure and the fix is #47. The jsonb type test rather than a cast is so
       -- that a scrape holding a string, a null or an object reads "not recorded"
       -- instead of raising out of the view.
       CASE WHEN jsonb_typeof(lr.progress -> 'spend_usd') = 'number'
            THEN (lr.progress ->> 'spend_usd')::numeric END AS run_cost_usd,
       CASE WHEN jsonb_typeof(lr.progress -> 'spend_usd') = 'number'
            THEN 'from the record kept of the last completed run'
            ELSE 'not recorded' END                         AS run_cost_basis,

       -- Seconds, not an interval, so the page and the CLI receive the same
       -- number through two different drivers. `run_wall_clock` is the run;
       -- `requester_wait` is what a requester actually experienced. Both are
       -- published because ROADMAP open question 5 — whether "about fifteen
       -- minutes" is a promise or a description — is answered by exactly this
       -- pair and by nothing else in the system.
       EXTRACT(EPOCH FROM (lr.finished_at - lr.started_at))::numeric AS run_wall_clock,
       EXTRACT(EPOCH FROM (lr.finished_at - lr.created_at))::numeric AS requester_wait

FROM genealogies g
LEFT JOIN verification  v  ON v.genealogy_id  = g.id
LEFT JOIN coverage      c  ON c.genealogy_id  = g.id
LEFT JOIN quotes        q  ON q.genealogy_id  = g.id
LEFT JOIN quote_max     qm ON qm.genealogy_id = g.id
LEFT JOIN endpoints     ep ON ep.genealogy_id = g.id
LEFT JOIN node_stats    ns ON ns.genealogy_id = g.id
LEFT JOIN node_islands  ni ON ni.genealogy_id = g.id
LEFT JOIN largest_node  ln ON ln.genealogy_id = g.id
LEFT JOIN edge_shape    es ON es.genealogy_id = g.id
LEFT JOIN pair_stats    ps ON ps.genealogy_id = g.id
LEFT JOIN year_stats    ys ON ys.genealogy_id = g.id
LEFT JOIN year_hist     yh ON yh.genealogy_id = g.id
LEFT JOIN run_count     rc ON rc.genealogy_id = g.id
LEFT JOIN last_run      lr ON lr.genealogy_id = g.id;

-- Every join above is LEFT so that a map with no edges, no definitions, no nodes
-- or no recorded run still has a row on this view. A map that vanishes from its
-- own report because it has nothing to report is the join deciding the question
-- again, one level up.


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `lineage_ro` holds SELECT on the tables that existed when it was created and
-- does NOT automatically hold it on a new view, so without this the CLI fails
-- with a permission error against production while working perfectly for the
-- owner. Guarded on pg_roles so a local database that has no such role still
-- migrates.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON map_report_by_source, map_report TO lineage_ro;
    END IF;
END
$$;

-- 020: which pass of the build read a paper — one row per map, computed on
-- read, stored nowhere.
--
-- Ticket #193, instrumenting the two-stage build designed on #184, and carrying
-- the free half of #188. Sibling of `016_map_report.sql`, `017_map_report_by_type.sql`
-- and `019_map_report_read_years.sql`, and every constraint in `016`'s header
-- applies here unchanged.
--
-- **What is missing.** `019` gave the report two year series — papers read and
-- papers that define — and that pair settled F5's diagnosis. A two-stage map
-- needs one thing more: WHICH PASS a paper entered on, because that is the only
-- way to separate what the second pass bought from what the first pass would
-- have found anyway. Pass two adds papers rather than displacing them, so every
-- total on the report rises when it runs; without the split, a map that read
-- fifteen more papers and learned nothing from any of them is indistinguishable
-- from one where the second pass moved the map.
--
-- **Nothing in this schema records a paper's pass today, and this migration does
-- not add it.** The orchestration that runs the two passes is #192 and it has
-- not landed. Where the pass is stored is #192's decision and #192's migration
-- (the architect's one rule on #193: it must not be a column on `papers`, which
-- is shared across every map, because a paper's pass is a property of one build
-- and not of the paper). This file is deliberately the other half of that
-- split: it fixes the QUESTION the report asks, and leaves #192 to say where the
-- answer is kept.
--
-- The seam is two views, `map_pass_papers` and `map_pass_build`, defined below
-- with the columns the report needs and **no rows at all**. Today every figure
-- downstream of them is therefore absent, and the report says the honest thing:
-- this map was built in one pass. When #192 lands it replaces those two views —
-- `DROP VIEW` then `CREATE VIEW`, in its own migration, over wherever it decided
-- to store the pass — and every figure here lights up without this file, the
-- page or `pipeline/map_report.py` being touched. That is the whole reason the
-- seam is a pair of views rather than a pair of columns: a view is a read-shape
-- holding nothing, so writing one commits no storage and reserves no name in any
-- table.
--
-- **Absence is not zero and the four existing maps are the proof.** Every map in
-- this database was built in one pass, and none of them records that fact,
-- because nothing was recording it when they were built. So `passes_recorded` is
-- NULL for them and every count below is NULL, and both consumers print words.
-- A `COALESCE(..., 0)` anywhere here would report four maps as having run a
-- second pass that read zero papers, which is a measurement of something that
-- never happened — the #30 defect this whole report exists to avoid. Once a
-- build IS recorded, a zero is a real zero: a second pass that ran and found
-- nothing reports `papers_read_pass_two = 0` beside an outcome naming why, and
-- that distinction between "none existed" and "we could not afford them" is one
-- of the five things the design says pass two may claim.
--
-- **`pass_two_outcome` is never blank and is reader-ready text, like
-- `run_cost_basis` on `016`.** Four states are named by the design — filled,
-- under-filled, none found, abandoned at the pre-flight gate — plus the state
-- every map is in today, which is that there was no second pass. The words for
-- the four arrive through the seam so that #192 records the state and this file
-- does not enumerate a list a fifth state would go missing from; the words for
-- "no second pass" and for a build that recorded no outcome are supplied here,
-- because those are facts about this view's own reading and not about the build.
--
-- **A fifth view rather than more columns on `map_report`, for `019`'s reason
-- and not for the grain.** The grain is per map, so on grain alone these would
-- be columns. `CREATE OR REPLACE VIEW` can only append trailing columns to a
-- definition given in full, which would put `map_report`'s live definition in
-- two files with the newer silently winning; and a missing *column* cannot be
-- guarded, because `app/lib/report.ts` names every column of `map_report` in one
-- statement, so the report page would raise `UndefinedColumn` and 500 for the
-- minutes between the Vercel deploy and Render's pre-deploy migration. A missing
-- *relation* is guarded by the `to_regclass` fallback #92 earned, and the page
-- loses one block instead of a page.
--
-- **`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or
-- reorder columns**, so a later change here beyond appending trailing columns is
-- `DROP VIEW map_report_passes` then `CREATE VIEW`. Consequently no consumer may
-- `SELECT *`: `app/lib/report.ts` and `pipeline/map_report.py` name every column
-- they read. The two seam views are the exception by design — replacing them is
-- exactly what #192 does, and it must be a DROP and a CREATE, because it is
-- adding rows and not columns.
--
-- **No threshold, and the two numbers that group rows are published rather than
-- implied.** Counted with comments and string literals removed, the numeric
-- literals in this file are exactly {1, 2, 10}. `1` and `2` name the first and
-- the second pass and decide nothing about a paper. `10` is the width of the
-- selection-rank bands #188's free half asks for, and it names populations
-- ("ranks 1 to 10") rather than cutting one: it ships as
-- `pass_two_rank_band_width` beside the bands and each band carries its own
-- first and last rank, so a reader never has to know the width to read the
-- table. Nothing here grades, colours or compares anything to anything. The same
-- two checks `016`, `017` and `019` carry run over this file's own text, and both
-- were run rather than reasoned about:
--
--   sed -E 's,--.*,,' 020_map_report_passes.sql | grep -c -i '\bMATERIALIZED\b'   # 0
--   sed -E 's,--.*,,' 020_map_report_passes.sql \
--     | grep -o -E '(^|[^A-Za-z0-9_.])[0-9]+(\.[0-9]+)?([^A-Za-z0-9_]|$)' \
--     | grep -o -E '[0-9]+(\.[0-9]+)?' | sort -u          # 1 2 10
--
-- **The one figure this file must never grow.** No recency score, no freshness
-- grade, no "up to date" badge, and no single number blending any of these
-- counts. Every ingredient is a count published here separately; a blend would be
-- this tool's weighting read as a measurement, which is what decision 15 kept
-- magnitude off the screen to avoid. The request arrives the week the first
-- two-stage map lands.


-- ── the seam: where a paper's pass comes from ───────────────────────────────
--
-- Two views with the right columns and no rows. `WHERE false` is what makes them
-- empty rather than a placeholder row: a row of nulls here would be a map with an
-- unknown pass, which is a different claim from the record saying nothing.
--
-- `map_pass_papers` is per (map, paper). `definition_id` rather than `paper_id`
-- because a map's membership is its `definitions` rows for that concept and
-- prompt version — `papers` is shared across every map ever traced, and joining
-- a pass to it is the mistake the architect ruled out. `build_pass` is 1 or 2.
-- `pass_rank` is the paper's position in that pass's own selection order,
-- 1-based, and NULL where the pass did not rank; #188's ladder is taken over
-- pass two's ranking and over no other, or it measures a ranking the build does
-- not use.
CREATE VIEW map_pass_papers AS
SELECT NULL::bigint AS genealogy_id,
       NULL::bigint AS definition_id,
       NULL::int    AS build_pass,
       NULL::int    AS pass_rank
WHERE false;

-- `map_pass_build` is per map, at most one row, and **its presence is the
-- question every figure below is gated on**: a map with no row here has no
-- record of having been built in passes, which is every map today.
--
-- `pass_two_outcome` is the reader's sentence, in the four states the design
-- names. It is recorded by the build rather than derived here, because "we could
-- not afford them" and "there were none" produce identical counts and only the
-- run knows which happened. `pass_two_seats` is R, so the report can print
-- "filled X of R" without the divisor. `pass_two_candidates` and
-- `pass_two_candidates_cleared` are the citation-graph facts either side of the
-- gate: how many recent papers cite this map at all, and how many cleared both
-- signals.
CREATE VIEW map_pass_build AS
SELECT NULL::bigint AS genealogy_id,
       NULL::int    AS passes,
       NULL::text   AS pass_two_outcome,
       NULL::int    AS pass_two_seats,
       NULL::int    AS pass_two_candidates,
       NULL::int    AS pass_two_candidates_cleared
WHERE false;


CREATE VIEW map_report_passes AS

-- The band width, defined once, here, and nowhere else, in the shape `019` gives
-- its recency window: named rather than written into the arithmetic, and shipped
-- as a column so a reader is never asked to reconstruct it.
WITH band AS (
    SELECT 10 AS width
),

-- Every paper this map read, with the pass the record puts it in. `019`'s
-- `read_rows` with the seam LEFT JOINed on, and the pass carried as a column
-- rather than as a filter — which is what makes the three pass counts below sum
-- to `papers read` BY CONSTRUCTION rather than by test. A map's papers are its
-- `definitions` rows for that concept and prompt version, which is the same
-- population `016` and `019` count under the same word (#123).
--
-- **The join to `definitions` is LEFT and that is behaviour, not uniformity**:
-- a map that has read nothing still gets a row here, carrying NULLs, so it
-- appears on this view rather than vanishing from it. Every count below excludes
-- the phantom row with `definition_id IS NOT NULL`.
pass_rows AS (
    SELECT g.id AS genealogy_id,
           d.id AS definition_id,
           d.paper_id,
           COALESCE(d.defines_concept, false) AS defines_concept,
           mp.build_pass,
           mp.pass_rank
    FROM genealogies g
    LEFT JOIN definitions d
      ON d.concept = g.concept AND d.prompt_version = g.prompt_version
    LEFT JOIN map_pass_papers mp
      ON mp.genealogy_id = g.id AND mp.definition_id = d.id
),

-- Which meanings the first pass found. A "meaning" is a node of the stored
-- grouping and its members are arxiv ids (`stage_c_cluster.py` writes
-- `{node_id, label, members:[{arxiv_id, year, title}]}`), so this is the one
-- place the report crosses from `definitions` to `genealogies.nodes` and back.
--
-- Malformed nodes are dropped rather than guessed at or raised on, which is
-- `016`'s posture on the same blob; a node with no readable `node_id` cannot be
-- named by an edge either, so dropping it here cannot manufacture a link.
node_members AS (
    SELECT g.id AS genealogy_id,
           n.value ->> 'node_id' AS node_id,
           m.value ->> 'arxiv_id' AS arxiv_id
    FROM genealogies g
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(g.nodes) = 'array' THEN g.nodes
             ELSE jsonb_build_array(g.nodes) END) AS n(value)
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(n.value -> 'members') = 'array'
             THEN n.value -> 'members' ELSE '[]'::jsonb END) AS m(value)
    WHERE jsonb_typeof(n.value) = 'object'
      AND jsonb_typeof(n.value -> 'node_id') = 'string'
),

-- A meaning "found in pass one" is one holding at least one paper the first pass
-- read. It is deliberately NOT "a meaning made only of pass-one papers": Stage C
-- re-clusters over the union corpus in pass two (the design's second load-bearing
-- choice), so most meanings a two-stage map ends with hold papers from both
-- passes, and requiring purity would report almost nothing.
pass_one_nodes AS (
    SELECT DISTINCT nm.genealogy_id, nm.node_id
    FROM node_members nm
    JOIN papers p ON p.arxiv_id = nm.arxiv_id
    JOIN pass_rows pr
      ON pr.genealogy_id = nm.genealogy_id AND pr.paper_id = p.id
    WHERE pr.build_pass = 1
),

-- Does this paper carry a relationship into a meaning the first pass found?
--
-- **This is the tool's reading and both consumers label it as such.** An edge is
-- a judgement about direction and kind, unlike Stage B's verdict on whether a
-- paper defines the term; it is the closest honest figure to "the idea moved
-- recently" and it is not that claim.
--
-- Computed as a column here rather than as a FILTER over the aggregate below,
-- because an aggregate's FILTER may not contain a subquery, and because the
-- correlated EXISTS reads plainly in a select list. Either end of the edge may be
-- the pass-two paper: an edge means the later paper did something to the earlier
-- one's concept, and pass two reads the newest work, but nothing guarantees the
-- direction and assuming it would silently drop half the population.
pass_links AS (
    SELECT pr.*,
           EXISTS (
               SELECT 1 FROM edges e
               WHERE e.genealogy_id = pr.genealogy_id
                 AND ((e.source_paper_id = pr.paper_id
                       AND EXISTS (SELECT 1 FROM pass_one_nodes pon
                                   WHERE pon.genealogy_id = e.genealogy_id
                                     AND pon.node_id = e.target_node))
                   OR (e.target_paper_id = pr.paper_id
                       AND EXISTS (SELECT 1 FROM pass_one_nodes pon
                                   WHERE pon.genealogy_id = e.genealogy_id
                                     AND pon.node_id = e.source_node)))
           ) AS links_into_pass_one
    FROM pass_rows pr
),

-- The counts, over maps whose build is recorded and no others. `JOIN
-- map_pass_build` rather than a CASE in the final select list is what makes the
-- absence structural: a map with no build record produces no row here, so the
-- final LEFT JOIN hands the consumers NULL, and there is no expression anywhere
-- that could accidentally coalesce it to a zero.
--
-- The third count is "marked as neither the first nor the second pass", not
-- "unmarked", so that the three sum to the papers read whatever the seam records
-- — including a pass number this view has never heard of. Anything above zero
-- there is a defect in the build's record and `pipeline/map_report.py` marks it
-- rather than leaving a reader to add three numbers.
pass_stats AS (
    SELECT pl.genealogy_id,
           count(*) FILTER (WHERE pl.definition_id IS NOT NULL
                              AND pl.build_pass = 1)  AS papers_read_pass_one,
           count(*) FILTER (WHERE pl.definition_id IS NOT NULL
                              AND pl.build_pass = 2)  AS papers_read_pass_two,
           count(*) FILTER (WHERE pl.definition_id IS NOT NULL
                              AND pl.build_pass IS DISTINCT FROM 1
                              AND pl.build_pass IS DISTINCT FROM 2)
                                                      AS papers_read_pass_unmarked,
           -- Stage B as the independent judge, over exactly the rows above, so
           -- this is a subset of the second count by construction.
           count(*) FILTER (WHERE pl.build_pass = 2
                              AND pl.defines_concept) AS papers_defining_pass_two,
           count(*) FILTER (WHERE pl.build_pass = 2
                              AND pl.links_into_pass_one)
                                                      AS papers_linking_into_pass_one
    FROM pass_links pl
    JOIN map_pass_build b ON b.genealogy_id = pl.genealogy_id
    GROUP BY pl.genealogy_id
),

-- #188's free half: the defining rate over what pass two actually read, by band
-- of selection rank. It runs on every two-stage build and costs nothing, because
-- it counts work the build already did. It bounds R from ABOVE and cannot bound
-- it from below — past the point where the rate falls off the seats are wasted,
-- and nothing here can say whether a seat below that point earned its place,
-- which is what the paid over-read on the first two-stage map is for.
--
-- Papers pass two read but did not rank are absent from the ladder and present in
-- `papers_read_pass_two`, which is why the ladder's own `read` figures are
-- published per band rather than left to be divided out of the total.
band_rows AS (
    SELECT pl.genealogy_id,
           ((pl.pass_rank - 1) / b.width) * b.width + 1 AS band_start,
           b.width,
           pl.defines_concept
    FROM pass_links pl
    CROSS JOIN band b
    JOIN map_pass_build mb ON mb.genealogy_id = pl.genealogy_id
    WHERE pl.build_pass = 2 AND pl.pass_rank IS NOT NULL
),
bands AS (
    SELECT genealogy_id,
           jsonb_agg(jsonb_build_object(
               'from', band_start, 'to', band_start + width - 1,
               'read', n_read, 'defining', n_defining)
               ORDER BY band_start) AS pass_two_rank_bands
    FROM (SELECT genealogy_id, band_start, width,
                 count(*)                                   AS n_read,
                 count(*) FILTER (WHERE defines_concept)    AS n_defining
          FROM band_rows
          GROUP BY genealogy_id, band_start, width) t
    GROUP BY genealogy_id
)

SELECT g.id AS genealogy_id,
       -- NULL, and never 0, when nothing recorded how this map was built. The
       -- state is named in the next column rather than inferred from this one.
       b.passes                          AS passes_recorded,
       CASE WHEN b.genealogy_id IS NULL
            THEN 'this map was built in one pass'
            ELSE COALESCE(b.pass_two_outcome, 'not recorded') END
                                         AS pass_two_outcome,
       b.pass_two_seats,
       b.pass_two_candidates,
       b.pass_two_candidates_cleared,
       s.papers_read_pass_one,
       s.papers_read_pass_two,
       s.papers_read_pass_unmarked,
       s.papers_defining_pass_two,
       s.papers_linking_into_pass_one,
       bd.pass_two_rank_bands,
       bw.width                          AS pass_two_rank_band_width
FROM genealogies g
CROSS JOIN band bw
-- Every join LEFT, so every map that exists gets a row on this view whatever the
-- seam holds. A map that disappears from its own report because a join found
-- nothing is the join deciding the question, which is the note `016` carries at
-- its foot and the reason `019` repeats it.
LEFT JOIN map_pass_build b ON b.genealogy_id = g.id
LEFT JOIN pass_stats s     ON s.genealogy_id = g.id
LEFT JOIN bands bd         ON bd.genealogy_id = g.id;


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `lineage_ro` does not automatically hold SELECT on a new view, so without this
-- `pipeline/map_report.py` fails with a permission error against production while
-- working perfectly for the owner. Guarded on pg_roles so a local database that
-- has no such role still migrates. Same shape as `016`'s, `017`'s and `019`'s.
--
-- The two seam views are granted as well as the report view, and that is a
-- decision rather than symmetry: `SELECT count(*) FROM map_pass_papers` is how an
-- Operator answers "has #192 landed on this database yet" without a write and
-- without reading the migration table.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON map_pass_papers  TO lineage_ro;
        GRANT SELECT ON map_pass_build   TO lineage_ro;
        GRANT SELECT ON map_report_passes TO lineage_ro;
    END IF;
END
$$;

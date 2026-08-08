-- 019: what the map READ, by year — one row per map, computed on read, stored
-- nowhere.
--
-- Ticket #182, designing #33 (F5). Sibling of `016_map_report.sql` and
-- `017_map_report_by_type.sql`, and every constraint in `016`'s header applies
-- here unchanged.
--
-- **What was missing.** `016`'s year block (`year_min`, `year_max`,
-- `year_counts`) is computed over DEFINING papers only: its `year_rows` CTE
-- joins `definitions ... AND d.defines_concept = true`. That is the right figure
-- for a reader and the wrong one for judging how papers are selected, because it
-- conflates two causes that need opposite fixes — selection never picked a
-- recent paper, or selection picked it, Stage B read it, and it did not define
-- the term. The first is a defect in the selection; the second is a finding
-- about the literature. The dark energy map reads `year_max = 2016` today and
-- nothing in this system can say which of the two that is.
--
-- This view is `year_rows` **minus** the `defines_concept = true` predicate,
-- with that predicate carried as a column instead of as a filter. Both series
-- therefore come out of one set of rows, which is what makes the defining papers
-- a subset of the papers read BY CONSTRUCTION rather than by test:
-- `read_year_max >= year_max` and `papers_defining_recent <=
-- papers_read_recent` cannot fail unless a join is wrong, and that is the
-- falsifier the ticket names.
--
-- **A fourth view rather than four more columns on `map_report`, and the reason
-- is the deploy window, not the grain.** The grain here is per map, the same as
-- `map_report`, so on grain alone these would be columns; `017` had the easier
-- case. Two things decide it the other way. `CREATE OR REPLACE VIEW` can only
-- append trailing columns to a definition it is given in full, so adding them
-- means restating all six hundred lines of `016` here, and the live definition
-- of `map_report` would then live in two files with the newer one silently
-- winning — the two-homes-for-one-fact pattern this record has already paid for.
-- And a push to `master` deploys Vercel and Render at once while Render's
-- pre-deploy is what runs the migration, so the app is live for a few minutes
-- against a schema one migration behind (CLAUDE.md). A missing *column* cannot
-- be guarded: `app/lib/report.ts` names every column of `map_report` in one
-- statement, so the whole report page would raise `UndefinedColumn` and 500 for
-- those minutes to add one figure. A missing *relation* is guarded by the
-- `to_regclass` fallback #92 earned and `017` already uses, and the page loses
-- one figure instead of a page. Purely additive: `CREATE VIEW` and a `GRANT`,
-- nothing existing is touched.
--
-- **`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or
-- reorder columns**, so a later change here beyond appending trailing columns is
-- `DROP VIEW map_report_read_years` then `CREATE VIEW`. Consequently no consumer
-- may `SELECT *`: `app/lib/report.ts` and `pipeline/map_report.py` name every
-- column they read.
--
-- **No threshold, and the one number that selects rows is published rather than
-- implied.** Counted with comments and string literals removed, the numeric
-- literals in this file are exactly {1, 5}: the `1` of `window_end - width + 1`
-- and of `SELECT 1 FROM pg_roles` in the GRANT, and the `5` of the recency
-- window. The `5` decides nothing about a paper — it names a population, and
-- both ends of that population ship as `recent_window_start` and
-- `recent_window_end` so the page can print "papers from 2022 to 2026" instead
-- of the word "recent". A window a reader cannot see is a threshold in disguise;
-- a window printed beside its count is a stated population. Nothing here grades,
-- colours or compares anything to it. The same two checks `016` and `017` carry
-- run over this file's own text, and both were run rather than reasoned about:
--
--   sed -E 's,--.*,,' 019_map_report_read_years.sql | grep -c -i '\bMATERIALIZED\b'   # 0
--   sed -E 's,--.*,,' 019_map_report_read_years.sql \
--     | grep -o -E '(^|[^A-Za-z0-9_.])[0-9]+(\.[0-9]+)?([^A-Za-z0-9_]|$)' \
--     | grep -o -E '[0-9]+(\.[0-9]+)?' | sort -u          # 1 5
--
-- **The window moves with the calendar, and that is why it is a column.**
-- `current_date` is evaluated when the view is read, so a reading taken in
-- January and one taken the following January cover different years, and the
-- server's timezone decides which side of a New Year a reading at midnight falls
-- on. Publishing both ends is what stops a figure recorded in a report ageing
-- into a claim about a window nobody can reconstruct.
--
-- **What `papers_read_recent` is for, and what it is not.** It is the
-- before-and-after instrument for F5 (#183), and it will move the moment a
-- recency reservation ships, BY CONSTRUCTION: a rule that puts papers in the
-- window cannot fail to raise a figure counting papers in the window. It is
-- instrumentation and not evidence, both consumers' copy says so, and the
-- evidence is `papers_defining_recent` and `read_year_max` against `year_max`,
-- because Stage B and the grounding check are independent judges that can return
-- false on exactly the papers a reservation admitted.


CREATE VIEW map_report_read_years AS

-- The window, defined once, here, and nowhere else. Five calendar years ending
-- in the current year and including it: read on 2026-08-08 that is 2022 to 2026,
-- which is 2026 - 5 + 1. `width` is named rather than written into the
-- subtraction so the file says "five years" where a reader looks for it, instead
-- of saying "minus four" and leaving them to reconstruct which convention it
-- meant.
WITH recency AS (
    SELECT w.width,
           w.window_end,
           w.window_end - w.width + 1 AS window_start
    FROM (SELECT 5 AS width,
                 EXTRACT(YEAR FROM current_date)::int AS window_end) w
),

-- Every paper this map read, defining or not. `016`'s `year_rows` with the
-- predicate moved out of the join and into a column.
--
-- **The join to `definitions` is LEFT and that is behaviour, not uniformity**:
-- a map that has read nothing still gets a row here, carrying NULLs, so it
-- appears on this view reporting zero papers read rather than vanishing from it.
-- A map that disappears from its own report because it has nothing to report is
-- the join deciding the question, which is the note `016` carries at its foot.
-- The phantom row is excluded from every count below by
-- `definition_id IS NOT NULL` or by a year test, which NULL fails.
--
-- `LEFT JOIN papers` for the reason `016` gives: `definitions.paper_id` is NOT
-- NULL with a cascading foreign key and cannot dangle, so it is identical to an
-- inner join today, and it is written this way so that widening the population
-- later cannot silently let the join decide the question.
read_rows AS (
    SELECT g.id AS genealogy_id,
           d.id AS definition_id,
           COALESCE(d.defines_concept, false) AS defines_concept,
           p.year
    FROM genealogies g
    LEFT JOIN definitions d
      ON d.concept = g.concept AND d.prompt_version = g.prompt_version
    LEFT JOIN papers p ON p.id = d.paper_id
),

-- The histogram over every paper read, in the shape `016`'s `year_counts`
-- already has, so the page draws the two series with one renderer. Undated
-- papers are absent from it and are counted separately, never given a guessed
-- year: `papers.year` is the earliest credible date (migration 009), and a
-- paper that has none of that is not a paper from year zero.
read_hist AS (
    SELECT genealogy_id, jsonb_object_agg(y::text, n ORDER BY y) AS read_year_counts
    FROM (SELECT genealogy_id, year AS y, count(*) AS n
          FROM read_rows WHERE year IS NOT NULL
          GROUP BY genealogy_id, year) t
    GROUP BY genealogy_id
),

-- `CROSS JOIN recency` is one row crossed with every map, so every map on this
-- view reports the same window and the window cannot differ between two figures
-- on one page. It is in the GROUP BY because it is selected, not because it
-- splits anything.
stats AS (
    SELECT r.genealogy_id,
           min(r.year) AS read_year_min,
           max(r.year) AS read_year_max,
           count(*) FILTER (WHERE r.definition_id IS NOT NULL AND r.year IS NULL)
                                                       AS papers_read_with_no_year,
           rc.window_start                             AS recent_window_start,
           rc.window_end                               AS recent_window_end,
           count(*) FILTER (WHERE r.year BETWEEN rc.window_start AND rc.window_end)
                                                       AS papers_read_recent,
           -- The same predicate with the defining test added, over the same
           -- rows, so this is a subset of the figure above by construction.
           count(*) FILTER (WHERE r.year BETWEEN rc.window_start AND rc.window_end
                              AND r.defines_concept)   AS papers_defining_recent
    FROM read_rows r
    CROSS JOIN recency rc
    GROUP BY r.genealogy_id, rc.window_start, rc.window_end
)

SELECT s.genealogy_id,
       s.read_year_min,
       s.read_year_max,
       h.read_year_counts,
       s.papers_read_with_no_year,
       s.recent_window_start,
       s.recent_window_end,
       s.papers_read_recent,
       s.papers_defining_recent
FROM stats s
-- LEFT, so a map whose papers all lack a year keeps its row and reports the
-- histogram as absent. NULL there means "no dated paper read", which is what
-- both consumers print words for; an empty object would be a different claim.
LEFT JOIN read_hist h ON h.genealogy_id = s.genealogy_id;


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `lineage_ro` does not automatically hold SELECT on a new view, so without this
-- `pipeline/map_report.py` fails with a permission error against production
-- while working perfectly for the owner. Guarded on pg_roles so a local database
-- that has no such role still migrates. Same shape as `016`'s and `017`'s.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON map_report_read_years TO lineage_ro;
    END IF;
END
$$;

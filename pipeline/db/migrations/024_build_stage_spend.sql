-- 024: what each step of a build spent, and the report figure that reads it.
-- Storage plus the read shape, in one file.
--
-- Ticket #47 ([B29]). The complaint it was filed on is that extraction cost a
-- cent a paper on one corpus and four cents a paper on another, and that nothing
-- in this system could say which step of a build the difference was in: the
-- worker scrapes a running total out of the stages' stdout for the progress feed
-- (#85), publishes it as one number on `map_report.run_cost_usd`, and throws the
-- per-step breakdown away line by line as it goes. Only Stage B is cached, so
-- clustering, edge classification, magnitude, threads and claims are paid again
-- on every build, and how much of a map's cost the shared extraction cache
-- actually avoids has never been a stored fact (decision 27, ROADMAP open
-- question 6).
--
-- **This is an instrument and it must land before the thing it measures.** The
-- owner's cost-reduction programme — the batch API, cheap-model triage, windowed
-- extraction — states its results as before-and-after per stage, and there is no
-- "before" until a build writes one down. Nothing here optimises anything.
--
-- **It persists what the worker already sees; no stage learns to account for
-- itself.** `Progress.line` in `worker/run.py` has matched every stage's spend
-- line since the feed existed and has always known which stage it was inside,
-- because it resets its per-stage total on `start_stage`. The whole change on the
-- writing side is to keep that number when the stage ends instead of folding it
-- into a running sum. So this migration adds no new arithmetic and no new claim:
-- the per-step figures sum to the same scrape the report already publishes, and
-- where they do not, `pipeline/map_report.py` says so rather than a reader having
-- to add up 28 rows.
--
-- **One file rather than #193's empty seam, because there is one ticket**, which
-- is `023`'s reasoning and not a new one. What survives from #193's design is the
-- shape that made it safe: the report figure is **its own view**, not more columns
-- on `map_report`, because `app/lib/report.ts` names every column of that view in
-- one statement and a missing *column* cannot be guarded — the page would raise
-- `UndefinedColumn` and 500 for the minutes between the Vercel deploy and
-- Render's pre-deploy migration. A missing *relation* is guarded by the
-- `to_regclass` fallback #92 earned, and the page loses one block instead of a
-- page.
--
-- **`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or
-- reorder columns**, so a later change here beyond appending trailing columns is
-- `DROP VIEW map_report_stages` then `CREATE VIEW`. Consequently no consumer may
-- `SELECT *`: `app/lib/report.ts` and `pipeline/map_report.py` name every column
-- they read.
--
-- **No threshold, no score, no grade, and no per-paper unit cost.** A cost per
-- paper is one division away from the numbers below and it is deliberately not
-- computed here: it reads as a price, it would be quoted as one, and the corpora
-- it would compare differ in how much text each paper carries — which is the
-- hypothesis the ticket wants tested, not a figure to publish beside it. Counted
-- with comments and string literals removed, the numeric literals in this file
-- are {0, 1, 2, 3, 4, 10, 12} and every one of them is a column width, a bound or
-- the name of a pass.


-- ── one row per step of one build ──────────────────────────────────────────
--
-- **A table of its own, not a column on `trace_requests` and not one on
-- `genealogies`.** The grain is (map, step) and neither of those tables has it: a
-- job row is one row per run and a genealogy row is one per map, so either would
-- have to hold the breakdown as a blob, and a blob is not something an Operator
-- can sum, filter by pass or order by cost. `022`'s rule applies here too — the
-- pass a step ran in and what it spent are properties of ONE BUILD of ONE MAP.
--
-- **Keyed on the map and cleared per build, like `map_build_pass_papers`.** A
-- rebuild re-states what it spent rather than adding to it, which is what makes a
-- requeue (#178) converge instead of accumulating two runs' steps under one map.
-- `run_id` is kept beside the rows so an Operator can see WHICH run they came
-- from: the report's own cost figure describes the last *completed* run, and a
-- build that recorded its steps and then failed at the publish would leave the
-- two describing different runs. That skew is visible rather than silent.
--
-- **`spend_usd` NULL and `spend_lines` 0 are the same fact and the CHECK makes
-- them inseparable: this step printed no cost line.** That is not a spend of
-- zero. Most steps of a build genuinely cost no model spend — fetching, text
-- extraction, the audit, grounding, the union, the recorders — and a step that
-- stopped printing its spend looks identical from here. The two cannot be told
-- apart by this table and neither may be reported as `US$0.00`; what the table
-- adds is that such a step is now a NAMED row with no figure instead of silently
-- vanishing into a total, which is the half of #85's complaint that was actually
-- fixable. A stage that DID print `$0.0000` (Stage C with every label cached, and
-- Stage D with every pair cached, both print it deliberately) carries
-- `spend_lines = 1` and a real zero.
--
-- `build_pass` is 1, 2, or NULL for a step belonging to neither — the snapshot,
-- the finishing stages that run once after both passes. The fallback steps of an
-- abandoned second pass are recorded as pass 2: they ran because pass two ran,
-- and their names ("fall back: …") say what they did. The step names are the
-- worker's own feed names and are not reconstructed here, so the breakdown and
-- the progress a requester watched use one vocabulary.
CREATE TABLE map_build_stages (
    genealogy_id bigint NOT NULL REFERENCES genealogies(id) ON DELETE CASCADE,
    -- The step's position in the build that ran, 1-based, which is the number the
    -- feed showed ("stage 7 of 28"). It is the key rather than the name because a
    -- two-pass build runs several stages twice under names that differ only by
    -- their prefix, and because the order is itself worth reading back.
    stage_no     int  NOT NULL CHECK (stage_no >= 1),
    stage        text NOT NULL CHECK (btrim(stage) <> ''),
    build_pass   int  CHECK (build_pass >= 1),
    spend_usd    numeric(10, 4) CHECK (spend_usd >= 0),
    spend_lines  int  NOT NULL DEFAULT 0 CHECK (spend_lines >= 0),
    -- Wall clock, from the subprocess starting to it exiting. Four significant
    -- places past the second would be a lie about a measurement taken around a
    -- process launch, so three.
    seconds      numeric(12, 3) CHECK (seconds >= 0),
    -- trace_requests.id, or NULL for a build run by hand from the command line.
    -- No foreign key: a request row deleted by an operator must not delete the
    -- record of what its build spent, which is exactly the figure that outlives
    -- the request.
    run_id       bigint,
    recorded_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (genealogy_id, stage_no),
    -- The zero-versus-absence rule, made structural rather than left to two
    -- writers to remember. `zero is a measurement, absence is not` (#87) was
    -- defeated last time by a placeholder minted at the write, so the constraint
    -- lives here where every writer meets it.
    CONSTRAINT map_build_stages_cost_line_agrees
        CHECK ((spend_usd IS NULL) = (spend_lines = 0))
);

CREATE INDEX idx_map_build_stages_run ON map_build_stages (run_id);

COMMENT ON TABLE map_build_stages IS
    'One row per (map, step of the build that produced it): what that step spent, '
    'how long it took and which pass it ran in. Issue #47; written by '
    'pipeline/record_spend.py and read through map_report_stages.';

COMMENT ON COLUMN map_build_stages.spend_usd IS
    'What this step printed as its own spend, or NULL when it printed no cost '
    'line at all. NULL is not zero: see the table''s CHECK and issue #85.';


-- ── the report figure ──────────────────────────────────────────────────────
--
-- Per map, like every other report view, so it joins into the report row rather
-- than arriving as a separate table.
--
-- **The population is named precisely and it is not the same population as
-- anything else on the report** (#123's rule). These count STEPS OF A BUILD, not
-- papers, not definitions and not relationships, so no label below uses the word
-- "papers" and none of these figures may be divided by one.
--
-- **Every figure is gated on the map having a step record at all, and the gate is
-- an inner GROUP BY plus a LEFT JOIN rather than a CASE** — `020`'s device. A map
-- with no rows produces no row in the CTE, so the consumers are handed NULL and
-- there is no expression anywhere that could coalesce it to a zero. That matters
-- more here than anywhere: every map in this database today was built before this
-- record existed, and "this build spent nothing" is precisely the wrong reading.
-- `stage_record_basis` is the words for it, never blank, in the shape
-- `run_cost_basis` already established.
--
-- Within a recorded build the zeros ARE real: `stages_with_no_cost_line` counts
-- steps that ran and printed nothing, which is a measurement of the record's own
-- completeness.
CREATE VIEW map_report_stages AS

-- The three-way split of the steps carries the pass as a COLUMN rather than as a
-- filter over three separate scans, `019`'s and `020`'s discipline, so
-- `stages_pass_one + stages_pass_two + stages_outside_passes = stages_recorded`
-- and the three spend subtotals sum to `stage_spend_usd` BY CONSTRUCTION rather
-- than by test. The third arm is "marked as neither pass one nor pass two", not
-- "unmarked", so the identity survives a pass number this view has never heard
-- of.
WITH stage_stats AS (
    SELECT s.genealogy_id,
           count(*)                                     AS stages_recorded,
           count(s.spend_usd)                           AS stages_with_a_cost,
           count(*) FILTER (WHERE s.spend_usd IS NULL)  AS stages_with_no_cost_line,
           -- NULL when no step reported a cost, which on a recorded build means
           -- every step of it printed nothing. sum() over an empty filtered set
           -- is NULL and is left that way on purpose.
           sum(s.spend_usd)                             AS stage_spend_usd,
           sum(s.seconds)                               AS stage_wall_clock,
           count(*) FILTER (WHERE s.build_pass = 1)     AS stages_pass_one,
           count(*) FILTER (WHERE s.build_pass = 2)     AS stages_pass_two,
           count(*) FILTER (WHERE s.build_pass IS DISTINCT FROM 1
                              AND s.build_pass IS DISTINCT FROM 2)
                                                        AS stages_outside_passes,
           sum(s.spend_usd) FILTER (WHERE s.build_pass = 1)
                                                        AS pass_one_spend_usd,
           sum(s.spend_usd) FILTER (WHERE s.build_pass = 2)
                                                        AS pass_two_spend_usd,
           sum(s.spend_usd) FILTER (WHERE s.build_pass IS DISTINCT FROM 1
                                      AND s.build_pass IS DISTINCT FROM 2)
                                                        AS spend_outside_passes,
           -- One build, one run, so max() picks the only value there is. It is
           -- published so an Operator can tell whether these steps and
           -- `map_report.run_cost_usd` describe the same run; the page declines
           -- to select it, the way it declines `named_by`.
           max(s.run_id)                                AS stage_record_run_id,
           -- The list, in the order the steps ran. NULL rather than an empty
           -- array is impossible here (a row in this CTE means at least one step),
           -- and it is aggregated rather than left to a second query because the
           -- breakdown IS the ticket: a total that cannot be opened is the figure
           -- we already had.
           jsonb_agg(jsonb_build_object(
               'stage_no',    s.stage_no,
               'stage',       s.stage,
               'build_pass',  s.build_pass,
               'spend_usd',   s.spend_usd,
               'spend_lines', s.spend_lines,
               'seconds',     s.seconds)
               ORDER BY s.stage_no)                     AS stages
    FROM map_build_stages s
    GROUP BY s.genealogy_id
),

-- The most expensive step of the build. `DISTINCT ON` rather than a window
-- function because the tie-break has to be stated: equal costs are resolved by
-- the earlier step, so two identical figures cannot make this column depend on
-- the order rows came back in.
--
-- Steps that printed no cost line are excluded, not treated as zero, so a build
-- where nothing reported a cost has no costliest step and every column here is
-- NULL rather than naming whichever step happened to sort first.
costliest AS (
    SELECT DISTINCT ON (s.genealogy_id)
           s.genealogy_id, s.stage, s.spend_usd
    FROM map_build_stages s
    WHERE s.spend_usd IS NOT NULL
    ORDER BY s.genealogy_id, s.spend_usd DESC, s.stage_no
)

SELECT g.id AS genealogy_id,
       -- NULL, never 0, when nothing recorded how this build spent. A build that
       -- ran zero steps does not exist, so a 0 here could only ever mean absence,
       -- and the column next door says so in words instead.
       t.stages_recorded,
       t.stages_with_a_cost,
       t.stages_with_no_cost_line,
       t.stage_spend_usd,
       -- The recorded steps only, and the label on both consumers says so. It is
       -- NOT the run's wall clock: the step that writes this record runs inside
       -- the build and cannot time itself or the publish that follows it, so this
       -- is always short of `run_wall_clock` by those two steps. Publishing it as
       -- the run's time would be a figure that is quietly wrong on every map.
       t.stage_wall_clock,
       t.stages_pass_one,
       t.stages_pass_two,
       t.stages_outside_passes,
       t.pass_one_spend_usd,
       t.pass_two_spend_usd,
       t.spend_outside_passes,
       c.stage    AS costliest_stage,
       c.spend_usd AS costliest_stage_usd,
       -- A share, and the categories genuinely partition the total: each step's
       -- spend is counted once and the steps sum to `stage_spend_usd`, so "half
       -- of what this build spent" means what it says (the trap in
       -- `a-share-needs-a-partition` is overlapping categories, and there are
       -- none here). NULLIF so a build whose recorded spend is zero reports no
       -- share rather than dividing by it.
       c.spend_usd / NULLIF(t.stage_spend_usd, 0) AS costliest_stage_share,
       CASE WHEN t.genealogy_id IS NULL
            THEN 'no step-by-step record of this build'
            ELSE 'from the record this build kept of each of its steps' END
                                                  AS stage_record_basis,
       t.stage_record_run_id,
       t.stages
FROM genealogies g
-- LEFT, so every map that exists gets a row on this view whatever the table
-- holds. A map that disappears from its own report because a join found nothing
-- is the join deciding the question, which is the note `016` carries at its foot
-- and the reason `019`, `020` and `023` all repeat it.
LEFT JOIN stage_stats t ON t.genealogy_id = g.id
LEFT JOIN costliest   c ON c.genealogy_id = g.id;


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `lineage_ro` does not automatically hold SELECT on a new table or view, so
-- without this `pipeline/map_report.py` fails with a permission error against
-- production while working perfectly for the owner. A view is executed with the
-- CALLER's privileges unless it is declared `security_definer`, so the base table
-- is granted as well as the view. Guarded on pg_roles so a local database with no
-- such role still migrates. Same shape as `016`'s, `017`'s, `019`'s, `022`'s and
-- `023`'s.
--
-- SELECT and nothing else: `lineage_ro` writes nowhere, and the step record is
-- written by the worker through DATABASE_URL like everything else.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON map_build_stages  TO lineage_ro;
        GRANT SELECT ON map_report_stages TO lineage_ro;
    END IF;
END
$$;

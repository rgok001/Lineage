-- 022: which pass of a two-stage build read a paper, and how that build's
-- second pass ended. The storage behind `020`'s seam.
--
-- Ticket #192, the orchestration designed on #184. `020_map_report_passes.sql`
-- shipped the report's whole pass block over two views with the right columns
-- and `WHERE false`, deliberately leaving where the answer LIVES to this
-- migration. This file adds that storage and re-points the two seam views at it.
-- It touches nothing else: not `020`, not `app/lib/report.ts`, not
-- `pipeline/map_report.py`, not the page. Every figure on the report lights up
-- from here.
--
-- **Two tables, not a column on `papers`.** The architect's one standing rule on
-- #193, and it is the same rule `016` follows about `definitions`: a paper is
-- shared across every map ever traced, and the pass it was read on is a property
-- of ONE BUILD of ONE MAP. A column on `papers` would be overwritten by the next
-- concept's build and would be silently wrong for both.
--
-- **The pass is stored per PAPER and the seam exposes it per DEFINITION**, and
-- the difference is deliberate. `020` names `definition_id` because a map's
-- membership is its `definitions` rows for that concept and prompt version
-- (#123) — that is the population `016` and `019` count under the word "papers",
-- and joining on anything else splits the surfaces. But what the build KNOWS,
-- while it is running, is which papers it read: the corpus files name arXiv ids,
-- and `stage_b_extract.py --refresh` can rewrite a definition without the paper
-- changing. So the row records the paper and the view resolves the definition
-- through the genealogy's own concept and prompt version. A paper the build read
-- that never produced a definition row therefore contributes no row to the seam,
-- which is right: it is not one of the papers the report counts.
--
-- **`CREATE OR REPLACE VIEW`, not the `DROP VIEW` + `CREATE VIEW` that `020`'s
-- header and #192's semantics comment both predicted.** Written down because the
-- prediction was reasonable and is wrong for a mechanical reason worth knowing:
-- `map_report_passes` SELECTs from both seam views, so `DROP VIEW
-- map_pass_papers` fails with a dependency error, and `DROP VIEW ... CASCADE`
-- would take `map_report_passes` with it and force this file to re-create it —
-- putting `020`'s definition in two files with the newer silently winning, which
-- is exactly the fault `020`'s own header refuses. `CREATE OR REPLACE VIEW` may
-- change a view's query however it likes as long as the output columns keep the
-- same names, types and order (it may only append), and that is precisely this
-- change: same four and same six columns, a different FROM. The types below are
-- therefore load-bearing and are spelled out in the tables: `bigint, bigint,
-- int, int` and `bigint, int, text, int, int, int`. Executed against a real
-- PostgreSQL before it was written down.
--
-- **What is NOT recorded here.** No recency score, no freshness grade, no "up to
-- date" badge, and no single number blending these counts — `020`'s closing rule,
-- repeated because this is the file that would make one easy to compute.


-- ── the build's own record: at most one row per map ────────────────────────
--
-- **Its PRESENCE is what every figure on the report is gated on**, so a build
-- that genuinely ran one pass writes NO row and the report says "this map was
-- built in one pass" and draws nothing (`020`'s third point). A build that TRIED
-- a second pass and got nowhere — none found, abandoned at the pre-flight spend
-- gate, or the pass failed and the build fell back to pass one — writes a row
-- with `passes = 1` and an outcome that says which, because "we could not afford
-- them" and "there were none" produce identical counts and only the run knows
-- which happened.
--
-- `pass_two_outcome` is the reader's sentence and not a code: `020` prints it
-- verbatim on the page and in `pipeline/map_report.py`, so a code would appear on
-- the page as a code. `worker/run.py` composes it in one function
-- (`pass_two_outcome_sentence`) so the four-or-five states have one author.
--
-- The three counts are nullable on purpose. A build that never reached the
-- selection has no candidate counts, and `020` prints a NULL as "not recorded"
-- rather than as a zero, which would claim the citation graph was asked and
-- answered nothing.
CREATE TABLE map_build_passes (
    genealogy_id                bigint PRIMARY KEY
                                REFERENCES genealogies(id) ON DELETE CASCADE,
    passes                      int  NOT NULL CHECK (passes >= 1),
    pass_two_outcome            text NOT NULL CHECK (btrim(pass_two_outcome) <> ''),
    pass_two_seats              int  CHECK (pass_two_seats >= 0),
    pass_two_candidates         int  CHECK (pass_two_candidates >= 0),
    pass_two_candidates_cleared int  CHECK (pass_two_candidates_cleared >= 0),
    recorded_at                 timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE map_build_passes IS
    'One row per map whose build ran (or attempted) a second pass. Issue #192; '
    'read through the map_pass_build view by 020''s report figures.';


-- ── which pass read which paper ────────────────────────────────────────────
--
-- The primary key is what keeps `020`'s sum identity true: a paper counted in
-- both passes would be one definition counted twice, and
-- `papers_read_pass_one + papers_read_pass_two + papers_read_pass_unmarked
--  = papers_with_a_reading` would fail on a map nobody had touched. Pass two
-- excludes papers already in the map by construction (#191), and this constraint
-- is what makes that a guarantee rather than a property of one selector.
--
-- `pass_rank` is the paper's position in THAT pass's own selection order,
-- 1-based, and NULL where the pass did not rank. Both corpus files are written
-- in their selector's ranked order, so both passes record it; #188's free half
-- bands pass two's and no other, which is `020`'s job and not this one's.
--
-- ON DELETE CASCADE on both sides: this is a fact about a build of a map, so it
-- has nothing left to say once either the map or the paper is gone.
CREATE TABLE map_build_pass_papers (
    genealogy_id bigint NOT NULL REFERENCES genealogies(id) ON DELETE CASCADE,
    paper_id     bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    build_pass   int NOT NULL CHECK (build_pass >= 1),
    pass_rank    int CHECK (pass_rank >= 1),
    recorded_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (genealogy_id, paper_id)
);

CREATE INDEX idx_map_build_pass_papers_paper ON map_build_pass_papers (paper_id);

COMMENT ON TABLE map_build_pass_papers IS
    'One row per (map, paper) saying which pass of the build read it. Issue '
    '#192; read through the map_pass_papers view by 020''s report figures.';


-- ── the seam, re-pointed ───────────────────────────────────────────────────
--
-- Same columns, same types, same order as `020` defined them; only the FROM
-- moves. `020`'s comments on what each column means still stand and are not
-- repeated here.
--
-- The join to `definitions` carries the genealogy's own concept and prompt
-- version, so a build's record cannot leak a pass onto another concept's map,
-- and a prompt-version bump leaves the old record attached to the old map.

CREATE OR REPLACE VIEW map_pass_papers AS
SELECT pp.genealogy_id,
       d.id AS definition_id,
       pp.build_pass,
       pp.pass_rank
FROM map_build_pass_papers pp
JOIN genealogies g ON g.id = pp.genealogy_id
JOIN definitions d ON d.paper_id = pp.paper_id
                  AND d.concept = g.concept
                  AND d.prompt_version = g.prompt_version;

CREATE OR REPLACE VIEW map_pass_build AS
SELECT b.genealogy_id,
       b.passes,
       b.pass_two_outcome,
       b.pass_two_seats,
       b.pass_two_candidates,
       b.pass_two_candidates_cleared
FROM map_build_passes b;


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `020` already granted SELECT on both views to `lineage_ro`, and a replaced
-- view keeps its grants — but it now reads two tables the role has never been
-- granted anything on, and a view is executed with the CALLER's privileges
-- unless it is declared `security_definer`. Without these two grants the
-- Operator's `pipeline/map_report.py` would fail with a permission error on the
-- underlying tables while the owner's own run worked perfectly, which is the
-- exact failure `016`'s grant block exists to prevent. Guarded on pg_roles so a
-- local database with no such role still migrates.
--
-- SELECT and nothing else: `lineage_ro` writes nowhere, and a build's record is
-- written by the worker through DATABASE_URL like everything else.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON map_build_passes      TO lineage_ro;
        GRANT SELECT ON map_build_pass_papers TO lineage_ro;
    END IF;
END
$$;

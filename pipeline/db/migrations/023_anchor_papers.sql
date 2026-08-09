-- 023: papers a person named at request time, and the report figure that
-- discloses them. Storage plus the read shape, in one file.
--
-- Ticket #198, accepted on the consolidated ruling on #184. A requester may name
-- 1 to 3 arXiv ids; those papers enter the corpus without competing for a seat.
-- **An anchor bypasses selection and nothing else** — Stage B still asks it
-- whether it defines the term, the grounding check still applies, and Stage D
-- still requires a real citation link before it will draw a relationship. A
-- named paper that does not belong therefore comes back as a paper that defines
-- nothing and connects to nothing, and both of those are already figures on the
-- report. This migration is what makes the third condition true as well: the
-- report says how many of a map's papers a person named, so a reader can tell a
-- paper the tool found from a paper a person supplied.
--
-- **One file rather than #193's empty seam, because there is one ticket.** `020`
-- shipped a question over `WHERE false` views and left `022` to say where the
-- answer lived, because the report and the orchestration were two tickets landing
-- weeks apart. Here the storage and the figure ship together, so the seam would
-- be ceremony. What survives from that design is the shape that made it safe: the
-- report figure is **its own view**, not four more columns on `map_report`,
-- because `app/lib/report.ts` names every column of `map_report` in one statement
-- and a missing *column* cannot be guarded — the page would raise
-- `UndefinedColumn` and 500 for the minutes between the Vercel deploy and
-- Render's pre-deploy migration. A missing *relation* is guarded by the
-- `to_regclass` fallback #92 earned, and the page loses one block instead of a
-- page.
--
-- **`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or
-- reorder columns**, so a later change here beyond appending trailing columns is
-- `DROP VIEW map_report_anchors` then `CREATE VIEW`. Consequently no consumer may
-- `SELECT *`: `app/lib/report.ts` and `pipeline/map_report.py` name every column
-- they read.
--
-- **Absence and zero are the same claim here, and that is why this file needs no
-- build record.** `020` needed one, because "no second pass ran" and "a second
-- pass ran and read nothing" are different facts with identical counts. Nothing
-- like that exists here: a map with no rows in `map_anchor_papers` had no paper
-- named by a person, and that is equally true of a map built before this feature
-- shipped and of a map built after it with the field left empty. So every figure
-- below is a genuine zero on every map in this database today, no `COALESCE`
-- fabricates anything, and both consumers print one sentence for it.
--
-- **No threshold, no score, no grade.** Counted with comments and string literals
-- removed, the numeric literals in this file are exactly {0, 1, 3}: `3` is the
-- cap the design fixes, `1` and `0` bound a column. Nothing here grades, colours
-- or blends anything, and no single number may ever be computed from these counts
-- — "how anchored is this map" would be this tool's weighting read as a
-- measurement, which is `020`'s closing rule and decision 15's reason.


-- ── what the requester named ───────────────────────────────────────────────
--
-- Additive, nullable, and the NULL is load-bearing: a request made before this
-- column existed carries NULL, and one made after it with nobody named carries
-- the empty array. The app writes `'{}'` deliberately rather than leaving the
-- column alone, so "the field was offered and declined" is not stored as "the
-- field did not exist".
--
-- `text[]` rather than a child table because these are at most three short
-- strings belonging to one row's payload, they are read exactly once (by the
-- worker, when it builds the command line), and nothing joins to them. The
-- thing that IS joined to lives in `map_anchor_papers` below, keyed to the map
-- rather than to the request, because a map can be rebuilt from the command line
-- with anchors and no request row at all.
ALTER TABLE trace_requests ADD COLUMN anchors text[];

-- The cap, enforced where it cannot be raced past. The app refuses first and
-- with better words (`app/lib/arxiv-id.ts`); this is the floor under every other
-- writer, including a hand-run INSERT. `3` is the design's cap and `0` is the
-- empty array, which must stay legal because it is how "offered and declined" is
-- spelled.
--
-- **No subquery, because a CHECK constraint may not contain one** — `NOT EXISTS
-- (SELECT 1 FROM unnest(anchors) ...)` is the natural way to write "no element is
-- blank" and PostgreSQL refuses it with `cannot use subquery in check
-- constraint`. Found by executing this file against a real PostgreSQL rather
-- than by reading it: `psql` reports the failed `ALTER TABLE` and carries on with
-- the rest of the migration, so the table would have shipped with no constraint
-- at all and nothing would have said so.
--
-- `array_position` is the form that works, and it does find NULL and '' (both
-- checked on the same server). **What it deliberately does not catch is an
-- element of pure whitespace**: catching that needs a per-element predicate,
-- which needs a subquery. It is left to the two writers that exist, both of which
-- discard empty tokens before they build the array, and it is named here so the
-- next reader does not mistake the gap for an oversight. The SHAPE of an id is
-- not tested here at all, on purpose: it lives in `app/lib/arxiv-id.ts` and
-- `corpus_select.ANCHOR_ID_RE`, and a third copy in SQL would be a third value
-- the moment one of them moved.
ALTER TABLE trace_requests ADD CONSTRAINT trace_requests_anchors_capped CHECK (
    anchors IS NULL
    OR (coalesce(array_length(anchors, 1), 0) <= 3
        AND array_position(anchors, NULL) IS NULL
        AND array_position(anchors, '') IS NULL)
);

COMMENT ON COLUMN trace_requests.anchors IS
    'arXiv ids the requester named, at most 3. NULL means the request predates '
    'the field; the empty array means it was offered and nobody was named. '
    'Issue #198.';


-- ── which of a map's papers a person named ─────────────────────────────────
--
-- One row per (map, named arXiv id). Keyed on the id and NOT on `papers.id`,
-- unlike `map_build_pass_papers`, and the difference is the whole point of
-- condition 4: an id that was named and could not be fetched has no `papers`
-- row, and it is exactly that case a requester must be able to see. A foreign
-- key to `papers` would delete the evidence of the failure.
--
-- `named_by` and `named_by_asserted` are decision 18's split, unchanged: `by` is
-- a GitHub login the app obtained from a session, `by_asserted` is what a
-- process claims about itself. A request made through the site carries the
-- first, because the app wrote that login from a session and the worker only
-- relays it; a corpus anchored from the command line carries the second, which
-- is all a script running for whoever holds the `.env` can honestly claim. A row
-- may carry one, the other or neither, and neither is reported as absence rather
-- than as a claim about origin.
--
-- ON DELETE CASCADE: this is a fact about one build of one map and has nothing
-- left to say once the map is gone.
CREATE TABLE map_anchor_papers (
    genealogy_id      bigint NOT NULL REFERENCES genealogies(id) ON DELETE CASCADE,
    arxiv_id          text   NOT NULL CHECK (btrim(arxiv_id) <> ''),
    named_by          text   CHECK (named_by IS NULL OR btrim(named_by) <> ''),
    named_by_asserted text   CHECK (named_by_asserted IS NULL
                                    OR btrim(named_by_asserted) <> ''),
    -- The paper's position among the named ids, 1-based, so an operator reading
    -- the table back sees them in the order they were typed rather than in
    -- whatever order the join returns.
    named_rank        int CHECK (named_rank >= 1),
    recorded_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (genealogy_id, arxiv_id)
);

CREATE INDEX idx_map_anchor_papers_arxiv ON map_anchor_papers (arxiv_id);

COMMENT ON TABLE map_anchor_papers IS
    'One row per (map, arXiv id a person named at request time). Issue #198; '
    'written by pipeline/record_anchors.py and read through map_report_anchors.';


-- ── the report figure ──────────────────────────────────────────────────────
--
-- Per map, like every other report view, so it joins into the report row rather
-- than arriving as a separate table.
--
-- **The population is named precisely and it is the same population every other
-- figure on the report calls "papers"** (#123): a map's papers are its
-- `definitions` rows for that concept and prompt version. So `papers_named` is
-- how many ids a person named, and `papers_named_read` is how many of those the
-- map actually holds. The two differ exactly when a named paper could not be
-- fetched or produced no reading, which is the failure that must stay visible.
--
-- `papers_named_defining` is Stage B's independent verdict over the named papers,
-- and `papers_named_linked` is whether the map drew any relationship touching
-- one. Together they are condition 1's honest failure, published: a named paper
-- that defines nothing and connects to nothing shows up as a name in the list
-- with `false` and `0` beside it.
CREATE VIEW map_report_anchors AS

-- Every named id, with the paper row if there is one and the map's own reading
-- of it if there is one. LEFT at both steps: an id nothing could fetch and a
-- paper nothing could read must both survive to the count.
WITH named AS (
    SELECT a.genealogy_id,
           a.arxiv_id,
           a.named_rank,
           a.named_by,
           a.named_by_asserted,
           p.id    AS paper_id,
           p.title AS title,
           p.year  AS year,
           d.id    AS definition_id,
           coalesce(d.defines_concept, false) AS defines_concept
    FROM map_anchor_papers a
    JOIN genealogies g ON g.id = a.genealogy_id
    LEFT JOIN papers p ON p.arxiv_id = a.arxiv_id
    LEFT JOIN definitions d ON d.paper_id = p.id
                           AND d.concept = g.concept
                           AND d.prompt_version = g.prompt_version
),

-- How many of this map's relationships touch the named paper. Either end counts:
-- a named paper may be the older work a later one extends, or the later work
-- itself, and assuming a direction would silently drop half the population --
-- the same reasoning `020`'s `pass_links` carries.
linked AS (
    SELECT n.*,
           (SELECT count(*) FROM edges e
             WHERE e.genealogy_id = n.genealogy_id
               AND n.paper_id IS NOT NULL
               AND (e.source_paper_id = n.paper_id
                 OR e.target_paper_id = n.paper_id)) AS relationships
    FROM named n
)

SELECT g.id AS genealogy_id,
       -- Every count is a real zero on a map nobody named a paper for, and that
       -- is true both of a map built before this shipped and of one built after
       -- it with the field left empty. No branch here can produce a NULL count.
       count(l.arxiv_id)                                       AS papers_named,
       count(l.definition_id)                                  AS papers_named_read,
       count(*) FILTER (WHERE l.defines_concept)               AS papers_named_defining,
       count(*) FILTER (WHERE l.relationships > 0)             AS papers_named_linked,
       -- The actor, resolved by the consumers with decision 18's precedence
       -- (`by` outranks `by_asserted`, neither is "actor not recorded"). A build
       -- has one requester, so max() picks the only value there is; it is a
       -- column of its own rather than a key in the list below so that
       -- `app/lib/report.ts` can decline to select it and a login never reaches
       -- a public page.
       max(l.named_by)                                         AS named_by,
       max(l.named_by_asserted)                                AS named_by_asserted,
       -- The list, in the order the ids were typed. NULL rather than an empty
       -- array when nobody was named, so a consumer can print a sentence instead
       -- of an empty table without inspecting the count.
       jsonb_agg(jsonb_build_object(
           'arxiv_id',      l.arxiv_id,
           'title',         l.title,
           'year',          l.year,
           'read',          l.definition_id IS NOT NULL,
           'defines',       l.defines_concept,
           'relationships', l.relationships)
           ORDER BY l.named_rank NULLS LAST, l.arxiv_id)
           FILTER (WHERE l.arxiv_id IS NOT NULL)               AS named_papers
FROM genealogies g
-- LEFT, so every map that exists gets a row on this view whatever the table
-- holds. A map that disappears from its own report because a join found nothing
-- is the join deciding the question, which is the note `016` carries at its foot.
LEFT JOIN linked l ON l.genealogy_id = g.id
GROUP BY g.id;


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `lineage_ro` does not automatically hold SELECT on a new table or view, so
-- without this `pipeline/map_report.py` fails with a permission error against
-- production while working perfectly for the owner. A view is executed with the
-- CALLER's privileges unless it is declared `security_definer`, so the base table
-- is granted as well as the view. Guarded on pg_roles so a local database with no
-- such role still migrates. Same shape as `016`'s, `017`'s, `019`'s and `022`'s.
--
-- SELECT and nothing else: `lineage_ro` writes nowhere, and the anchor record is
-- written by the worker through DATABASE_URL like everything else.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON map_anchor_papers   TO lineage_ro;
        GRANT SELECT ON map_report_anchors  TO lineage_ro;
    END IF;
END
$$;

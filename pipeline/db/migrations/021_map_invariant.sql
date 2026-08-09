-- 021: the publish invariant — six clauses about a map, computed on read.
--
-- Ticket #168, which is the missing piece named in #149 and the publish half of
-- #2. The design is the Architect's comment of 2026-08-08 on both of those
-- tickets (it names a document `docs/design/publish-invariant.md` §3; the
-- document is not in this repository, the comment is the design of record).
-- Migration 016 is the precedent for everything structural below.
--
-- **Nothing in this system ever re-asks whether a map already published still
-- satisfies the rules of the stages that built it.** #149 is what that costs:
-- map 13 carries node `n21` whose only definition row says
-- `defines_concept = false` with no text and no embedding, seven relationships
-- hang off it, and today's Stage C could not have built it. The disagreement
-- between the stored map and the stage that wrote it went unread because no
-- surface asks the question. These two views are the surface.
--
-- **One expression, three consumers.** Stage E's gate (#171), the read-only
-- `pipeline/check_map.py`, and — when #174 lands — the report page all read
-- these views, so none of them can hold a different opinion about the same map.
--
-- **Nothing is stored.** No verdict column, no `checked_at`, no provenance
-- column, no MATERIALIZED. The recomputation is a `SELECT`, so a stored column
-- could only be a second ageing copy of something free, and the honest answer to
-- "when was this last checked" is "when you asked". Reversed by
--   DROP VIEW map_invariant; DROP VIEW map_invariant_findings;
--
-- **No constraint and no trigger**, and each refusal has its own reason. A CHECK
-- cannot reference another table; `edges.source_node` is TEXT into JSONB with no
-- foreign key available; a trigger would fire mid-rebuild, where violation is
-- legitimate and expected. `CHECK (source_node <> target_node)` was available and
-- is refused too: `workbench.py`'s merge creates self-loops and deletes them in
-- the same transaction.
--
-- **No threshold anywhere, and there must never be one.** Every clause is an
-- existence test or an equality — the same standing rule as `016` and
-- `check_record.py`. There is no score, no share, no grade and no colour here:
-- a map either satisfies all six clauses or it names what it violates. Counted
-- with comments stripped, the numeric literals in this file are exactly
-- {0, 1, 2, 3, 4, 5, 6}: the six clause numbers, the 0 of `= 0` and of every
-- COALESCEd count, and the 1 of `count(*) > 1` (which is the definition of a
-- duplicate, not a calibration) and of `SELECT 1`.
--
--   sed -E 's,--.*,,' 021_map_invariant.sql | grep -c -i '\bMATERIALIZED\b'  # 0
--   sed -E 's,--.*,,' 021_map_invariant.sql \
--     | grep -o -E '(^|[^A-Za-z0-9_.])[0-9]+(\.[0-9]+)?([^A-Za-z0-9_]|$)' \
--     | grep -o -E '[0-9]+(\.[0-9]+)?' | sort -u          # 0 1 2 3 4 5 6
--
-- **`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or
-- reorder columns**, so any later change beyond appending trailing columns is
-- `DROP VIEW ... CASCADE` then `CREATE VIEW`. Consequently no consumer may
-- `SELECT *`: `pipeline/check_map.py` and `pipeline/stage_e_ground.py` name
-- every column they read, so a redefinition cannot silently change a verdict.
--
-- **Two views, and the map-level one is an aggregate of the finding-level one**,
-- for the reason `016` gives about its own pair: two counts computed by two
-- separate expressions are two homes for one fact. `map_invariant`'s six counts
-- are `count(*) FILTER` over `map_invariant_findings`, so "the counts describe
-- the findings" is true by construction rather than by test.


-- ── one row per violation ──────────────────────────────────────────────────
--
-- For whoever has to repair it, so every row names the node, the relationship or
-- the thread it is about, and says in words what is wrong with it. A map that
-- satisfies the invariant contributes no rows at all.

CREATE VIEW map_invariant_findings AS

-- The concept-states, read exactly as `016`'s `node_shape` reads them, because a
-- clause that disagreed with the report about what a readable node is would be a
-- second definition of the same thing. A blob that is not an array is wrapped
-- into a one-element array so it lands as one unreadable node rather than
-- raising out of the view and taking every other clause with it.
WITH node_rows AS (
    SELECT g.id AS genealogy_id, g.concept, g.prompt_version,
           n.ord AS node_ordinal, n.node
    FROM genealogies g
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(g.nodes) = 'array' THEN g.nodes
             ELSE jsonb_build_array(g.nodes) END) WITH ORDINALITY AS n(node, ord)
),
node_shape AS (
    SELECT genealogy_id, concept, prompt_version, node_ordinal, node,
           COALESCE(jsonb_typeof(node) = 'object'
                    AND jsonb_typeof(node -> 'node_id') = 'string'
                    AND jsonb_typeof(node -> 'members') = 'array', false) AS readable,
           node ->> 'node_id' AS node_id
    FROM node_rows
),

-- Every entry of every node's `definition_ids`, one row each, with the id it
-- names resolved.
--
-- **The id stays `numeric` and is never cast to bigint.** `definition_ids` is
-- JSONB written by Stage C and rewritten by the workbench and both restore
-- scripts, so it can hold anything JSON can hold; a bigint cast of a number too
-- large for the column would raise out of the view, and a view that can raise on
-- bad data is no use as the instrument for finding bad data. Postgres compares
-- `definitions.id = <numeric>` by widening the column, which is what the join
-- below does. A number with a fractional part is not an id and resolves to NULL,
-- which clause 1 reports as "not a definition id" rather than rounding it into
-- one.
def_slots AS (
    SELECT ns.genealogy_id, ns.concept, ns.prompt_version,
           ns.node_ordinal, ns.node_id, d.ord AS slot, d.raw
    FROM node_shape ns
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(ns.node -> 'definition_ids') = 'array'
             THEN ns.node -> 'definition_ids' ELSE '[]'::jsonb END)
        WITH ORDINALITY AS d(raw, ord)
    WHERE ns.readable
),
def_ids AS (
    SELECT s.*,
           CASE WHEN jsonb_typeof(s.raw) = 'number'
                 AND (s.raw #>> '{}')::numeric = trunc((s.raw #>> '{}')::numeric)
                THEN (s.raw #>> '{}')::numeric END AS definition_id
    FROM def_slots s
),

-- CLAUSE 1, one row per `definition_ids` entry: does this entry name a
-- definition Stage C would admit today?
--
-- `defines_concept = true` is Stage C's own filter, verbatim from `SELECT_DEFS`
-- in `stage_c_cluster.py`. The other two are what make a definition clusterable
-- at all: a NULL embedding has no vector to cluster on, and an empty definition
-- is nothing to embed. Row 309 of #149 fails all three at once, which is the
-- signature of `stage_b_extract.py --refresh` demoting a paper out of the
-- population Stage C admits while `genealogies.nodes` kept its membership.
--
-- The `(concept, prompt_version)` test is what stops a node citing another map's
-- definition. Nothing does that today; the clause is cheap and the base case is
-- exactly what nobody asserts (decision 20 covers the inductive step).
def_verdict AS (
    SELECT i.genealogy_id, i.node_ordinal, i.node_id, i.slot, i.raw, i.definition_id,
           d.id IS NOT NULL                                                AS exists_row,
           COALESCE(d.concept = i.concept
                    AND d.prompt_version = i.prompt_version, false)        AS this_map,
           COALESCE(d.defines_concept, false)                              AS defines_concept,
           COALESCE(btrim(d.definition) <> '', false)                      AS has_definition,
           COALESCE(d.embedding IS NOT NULL, false)                        AS has_embedding,
           COALESCE(d.id IS NOT NULL
                    AND d.concept = i.concept
                    AND d.prompt_version = i.prompt_version
                    AND d.defines_concept
                    AND btrim(d.definition) <> ''
                    AND d.embedding IS NOT NULL, false)                    AS admissible,
           d.paper_id
    FROM def_ids i
    LEFT JOIN definitions d ON d.id = i.definition_id
),
clause_1 AS (
    SELECT genealogy_id, 1 AS clause, 'concept-state' AS subject_kind,
           node_id AS subject,
           CASE WHEN definition_id IS NULL
                THEN 'definition_ids entry ' || slot || ' is not a definition id: '
                     || raw::text
                ELSE 'definition ' || definition_id || ': ' || array_to_string(ARRAY[
                       CASE WHEN NOT exists_row      THEN 'no definitions row with this id' END,
                       CASE WHEN exists_row AND NOT this_map
                            THEN 'belongs to another concept or prompt version' END,
                       CASE WHEN exists_row AND NOT defines_concept
                            THEN 'defines_concept is false' END,
                       CASE WHEN exists_row AND NOT has_definition
                            THEN 'the definition text is empty' END,
                       CASE WHEN exists_row AND NOT has_embedding
                            THEN 'the embedding is NULL' END], '; ')
                END AS detail
    FROM def_verdict
    WHERE NOT admissible
),

-- CLAUSE 2, one row per concept-state: do `members` and `definition_ids`
-- describe the same papers?
--
-- This is #149's 85-against-84 gap stated as a rule, and it is written at the
-- width the F7 note on that ticket asked for: **every member of a stored node
-- resolves to exactly one live paper row that still satisfies the rule of the
-- stage that put it there.** So a member is compared against the papers of the
-- definitions this node names *and that clause 1 would admit* — not against the
-- raw id list — which is why `n21` produces a finding here as well as under
-- clause 1, and why F7 adds a clause to this rather than writing a second
-- checker.
--
-- **The paper is resolved through `definition_ids -> definitions.paper_id ->
-- papers.id`, never by joining `members ->> 'arxiv_id'` to `papers`.** The
-- member's arXiv id is used only to *name* what did not resolve, in the detail
-- string. When a map may draw papers from more than one source, an arXiv id is
-- no longer an identity and that join would silently pair a member with the
-- wrong row.
--
-- One finding per concept-state, never one per member: a node whose whole
-- membership is stale is one thing to repair, and #168's acceptance test is that
-- map 13 reports exactly one finding here.
member_slots AS (
    SELECT ns.genealogy_id, ns.node_ordinal, m.ord AS slot, m.member
    FROM node_shape ns
    CROSS JOIN LATERAL jsonb_array_elements(ns.node -> 'members')
        WITH ORDINALITY AS m(member, ord)
    WHERE ns.readable
),
member_stats AS (
    SELECT genealogy_id, node_ordinal, count(*) AS members_total,
           array_agg(CASE WHEN jsonb_typeof(member -> 'arxiv_id') = 'string'
                          THEN member ->> 'arxiv_id' END ORDER BY slot) AS member_arxiv
    FROM member_slots
    GROUP BY genealogy_id, node_ordinal
),
node_admissible AS (
    SELECT v.genealogy_id, v.node_ordinal,
           count(DISTINCT p.arxiv_id) AS admissible_total,
           array_agg(DISTINCT p.arxiv_id) AS admissible_arxiv
    FROM def_verdict v
    JOIN papers p ON p.id = v.paper_id
    WHERE v.admissible
    GROUP BY v.genealogy_id, v.node_ordinal
),
clause_2 AS (
    SELECT ns.genealogy_id, 2 AS clause, 'concept-state' AS subject_kind,
           ns.node_id AS subject,
           x.members_total || ' member(s), ' || x.admissible_total
           || ' admissible definition(s)'
           || CASE WHEN x.unresolved IS NULL THEN ''
                   ELSE '; no admissible definition of this concept-state for: '
                        || array_to_string(x.unresolved, ', ') END AS detail
    FROM node_shape ns
    LEFT JOIN member_stats ms
           ON ms.genealogy_id = ns.genealogy_id AND ms.node_ordinal = ns.node_ordinal
    LEFT JOIN node_admissible na
           ON na.genealogy_id = ns.genealogy_id AND na.node_ordinal = ns.node_ordinal
    CROSS JOIN LATERAL (
        SELECT COALESCE(ms.members_total, 0)   AS members_total,
               COALESCE(na.admissible_total, 0) AS admissible_total,
               (SELECT array_agg(COALESCE(a, '(a member with no arxiv_id)') ORDER BY a)
                  FROM unnest(COALESCE(ms.member_arxiv, ARRAY[]::text[])) AS a
                 WHERE a IS NULL
                    OR NOT (a = ANY(COALESCE(na.admissible_arxiv, ARRAY[]::text[]))))
                                               AS unresolved
    ) x
    WHERE ns.readable
      AND (x.members_total <> x.admissible_total OR x.unresolved IS NOT NULL)
),

-- CLAUSE 3, one row per unreadable concept-state and one per repeated id: is
-- every concept-state readable and uniquely named?
--
-- `016` already counts the unreadable ones on the report; uniqueness is new and
-- nothing has ever asserted it. A repeated `node_id` is not cosmetic: every
-- surface in the app resolves an edge's endpoint by `find(n => n.node_id === id)`
-- and takes the first, so a duplicate silently attributes one node's evidence to
-- another's label.
clause_3_unreadable AS (
    SELECT genealogy_id, 3 AS clause, 'concept-state' AS subject_kind,
           -- Its position in the blob, because an unreadable node may have no
           -- id to be named by; every consumer prints the kind beside it.
           '#' || node_ordinal AS subject,
           'this concept-state could not be read: ' || array_to_string(ARRAY[
               CASE WHEN jsonb_typeof(node) IS DISTINCT FROM 'object'
                    THEN 'it is not an object, it is ' || jsonb_typeof(node) END,
               CASE WHEN jsonb_typeof(node) = 'object'
                     AND jsonb_typeof(node -> 'node_id') IS DISTINCT FROM 'string'
                    THEN 'node_id is not a string' END,
               CASE WHEN jsonb_typeof(node) = 'object'
                     AND jsonb_typeof(node -> 'members') IS DISTINCT FROM 'array'
                    THEN 'members is not an array' END], '; ') AS detail
    FROM node_shape
    WHERE NOT readable
),
clause_3_duplicate AS (
    SELECT genealogy_id, 3 AS clause, 'concept-state' AS subject_kind,
           node_id AS subject,
           'this id names ' || count(*) || ' concept-states of this map' AS detail
    FROM node_shape
    WHERE readable
    GROUP BY genealogy_id, node_id
    HAVING count(*) > 1
),

-- CLAUSE 4, one row per relationship: do its endpoints exist in this map, and
-- do they differ?
--
-- Stage E's orphan sweep removes exactly the first half before it grounds
-- anything (decision 20), so a map that has been through Stage E should satisfy
-- this; the clause exists because nothing asserts it for a map that has been
-- through the workbench or a restore since. The self-loop half is here rather
-- than as a CHECK constraint because `workbench.py`'s merge creates self-loops
-- and deletes them in the same transaction.
live_nodes AS (
    SELECT genealogy_id, array_agg(node_id) AS node_ids
    FROM node_shape WHERE readable GROUP BY genealogy_id
),
clause_4 AS (
    SELECT e.genealogy_id, 4 AS clause, 'relationship' AS subject_kind,
           e.id::text AS subject,
           array_to_string(ARRAY[
               CASE WHEN NOT (e.source_node = ANY(COALESCE(l.node_ids, ARRAY[]::text[])))
                    THEN 'source ' || e.source_node
                         || ' is not a concept-state of this map' END,
               CASE WHEN NOT (e.target_node = ANY(COALESCE(l.node_ids, ARRAY[]::text[])))
                    THEN 'target ' || e.target_node
                         || ' is not a concept-state of this map' END,
               CASE WHEN e.source_node = e.target_node
                    THEN 'source and target are the same concept-state ('
                         || e.source_node || ')' END], '; ') AS detail
    FROM edges e
    LEFT JOIN live_nodes l ON l.genealogy_id = e.genealogy_id
    WHERE NOT (e.source_node = ANY(COALESCE(l.node_ids, ARRAY[]::text[])))
       OR NOT (e.target_node = ANY(COALESCE(l.node_ids, ARRAY[]::text[])))
       OR e.source_node = e.target_node
),

-- CLAUSE 5, one row per relationship: are its two papers members of the two
-- concept-states it names?
--
-- **Nothing asserts this today.** Decision 20 keeps an edge only while both of
-- its concept-states still denote the definitions they denoted, which is the
-- inductive step; the base case — that the edge's evidence comes from the
-- concept-states the edge is about — has never been checked. An edge that fails
-- it renders in full on the evidence page, with two quotes, over a transition
-- neither quote is evidence for.
--
-- Compared on `papers.id`, never on the arXiv id, for the F7 reason clause 2
-- gives. A NULL `source_paper_id` or `target_paper_id` cannot be a member of
-- anything and is reported as its own case: those edges exist (issue #79) and
-- are deliberately still displayed, and that is a different decision from
-- whether the map is publishable.
node_papers AS (
    SELECT DISTINCT v.genealogy_id, v.node_id, v.paper_id
    FROM def_verdict v
    WHERE v.paper_id IS NOT NULL
),
clause_5 AS (
    SELECT e.genealogy_id, 5 AS clause, 'relationship' AS subject_kind,
           e.id::text AS subject,
           array_to_string(ARRAY[
               CASE WHEN NOT EXISTS (SELECT 1 FROM node_papers np
                                      WHERE np.genealogy_id = e.genealogy_id
                                        AND np.node_id = e.source_node
                                        AND np.paper_id = e.source_paper_id)
                    THEN CASE WHEN e.source_paper_id IS NULL
                              THEN 'no source paper is recorded on this relationship'
                              ELSE 'the source paper is not a member of ' || e.source_node
                         END END,
               CASE WHEN NOT EXISTS (SELECT 1 FROM node_papers np
                                      WHERE np.genealogy_id = e.genealogy_id
                                        AND np.node_id = e.target_node
                                        AND np.paper_id = e.target_paper_id)
                    THEN CASE WHEN e.target_paper_id IS NULL
                              THEN 'no target paper is recorded on this relationship'
                              ELSE 'the target paper is not a member of ' || e.target_node
                         END END], '; ') AS detail
    FROM edges e
    WHERE NOT EXISTS (SELECT 1 FROM node_papers np
                       WHERE np.genealogy_id = e.genealogy_id
                         AND np.node_id = e.source_node
                         AND np.paper_id = e.source_paper_id)
       OR NOT EXISTS (SELECT 1 FROM node_papers np
                       WHERE np.genealogy_id = e.genealogy_id
                         AND np.node_id = e.target_node
                         AND np.paper_id = e.target_paper_id)
),

-- CLAUSE 6, one row per paper the threads name that the map does not hold: is
-- every paper named in `genealogies.streams` a member of some concept-state of
-- the same map?
--
-- This is the clause that stops a repair leaving thread `s4` advertising a paper
-- the map no longer has. It is deliberately node-agnostic — Stage G composes
-- threads across concept-states, so a paper moving between them is not a
-- violation — and it is measured against every paper the map's `definition_ids`
-- name, admissible or not, so that a definition clause 1 already reports is not
-- reported a second time here under a different name.
map_papers AS (
    SELECT DISTINCT v.genealogy_id, p.arxiv_id
    FROM def_verdict v
    JOIN papers p ON p.id = v.paper_id
),
thread_papers AS (
    SELECT g.id AS genealogy_id, s.stream ->> 'id' AS stream_id,
           pp.paper ->> 'arxiv' AS arxiv_id
    FROM genealogies g
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(g.streams -> 'streams') = 'array'
             THEN g.streams -> 'streams' ELSE '[]'::jsonb END) AS s(stream)
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(s.stream -> 'papers') = 'array'
             THEN s.stream -> 'papers' ELSE '[]'::jsonb END) AS pp(paper)
),
clause_6 AS (
    SELECT DISTINCT tp.genealogy_id, 6 AS clause, 'thread' AS subject_kind,
           COALESCE(tp.stream_id, '(a thread with no id)') AS subject,
           'this thread names paper '
           || COALESCE(tp.arxiv_id, '(a paper with no arxiv id)')
           || ', which no concept-state of this map holds' AS detail
    FROM thread_papers tp
    WHERE tp.arxiv_id IS NULL
       OR NOT EXISTS (SELECT 1 FROM map_papers mp
                       WHERE mp.genealogy_id = tp.genealogy_id
                         AND mp.arxiv_id = tp.arxiv_id)
),

findings AS (
    SELECT * FROM clause_1
    UNION ALL SELECT * FROM clause_2
    UNION ALL SELECT * FROM clause_3_unreadable
    UNION ALL SELECT * FROM clause_3_duplicate
    UNION ALL SELECT * FROM clause_4
    UNION ALL SELECT * FROM clause_5
    UNION ALL SELECT * FROM clause_6
)

-- The six clause names live here and nowhere else, so a consumer prints the
-- clause it was handed rather than keeping its own copy of the list.
SELECT f.genealogy_id, f.clause, c.clause_name, f.subject_kind, f.subject, f.detail
FROM findings f
JOIN (VALUES
    (1, 'every definition a concept-state names is one this map would admit today'),
    (2, 'a concept-state''s members and its definitions describe the same papers'),
    (3, 'every concept-state is readable and uniquely named'),
    (4, 'every relationship names two different concept-states of this map'),
    (5, 'every relationship''s two papers are members of the concept-states it names'),
    (6, 'every paper the threads name is held by some concept-state of this map')
) AS c(clause, clause_name) ON c.clause = f.clause;


-- ── one row per map ────────────────────────────────────────────────────────
--
-- Six exact counts and one boolean, true only when all six are zero. LEFT JOIN,
-- so a map with no findings is a row reading six zeros rather than a row that is
-- not there: "this map was not checked" and "this map has nothing wrong with it"
-- are different claims and a consumer must be able to tell them apart.

CREATE VIEW map_invariant AS
SELECT g.id AS genealogy_id,
       g.concept,
       g.prompt_version,
       g.status,
       count(*) FILTER (WHERE f.clause = 1) AS definitions_not_admissible,
       count(*) FILTER (WHERE f.clause = 2) AS nodes_whose_members_and_definitions_differ,
       count(*) FILTER (WHERE f.clause = 3) AS nodes_unreadable_or_duplicated,
       count(*) FILTER (WHERE f.clause = 4) AS relationships_with_a_bad_concept_state,
       count(*) FILTER (WHERE f.clause = 5) AS relationships_not_evidenced_by_their_nodes,
       count(*) FILTER (WHERE f.clause = 6) AS thread_papers_the_map_does_not_hold,
       count(f.clause)                      AS findings_total,
       count(f.clause) = 0                  AS satisfies_publish_invariant
FROM genealogies g
LEFT JOIN map_invariant_findings f ON f.genealogy_id = g.id
GROUP BY g.id, g.concept, g.prompt_version, g.status;


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `lineage_ro` does not automatically hold SELECT on a new view, so without this
-- `pipeline/check_map.py` fails with a permission error against production while
-- working perfectly for the owner. Guarded on pg_roles so a local database that
-- has no such role still migrates. Same shape as `016`'s, `017`'s and `019`'s.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON map_invariant_findings TO lineage_ro;
        GRANT SELECT ON map_invariant TO lineage_ro;
    END IF;
END
$$;

-- 017: the mix of kinds of link — one row per (map, kind), computed on read,
-- stored nowhere.
--
-- Ticket #162, designing #35 (F7). Sibling of `016_map_report.sql`, and every
-- constraint in that file's header applies here unchanged.
--
-- **What was missing.** `016` publishes verification by state, quote reuse,
-- singleton share, largest-meaning share, multi-linked pairs, corpus years and
-- run cost. It touches `edge_type` exactly once, as `count(DISTINCT edge_type)`
-- inside the multi-linked-pair test, so nothing anywhere says how a map's
-- relationships divide across the six kinds. A map whose 300 relationships are
-- 290 `extends` and 10 everything-else reads as an excellent map on every figure
-- `016` publishes — definitions verified, relationships verified, evidence all
-- present — while a classifier returning one label out of six is not
-- classifying. That is the shape a literature which does not move the way this
-- taxonomy assumes would produce, and it is the first thing to go wrong when a
-- map is built outside the field the taxonomy was written against (#164).
--
-- **Nothing is stored** and **no threshold**, for the reasons `016` gives at
-- length. Counted with comments and string literals removed, the numeric
-- literals in this file are exactly {0, 1}: the `0` of the `NULLIF` denominator,
-- which guards a division, and the `1` of `SELECT 1 FROM pg_roles` in the GRANT
-- block at the foot. Neither decides anything. The same two checks `016` carries
-- run here, and both were run on this file rather than reasoned about — the
-- first pass of the census said {0} and had forgotten the GRANT:
--
--   sed -E 's,--.*,,' 017_map_report_by_type.sql | grep -c -i '\bMATERIALIZED\b'   # 0
--   sed -E 's,--.*,,' 017_map_report_by_type.sql \
--     | grep -o -E '(^|[^A-Za-z0-9_.])[0-9]+(\.[0-9]+)?([^A-Za-z0-9_]|$)' \
--     | grep -o -E '[0-9]+(\.[0-9]+)?' | sort -u          # 0 1
--
-- **A third view rather than six more columns on `map_report`.** An edge's kind
-- is a per-kind grain, not a per-map one, exactly as a source is a per-source
-- grain; six columns would have been six homes for one shape. It also keeps this
-- migration purely additive: `CREATE VIEW` and nothing else, so no existing
-- consumer of `map_report` or `map_report_by_source` can be broken by it, and an
-- app deployed before this migration lands loses one figure rather than a page
-- (CLAUDE.md's rule that the app must tolerate a schema one migration behind;
-- `app/lib/report.ts` carries the #92 fallback the RUNBOOK names as the pattern).
--
-- **`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or
-- reorder columns**, so a later change here beyond appending trailing columns is
-- `DROP VIEW map_report_by_type` then `CREATE VIEW`. Consequently no consumer
-- may `SELECT *`: `app/lib/report.ts` and `pipeline/map_report.py` name every
-- column they read.


CREATE VIEW map_report_by_type AS

-- The six of the taxonomy, in the order CLAUDE.md lists them, which is the order
-- both surfaces print them in. **This list is not the authority on what is
-- permitted** — `edges.edge_type`'s CHECK constraint in `001_init.sql` is, and
-- this is a second copy of those six strings, which is a thing this record
-- normally refuses. It is written that way deliberately and the duplication is
-- bounded by the branch below: this list decides only which kinds are *zero
-- filled* and in what order, while `unmatched` emits a row for any kind actually
-- present that is not in it. So widening the CHECK without touching this file
-- makes the new kind appear on the report as an extra row rather than
-- disappearing from the counts, and the sum still equals the map's relationship
-- count. A kind the constraint permits and this view forgot cannot go missing.
--
-- `WITH ORDINALITY` rather than a written-out rank, so the order is the order of
-- the list and there is no second place to keep it in step.
WITH taxonomy AS (
    SELECT edge_type, ordinality AS taxonomy_rank
    FROM unnest(ARRAY['extends', 'contests', 'narrows',
                      'renames', 'merges', 'migrates'])
         WITH ORDINALITY AS t(edge_type, ordinality)
),

-- Every map crossed with every kind, so a kind with none is a row reading zero
-- rather than a row that is not there. Zero is a measurement here and absence is
-- not: "this map has no `contests` links" is the finding, and a page that simply
-- omitted the line would print the same thing a page that never counted it
-- prints.
grid AS (
    SELECT g.id AS genealogy_id, t.edge_type, t.taxonomy_rank
    FROM genealogies g
    CROSS JOIN taxonomy t

    UNION ALL

    -- The escape hatch described above. `NOT IN` against a subquery of six
    -- non-NULL literals, so no NULL semantics are in play; `taxonomy_rank` is
    -- NULL for these and both consumers sort them last, under a name that says
    -- the taxonomy does not know them.
    SELECT DISTINCT e.genealogy_id, e.edge_type, NULL::bigint
    FROM edges e
    WHERE e.edge_type NOT IN (SELECT edge_type FROM taxonomy)
)

SELECT grid.genealogy_id,
       grid.edge_type,
       grid.taxonomy_rank,

       -- `count(e.id)`, not `count(*)`: the join is LEFT, so a kind with no
       -- edges arrives as one row with a NULL `e.id`, and `count(*)` would call
       -- that one edge. The join is on the two columns the grid is keyed by and
       -- `edges.id` is its primary key, so no edge is counted twice and none is
       -- dropped — which is what makes the sum below an identity rather than a
       -- resemblance.
       count(e.id) AS edges,

       -- The denominator is **the sum of this view's own rows for this map**,
       -- not a second count of `edges` and not a read of `map_report.edges_total`.
       -- Two expressions for one total is the pattern `016`'s header refuses, and
       -- computing it here as a window over the counts above makes "the kinds add
       -- up to the map's relationships" true by construction inside this view. The
       -- cross-check that matters to a reader — that this total equals the
       -- `typed relationships` figure `map_report` publishes — stays a falsifier
       -- taken against the live page rather than something this view can assert
       -- about itself.
       --
       -- NULLIF, so a map with no relationships reports the share absent rather
       -- than 0%: zero percent is a claim about a population and there is no
       -- population. Same rule as every share in `016`.
       count(e.id)::numeric
         / NULLIF(SUM(count(e.id)) OVER (PARTITION BY grid.genealogy_id), 0)
                                                             AS edges_share

FROM grid
LEFT JOIN edges e
       ON e.genealogy_id = grid.genealogy_id
      AND e.edge_type    = grid.edge_type
GROUP BY grid.genealogy_id, grid.edge_type, grid.taxonomy_rank;


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `lineage_ro` does not automatically hold SELECT on a new view, so without this
-- `pipeline/map_report.py` fails with a permission error against production
-- while working perfectly for the owner. Guarded on pg_roles so a local database
-- that has no such role still migrates. Same shape as `016`'s.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON map_report_by_type TO lineage_ro;
    END IF;
END
$$;

-- 028: a version number belongs to one map, and a number that has been used is
-- never handed out again.
--
-- Ticket #241 (finding H7), the storage half of the Architect's repair ruling on
-- #241/#242/#243/#244. It ships with `stage_c_cluster.py`'s advisory lock around
-- the mint and is not meaningful without it: the lock is what makes two
-- concurrent builds take N and N+1, and the two objects below are what catch a
-- writer that did not take it.
--
-- **What was measured.** #207b mints `version = max(version) + 1` per concept
-- across prompt versions, with 025's `UNIQUE (concept, prompt_version, version)`
-- named as the thing that "makes a lost race a refusal rather than two rows both
-- calling themselves version 2". On a throwaway Postgres the Tester ran two Stage
-- Cs concurrently and got both halves of that claim wrong. Same prompt version:
-- the loser died on an unhandled `UniqueViolation` after Stage B had already been
-- paid for — a refusal in the sense that a traceback is a refusal, at the worst
-- moment to meet one. Different prompt versions: **both minted version 3**, no
-- error, and one concept held two rows both called version 3, which the app's
-- version list and `version_note` render side by side as siblings.
--
-- ── the index: (concept, version), and the hole in it, stated ───────────────
--
-- The key the system actually means is `(concept, version)`: 025 numbers a
-- concept's versions in ONE sequence across prompt versions, precisely so that a
-- map rebuilt at a new prompt version does not restart at v1 beside a v3 that is
-- still on the site. `genealogies_concept_pv_version_key` keys on the prompt
-- version too, so it cannot see the cross-prompt collision at all — that is the
-- measurement above, not a deduction.
--
-- **It is partial, `WHERE version > 1`, and that is a hole rather than a
-- subtlety.** 025's backfill gave every row that existed at that moment `version
-- 1` by column default: four published maps and every `running`, `failed` and
-- `aborted_spend_cap` row from a build that did not finish, across every prompt
-- version. A total unique index would refuse to be created on the database we
-- have, and renumbering rows that readers have seen — `/g/<id>` is a permanent
-- address since #208 — is a worse trade than a stated hole.
--
-- So, plainly: **version 1 is unconstrained.** Two rows of one concept may both
-- be version 1, and that is exactly what a concept's first build at two prompt
-- versions racing each other would produce. What covers it is the advisory lock
-- in the mint, which is where the number is decided; this index is the backstop
-- that catches a writer which did not take the lock. Above version 1 the index is
-- satisfiable by construction, because a row numbered above 1 can only have come
-- from #207b's Stage C or from `restore_genealogy.py`, both of which mint through
-- the same expression.
--
-- 025's `genealogies_concept_pv_version_key` stays. It is implied by this index
-- for `version > 1` and is the only guard at version 1, which is the half of the
-- space this one gives up.
--
-- ── the ledger: numbers are never re-issued ────────────────────────────────
--
-- `genealogy_deletions` exists because deleting a map must not free its number.
-- The export a map's own Stage E writes is `genealogy_<concept>_<pv>_v<N>.json`,
-- the de-facto backup (incident 4), so a re-minted N overwrites the deleted
-- version's backup on the next build — the one file that could have brought it
-- back, destroyed by a run that was told nothing was wrong. The delete itself is
-- #243 and lands separately; the ledger lands here, because the mint that reads
-- it is here and a ledger arriving after the deletes it is supposed to remember
-- would start life already wrong.
--
-- **A ledger and not a counter.** A `next_version` column per concept is smaller
-- and is a cache of history: if it ever drifts low it re-issues silently, and
-- nothing in the system can tell that it has, because the row it would collide
-- with is the row that was deleted. A ledger cannot drift, because it is not
-- derived from anything — it is the history, and the mint reads the greatest of
-- the live rows and this table.
--
-- **Append-only is enforced, not asked for.** The guarantee above is exactly as
-- strong as the promise that no row leaves this table, so the promise is a
-- trigger rather than a sentence: UPDATE and DELETE raise. To correct the ledger
-- — and correcting it means deciding that a number may be handed out twice — the
-- owner drops `genealogy_deletions_append_only` deliberately, which is the point:
-- it is an act, not a typo.
--
-- ── what this migration does not do ────────────────────────────────────────
--
-- **No column is added to `genealogies`**, so 025's warning does not bite: its
-- `CREATE VIEW genealogies_current AS SELECT *` froze its column list at CREATE
-- time and a migration that adds a column to the table must drop and recreate the
-- view. An index, a table and a trigger are none of those things.
--
-- **The deploy window** (decision 31). Both objects are new, so nothing an app
-- one migration behind names can change meaning: the app does not read
-- `genealogy_deletions` until #243's delete ships, and no read path names the
-- index. Render's pre-deploy applies this before the worker starts, so the Stage C
-- that names the ledger never runs against a database without it — and when it
-- does anyway, on a local database nobody migrated, it refuses by name rather
-- than raising `UndefinedTable` mid-build.
--
-- **No threshold, no score, no grade.** Counted with comments and string literals
-- removed, the numeric literals in this file are exactly {1}: the version above
-- which the index applies, and the `1` of `SELECT 1 FROM pg_roles` in the GRANT.


-- ── one map per (concept, version), above the backfilled floor ─────────────
CREATE UNIQUE INDEX genealogies_concept_version_key
    ON genealogies (concept, version) WHERE version > 1;


-- ── the numbers that have been issued and no longer have a row ─────────────
--
-- One row per deleted genealogy. `genealogy_id` is the id the row had and is not
-- a foreign key — the whole point is that the row is gone — and the columns after
-- it are what the map was at the moment it was deleted, so that a version number
-- appearing in no map can still be accounted for. `deleted_by` is nullable
-- because a CLI path has no authenticated actor; the app's delete fills it with
-- the same login `user_edits` records.
CREATE TABLE genealogy_deletions (
    id             BIGSERIAL PRIMARY KEY,
    genealogy_id   INT         NOT NULL,
    concept        TEXT        NOT NULL,
    prompt_version TEXT        NOT NULL,
    version        INT         NOT NULL,
    status         TEXT,
    was_current    BOOLEAN     NOT NULL DEFAULT false,
    deleted_by     TEXT,
    deleted_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The mint's read: `max(version) WHERE concept = ...`. Both minters run it inside
-- the transaction that inserts, so this index is on the path of every build.
CREATE INDEX genealogy_deletions_concept_version
    ON genealogy_deletions (concept, version);

CREATE FUNCTION genealogy_deletions_no_rewrite() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'genealogy_deletions is append-only: % refused', TG_OP
        USING HINT = 'A version number that has been issued is never re-issued. '
                     'Drop trigger genealogy_deletions_append_only deliberately '
                     'if a number really must be freed.';
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER genealogy_deletions_append_only
    BEFORE UPDATE OR DELETE ON genealogy_deletions
    FOR EACH ROW EXECUTE FUNCTION genealogy_deletions_no_rewrite();


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- The Operator's instruments answer "why is this concept's newest map version 5
-- when the site shows three", and the answer is in this table. `lineage_ro` holds
-- SELECT per table rather than by default, so a new table is invisible to it
-- without this. Guarded on `pg_roles` so a local database with no such role still
-- migrates — the same shape as `016`'s, `017`'s, `019`'s, `023`'s and `025`'s.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON genealogy_deletions TO lineage_ro;
    END IF;
END
$$;

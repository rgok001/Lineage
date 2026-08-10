-- 025: a map's version identity, and currency as a fact the database holds
-- rather than a convention four read functions agree about.
--
-- Ticket #206, the first of the F4 programme (#32) and the one every other
-- ticket in it depends on. **It changes no behaviour.** After this migration
-- every page renders exactly what it renders today: `is_current` is true on the
-- four published maps and false nowhere, nothing reads it, nothing writes it,
-- and the view below has no consumer until #208 and #209. That is deliberate —
-- the shape lands and is verified on an otherwise unchanged system, so a defect
-- in it is found here rather than underneath five other changes.
--
-- **Why currency is a flag on the row and not a `maps` table.** The reviewer's
-- shape and the Architect's agree on immutable rows and an atomic swap and
-- differ only on where the pointer lives. A partial unique index makes two
-- current versions of one concept *impossible*; a pointer column in a second
-- table makes them merely unlikely, and adds an id space, a join on every read,
-- and a second thing to keep in agreement. CLAUDE.md asks for the smallest
-- number of moving parts.
--
-- ── what this migration does NOT do, and why ───────────────────────────────
--
-- **007's `UNIQUE (concept, prompt_version)` stays.** The design ends this
-- migration with `DROP CONSTRAINT genealogies_concept_pv_key`; that statement
-- cannot ship in a ticket that promises unchanged behaviour, and the reason was
-- executed rather than reasoned about (#206, comment). `stage_c_cluster.py`'s
-- UPSERT_GENEALOGY is `INSERT ... ON CONFLICT (concept, prompt_version) DO
-- UPDATE`, and Postgres resolves a conflict target's arbiter index when it PLANS
-- the statement, not when a conflict occurs. With the constraint dropped and
-- Stage C unchanged, that INSERT raises `InvalidColumnReference: there is no
-- unique or exclusion constraint matching the ON CONFLICT specification` on
-- every build — including the first build of a concept nobody has ever mapped,
-- where a conflict is impossible. `UNIQUE (concept, prompt_version, version)`
-- below does not satisfy the inference either: a conflict target must match an
-- index's columns exactly.
--
-- So the drop moves to #207, the commit that rewrites Stage C to insert instead
-- of upsert, and the constraint and the code that needs it change together.
-- Nothing in this migration wants the drop: the partial index, the CHECK and the
-- version key are all independent of it.
--
-- **And 007's third guarantee is still live.** Its header gives three reasons,
-- and the third — "Stage D/E resolve the genealogy by (concept, prompt_version)
-- with a bare fetchone(), nondeterministic the moment a duplicate exists" — is
-- now thirteen scripts, not two. The partial index does not replace it: that
-- index keys on `(concept) WHERE is_current`, which answers a different
-- question. Keeping 007's constraint through this wave keeps all three of its
-- guarantees intact while the shape is proved; #207 carries the list.
--
-- **One residue, named rather than smuggled in.** Nothing here forbids
-- `is_current = true` beside a non-NULL `superseded_at` — a live map recorded as
-- replaced. The design fixes three constraints and says of these two columns
-- "one job each, the second never inferred from the first", so a fourth
-- constraint is not this ticket's to add. If it is wanted it belongs in #207,
-- beside the swap that writes the column. It is raised there.
--
-- **No threshold, no score, no grade.** Counted with comments and string
-- literals removed, the numeric literals in this file are exactly {1}: the
-- default version number, and the `1` of `SELECT 1 FROM pg_roles` in the GRANT.


-- ── the three columns ──────────────────────────────────────────────────────
--
-- Additive and nullable-or-defaulted throughout, because a push to `master`
-- deploys Vercel and Render at once while Render's pre-deploy is what runs the
-- migration (decision 31): the app is live against a schema one migration behind
-- for a few minutes, and an app one migration behind never names these columns.
--
-- `version` is display and ordering, and its DEFAULT is the backfill: every row
-- that exists when this runs becomes version 1 without an UPDATE, because a
-- column added with a non-volatile default is materialised for existing rows.
-- Saying it here rather than writing a redundant UPDATE is the difference
-- between a reader believing the backfill happened and being able to see where.
--
-- `is_current` is **the pointer**, and it is born `false` so that a build's row
-- cannot be mistaken for the live map while it is still being written. That is
-- the whole reason the default is false and not true: the row exists from Stage
-- C, and the map is not a map until Stage E publishes it.
--
-- `superseded_at` is **the record**, written by the swap that clears
-- `is_current` (#207). Two columns, one job each: one is what the read path
-- tests, one is what the page prints. The second is never inferred from the
-- first — "when was this replaced" has no answer derivable from "this is not
-- current", because a row that was never current was never replaced either.
ALTER TABLE genealogies
    ADD COLUMN version       INT         NOT NULL DEFAULT 1,
    ADD COLUMN is_current    BOOLEAN     NOT NULL DEFAULT false,
    ADD COLUMN superseded_at TIMESTAMPTZ;


-- ── the backfill: today's published maps are version 1, current ────────────
--
-- Four rows on this database, one per concept — `embedding` (/g/10), `attention`
-- (/g/13), `dark energy` (/g/17), `instrumental variable` (/g/18) — so the
-- partial index below is satisfiable by construction. Everything else in the
-- table is a `running`, `failed` or `aborted_spend_cap` row from a build that
-- did not finish, and those stay `is_current = false`: they are not published,
-- no read path has ever shown them, and the CHECK below would refuse them
-- anyway.
--
-- `status = 'complete'` is the predicate because that is what publication IS
-- (#168) — the same column `listGenealogies`, `getGenealogy`, `getMapRow` and
-- `listMapReports` already test. Currency is a second, narrower test layered on
-- publication, never a replacement for it.
--
-- **If this ever selects two rows for one concept the migration fails here**,
-- on the index, and the whole file rolls back — `migrate.py` applies every
-- pending migration in one transaction. That is the correct ending rather than a
-- silent choice: two published maps for one concept is a state somebody has to
-- decide about, and a migration that picks a winner would decide it for them at
-- the moment nobody is watching. It cannot happen on this database today; it is
-- written down because the failure would otherwise read as a broken migration
-- rather than as a finding.
UPDATE genealogies SET is_current = true WHERE status = 'complete';


-- ── at most one current map per concept ────────────────────────────────────
--
-- **Per concept, not per (concept, prompt_version).** A newer prompt version's
-- map supersedes the older one rather than sitting beside it, because "one
-- concept, one current map" is the reader's model and the alternative puts two
-- cards for one term on the concepts list. That duplicate is latent today: two
-- `complete` rows differing only in `prompt_version` would both pass every read
-- function's filter, and nothing anywhere refuses it.
--
-- A partial index rather than a constraint because Postgres has no partial
-- UNIQUE constraint; the guarantee is identical and the name says what it is.
-- `WHERE is_current` rather than `WHERE is_current = true` is the same predicate
-- and is what Postgres will print back when anyone asks the catalogue what this
-- index is.
CREATE UNIQUE INDEX genealogies_one_current_per_concept
    ON genealogies (concept) WHERE is_current;


-- ── current implies published ──────────────────────────────────────────────
--
-- #168 made publication an act; this makes "the live map is a published map" a
-- fact the database holds rather than a property four read functions happen to
-- agree about. The direction matters: it constrains currency by status and not
-- status by currency, so a published map that is not current is perfectly legal
-- — that is every superseded version, and after #208 they still render at their
-- own addresses for ever.
--
-- Written `NOT is_current OR status = 'complete'` rather than `is_current
-- IMPLIES ...` because SQL has no implication operator, and this is its
-- definition. Both operands are NOT NULL columns, so no three-valued logic
-- enters: a CHECK is satisfied by NULL, and a nullable column here would mean a
-- row could evade it.
ALTER TABLE genealogies
    ADD CONSTRAINT genealogies_current_is_published
    CHECK (NOT is_current OR status = 'complete');


-- ── a version number cannot be issued twice ────────────────────────────────
--
-- The worker is serial today (#177), so there is no race to lose; this is here
-- so that when there is one it fails loudly instead of minting two rows both
-- calling themselves version 2. #210 replaces the serial worker's accident with
-- a stated rule — at most one in-flight build per concept — and this constraint
-- is what makes that rule's failure mode a refusal rather than a duplicate.
--
-- Redundant while 007's `UNIQUE (concept, prompt_version)` stands, which implies
-- it. That is the point: it ships and is verified now, so #207's drop of 007's
-- constraint is one line against a replacement already in place rather than a
-- swap of one guarantee for another in the same breath.
ALTER TABLE genealogies
    ADD CONSTRAINT genealogies_concept_pv_version_key
    UNIQUE (concept, prompt_version, version);


-- ── the currency filter, as a relation the app can probe ───────────────────
--
-- **A view because of the deploy window, and this is the project's own
-- precedent.** Vercel deploys the app minutes before Render's pre-deploy runs
-- this migration, so a new app must tolerate the old schema. #182 established
-- that a missing *column* cannot be guarded — `app/lib/report.ts` names every
-- column in one statement and would raise `UndefinedColumn` and 500 — while a
-- missing *relation* is guarded by #92's `to_regclass` probe, which `017` and
-- `019` already use. So the currency filter ships as a relation, and the reads
-- that arrive in #208 and #209 probe for it.
--
-- **The fallback is correct rather than degraded**, which is the unusual part.
-- Before this migration there is exactly one row per concept, so an app that
-- cannot find this view and reads `genealogies WHERE status = 'complete'`
-- returns precisely the same set. The reverse direction is safe too: an old app
-- never names the new columns, and no second version can exist until the worker
-- that creates them has deployed with this migration.
--
-- **`SELECT *` here is expanded at CREATE time and then frozen**, the same
-- catalogue behaviour that makes `CREATE OR REPLACE VIEW` unable to reorder or
-- drop a column. So a later migration that adds a column to `genealogies` will
-- NOT see it appear on this view: it must `DROP VIEW genealogies_current` and
-- recreate it, after the ALTER, in that migration. That is written here because
-- the next person to add a column to this table will read this file looking for
-- exactly one thing, and it is this.
--
-- The `*` is deliberate all the same: this view is a filter, not a projection.
-- Naming columns would freeze the same list while implying a choice was made
-- about which ones a reader gets, and a consumer that means "the current rows"
-- should get the row it would have got from the table.
CREATE VIEW genealogies_current AS
    SELECT * FROM genealogies WHERE is_current;


-- ── the read-only role ─────────────────────────────────────────────────────
--
-- `lineage_ro` holds SELECT on `genealogies` but does not inherit it onto a new
-- view, so without this the Operator's instruments fail with a permission error
-- against production while working perfectly for the owner. Guarded on
-- `pg_roles` so a local database with no such role still migrates. Same shape as
-- `016`'s, `017`'s, `019`'s and `023`'s.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lineage_ro') THEN
        GRANT SELECT ON genealogies_current TO lineage_ro;
    END IF;
END
$$;

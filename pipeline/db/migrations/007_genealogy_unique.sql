-- 007: one genealogy per (concept, prompt_version), enforced.
--
-- Stage C used to DELETE then INSERT the genealogy each run, so every re-run
-- minted a NEW row id: links to /g/<id> broke after any re-trace, a crash
-- between Stage C and Stage E left an orphaned 'running' row, and Stage D/E
-- resolve the genealogy by (concept, prompt_version) with a bare fetchone() —
-- nondeterministic the moment a duplicate exists. A UNIQUE constraint fixes all
-- three: it lets Stage C upsert in place (stable id) and makes the lookups
-- provably single-valued.
--
-- Dedupe first so the constraint can be added on a database that ran the old
-- code. Keep the newest row per key; edges cascade-delete with the losers.

DELETE FROM genealogies g
USING genealogies newer
WHERE g.concept = newer.concept
  AND g.prompt_version = newer.prompt_version
  AND g.id < newer.id;

ALTER TABLE genealogies
    ADD CONSTRAINT genealogies_concept_pv_key UNIQUE (concept, prompt_version);

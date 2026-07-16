-- 004: record which model produced each definition.
--
-- The cache key is (paper, concept, prompt_version) per the spec — deliberately
-- NOT including the model, so switching models does not silently re-bill an
-- already-extracted corpus. The trade-off is that the model becomes invisible:
-- without this column there is no way to tell an Opus definition from a Haiku
-- one, which matters for a workbench whose whole claim is auditable evidence.
--
-- Provenance, not cache key. To deliberately re-extract with a different model,
-- bump PROMPT_VERSION.

ALTER TABLE definitions ADD COLUMN model TEXT;

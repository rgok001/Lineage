-- 003: record "this paper does NOT define the concept" as a real result.
--
-- Stage B's cache asks whether a definitions row exists for
-- (paper, concept, prompt_version). Negative verdicts wrote no row, so every
-- re-run re-paid the LLM for papers already known not to define the concept —
-- on a 150-paper corpus that is most of the corpus and most of the bill.
--
-- A negative is a finding, not an absence of one. Store it, with empty
-- definition/quote. Downstream stages (C onwards) must filter
-- defines_concept = true.

ALTER TABLE definitions ADD COLUMN defines_concept BOOLEAN NOT NULL DEFAULT true;

CREATE INDEX idx_definitions_concept_defines
    ON definitions (concept, prompt_version, defines_concept);

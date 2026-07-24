-- 010: store the BASIS of each edge — what one paper did to the concept, and how.
--
-- Until now an edge stored only its type, confidence, and each paper's own
-- definition quote. That answers "are these two related?" but not the question a
-- researcher actually asks: "what did the later paper take from the earlier one,
-- and how did it move the concept forward?"
--
-- Stage D already computes that answer, twice, and threw both away:
--   * rationale        — the classifier's one-sentence justification for the type,
--                        model-generated prose ("generalises A's word-vector
--                        formulation to graph nodes"). This is reasoning, NOT a
--                        verbatim quote: it is not string-verifiable and must
--                        never render with the verified ✓ (core product rule 2).
--   * citation_context — the verbatim sentence(s) from the citing paper where it
--                        cites the earlier one, from Semantic Scholar. Real text,
--                        but from S2's PDF extraction, so it will NOT string-match
--                        our LaTeX-extracted source and Stage E cannot ground it.
--                        Display as "verbatim, per Semantic Scholar", never as a
--                        grounded quote.
--
-- Both nullable: edges built before this migration have neither, and a citation
-- with no context sentence still classifies fine.

ALTER TABLE edges ADD COLUMN IF NOT EXISTS rationale        TEXT;
ALTER TABLE edges ADD COLUMN IF NOT EXISTS citation_context TEXT;

-- 002: record how well a paper's title matches its extracted text.
--
-- Guards against upstream metadata mismatches: OpenAlex sometimes attaches the
-- wrong arXiv ID to a work, so the fetch succeeds but the text belongs to a
-- different paper. Downstream stages should require text_title_match >= 0.5
-- rather than trusting extracted_text_path alone.
--
-- NULL = not yet computed. 0..1 = fraction of significant title words found.

ALTER TABLE papers ADD COLUMN text_title_match REAL;

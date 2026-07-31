-- 013: what we know about the fidelity of a paper's extracted text.
--
-- The grounding check certifies that a quote is a span of our extracted text.
-- It cannot certify that the text is a faithful rendering of the paper, and
-- incident 10 is what the gap costs: the extractor was dropping citation macros
-- in silence, both sides of the comparison came from the same damaged file, and
-- every mangled quote passed. The same class of bug then turned up one level
-- wider, in the macros papers define for themselves.
--
-- check_extraction.py --write fills these. A verdict is a lower bound: it finds
-- damage that leaves a mark, and silence leaves none, so NULL means unchecked
-- and 'clean' means nothing was found rather than nothing is wrong.

ALTER TABLE papers
    ADD COLUMN extraction_verdict    TEXT
        CHECK (extraction_verdict IN ('clean', 'suspect', 'damaged')),
    ADD COLUMN extraction_signals    JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN extraction_checked_at TIMESTAMPTZ;

-- The dossier asks for one paper by arxiv_id; the audit asks for the corpus's
-- worst. Only the second wants an index.
CREATE INDEX papers_extraction_verdict_idx ON papers (extraction_verdict)
    WHERE extraction_verdict IS DISTINCT FROM 'clean';

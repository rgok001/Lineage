-- 006: give a trace request a subject field and a sense gloss.
--
-- field_id scopes corpus selection to an OpenAlex field (its classification of
-- a paper's primary subject) instead of the old hardcoded Computer Science
-- concept. Default 'fields/17' is Computer Science, so existing behaviour and
-- the CLI are unchanged when nothing is chosen. A polysemous word collides
-- WITHIN a field (OS "kernel" vs ML "kernel" are both computer science), so
-- the field is not a disambiguator; the gloss is.
--
-- gloss is the requester's one-line clarification of which sense they mean
-- ("kernel, as in kernel methods for SVMs"). It does two jobs downstream: it
-- becomes the embedding query for seed relevance (so retrieval ranks the right
-- sense first), and it is injected into Stage B's extraction question (so
-- "does this paper define <concept>?" is asked about the intended sense). NULL
-- means no gloss: the bare concept is used, exactly as before.

ALTER TABLE trace_requests ADD COLUMN field_id TEXT NOT NULL DEFAULT 'fields/17';
ALTER TABLE trace_requests ADD COLUMN gloss    TEXT;

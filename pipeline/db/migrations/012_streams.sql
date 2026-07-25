-- 012: the river — conceptual streams of how the term evolved, generated per map.
--
-- A separate rendering from nodes/edges: nodes are senses, edges are pairwise
-- links, but a researcher wants the streams (parallel currents of the idea) and
-- the cross-currents where one fed another. This is produced by reading the
-- corpus's content (definitions + contributions), not its citation topology, so
-- it lives as its own generated artifact rather than being derived at render time.
--
-- Shape (JSONB):
--   { "through_line": text,
--     "streams": [ { "id", "name", "tagline", "arc", "color", "origin_year",
--                    "papers": [ { "arxiv","year","title","move","prose","quote" } ] } ],
--     "cross_currents": [ { "from","to","year","label" } ] }
-- Each paper's "quote" is a string-verified span; "move"/"prose" are grounded
-- synthesis leashed to the paper's own extracted content. Nullable: only maps
-- that have had the streams job run carry it.

ALTER TABLE genealogies ADD COLUMN IF NOT EXISTS streams JSONB;

-- 015: a stamp names the bytes it was checked against.
--
-- Ticket #29 ([F1]); the design is docs/design/recheckable-stamp.md.
--
-- Every verification stamp in this database is an assertion the pipeline made
-- about a file on one worker's disk at one moment, and nothing stored beside it
-- says which file, which bytes, or where in them the quote was found.
-- definitions.quote_verified and edges.verified are bare booleans and the only
-- link back to the evidence is papers.extracted_text_path, a relative path on
-- one machine. A reader cannot re-check a tick, and neither can we without
-- holding the corpus. That is not evidence about a paper; it is our claim that
-- we once looked, and it is the project's defining incident one level up
-- (incidents 10 and 12, decisions 21 and 25).
--
-- Three facts per stamp, all true at the moment the match ran: where in the text
-- it matched, a digest of the bytes it matched against, and which extractor
-- produced those bytes. Plus, on papers, the digest of the file as it is on disk
-- now. A stamp is displayable as verified only when its digest equals the
-- paper's current digest; otherwise it renders stale, whatever the boolean says.
--
-- The two digests are never copied from one another: one is written by the code
-- that just performed the match, the other by the code that just wrote the file.
-- That is what lets the comparison return false, and it is the whole feature.
--
-- Additive only. No DEFAULT and no NOT NULL, so no row is rewritten and no table
-- rewrite lock is taken. NULL is meaningful everywhere below: it means this
-- stamp was never made in a re-checkable way, and it renders stale.
--
-- **There is no honest backfill of a stamp column.** Filling quote_text_digest
-- from the paper's current digest would turn every unproven stamp green in one
-- statement, which is the silent re-anchoring incident 10 forbids. The only way
-- a stamp becomes re-checkable is by being re-checked, and re-checking is free
-- (stage_b_extract.py --reground, then stage_e_ground.py). Between this
-- migration and that re-ground every stamp renders stale, including all 287
-- verified edges on `attention`. That is correct: those stamps genuinely are not
-- re-checkable, which is what the ticket says.
--
-- No index. The staleness test always runs alongside the join to papers that the
-- evidence page and the exports already do, and these tables are in the hundreds.

ALTER TABLE papers
    ADD COLUMN extracted_text_digest TEXT,
    ADD COLUMN extractor_version     TEXT;

-- papers.extractor_version stays NULL for text extracted before this migration,
-- and that is the point rather than a gap: NULL IS DISTINCT FROM any real
-- version, so `WHERE extractor_version IS DISTINCT FROM <current>` selects
-- exactly the papers whose text predates the current extractor. That query is
-- backlog item 4, which this column unblocks. extract_text.py writes it only
-- when it has just produced the file, never on the skip path, because a skip
-- knows the bytes and not who made them.

ALTER TABLE definitions
    ADD COLUMN quote_start             INT,
    ADD COLUMN quote_end               INT,
    ADD COLUMN quote_text_digest       TEXT,
    ADD COLUMN quote_extractor_version TEXT;

-- Half-open character offsets into the UTF-8 decoding of the file's bytes, NULL
-- when nothing matched. **The unit is Unicode code points, not UTF-16 code
-- units, because Python is what indexes the text: JavaScript must not slice with
-- these directly.** For any character outside the BMP the two disagree, and a
-- JS reader slicing a Python offset gets a passage shifted by one per astral
-- character before it -- measured, a line with one U+1D465 and one emoji is 47
-- code points and 49 code units, and the slice lands two short (issue #61).
-- Anything in TypeScript that consumes these converts once at the boundary
-- rather than per caller. Same for a third party who reproduces the digest with
-- sha256sum and then indexes the text with a UTF-16 tool.
-- The span is deliberately NOT a second confirmation of
-- the boolean: slicing it and finding the quote there proves nothing, because
-- the same matcher put it there. It is stored so a human can look, and so
-- somebody can one day measure *where* matches land -- a short quote grounding
-- inside a bibliography is a real failure this system currently cannot see.

ALTER TABLE edges
    ADD COLUMN source_quote_start       INT,
    ADD COLUMN source_quote_end         INT,
    ADD COLUMN source_text_digest       TEXT,
    ADD COLUMN source_extractor_version TEXT,
    ADD COLUMN target_quote_start       INT,
    ADD COLUMN target_quote_end         INT,
    ADD COLUMN target_text_digest       TEXT,
    ADD COLUMN target_extractor_version TEXT;

-- Flat columns rather than one JSONB blob, source_/target_-prefixed to match the
-- quote columns already there: the staleness test is a join predicate against
-- papers, and the table already carries its evidence in this shape.
--
-- Not derived by joining to the definition's stamp. Stage E's re-sync
-- deliberately skips empty definitions, so an edge quote can legitimately differ
-- from the definition quote, and a joined stamp would then be a verdict about a
-- different string. A stamp must be about the unit it is displayed on.

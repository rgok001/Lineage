-- 009: correct publication years that OpenAlex placed in the future.
--
-- A genealogy is ordered by when an idea first appeared, so a wrong year does
-- not just mislabel a card, it reorders history. OpenAlex dated
-- "Attention Is All You Need" (arXiv 1706.03762) to 2025, which rendered a 2017
-- pivot paper as the newest work in its lineage.
--
-- The fetcher now stores the earliest credible date (see fetch_papers
-- .earliest_year): the minimum of the OpenAlex year and the year encoded in the
-- arXiv id itself. This migration applies the same rule to rows already stored,
-- but only where the stored year is LATER than the arXiv id's own date. Rows
-- where the stored year is earlier are left alone: those are genuinely old
-- papers uploaded to arXiv years afterwards, where OpenAlex holds the true date.
--
-- New-style ids are YYMM.NNNNN; old-style are archive/YYMMNNN. Both encode the
-- submission year in the first two digits of the numeric part.

UPDATE papers
SET year = sub.arxiv_year
FROM (
    SELECT arxiv_id,
           CASE
               WHEN arxiv_id ~ '^[0-9]{4}\.[0-9]{4,5}$'
                   THEN 2000 + substring(arxiv_id from 1 for 2)::int
               WHEN arxiv_id ~ '^[a-z\-\.]+/[0-9]{7}$'
                   THEN CASE
                       WHEN substring(split_part(arxiv_id, '/', 2) from 1 for 2)::int >= 91
                           THEN 1900 + substring(split_part(arxiv_id, '/', 2) from 1 for 2)::int
                       ELSE 2000 + substring(split_part(arxiv_id, '/', 2) from 1 for 2)::int
                   END
           END AS arxiv_year
    FROM papers
) AS sub
WHERE papers.arxiv_id = sub.arxiv_id
  AND sub.arxiv_year IS NOT NULL
  AND papers.year > sub.arxiv_year;

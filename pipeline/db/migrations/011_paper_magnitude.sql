-- 011: per-paper magnitude scores that decide the paper-centric spine order.
--
-- A researcher asks "which papers shaped this term, and how" — so the page needs
-- to rank papers, not just cluster them. Two orthogonal scores (proven
-- uncorrelated on /g/10: Spearman +0.05), each answering a different question:
--   attention    — how hard later work leaned on THIS paper for the term. Not raw
--                  citations (that rewards famous-but-incidental work like a vision
--                  backbone); an ON-TERM weighted count where each citation is
--                  scored by whether the citing sentence actually engages this
--                  paper's embedding contribution.
--   displacement — how far this paper moved the term's meaning from what came
--                  before (distance of its definition embedding from the centroid
--                  of earlier definitions). Marks turning points, which attention
--                  structurally misses (a paper that moves a term is cited by the
--                  field it moved INTO, not this corpus).
--
-- Both per (paper, concept, prompt_version) — a paper's magnitude is relative to
-- the term being traced — so they live on definitions. Both nullable: scores are
-- computed by a post-Stage-D job, and the earliest paper has no earlier work to
-- be displaced from.

ALTER TABLE definitions ADD COLUMN IF NOT EXISTS attention    REAL;
ALTER TABLE definitions ADD COLUMN IF NOT EXISTS displacement REAL;

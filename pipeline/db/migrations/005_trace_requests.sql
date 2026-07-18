-- 005: trace requests — one table that is both the request inbox and the job queue.
--
-- Running a trace costs real money (~$6 of LLM spend at 150 papers), so a
-- public "trace" button is a way for strangers to spend the owner's money.
-- Instead: anyone signed in may REQUEST a trace (status 'requested'); only the
-- owner's decision moves it to 'approved'. The worker polls for 'approved'
-- ONLY — a row can never reach the worker without passing through the owner.
-- The owner's own submissions are inserted directly as 'approved'.
--
-- The worker claims a job with UPDATE ... FOR UPDATE SKIP LOCKED, so Postgres
-- itself is the queue: no second piece of infrastructure, and two workers can
-- never claim the same row.
--
-- progress is written by the worker as it streams the pipeline's stdout:
--   {"stage": "extract definitions", "stage_no": 4, "stages": 7,
--    "message": "[47/132] 1810.04805: …", "current": 47, "total": 132,
--    "spend_usd": 1.23}
-- updated_at doubles as the worker heartbeat: a 'running' row whose updated_at
-- is minutes old means the worker died mid-job.

CREATE TABLE trace_requests (
    id           BIGSERIAL PRIMARY KEY,
    concept      TEXT NOT NULL,
    corpus_limit INT NOT NULL DEFAULT 150 CHECK (corpus_limit BETWEEN 5 AND 300),
    requested_by TEXT NOT NULL,            -- GitHub login of the requester
    note         TEXT,                     -- requester's "why this concept"
    status       TEXT NOT NULL DEFAULT 'requested'
                 CHECK (status IN ('requested', 'approved', 'rejected',
                                   'running', 'complete', 'failed')),
    decided_by   TEXT,                     -- owner login who approved/rejected
    decided_at   TIMESTAMPTZ,
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    progress     JSONB NOT NULL DEFAULT '{}',
    error        TEXT,                     -- failure reason + stdout tail
    genealogy_id BIGINT REFERENCES genealogies(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_trace_requests_status ON trace_requests (status);

-- One open request per concept, enforced where it can't be raced: the app
-- checks too, but two simultaneous submits would both pass an app-level check.
CREATE UNIQUE INDEX idx_trace_requests_open_concept
    ON trace_requests (concept)
    WHERE status IN ('requested', 'approved', 'running');

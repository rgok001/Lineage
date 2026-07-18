import { sql } from "./db";

/** A trace request is both a request-for-approval and (once approved) a queue
 *  job. The status column is the whole workflow:
 *
 *    requested -> approved -> running -> complete
 *            \-> rejected           \-> failed
 *
 *  The worker (worker/run.py) polls for 'approved' only, so nothing a
 *  non-owner does can start a run — approval is the owner's alone. */
export type TraceProgress = {
  stage?: string;
  stage_no?: number;
  stages?: number;
  message?: string;
  current?: number | null;
  total?: number | null;
  spend_usd?: number;
};

export type TraceRequest = {
  id: number;
  concept: string;
  corpus_limit: number;
  requested_by: string;
  note: string | null;
  status: "requested" | "approved" | "rejected" | "running" | "complete" | "failed";
  decided_by: string | null;
  started_at: string | null;
  finished_at: string | null;
  progress: TraceProgress;
  error: string | null;
  genealogy_id: number | null;
  created_at: string;
  updated_at: string;
};

/** The DB is the only clock anyone shares. Timestamps come from Postgres
 *  now(), so "how long ago" must be measured against Postgres now() too — a
 *  viewer's machine clock can be minutes (or hours) off, which would corrupt
 *  both the relative times and the worker-heartbeat staleness check. */
export async function dbNow(): Promise<string> {
  const [{ now }] = (await sql`SELECT now() AS now`) as { now: string }[];
  return new Date(now).toISOString();
}

export async function listTraceRequests(): Promise<TraceRequest[]> {
  return (await sql`
    SELECT id, concept, corpus_limit, requested_by, note, status, decided_by,
           started_at, finished_at, progress, error, genealogy_id,
           created_at, updated_at
    FROM trace_requests
    ORDER BY created_at DESC
    LIMIT 50
  `) as TraceRequest[];
}

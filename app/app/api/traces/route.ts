import { dbNow, listTraceRequests } from "../../../lib/traces";

/** Read-only polling endpoint for live trace progress. The worker writes
 *  progress into trace_requests; clients poll this every few seconds while a
 *  trace is active. Plain polling beats SSE here: on serverless there is no
 *  process to hold a stream open, and the progress lives in Postgres anyway. */
export const dynamic = "force-dynamic";

export async function GET() {
  const [now, rows] = await Promise.all([dbNow(), listTraceRequests()]);
  return Response.json({ now, rows });
}

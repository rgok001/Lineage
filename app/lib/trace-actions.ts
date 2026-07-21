"use server";

import { revalidatePath } from "next/cache";
import { getViewer, isOwner, requireOwner, requireViewer } from "./authz";
import { sql } from "./db";

/** Server Actions for the trace queue. Same security posture as actions.ts:
 *  every mutation authorises itself on its first line, because a Server Action
 *  is a public HTTP endpoint no matter what the UI shows.
 *
 *  Money rule: a run costs real LLM spend (~$6 at 150 papers), so nothing here
 *  ever inserts 'approved' except on behalf of the owner. Everyone else's
 *  request parks at 'requested' until the owner decides. */

export type TraceFormState = { ok: boolean; message: string } | null;

const CONCEPT_RE = /^[a-z0-9][a-z0-9 -]{1,59}$/;
const FIELD_RE = /^fields\/\d{1,4}$/;
const DEFAULT_FIELD_ID = "fields/17"; // Computer Science

// Non-owner quota: an inbox for humans, not an API.
const MAX_OPEN_PER_USER = 1;
const MAX_PER_WEEK = 3;

export async function requestTrace(
  _prev: TraceFormState,
  formData: FormData,
): Promise<TraceFormState> {
  const viewer = await requireViewer();
  const owner = isOwner(viewer);

  // Normalise then whitelist: this string becomes a worker subprocess argument
  // and part of a filename, so it is validated at the door, once, strictly.
  const concept = String(formData.get("concept") ?? "")
    .trim().toLowerCase().replace(/\s+/g, " ");
  const note = String(formData.get("note") ?? "").trim().slice(0, 500) || null;

  // Subject field: scopes the corpus to a discipline. Validate the shape (it
  // becomes a CLI arg); a malformed value falls back to Computer Science rather
  // than blocking the request. The dropdown only ever sends valid ids.
  const rawField = String(formData.get("field_id") ?? "");
  const fieldId = FIELD_RE.test(rawField) ? rawField : DEFAULT_FIELD_ID;

  // Sense gloss: free text, so strip control chars and bound the length. Passed
  // to subprocesses as a single argv element (no shell), and into an LLM prompt.
  const gloss =
    String(formData.get("gloss") ?? "").replace(/[\x00-\x1f]/g, " ").trim().slice(0, 200) ||
    null;

  if (!CONCEPT_RE.test(concept)) {
    return {
      ok: false,
      message: "Concept names are 2–60 characters: letters, numbers, spaces, and hyphens.",
    };
  }

  // A concept that already has a genealogy is refused for everyone — partly to
  // avoid duplicate spend, mostly because re-running Stage C would overwrite
  // the curated nodes of the existing map. Deliberate re-traces stay CLI-only.
  const existing = (await sql`
    SELECT id FROM genealogies WHERE concept = ${concept} LIMIT 1
  `) as { id: number }[];
  if (existing.length) {
    return { ok: false, message: `“${concept}” has already been traced. Its genealogy is listed above.` };
  }

  if (!owner) {
    const [{ open, week }] = (await sql`
      SELECT count(*) FILTER (WHERE status IN ('requested', 'approved', 'running')) AS open,
             count(*) FILTER (WHERE created_at > now() - interval '7 days')         AS week
      FROM trace_requests WHERE requested_by = ${viewer.login}
    `) as { open: number; week: number }[];
    if (Number(open) >= MAX_OPEN_PER_USER) {
      return { ok: false, message: "You already have a request in progress. Requests are limited to one at a time." };
    }
    if (Number(week) >= MAX_PER_WEEK) {
      return { ok: false, message: `You have reached the limit of ${MAX_PER_WEEK} requests per week.` };
    }
  }

  // Corpus size is the cost dial (~$6 at 150 papers), so only the owner's
  // choice is honoured; everyone else gets the default.
  const corpusLimit = owner
    ? Math.min(300, Math.max(5, Number(formData.get("corpus_limit")) || 150))
    : 150;

  try {
    if (owner) {
      await sql`
        INSERT INTO trace_requests
          (concept, note, requested_by, corpus_limit, field_id, gloss, status, decided_by, decided_at)
        VALUES
          (${concept}, ${note}, ${viewer.login}, ${corpusLimit}, ${fieldId}, ${gloss}, 'approved', ${viewer.login}, now())
      `;
    } else {
      await sql`
        INSERT INTO trace_requests (concept, note, requested_by, field_id, gloss)
        VALUES (${concept}, ${note}, ${viewer.login}, ${fieldId}, ${gloss})
      `;
    }
  } catch (e) {
    // 23505 = the partial unique index on open requests per concept: someone
    // beat us to it between our checks and the insert. The index is the real
    // guard; this is just the polite version of its message.
    if ((e as { code?: string }).code === "23505") {
      return { ok: false, message: `There is already an open request for “${concept}”.` };
    }
    throw e;
  }

  revalidatePath("/");
  return {
    ok: true,
    message: owner
      ? `Queued. “${concept}” will begin shortly.`
      : `Request received. The curator reviews all requests before a trace runs; progress will appear here.`,
  };
}

export async function approveTrace(formData: FormData) {
  const who = await requireOwner();
  const id = Number(formData.get("id"));
  await sql`
    UPDATE trace_requests
    SET status = 'approved', decided_by = ${who.login}, decided_at = now(), updated_at = now()
    WHERE id = ${id} AND status = 'requested'
  `;
  revalidatePath("/");
}

/** Rejects a pending request — or withdraws an approved one the worker has not
 *  claimed yet. Once 'running', the row belongs to the worker. */
export async function rejectTrace(formData: FormData) {
  const who = await requireOwner();
  const id = Number(formData.get("id"));
  await sql`
    UPDATE trace_requests
    SET status = 'rejected', decided_by = ${who.login}, decided_at = now(), updated_at = now()
    WHERE id = ${id} AND status IN ('requested', 'approved')
  `;
  revalidatePath("/");
}

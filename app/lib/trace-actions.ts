"use server";

import { revalidatePath } from "next/cache";
import { MAX_ANCHORS, parseAnchors } from "./arxiv-id";
import { getViewer, isOwner, requireOwner, requireViewer } from "./authz";
import { sql } from "./db";
import { getArxivFields, isKnownField } from "./openalex";

/** Server Actions for the trace queue. Same security posture as actions.ts:
 *  every mutation authorises itself on its first line, because a Server Action
 *  is a public HTTP endpoint no matter what the UI shows.
 *
 *  Money rule: a run costs real LLM spend (~$6 at 150 papers), so nothing here
 *  ever inserts 'approved' except on behalf of the owner. Everyone else's
 *  request parks at 'requested' until the owner decides. */

export type TraceFormState = { ok: boolean; message: string } | null;

const CONCEPT_RE = /^[a-z0-9][a-z0-9 -]{1,59}$/;

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

  // Subject field: scopes the corpus to a discipline, and becomes a CLI arg for
  // corpus_select.py --field. Checked for membership of the real field list
  // below, not merely for shape.
  const fieldId = String(formData.get("field_id") ?? "");

  // Sense gloss: free text, so strip control chars and bound the length. Passed
  // to subprocesses as a single argv element (no shell), and into an LLM prompt.
  const gloss =
    String(formData.get("gloss") ?? "").replace(/[\x00-\x1f]/g, " ").trim().slice(0, 200) ||
    null;

  // Papers the requester names (issue #198). Every id is normalised to the one
  // spelling this system stores and a bad one is NAMED BACK rather than dropped:
  // a silently discarded id is a requester believing their paper is in a map that
  // does not contain it, which is the one failure this feature may not have.
  //
  // Shape here, existence in the pipeline. `corpus_select.py` resolves every
  // named id against OpenAlex before the build fetches or spends anything and
  // refuses the whole run by name if one does not resolve, so a check here would
  // be a second answer to a question the later one has to settle anyway: an id
  // can be well-formed, resolve at request time, and still be unfindable when the
  // build runs. The 500-character bound is the same posture the note field has;
  // the cap is enforced after duplicates fold.
  const anchorsRaw = String(formData.get("anchors") ?? "").slice(0, 500);
  const anchorParse = parseAnchors(anchorsRaw);

  if (!CONCEPT_RE.test(concept)) {
    return {
      ok: false,
      message: "Concept names are 2–60 characters: letters, numbers, spaces, and hyphens.",
    };
  }

  if (!anchorParse.ok) {
    return {
      ok: false,
      message: anchorParse.reason === "too many"
        ? `Name at most ${MAX_ANCHORS} papers. Naming more than that is a different thing from pointing at the ones a map should not miss.`
        : `“${anchorParse.bad}” is not an arXiv id, so nothing was submitted. Use the id as it appears on the paper, like 2404.03002 or hep-th/9711200, separated by spaces or commas.`,
    };
  }
  const anchors = anchorParse.ids;

  // The picker is not the allow-list, because this is a public HTTP endpoint no
  // matter what the UI renders (issue #175). The old check was a shape test,
  // /^fields\/\d{1,4}$/, which accepted ten thousand ids for the twenty-six that
  // exist: `fields/9999` passed, was approved, and died at Stage A with no seeds.
  // Membership of the list the picker is drawn from is the real constraint, so
  // ask for that list and check against it.
  //
  // Refusing beats the substitution this replaces. A shape failure used to be
  // rewritten to Computer Science in silence, which answers a request for one
  // subject with a map of another — the quieter half of the same defect.
  if (!isKnownField(await getArxivFields(), fieldId)) {
    return {
      ok: false,
      message: "That subject is not one we can search. Choose one from the list and try again.",
    };
  }

  // A concept that already has a genealogy is refused for everyone — partly to
  // avoid duplicate spend, mostly because re-running Stage C would overwrite
  // the curated nodes of the existing map. Deliberate re-traces stay CLI-only.
  const existing = (await sql`
    SELECT id FROM genealogies WHERE concept = ${concept} LIMIT 1
  `) as { id: number }[];
  if (existing.length) {
    return { ok: false, message: `“${concept}” is already mapped. You can open it from the home page.` };
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

  // `anchors` writes the empty array rather than nothing when nobody was named,
  // so the row records "the field was offered and declined" instead of "the field
  // did not exist" — which is what NULL means on this column, and which only rows
  // predating migration 023 may say.
  const insert = async (withAnchors: boolean) => {
    if (owner && withAnchors) {
      await sql`
        INSERT INTO trace_requests
          (concept, note, requested_by, corpus_limit, field_id, gloss, anchors, status, decided_by, decided_at)
        VALUES
          (${concept}, ${note}, ${viewer.login}, ${corpusLimit}, ${fieldId}, ${gloss}, ${anchors}, 'approved', ${viewer.login}, now())
      `;
    } else if (owner) {
      await sql`
        INSERT INTO trace_requests
          (concept, note, requested_by, corpus_limit, field_id, gloss, status, decided_by, decided_at)
        VALUES
          (${concept}, ${note}, ${viewer.login}, ${corpusLimit}, ${fieldId}, ${gloss}, 'approved', ${viewer.login}, now())
      `;
    } else if (withAnchors) {
      await sql`
        INSERT INTO trace_requests (concept, note, requested_by, field_id, gloss, anchors)
        VALUES (${concept}, ${note}, ${viewer.login}, ${fieldId}, ${gloss}, ${anchors})
      `;
    } else {
      await sql`
        INSERT INTO trace_requests (concept, note, requested_by, field_id, gloss)
        VALUES (${concept}, ${note}, ${viewer.login}, ${fieldId}, ${gloss})
      `;
    }
  };

  try {
    await insert(true);
  } catch (e) {
    const code = (e as { code?: string }).code;
    // 23505 = the partial unique index on open requests per concept: someone
    // beat us to it between our checks and the insert. The index is the real
    // guard; this is just the polite version of its message.
    if (code === "23505") {
      return { ok: false, message: `There is already an open request for “${concept}”.` };
    }
    // 42703 = there is no `anchors` column yet. A push deploys Vercel and Render
    // at once and Render's pre-deploy is what runs the migration, so for a few
    // minutes this app is live against a schema one migration behind, and
    // CLAUDE.md requires it to tolerate that. Caught rather than probed for,
    // because a probe answers about a NAME and this asks the question that
    // matters — can this statement run here, now — and costs nothing on every
    // deployment that has the column (#92's third case).
    //
    // The two arms are different on purpose. Nobody named a paper, so nothing is
    // lost: queue the request in its old shape, and the row's NULL then says
    // truthfully that no name is recorded for it. Somebody DID name papers, so
    // queueing without them would build a map missing the papers they asked for
    // and tell them nothing — the one outcome this feature may not have. Refuse,
    // name the reason, and let them press the button again in a minute.
    if (code === "42703") {
      if (anchors.length) {
        return {
          ok: false,
          message: "The papers you named could not be recorded yet, so nothing was submitted. This part of the site finishes updating within a few minutes; try again then, or submit without naming any.",
        };
      }
      console.warn("[trace] trace_requests.anchors is not there yet; queued without it");
      try {
        await insert(false);
      } catch (e2) {
        if ((e2 as { code?: string }).code === "23505") {
          return { ok: false, message: `There is already an open request for “${concept}”.` };
        }
        throw e2;
      }
    } else {
      throw e;
    }
  }

  revalidatePath("/");
  revalidatePath("/trace");
  // The count is echoed back rather than left implied: the field takes free text
  // and folds duplicates, so "3 papers" beside a submit is the only place a
  // requester learns that what they typed was read as what they meant.
  const named = anchors.length
    ? ` ${anchors.length} named paper${anchors.length > 1 ? "s" : ""} will be read: ${anchors.join(", ")}.`
    : "";
  return {
    ok: true,
    message: owner
      ? `Queued. “${concept}” starts shortly; progress appears below.${named}`
      : `Request received. A curator reviews each one before it runs; progress will appear below.${named}`,
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
  revalidatePath("/trace");
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
  revalidatePath("/trace");
}

/** Sign-in that returns you to the request page rather than the home page, so
 *  the form you came for is the thing you land on. */
export async function signInHere() {
  const { signIn } = await import("../auth");
  await signIn("github", { redirectTo: "/trace" });
}

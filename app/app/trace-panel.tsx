"use client";

import Link from "next/link";
import { useActionState, useCallback, useEffect, useRef, useState } from "react";
import { approveTrace, rejectTrace, requestTrace, signInHere } from "../lib/trace-actions";
import type { TraceRequest } from "../lib/traces";
import type { ArxivField } from "../lib/openalex";

/**
 * The live-trace panel: request form, queue, and progress.
 *
 * Progress transport is plain polling of /api/traces every 3s while any trace
 * is active. The worker already writes progress rows to Postgres; a poll of a
 * tiny JSON route gives the same live feel as SSE without holding serverless
 * functions open, and it survives reconnects and redeploys for free.
 *
 * The owner-only buttons here are cosmetic gating — the real authorisation is
 * inside the Server Actions themselves (lib/trace-actions.ts).
 */

const STATUS_COLOR: Record<TraceRequest["status"], string> = {
  requested: "var(--edge-renames)",
  approved: "var(--edge-extends)",
  running: "var(--edge-narrows)",
  complete: "var(--verified)",
  failed: "var(--inferred)",
  rejected: "var(--ink-soft)",
};

const ACTIVE = new Set(["requested", "approved", "running"]);

/** Seconds elapsed since `iso`, measured on the DATABASE's clock: skewMs is
 *  (client now − DB now) sampled at fetch time, so subtracting it removes the
 *  viewer's clock error. Timestamps and now() both come from Postgres; the
 *  client clock alone decides nothing. */
function elapsedS(iso: string, skewMs: number): number {
  return Math.max(0, (Date.now() - skewMs - new Date(iso).getTime()) / 1000);
}

function ago(iso: string, skewMs: number): string {
  const s = elapsedS(iso, skewMs);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function TracePanel({
  initial,
  initialNow,
  fields,
  defaultField,
  signedIn,
  owner,
}: {
  initial: TraceRequest[];
  initialNow: string;
  fields: ArxivField[];
  // Passed in rather than imported, so the one definition in lib/openalex.ts
  // stays server-side. It was spelled "fields/17" here and in trace-actions.ts
  // as well, three copies of one id (issue #175).
  defaultField: string;
  signedIn: boolean;
  owner: boolean;
}) {
  const [rows, setRows] = useState(initial);
  const [skewMs, setSkewMs] = useState(() => Date.now() - new Date(initialNow).getTime());
  const [formState, formAction, pending] = useActionState(requestTrace, null);
  const formRef = useRef<HTMLFormElement>(null);

  const anyActive = rows.some((r) => ACTIVE.has(r.status));

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/traces", { cache: "no-store" });
      if (res.ok) {
        const data: { now: string; rows: TraceRequest[] } = await res.json();
        setRows(data.rows);
        setSkewMs(Date.now() - new Date(data.now).getTime());
      }
    } catch {
      /* transient network blip — next tick will retry */
    }
  }, []);

  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [anyActive, refresh]);

  // Draw the request the moment it exists, rather than at the reader's next
  // manual reload (issue #176: "no way of knowing that it has been submitted
  // until they refresh the page").
  //
  // requestTrace() already calls revalidatePath("/trace"), and that is not
  // enough on its own: `rows` is seeded from the `initial` prop by useState,
  // which reads it once, so React keeps the old array across the re-render the
  // Server Action triggers and the new row never arrives. The 3s poll could not
  // rescue it either, because it only runs while a row is already active — and
  // before the first request there are none, which is exactly the case the
  // owner hit. So fetch once on success; the row that comes back is active, so
  // the existing poll takes over from there and no second timer is needed.
  //
  // Only on success. A refusal keeps what was typed, because the reader is
  // about to correct one field of it, and the message beside the button says
  // which (that is where the #175 membership refusal lands).
  useEffect(() => {
    if (!formState?.ok) return;
    formRef.current?.reset();
    refresh();
  }, [formState, refresh]);

  return (
    <section>
      <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.15rem",
        color: "var(--ink)", margin: "0 0 .35rem" }}>
        {signedIn ? "Which concept?" : "Requests"}
      </h2>
      {/* "A curator reviews each request" used the team's word for the person
          doing it (issue #128). /about explains what a curator is, and this page
          is often the one a reader reaches first. */}
      <p style={{ fontSize: ".85rem", color: "var(--ink-soft)", margin: "0 0 .9rem", lineHeight: 1.55 }}>
        {owner
          ? "Yours start straight away. Anyone else's waits here for your approval."
          : "Someone reviews each request before it runs."}
      </p>

      {/* Above the branch, not inside the form, so the signed-out reader deciding
          whether this tool is for them gets it too — they are the person forming
          the expectation, and the form they would meet it in is behind a sign-in.
          The picker offers all 26 fields OpenAlex finds arXiv work in, which is
          the owner's decision 36 ("we should not discriminate"). What varies is
          the share, by three orders of magnitude: measured 2026-08-08, arXiv is
          21.6% of mathematics and 20.6% of physics against 0.13% of medicine and
          0.04% of arts and humanities. Stage A has no corpus floor, so a thin
          field yields a small map wearing the same stamps as a good one rather
          than a refusal, which is why this sits at the control and not only on
          /about (issue #175). /about's "Coverage is arXiv-only" wording,
          deliberately: one fact, one phrasing. */}
      <p style={{ fontSize: ".85rem", color: "var(--ink-soft)", margin: "0 0 .9rem", lineHeight: 1.55 }}>
        Lineage reads arXiv only, so fields that publish mainly through journals, conferences or
        books are thin here or missing. If yours does not preprint, this is not the right tool yet.
      </p>

      {signedIn ? (
        <form
          ref={formRef}
          action={formAction}
          style={{
            background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8,
            padding: ".9rem 1rem", marginBottom: "1rem",
            display: "flex", flexWrap: "wrap", gap: ".6rem", alignItems: "center",
          }}
        >
          <input
            name="concept"
            placeholder="A term, e.g. “batch normalization”"
            required
            maxLength={60}
            style={{ ...input, flex: "1 1 150px" }}
          />
          <select name="field_id" defaultValue={defaultField} aria-label="Subject field"
            title="Which discipline to search" style={{ ...input, flex: "1 1 150px" }}>
            {fields.map((f) => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
          <input
            name="gloss"
            placeholder="Which sense? e.g. “kernel methods in SVMs” (optional)"
            maxLength={200}
            title="Disambiguates a word with more than one meaning"
            style={{ ...input, flex: "1 1 100%" }}
          />
          <input
            name="anchors"
            placeholder="Papers it should not miss, by arXiv id, e.g. 2404.03002 (optional, up to 3)"
            maxLength={120}
            title="Up to three arXiv ids, separated by spaces or commas"
            style={{ ...input, flex: "1 1 100%" }}
          />
          {/* Attached to its control rather than to the page, unlike the
              arXiv-only caveat above: that one is about whether this tool suits
              you at all and a signed-out reader needs it, this one is about how
              to use a field only a signed-in reader is shown.
              What it must say, and what it must not, is the design's first
              integrity condition (issue #198): naming a paper skips SELECTION
              and nothing else. It buys a reading, not a place on the map, and
              the honest failure — a named paper that defines nothing and links
              to nothing — is a figure on the report rather than something the
              tool hides. No em dash; house style. */}
          <p style={{ flexBasis: "100%", margin: "-.15rem 0 .1rem", fontSize: ".78rem",
            lineHeight: 1.55, color: "var(--ink-soft)" }}>
            If you know a paper this map should not miss, name up to three by their arXiv
            id. Named papers are read and checked like any other; naming one does not make
            it matter. It earns a place on the map only through the papers it actually
            cites, and if it turns out not to define the term it is counted among the
            papers that do not. Every map says how many of its papers a person named.
          </p>
          <input
            name="note"
            placeholder="Why you want it (optional)"
            maxLength={500}
            style={{ ...input, flex: "2 1 240px" }}
          />
          {owner && (
            <input
              name="corpus_limit"
              type="number"
              min={5}
              max={300}
              defaultValue={150}
              title="Corpus size (papers)"
              aria-label="Corpus size (papers)"
              style={{ ...input, width: 90 }}
            />
          )}
          <button type="submit" disabled={pending} style={btn}>
            {pending ? "Submitting…" : owner ? "Start mapping" : "Request it"}
          </button>
          {/* Announced, not just coloured: this is the only acknowledgement a
              submit gets, and green-versus-red carries none of it to a screen
              reader or to anyone who cannot tell the two apart (#176). */}
          {formState && (
            <span
              role="status"
              aria-live="polite"
              style={{
                flexBasis: "100%", fontSize: ".78rem",
                color: formState.ok ? "var(--verified)" : "var(--inferred)",
              }}
            >
              {formState.message}
            </span>
          )}
        </form>
      ) : (
        <form action={signInHere}
          style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8,
            padding: "1rem 1.1rem", marginBottom: "1rem" }}>
          {/* "Attribute", "queuing" and "corpus" in one clause, and the joke in
              "the whole corpus" only works for someone who knows what one is
              (issue #128). Same two reasons for asking, said plainly. */}
          <p style={{ margin: "0 0 .8rem", fontSize: ".88rem", lineHeight: 1.6, color: "var(--ink-soft)" }}>
            Sign in to name a term. Your GitHub username is used only to record who asked, and to
            stop one person requesting every map at once.
          </p>
          <button type="submit"
            style={{ font: "inherit", fontSize: ".85rem", cursor: "pointer", background: "#1d3b31",
              color: "#bfe6d4", border: "1px solid #2f5f4d", borderRadius: 8, padding: ".55rem 1rem" }}>
            Sign in with GitHub to continue →
          </button>
        </form>
      )}

      {rows.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
          {rows.map((r) => (
            <TraceRow key={r.id} r={r} owner={owner} skewMs={skewMs} />
          ))}
        </div>
      )}
    </section>
  );
}

function TraceRow({ r, owner, skewMs }: { r: TraceRequest; owner: boolean; skewMs: number }) {
  const p = r.progress ?? {};
  // The worker heartbeats every ~30s while alive (worker/run.py Heartbeat) and
  // the stale-row sweeper gives up at 600s. Warn only well past a few missed
  // heartbeats, so a silent-but-healthy stage never trips this — but still
  // ahead of the sweeper, so a genuinely dead worker surfaces here first.
  const heartbeatStale = r.status === "running" && elapsedS(r.updated_at, skewMs) > 240;

  return (
    <div style={{
      background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8,
      padding: ".75rem 1rem",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: ".7rem", flexWrap: "wrap" }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: ".68rem", fontWeight: 600,
          color: STATUS_COLOR[r.status], border: `1px solid ${STATUS_COLOR[r.status]}`,
          borderRadius: 4, padding: ".1rem .45rem", textTransform: "uppercase",
        }}>
          {r.status}
        </span>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.05rem" }}>
          {r.concept}
        </span>
        <span style={{ fontSize: ".74rem", color: "var(--ink-soft)" }}>
          by {r.requested_by} · {ago(r.created_at, skewMs)}
          {typeof p.spend_usd === "number" && p.spend_usd > 0 && (
            <> · ${p.spend_usd.toFixed(2)} spent</>
          )}
        </span>

        <span style={{ flex: 1 }} />

        {r.status === "complete" && r.genealogy_id && (
          <Link href={`/g/${r.genealogy_id}`} style={{ fontSize: ".8rem", color: "var(--edge-extends)" }}>
            Open the map ›
          </Link>
        )}
        {owner && r.status === "requested" && (
          <span style={{ display: "flex", gap: ".4rem" }}>
            <form action={approveTrace}>
              <input type="hidden" name="id" value={r.id} />
              <button type="submit" style={{ ...btn, borderColor: "var(--verified)", color: "var(--verified)" }}>
                Approve
              </button>
            </form>
            <form action={rejectTrace}>
              <input type="hidden" name="id" value={r.id} />
              <button type="submit" style={{ ...btn, borderColor: "var(--inferred)", color: "var(--inferred)" }}>
                Reject
              </button>
            </form>
          </span>
        )}
        {owner && r.status === "approved" && (
          <form action={rejectTrace}>
            <input type="hidden" name="id" value={r.id} />
            <button type="submit" style={btn}>Withdraw</button>
          </form>
        )}
      </div>

      {r.gloss && (
        <div style={{ fontSize: ".76rem", color: "var(--ink-soft)", marginTop: ".3rem" }}>
          sense: <span style={{ color: "var(--ink)" }}>{r.gloss}</span>
        </div>
      )}

      {r.note && (
        <div style={{ fontSize: ".78rem", color: "var(--ink-soft)", marginTop: ".35rem", fontStyle: "italic" }}>
          “{r.note}”
        </div>
      )}

      {r.status === "running" && (
        <div style={{ marginTop: ".55rem" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink)" }}>
            {/* The worker always writes `stages`; the fallback only covers a row
                whose progress predates it, and it still has to track what
                the worker's plan returns, or a live run reads as "stage 13 of 7".
                30 since #198: 28 in the nominal two-pass plan, plus the step that
                records how the second pass ended and the step that records the
                papers a person named. The worker corrects the total downward when
                it skips a pass. */}
            stage {p.stage_no ?? "?"}/{p.stages ?? 30} · {p.stage ?? "…"}
            {p.current != null && p.total != null && <> · {p.current} of {p.total}</>}
          </div>
          {p.message && (
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-soft)",
              marginTop: ".2rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>
              {p.message}
            </div>
          )}
          {p.current != null && p.total != null && p.total > 0 && (
            <div style={{ background: "var(--line)", borderRadius: 3, height: 4, marginTop: ".4rem" }}>
              <div style={{
                width: `${Math.min(100, (p.current / p.total) * 100)}%`,
                background: "var(--edge-narrows)", height: 4, borderRadius: 3,
                transition: "width .6s ease",
              }} />
            </div>
          )}
          {heartbeatStale && (
            <div style={{ fontSize: ".72rem", color: "var(--inferred)", marginTop: ".35rem" }}>
              Quiet for a few minutes. Long stages often look like this; if it stays here it may need a restart.
            </div>
          )}
        </div>
      )}

      {r.status === "failed" && (
        owner && r.error ? (
          // Raw run output is a debugging tool for the owner, not a public artifact.
          <details style={{ marginTop: ".45rem" }}>
            <summary style={{ fontSize: ".75rem", color: "var(--inferred)", cursor: "pointer" }}>
              Failure details
            </summary>
            <pre style={{
              fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)",
              whiteSpace: "pre-wrap", margin: ".4rem 0 0", maxHeight: 220, overflow: "auto",
            }}>
              {r.error}
            </pre>
          </details>
        ) : (
          <div style={{ marginTop: ".45rem", fontSize: ".75rem", color: "var(--ink-soft)" }}>
            This run stopped early. Work already done is kept, so re-running costs only what is left.
          </div>
        )
      )}
    </div>
  );
}

const input: React.CSSProperties = {
  font: "inherit", fontSize: ".82rem", padding: ".45rem .6rem",
  border: "1px solid var(--line)", borderRadius: 4,
  background: "var(--paper)", color: "var(--ink)",
};

const btn: React.CSSProperties = {
  font: "inherit", fontSize: ".76rem", padding: ".35rem .7rem", cursor: "pointer",
  border: "1px solid var(--ink-soft)", borderRadius: 4,
  background: "var(--card)", color: "var(--ink)",
};

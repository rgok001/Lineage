"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";
import { approveTrace, rejectTrace, requestTrace } from "../lib/trace-actions";
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
  signedIn,
  owner,
}: {
  initial: TraceRequest[];
  initialNow: string;
  fields: ArxivField[];
  signedIn: boolean;
  owner: boolean;
}) {
  const [rows, setRows] = useState(initial);
  const [skewMs, setSkewMs] = useState(() => Date.now() - new Date(initialNow).getTime());
  const [formState, formAction, pending] = useActionState(requestTrace, null);

  const anyActive = rows.some((r) => ACTIVE.has(r.status));

  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(async () => {
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
    }, 3000);
    return () => clearInterval(t);
  }, [anyActive]);

  return (
    <section style={{ marginTop: "2.2rem" }}>
      <h2 style={{ fontSize: "1rem", color: "var(--ink)", margin: "0 0 .35rem" }}>Live traces</h2>
      <p style={{ fontSize: ".8rem", color: "var(--ink-soft)", margin: "0 0 .9rem", lineHeight: 1.5 }}>
        A trace reads up to 150 papers and takes about 15 minutes.{" "}
        {owner
          ? "Your traces start automatically; visitor requests wait below for your approval."
          : "Requests are reviewed by the curator before a trace runs."}
      </p>

      {signedIn ? (
        <form
          action={formAction}
          style={{
            background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8,
            padding: ".9rem 1rem", marginBottom: "1rem",
            display: "flex", flexWrap: "wrap", gap: ".6rem", alignItems: "center",
          }}
        >
          <input
            name="concept"
            placeholder="Concept, e.g. “batch normalization”"
            required
            maxLength={60}
            style={{ ...input, flex: "1 1 150px" }}
          />
          <select name="field_id" defaultValue="fields/17" aria-label="Subject field"
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
            name="note"
            placeholder="Why this concept? (optional)"
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
            {pending ? "Submitting…" : owner ? "Queue trace" : "Request trace"}
          </button>
          {formState && (
            <span
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
        <p style={{ fontSize: ".8rem", color: "var(--ink-soft)", fontStyle: "italic" }}>
          Sign in with GitHub to request a trace of a concept you care about.
        </p>
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
            View genealogy ›
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
            stage {p.stage_no ?? "?"}/{p.stages ?? 7} · {p.stage ?? "…"}
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
              No progress for a few minutes. The trace is usually still working
              through a quiet stage; if it stays here it may need a restart.
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
            This trace did not complete. It can be re-run at no extra cost for the work already done.
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

import Link from "next/link";
import TracePanel from "../trace-panel";
import { getViewer, isOwner } from "../../lib/authz";
import { getArxivFields } from "../../lib/openalex";
import { dbNow, listTraceRequests } from "../../lib/traces";

export const dynamic = "force-dynamic";

export const metadata = { title: "Map a new concept — Lineage" };

export default async function TracePage() {
  const [traces, now, fields, viewer] = await Promise.all([
    listTraceRequests(),
    dbNow(),
    getArxivFields(),
    getViewer(),
  ]);

  return (
    <main style={{ maxWidth: 880, margin: "0 auto", padding: "1rem 1.5rem 5rem" }}>
      <header style={{ padding: "0 0 1.3rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2rem", margin: 0 }}>
          Map a new concept
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".7rem 0 0", lineHeight: 1.6, maxWidth: "40rem" }}>
          Name a term and Lineage reads the literature around it: what each paper means by the term,
          which papers moved it forward, and how those papers connect. You get a map you can read and
          a quote behind every claim.
        </p>
      </header>

      <section style={{ display: "flex", gap: ".8rem", flexWrap: "wrap", marginBottom: "1.8rem" }}>
        {[
          ["1", "You name a term", "Say which field it belongs to, and what you mean by it if the word has more than one sense."],
          ["2", "It reads the papers", "Up to 150 of them, about fifteen minutes. You can watch the progress here."],
          ["3", "You get the map", "The threads the idea split into, the papers that shaped it, and the evidence for each."],
        ].map(([n, title, body]) => (
          <div key={n} style={{ flex: "1 1 210px", background: "var(--card)", border: "1px solid var(--line)",
            borderRadius: 10, padding: ".9rem 1rem" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", letterSpacing: ".14em",
              color: "var(--ink-faint)" }}>STEP {n}</div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1rem", margin: ".3rem 0 .25rem" }}>
              {title}
            </div>
            <p style={{ margin: 0, fontSize: ".84rem", lineHeight: 1.55, color: "var(--ink-soft)" }}>{body}</p>
          </div>
        ))}
      </section>

      <TracePanel initial={traces} initialNow={now} fields={fields}
        signedIn={!!viewer} owner={isOwner(viewer)} />

      <p style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-faint)",
        lineHeight: 1.8, marginTop: "2rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}>
        Reading a corpus costs real money in model usage, so requests are reviewed before they run.{" "}
        <Link href="/about" style={{ color: "var(--edge-extends)" }}>How it works ›</Link>
      </p>
    </main>
  );
}

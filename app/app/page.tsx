import Link from "next/link";
import { getViewer, isOwner } from "../lib/authz";
import { listGenealogies } from "../lib/genealogy";
import { getArxivFields } from "../lib/openalex";
import { dbNow, listTraceRequests } from "../lib/traces";

export const dynamic = "force-dynamic"; // always read live DB state

export default async function Home() {
  const [rows, traces, now, fields, viewer] = await Promise.all([
    listGenealogies(),
    listTraceRequests(),
    dbNow(),
    getArxivFields(),
    getViewer(),
  ]);

  const active = traces.filter((t) => ["requested", "approved", "running"].includes(t.status)).length;

  return (
    <main style={{ maxWidth: 880, margin: "0 auto", padding: "1rem 1.5rem 4rem" }}>
      <header style={{ paddingBottom: "1.1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2.1rem", margin: 0 }}>
          Read a concept’s development
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".45rem 0 0", lineHeight: 1.5 }}>
          Read how an academic concept evolved: the threads it split into, how they fed each other,
          and the papers that moved it, in order. Every claim is tied to a verbatim quote, verified
          against the source text.{" "}
          <Link href="/about" style={{ color: "var(--edge-extends)", whiteSpace: "nowrap" }}>
            How it works ›
          </Link>
        </p>
      </header>

      <h2 style={{ fontSize: "1rem", color: "var(--ink)", margin: "0 0 .9rem" }}>Concepts</h2>

      {rows.length === 0 ? (
        <p style={{ color: "var(--ink-soft)" }}>
          Nothing mapped yet. Map the first concept below.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
          {rows.map((g) => (
            <Link key={g.id} href={`/g/${g.id}`} style={{ textDecoration: "none" }}>
              <div style={{
                background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8,
                padding: "1rem 1.1rem", display: "flex", alignItems: "center", gap: "1rem",
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.2rem", color: "var(--ink)" }}>
                    {g.concept}
                  </div>
                  <div style={{ fontSize: ".8rem", color: "var(--ink-soft)", marginTop: ".25rem" }}>
                    {g.paper_count} papers ·{" "}
                    {g.stream_count != null
                      ? <>{g.stream_count} threads</>
                      : <>{g.edge_count} relationships</>} ·{" "}
                    <span style={{ color: "var(--verified)" }}>{g.verified_count} verified quotes</span>
                    {g.edit_count > 0 && <> · {g.edit_count} curatorial change(s)</>}
                  </div>
                </div>
                <div style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>
                  <div>{g.status}</div>
                </div>
                <span style={{ color: "var(--ink-soft)", fontSize: "1.3rem" }}>›</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      <Link href="/trace" style={{ display: "flex", alignItems: "center", gap: ".8rem", flexWrap: "wrap",
        textDecoration: "none", marginTop: "1.6rem", background: "var(--card)",
        border: "1px solid var(--line)", borderRadius: 10, padding: ".9rem 1.1rem" }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.05rem", color: "var(--ink)" }}>
          Map a new concept →
        </span>
        <span style={{ fontSize: ".85rem", color: "var(--ink-soft)", marginLeft: "auto" }}>
          {active > 0
            ? `${active} being mapped right now`
            : "name a term and Lineage reads the literature around it"}
        </span>
      </Link>

      {/* Counted, never assumed. This read "then curated by hand" on every map,
          including ones whose audit trail is empty — the claim this project's
          own as-built had to retract about the showcase map. */}
      <p style={{ marginTop: "2rem", fontSize: ".78rem", color: "var(--ink-soft)", fontStyle: "italic" }}>
        Each account is drafted automatically from the papers themselves.{" "}
        {rows.some((g) => g.edit_count > 0)
          ? "Where a map has been curated since, the count is shown above and every change is recorded in an audit trail with who made it."
          : "None has been curated since; any curatorial change would be recorded in an audit trail with who made it."}
      </p>
    </main>
  );
}

import Link from "next/link";
import SignInButton from "./signin-button";
import TracePanel from "./trace-panel";
import { getViewer, isOwner } from "../lib/authz";
import { listGenealogies } from "../lib/genealogy";
import { dbNow, listTraceRequests } from "../lib/traces";

export const dynamic = "force-dynamic"; // always read live DB state

export default async function Home() {
  const [rows, traces, now, viewer] = await Promise.all([
    listGenealogies(),
    listTraceRequests(),
    dbNow(),
    getViewer(),
  ]);

  return (
    <main style={{ maxWidth: 880, margin: "0 auto", padding: "2.5rem 1.5rem 4rem" }}>
      <header style={{ borderBottom: "2px solid var(--line)", paddingBottom: "1.1rem", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2.1rem", margin: 0 }}>
            Lineage
          </h1>
          <SignInButton />
        </div>
        <p style={{ color: "var(--ink-soft)", margin: ".45rem 0 0", lineHeight: 1.5 }}>
          Trace how an academic concept evolved across papers — every relationship backed by a
          verbatim quote from both papers, verified against the source text.
        </p>
      </header>

      <h2 style={{ fontSize: "1rem", color: "var(--ink)", margin: "0 0 .9rem" }}>Your genealogies</h2>

      {rows.length === 0 ? (
        <p style={{ color: "var(--ink-soft)" }}>
          No genealogies yet. Build one with the pipeline:{" "}
          <code>python pipeline/corpus_select.py &quot;attention&quot;</code> …
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
                    {g.node_count} concept-states · {g.edge_count} relationships ·{" "}
                    <span style={{ color: "var(--verified)" }}>{g.verified_count} verified</span>
                    {g.edge_count - g.verified_count > 0 && (
                      <span style={{ color: "var(--inferred)" }}>
                        {" "}· {g.edge_count - g.verified_count} inferred
                      </span>
                    )}
                    {g.edit_count > 0 && <> · {g.edit_count} manual edit(s)</>}
                  </div>
                </div>
                <div style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>
                  <div>prompt {g.prompt_version}</div>
                  <div>{g.status}</div>
                </div>
                <span style={{ color: "var(--ink-soft)", fontSize: "1.3rem" }}>›</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      <TracePanel initial={traces} initialNow={now} signedIn={!!viewer} owner={isOwner(viewer)} />

      <p style={{ marginTop: "2rem", fontSize: ".78rem", color: "var(--ink-soft)", fontStyle: "italic" }}>
        Reading live from the database. Edits you make in a genealogy are saved there and recorded
        in its audit trail.
      </p>
    </main>
  );
}

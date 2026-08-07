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
                    {/* "verified relationships", not "verified quotes" (issue #73).
                        verified_count counts EDGES whose two quotes both verified,
                        and edges fan out over quotes because many of them cite the
                        same passage: measured on the shipped exports, "attention"
                        is 287 verified edges over 79 distinct quote strings and
                        "embedding" 286 over 107, so the old noun overstated the
                        evidence three- to fourfold on the one number the product's
                        central promise rests on. The evidence page has always said
                        "N typed relationships (M verified)" about this quantity;
                        this is that vocabulary, not a new one. A quote count, if it
                        is ever wanted here, has to be counted with DISTINCT and not
                        renamed into existence. */}
                    {/* Absence, not zero (issue #92). The counts are null only
                        when the report the card reads them from is not in the
                        database yet — an app deployed ahead of its migration.
                        "0 verified relationships" on a map holding 287 of them
                        would be a worse answer than the 500 this replaced, and
                        it would be a green one. No verified colour on it
                        either: green here is the stamp. */}
                    {g.verified_count === null ? (
                      <span style={{ color: "var(--ink-soft)", fontStyle: "italic" }}>
                        verified relationships not counted
                      </span>
                    ) : (
                      <>
                        <span style={{ color: "var(--verified)" }}>{g.verified_count} verified relationships</span>
                        {Number(g.stale_count ?? 0) > 0 && (
                          <span style={{ color: "var(--ink-soft)" }}> · {g.stale_count} not re-checked</span>
                        )}
                      </>
                    )}
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

      {/* Counted, never assumed, and the count is of curatorial ops only. This
          read "then curated by hand" on every map; then it counted a restore
          after an incident as somebody's editorial work. And "with who made it"
          asserts an attribution the entries themselves may not carry, which is
          the defect decision 18 exists to remove, restated in its own copy. */}
      <p style={{ marginTop: "2rem", fontSize: ".78rem", color: "var(--ink-soft)", fontStyle: "italic" }}>
        Each account is drafted automatically from the papers themselves.{" "}
        {rows.some((g) => g.edit_count > 0)
          ? "Where one has been curated since, the count is shown above and each change is listed in that map’s audit trail, with its actor where one was recorded."
          : "None has been curated since. Any curatorial change is listed in the map’s audit trail, with its actor where one was recorded."}
      </p>
    </main>
  );
}

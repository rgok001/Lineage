import Link from "next/link";
import { notFound } from "next/navigation";
import { sql } from "../../../../../lib/db";
import { getRiver, readableQuote } from "../../../../../lib/genealogy";

export const dynamic = "force-dynamic";

export default async function DivePage({ params }: { params: Promise<{ id: string; sid: string }> }) {
  const { id, sid } = await params;
  const data = await getRiver(Number(id));
  if (!data) notFound();
  const s = data.river.streams.find((x) => x.id === sid);
  if (!s) notFound();
  const c = s.color;

  /* The evidence is the paper's own definition span, the one Stage E matched
     against the extracted source. The river's generated "quote" field is NOT
     shown: it is a summary of the paper, not a passage from it, and rendering
     it under a verified stamp claimed a grounding it never had. Same source as
     the dossier route, so a reader meets one quote per paper, not two. */
  const g = (await sql`SELECT concept, prompt_version FROM genealogies WHERE id = ${Number(id)}`) as
    { concept: string; prompt_version: string }[];
  const arxivs = s.papers.map((p) => p.arxiv);
  const quoteRows = (arxivs.length && g.length
    ? await sql`
        SELECT p.arxiv_id AS arxiv, d.verbatim_quote AS quote, d.quote_verified AS verified
        FROM definitions d JOIN papers p ON p.id = d.paper_id
        WHERE p.arxiv_id = ANY(${arxivs}) AND d.concept = ${g[0].concept}
          AND d.prompt_version = ${g[0].prompt_version} AND d.defines_concept = true
      `
    : []) as { arxiv: string; quote: string | null; verified: boolean | null }[];
  const evidence = new Map(quoteRows.map((r) => [r.arxiv, r]));

  return (
    <main style={{ padding: "2rem 1.5rem 5rem" }}>
      <div style={{ maxWidth: "42rem", margin: "0 auto" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>
          <Link href={`/g/${id}`} style={{ color: c, textDecoration: "none" }}>‹ the map</Link>
          {" / "}<span style={{ color: "var(--ink)" }}>{s.name}</span>
        </div>

        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2rem", lineHeight: 1.14,
          margin: ".7rem 0 0" }}>{s.name}</h1>
        {s.arc && (
          <p style={{ fontFamily: "var(--font-display)", fontSize: "1.1rem", lineHeight: 1.6,
            color: "var(--ink)", margin: "1rem 0 0" }}>{s.arc}</p>
        )}
        <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)",
          margin: "1.3rem 0 0", paddingTop: ".9rem", borderTop: "1px solid var(--line)" }}>
          {s.papers.length} papers, in the order the idea moved · each quote is the paper’s own definition, marked verified or inferred
        </p>

        <div style={{ position: "relative", marginTop: "2.4rem" }}>
          <div style={{ position: "absolute", left: 5, top: 6, bottom: 40, width: 2, background: "var(--line)" }} />
          {s.papers.map((p) => {
            const move = typeof p.move === "string" ? p.move : "";
            const prose = typeof p.prose === "string" ? p.prose : "";
            const ev = evidence.get(p.arxiv);
            const quote = readableQuote((typeof ev?.quote === "string" ? ev.quote : "").replace(/\s+/g, " ").trim());
            const verified = ev?.verified === true;
            return (
            <section key={p.arxiv} style={{ position: "relative", padding: "0 0 2.2rem 2rem" }}>
              <span style={{ position: "absolute", left: 0, top: 5, width: 12, height: 12, borderRadius: "50%",
                background: "var(--paper)", border: `2px solid ${c}`, boxSizing: "border-box" }} />
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>
                <span style={{ color: c }}>{p.year}</span>{" · "}
                <a href={`https://arxiv.org/abs/${p.arxiv}`} target="_blank" rel="noopener noreferrer"
                  style={{ color: "var(--ink)", textDecoration: "none", borderBottom: "1px solid var(--line)" }}>
                  {p.title}
                </a>
              </div>
              {move && (
                <h3 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.14rem",
                  lineHeight: 1.3, margin: ".35rem 0 .5rem" }}>{move}</h3>
              )}
              {prose && (
                <p style={{ margin: 0, fontSize: "1rem", lineHeight: 1.65, color: "var(--ink)" }}>
                  {prose}
                  {/* The verified stamp below belongs to the quote, not to this
                      paragraph. Unlabelled, the layout lends it the quote's
                      authority; the dossier and the export already say this. */}
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem",
                    color: "var(--ink-faint)", marginLeft: ".45rem", whiteSpace: "nowrap" }}>
                    the tool’s reading
                  </span>
                </p>
              )}
              {quote && (
                <div style={{ margin: ".7rem 0 0", padding: ".55rem .8rem", background: "var(--card)",
                  borderLeft: `2px solid var(--${verified ? "verified" : "inferred"})`, borderRadius: "0 6px 6px 0" }}>
                  <blockquote style={{ margin: 0, fontFamily: "var(--font-display)", fontStyle: "italic",
                    fontSize: ".92rem", lineHeight: 1.5, color: "var(--ink)" }}>
                    “{quote}”
                  </blockquote>
                  <span style={{ display: "block", marginTop: ".35rem", fontFamily: "var(--font-mono)",
                    fontSize: ".64rem", color: `var(--${verified ? "verified" : "inferred"})`, letterSpacing: ".04em" }}>
                    {verified ? "✓ verified" : "○ inferred"} · {p.title.length > 40 ? p.title.slice(0, 40) + "…" : p.title}, {p.year}
                  </span>
                </div>
              )}
            </section>
            );
          })}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: ".6rem", flexWrap: "wrap",
          marginTop: "1.4rem", padding: ".65rem .9rem", borderRadius: 8, border: "1px dashed var(--line)" }}>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: ".95rem", color: "var(--ink)" }}>
            Take this thread to your draft
          </span>
          <span style={{ fontSize: ".8rem", color: "var(--ink-soft)" }}>
            these papers only, with their quotes and citations
          </span>
          <span style={{ marginLeft: "auto", display: "flex", gap: ".7rem",
            fontFamily: "var(--font-mono)", fontSize: ".72rem" }}>
            <a href={`/g/${id}/export?thread=${encodeURIComponent(s.id)}`} style={{ color: c }}>Markdown</a>
            <a href={`/g/${id}/export?thread=${encodeURIComponent(s.id)}&format=bib`} style={{ color: c }}>BibTeX</a>
          </span>
        </div>

        <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)",
          lineHeight: 1.9, marginTop: "1.4rem", paddingTop: "1.1rem", borderTop: "1px solid var(--line)" }}>
          One thread of the map, each claim pinned to the paper’s own words. A chatbot gives you the
          canon; this carries the papers in between, in order, with the evidence attached.
        </p>
      </div>
    </main>
  );
}

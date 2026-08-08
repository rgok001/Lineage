import Link from "next/link";
import { notFound } from "next/navigation";
import { paperAnchor } from "../../../../../lib/anchors";
import { sql } from "../../../../../lib/db";
import { getMapRow, readableQuote } from "../../../../../lib/genealogy";
import { STAMP_COLOR, STAMP_LABEL, stampOf } from "../../../../../lib/stamp";

export const dynamic = "force-dynamic";

export default async function DivePage({ params }: { params: Promise<{ id: string; sid: string }> }) {
  const { id, sid } = await params;
  // One row read, where this was `getRiver` and then a second SELECT on the same
  // `genealogies` row for the prompt version (issue #140).
  const data = await getMapRow(Number(id));
  if (!data?.river) notFound();
  const s = data.river.streams.find((x) => x.id === sid);
  if (!s) notFound();
  const c = s.color;

  /* The evidence is the paper's own definition span, the one Stage E matched
     against the extracted source. The river's generated "quote" field is NOT
     shown: it is a summary of the paper, not a passage from it, and rendering
     it under a verified stamp claimed a grounding it never had. Same source as
     the dossier route, so a reader meets one quote per paper, not two. */
  const arxivs = s.papers.map((p) => p.arxiv);
  // `in_evidence` rides on the statement that was already running (issue #146).
  // The evidence page groups by relationship, so a paper taking part in none has
  // no place there to link to, and a link that lands at the top of 62 screens is
  // the failure that ticket exists to remove rather than a small imperfection.
  // Measured on /g/13/river/s0 before this column: two of six links missed.
  const quoteRows = (arxivs.length
    ? await sql`
        SELECT p.arxiv_id AS arxiv, d.verbatim_quote AS quote, d.quote_verified AS verified,
               d.quote_text_digest, p.extracted_text_digest,
               EXISTS (SELECT 1 FROM edges e
                        WHERE e.genealogy_id = ${Number(id)}
                          AND (e.source_paper_id = p.id OR e.target_paper_id = p.id)) AS in_evidence
        FROM definitions d JOIN papers p ON p.id = d.paper_id
        WHERE p.arxiv_id = ANY(${arxivs}) AND d.concept = ${data.concept}
          AND d.prompt_version = ${data.prompt_version} AND d.defines_concept = true
      `
    : []) as { arxiv: string; quote: string | null; verified: boolean | null;
               quote_text_digest: string | null; extracted_text_digest: string | null;
               in_evidence: boolean }[];
  const evidence = new Map(quoteRows.map((r) => [r.arxiv, {
    ...r,
    // The same resolver the dossier and the evidence page use (migration 015).
    // This page shows the same quote as the dossier, so it must say the same
    // thing about it.
    stamp: stampOf(r.verified, r.quote_text_digest, r.extracted_text_digest),
  }]));

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
          {/* The three state words are defined on the evidence page, and a
              reader can reach a thread straight from the front door without ever
              going there (issue #127). They then meet "✓ the paper's own words"
              and "the tool's reading" with no key. Spelled out here rather than
              linked, because the key is three clauses long. */}
          {s.papers.length} papers, in the order the idea moved · each quote is the paper’s own
          definition, and each is marked to say whether we found it word for word in the paper
          (verified), could not find it (inferred), or have not re-checked it against the
          paper’s text as it now stands
        </p>

        <div style={{ position: "relative", marginTop: "2.4rem" }}>
          <div style={{ position: "absolute", left: 5, top: 6, bottom: 40, width: 2, background: "var(--line)" }} />
          {s.papers.map((p) => {
            const move = typeof p.move === "string" ? p.move : "";
            const prose = typeof p.prose === "string" ? p.prose : "";
            const claims = Array.isArray(p.claims) ? p.claims.filter((c) => c?.text) : [];
            const ev = evidence.get(p.arxiv);
            const quote = readableQuote((typeof ev?.quote === "string" ? ev.quote : "").replace(/\s+/g, " ").trim());
            const stamp = ev?.stamp ?? "stale";
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
                {/* Straight to this paper's own place in the evidence, rather
                    than to the top of 62 screens (issue #146). The anchor is
                    built from the arXiv id, which is all this page has and all
                    it needs: see lib/anchors.ts for why it is not an edge id.
                    Shown only where the paper has a place to land, which is what
                    `in_evidence` is for. */}
                {ev?.in_evidence && (
                  <>
                    {" · "}
                    <Link href={`/g/${id}/evidence#${paperAnchor(p.arxiv)}`}
                      style={{ color: "var(--ink-soft)", textDecoration: "none",
                        borderBottom: "1px solid var(--line)" }}>
                      its evidence
                    </Link>
                  </>
                )}
              </div>
              {move && (
                <h3 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.14rem",
                  lineHeight: 1.3, margin: ".35rem 0 .5rem" }}>{move}</h3>
              )}
              {/* Claim-level evidence where Stage H has run: each sentence carries
                  the passage that shows it, or says plainly that it carries none.
                  Falls back to the paragraph, which is one label for several
                  assertions and only as good as the reader's care. */}
              {claims.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
                  {claims.map((cl, i) => (
                    <div key={i} style={{ borderLeft: `2px solid var(--${cl.verified ? "verified" : "line"})`,
                      paddingLeft: ".7rem" }}>
                      <p style={{ margin: 0, fontSize: "1rem", lineHeight: 1.55, color: "var(--ink)" }}>
                        {cl.text}
                      </p>
                      {cl.verified && cl.quote ? (
                        <blockquote style={{ margin: ".35rem 0 0", fontFamily: "var(--font-display)",
                          fontStyle: "italic", fontSize: ".88rem", lineHeight: 1.5, color: "var(--ink-soft)" }}>
                          “{readableQuote(cl.quote)}”
                          <span style={{ display: "block", marginTop: ".2rem", fontStyle: "normal",
                            fontFamily: "var(--font-mono)", fontSize: ".6rem", color: "var(--verified)",
                            letterSpacing: ".04em" }}>
                            ✓ the paper’s own words
                          </span>
                        </blockquote>
                      ) : (
                        <span style={{ display: "block", marginTop: ".2rem", fontFamily: "var(--font-mono)",
                          fontSize: ".6rem", color: "var(--ink-faint)" }}>
                          the tool’s reading · no passage in the paper was matched to this
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : prose ? (
                <p style={{ margin: 0, fontSize: "1rem", lineHeight: 1.65, color: "var(--ink)" }}>
                  {prose}
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem",
                    color: "var(--ink-faint)", marginLeft: ".45rem", whiteSpace: "nowrap" }}>
                    the tool’s reading
                  </span>
                </p>
              ) : null}
              {quote && (
                <div style={{ margin: ".7rem 0 0", padding: ".55rem .8rem", background: "var(--card)",
                  borderLeft: `2px solid ${STAMP_COLOR[stamp]}`, borderRadius: "0 6px 6px 0" }}>
                  <blockquote style={{ margin: 0, fontFamily: "var(--font-display)", fontStyle: "italic",
                    fontSize: ".92rem", lineHeight: 1.5, color: "var(--ink)" }}>
                    “{quote}”
                  </blockquote>
                  <span style={{ display: "block", marginTop: ".35rem", fontFamily: "var(--font-mono)",
                    fontSize: ".64rem", color: STAMP_COLOR[stamp], letterSpacing: ".04em" }}>
                    {STAMP_LABEL[stamp]} · {p.title.length > 40 ? p.title.slice(0, 40) + "…" : p.title}, {p.year}
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

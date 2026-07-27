import Link from "next/link";
import { notFound } from "next/navigation";
import { sql } from "../../../../../lib/db";
import { getRiver, EDGE_MEANING } from "../../../../../lib/genealogy";

export const dynamic = "force-dynamic";

/** A paper's dossier: what it contributed, how it moved the term (its typed
 *  links, each with the tool's reading), and the verified quote. The deepest
 *  dive of the map — every claim either verbatim-verified or labelled as the
 *  tool's reading, never blended. */
export default async function PaperPage({ params }: { params: Promise<{ id: string; arxiv: string }> }) {
  const { id, arxiv: raw } = await params;
  const arxiv = decodeURIComponent(raw);

  const g = (await sql`SELECT concept, prompt_version FROM genealogies WHERE id = ${Number(id)}`) as
    { concept: string; prompt_version: string }[];
  if (!g.length) notFound();

  const defs = (await sql`
    SELECT p.id AS pid, p.year, p.title, d.definition, d.verbatim_quote, d.quote_verified,
           d.section, d.novelty_claims AS novelty, d.displacement
    FROM definitions d JOIN papers p ON p.id = d.paper_id
    WHERE p.arxiv_id = ${arxiv} AND d.concept = ${g[0].concept}
      AND d.prompt_version = ${g[0].prompt_version} AND d.defines_concept = true
  `) as { pid: number; year: number; title: string; definition: string | null; verbatim_quote: string | null;
          quote_verified: boolean | null; section: string | null; novelty: string[] | null; displacement: number | null }[];
  if (!defs.length) notFound();
  const d = defs[0];

  const links = (await sql`
    SELECT sp.arxiv_id AS src, sp.title AS src_title, sp.year AS src_year,
           tp.arxiv_id AS dst, tp.title AS dst_title, tp.year AS dst_year,
           e.edge_type, e.rationale, e.verified
    FROM edges e JOIN papers sp ON sp.id = e.source_paper_id
                 JOIN papers tp ON tp.id = e.target_paper_id
    WHERE e.genealogy_id = ${Number(id)} AND (e.source_paper_id = ${d.pid} OR e.target_paper_id = ${d.pid})
    ORDER BY e.confidence DESC
  `) as { src: string; src_title: string; src_year: number; dst: string; dst_title: string; dst_year: number;
          edge_type: string; rationale: string | null; verified: boolean }[];
  const drew = links.filter((l) => l.dst === arxiv);   // what this paper drew from
  const fed = links.filter((l) => l.src === arxiv);    // what drew from this paper

  const river = await getRiver(Number(id));
  const stream = river?.river.streams.find((s) => s.papers.some((p) => p.arxiv === arxiv));
  const claims = (d.novelty ?? []).filter((c) => c && c.trim());
  const turning = (d.displacement ?? 0) >= 0.25;

  const EdgeLine = ({ l, dir }: { l: (typeof links)[number]; dir: "in" | "out" }) => {
    const other = dir === "in" ? { a: l.src, t: l.src_title, y: l.src_year } : { a: l.dst, t: l.dst_title, y: l.dst_year };
    return (
      <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8, padding: ".65rem .85rem" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: ".55rem", flexWrap: "wrap" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem", textTransform: "uppercase",
            letterSpacing: ".06em", color: `var(--edge-${l.edge_type})` }}>
            {dir === "in" ? `${l.edge_type} from` : l.edge_type}
          </span>
          <Link href={`/g/${id}/p/${encodeURIComponent(other.a)}`}
            style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: ".92rem",
              color: "var(--ink)", textDecoration: "none" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)" }}>{other.y}</span>{" "}
            {other.t.length > 64 ? other.t.slice(0, 63) + "…" : other.t}
          </Link>
          {!l.verified && (
            <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--inferred)" }}>
              ○ inferred
            </span>
          )}
        </div>
        {l.rationale && (
          <p style={{ margin: ".35rem 0 0", fontSize: ".82rem", lineHeight: 1.5, color: "var(--ink-soft)" }}>
            {l.rationale}
            <span style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", marginLeft: ".4rem", whiteSpace: "nowrap" }}>
              — the tool’s reading
            </span>
          </p>
        )}
      </div>
    );
  };

  return (
    <main style={{ padding: "2rem 1.5rem 4rem" }}>
      <div style={{ maxWidth: "44rem", margin: "0 auto" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>
          <Link href={`/g/${id}`} style={{ color: stream?.color ?? "var(--ink-soft)", textDecoration: "none" }}>‹ the map</Link>
          {stream && (
            <>
              {" / "}
              <Link href={`/g/${id}/river/${stream.id}`} style={{ color: "var(--ink-soft)", textDecoration: "none" }}>
                {stream.name}
              </Link>
            </>
          )}
        </div>

        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.7rem", lineHeight: 1.2, margin: ".7rem 0 0" }}>
          {d.title}
        </h1>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-soft)", margin: ".35rem 0 1.4rem" }}>
          {d.year}
          {stream && <> · <span style={{ color: stream.color }}>●</span> {stream.name}</>}
          {turning && " · a turning point"}
          {" · "}
          <a href={`https://arxiv.org/abs/${arxiv}`} target="_blank" rel="noopener noreferrer"
            style={{ color: "var(--ink-soft)", borderBottom: "1px solid var(--line)", textDecoration: "none" }}>
            arXiv:{arxiv}
          </a>
        </div>

        {claims.length > 0 && (
          <section style={{ marginBottom: "1.5rem" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", letterSpacing: ".12em",
              textTransform: "uppercase", color: "var(--ink-faint)", marginBottom: ".4rem" }}>
              What it contributed · extracted, not verbatim
            </div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: "1.05rem", lineHeight: 1.55 }}>{claims[0]}</div>
            {claims.length > 1 && (
              <ul style={{ margin: ".5rem 0 0", paddingLeft: "1.1rem", fontSize: ".86rem",
                lineHeight: 1.55, color: "var(--ink-soft)" }}>
                {claims.slice(1, 4).map((c, i) => <li key={i} style={{ marginBottom: ".25rem" }}>{c}</li>)}
              </ul>
            )}
          </section>
        )}

        {d.verbatim_quote && (
          <section style={{ marginBottom: "1.6rem" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", letterSpacing: ".12em",
              textTransform: "uppercase", color: "var(--ink-faint)", marginBottom: ".4rem" }}>
              How it defines “{g[0].concept}”{d.section ? ` · §${d.section}` : ""}
            </div>
            <blockquote style={{ margin: 0, fontFamily: "var(--font-display)", fontStyle: "italic",
              fontSize: ".95rem", lineHeight: 1.55, borderLeft: `2px solid var(--${d.quote_verified === false ? "inferred" : "verified"})`,
              padding: ".55rem .85rem", background: "var(--card)", borderRadius: "0 6px 6px 0" }}>
              “{d.verbatim_quote.length > 500 ? d.verbatim_quote.slice(0, 500) + "…" : d.verbatim_quote}”
            </blockquote>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", marginTop: ".35rem",
              color: d.quote_verified === false ? "var(--inferred)" : "var(--verified)" }}>
              {d.quote_verified === false ? "○ could not be string-matched · shown as inferred" : "✓ verified verbatim against the source text"}
            </div>
          </section>
        )}

        {drew.length > 0 && (
          <section style={{ marginBottom: "1.4rem" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", letterSpacing: ".12em",
              textTransform: "uppercase", color: "var(--ink-faint)", marginBottom: ".5rem" }}>
              What it drew from
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
              {drew.map((l, i) => <EdgeLine key={i} l={l} dir="in" />)}
            </div>
          </section>
        )}

        {fed.length > 0 && (
          <section>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", letterSpacing: ".12em",
              textTransform: "uppercase", color: "var(--ink-faint)", marginBottom: ".5rem" }}>
              What drew from it
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
              {fed.map((l, i) => <EdgeLine key={i} l={l} dir="out" />)}
            </div>
          </section>
        )}

        {drew.length === 0 && fed.length === 0 && (
          <p style={{ fontSize: ".85rem", color: "var(--ink-soft)" }}>
            No typed links recorded for this paper among the corpus. ({Object.keys(EDGE_MEANING).length} link
            types are traced; links only exist where one corpus paper cites another across meanings.)
          </p>
        )}

        <p style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem", color: "var(--ink-faint)",
          lineHeight: 1.8, marginTop: "2rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}>
          Verbatim quotes are string-matched against our own extraction of the source; the tool’s
          readings are labelled as such and never wear the verified stamp.
        </p>
      </div>
    </main>
  );
}

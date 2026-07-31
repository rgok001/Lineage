import Link from "next/link";
import { redirect } from "next/navigation";
import { getInfluenceMap } from "../../../lib/genealogy";
import InfluenceMap from "./InfluenceMap";

export const dynamic = "force-dynamic";

export default async function GenealogyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getInfluenceMap(Number(id));
  if (!data) redirect(`/g/${id}/evidence`); // maps without a generated river fall back to the evidence view

  const legend: [string, string][] = [
    ["migrates", "jumped fields"], ["extends", "built on"], ["narrows", "specialised"], ["renames", "same idea, new name"],
  ];

  return (
    <main style={{ maxWidth: 1400, margin: "0 auto", padding: "1rem 1.5rem 4rem" }}>
      <header style={{ padding: "0 0 1.2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2.1rem", margin: 0, letterSpacing: "-.01em" }}>
            How “{data.concept}” evolved
          </h1>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)",
            background: "var(--card)", border: "1px solid var(--line)", borderRadius: 999, padding: ".38rem .8rem", marginTop: ".4rem" }}>
            {data.papers.length} pivotal of {data.total_papers} papers ·{" "}
            {data.edges.length === 0
              ? "no links between them"
              : `${data.edges.filter((e) => e.verified).length} of ${data.edges.length} links shown quote-verified`}
          </span>
        </div>
        {data.through_line && (
          <p style={{ fontFamily: "var(--font-display)", fontSize: "1.08rem", lineHeight: 1.6,
            color: "var(--ink)", margin: ".9rem 0 0", maxWidth: "46rem" }}>
            {data.through_line}
          </p>
        )}
        <div style={{ display: "flex", flexWrap: "wrap", gap: ".35rem 1.2rem", margin: ".9rem 0 0",
          fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>
          {legend.map(([t, gloss]) => (
            <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: ".35rem" }}>
              <span style={{ width: 16, borderTop: `2px solid var(--edge-${t})` }} />
              <span style={{ color: `var(--edge-${t})` }}>▶</span>{t} · {gloss}
            </span>
          ))}
          <span style={{ display: "inline-flex", alignItems: "center", gap: ".35rem" }}>
            <span style={{ width: 10, height: 10, border: "2px solid var(--ink)", borderRadius: "50%" }} />turning point
          </span>
          <span style={{ color: "var(--ink-faint)" }}>
            the arrow points at the newer paper, and names what it did to the older one’s idea
          </span>
        </div>
      </header>

      <InfluenceMap id={Number(id)} data={data} />

      <section style={{ marginTop: "1.6rem" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", letterSpacing: ".14em",
          textTransform: "uppercase", color: "var(--ink-faint)", margin: "0 0 .6rem" }}>
          Read a thread as an account
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
          {data.streams.map((s) => (
            <Link key={s.id} href={`/g/${id}/river/${s.id}`}
              style={{ display: "flex", gap: ".8rem", alignItems: "baseline", textDecoration: "none",
                background: "var(--card)", border: "1px solid var(--line)", borderLeft: `4px solid ${s.color}`,
                borderRadius: 8, padding: ".6rem .9rem" }}>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: ".98rem", color: "var(--ink)" }}>
                {s.name}
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)" }}>
                {s.count} papers
              </span>
              <span style={{ marginLeft: "auto", color: "var(--ink-faint)" }}>›</span>
            </Link>
          ))}
        </div>
      </section>

      <Link href={`/g/${id}/evidence`} style={{ display: "flex", alignItems: "center", gap: ".6rem",
        textDecoration: "none", marginTop: "1.5rem", padding: ".65rem .9rem", borderRadius: 8,
        border: "1px dashed var(--line)" }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: ".95rem", color: "var(--ink)" }}>
          The evidence and workbench →
        </span>
        <span style={{ fontSize: ".8rem", color: "var(--ink-soft)", marginLeft: "auto" }}>
          every typed relationship, the proof, and the curation tools
        </span>
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: ".6rem", flexWrap: "wrap",
        marginTop: ".6rem", padding: ".65rem .9rem", borderRadius: 8, border: "1px dashed var(--line)" }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: ".95rem", color: "var(--ink)" }}>
          Take it to your draft
        </span>
        <span style={{ fontSize: ".8rem", color: "var(--ink-soft)" }}>
          every thread, in order, with the quotes and the citations
        </span>
        <span style={{ marginLeft: "auto", display: "flex", gap: ".7rem", fontFamily: "var(--font-mono)", fontSize: ".72rem" }}>
          <a href={`/g/${id}/export`} style={{ color: "var(--edge-extends)" }}>Markdown</a>
          <a href={`/g/${id}/export?format=bib`} style={{ color: "var(--edge-extends)" }}>BibTeX</a>
        </span>
      </div>

      <p style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-faint)",
        lineHeight: 1.8, marginTop: "1.8rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}>
        Drafted automatically from the papers’ own words. {data.curation}{" "}
        Scope is the corpus: broadening the source adds threads, each arriving with its
        evidence attached.
      </p>
    </main>
  );
}

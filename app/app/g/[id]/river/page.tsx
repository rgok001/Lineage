import Link from "next/link";
import { notFound } from "next/navigation";
import { getRiver } from "../../../../lib/genealogy";
import RiverChart from "./RiverChart";

export const dynamic = "force-dynamic";

export default async function RiverPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getRiver(Number(id));
  if (!data) notFound();
  const { concept, river } = data;

  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "2rem 1.5rem 5rem" }}>
      <Link href={`/g/${id}`} style={{ fontSize: ".8rem", color: "var(--ink-soft)" }}>
        ‹ the full evidence view
      </Link>

      <header style={{ borderBottom: "2px solid var(--line)", padding: "1rem 0 1.1rem", margin: "0 0 1.4rem" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".14em",
          textTransform: "uppercase", color: "var(--ink-soft)" }}>
          The river · {river.streams.length} currents · grounded
        </div>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2.1rem", margin: ".5rem 0 0" }}>
          How “{concept}” evolved
        </h1>
        {river.through_line && (
          <p style={{ fontFamily: "var(--font-display)", fontSize: "1.1rem", lineHeight: 1.6,
            color: "var(--ink)", margin: "1rem 0 0", maxWidth: "44rem" }}>
            {river.through_line}
          </p>
        )}
        <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)", margin: "1.2rem 0 0" }}>
          time → · hover a current to trace where it fed the others · click one to dive into its papers
        </p>
      </header>

      <RiverChart id={Number(id)} river={river} />

      <div style={{ display: "flex", flexDirection: "column", gap: ".55rem", marginTop: "1.6rem" }}>
        {[...river.streams].sort((a, b) => (a.origin_year ?? 0) - (b.origin_year ?? 0)).map((s) => (
          <Link key={s.id} href={`/g/${id}/river/${s.id}`}
            style={{ display: "flex", gap: ".8rem", alignItems: "baseline", textDecoration: "none",
              background: "var(--card)", border: "1px solid var(--line)", borderLeft: `4px solid ${s.color}`,
              borderRadius: 8, padding: ".7rem .95rem" }}>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1rem", color: "var(--ink)" }}>
              {s.name}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-soft)" }}>
              {s.papers.length} papers
            </span>
            {s.tagline && (
              <span style={{ fontSize: ".84rem", color: "var(--ink-soft)", marginLeft: "auto" }}>{s.tagline}</span>
            )}
          </Link>
        ))}
      </div>

      <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)",
        lineHeight: 1.9, marginTop: "2rem", paddingTop: "1.1rem", borderTop: "1px solid var(--line)" }}>
        Drawn from 134 papers’ own words, grouped by understanding rather than citation. Scope is the
        corpus: broadening the source would add currents, each arriving with its evidence attached.
      </p>
    </main>
  );
}

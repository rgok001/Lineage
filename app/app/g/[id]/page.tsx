import Link from "next/link";
import { redirect } from "next/navigation";
import SignInButton from "../../signin-button";
import { getRiver } from "../../../lib/genealogy";
import RiverChart from "./river/RiverChart";

export const dynamic = "force-dynamic";

export default async function GenealogyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getRiver(Number(id));
  if (!data) redirect(`/g/${id}/evidence`); // maps without a generated river fall back to the evidence view
  const { concept, river } = data;
  const streams = [...river.streams].sort((a, b) => (a.origin_year ?? 0) - (b.origin_year ?? 0));

  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "2rem 1.5rem 5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Link href="/" style={{ fontSize: ".8rem", color: "var(--ink-soft)" }}>‹ all genealogies</Link>
        <SignInButton />
      </div>

      <header style={{ borderBottom: "2px solid var(--line)", padding: "1rem 0 1.1rem", margin: "0 0 1.4rem" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".14em",
          textTransform: "uppercase", color: "var(--ink-soft)" }}>
          {streams.length} currents · every claim tied to a verified quote
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
        {streams.map((s) => (
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

      <Link href={`/g/${id}/evidence`} style={{ display: "flex", alignItems: "center", gap: ".6rem",
        textDecoration: "none", marginTop: "1.8rem", padding: ".7rem .95rem", borderRadius: 8,
        border: "1px dashed var(--line)" }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--ink)" }}>
          The evidence and workbench →
        </span>
        <span style={{ fontSize: ".82rem", color: "var(--ink-soft)", marginLeft: "auto" }}>
          the ranked papers and every typed relationship, with the proof and the editing tools
        </span>
      </Link>

      <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)",
        lineHeight: 1.9, marginTop: "2rem", paddingTop: "1.1rem", borderTop: "1px solid var(--line)" }}>
        Drawn from the papers’ own words, grouped by understanding rather than citation. Scope is the
        corpus: broadening the source would add currents, each arriving with its evidence attached.
      </p>
    </main>
  );
}

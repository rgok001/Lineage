import Link from "next/link";
import { EDGE_MEANING } from "../../lib/genealogy";

/** Static methods page: what the site claims and how each claim is earned.
 *  No data fetching — this is documentation, in the product's own voice. */

export const metadata = { title: "How Lineage works" };

const EDGE_COLORS: Record<string, string> = {
  extends: "var(--edge-extends)",
  contests: "var(--edge-contests)",
  narrows: "var(--edge-narrows)",
  renames: "var(--edge-renames)",
  merges: "var(--edge-merges)",
  migrates: "var(--edge-migrates)",
};

export default function AboutPage() {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "2rem 1.5rem 5rem" }}>
      <Link href="/" style={{ fontSize: ".8rem", color: "var(--ink-soft)" }}>‹ all genealogies</Link>

      <header style={{ borderBottom: "2px solid var(--line)", padding: "1rem 0 1.1rem", marginBottom: "1.6rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2rem", margin: 0 }}>
          How Lineage works
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".5rem 0 0", lineHeight: 1.55 }}>
          Scientific terms drift. “Attention” in 2013 named a Gaussian window over handwriting
          strokes; by 2017 it named an entire architecture. Lineage maps that drift — and backs
          every step of the map with quotes you can check.
        </p>
      </header>

      <Section title="The claim">
        <P>
          Each genealogy says: <em>here are the distinct meanings a concept has had, and here is
          how each meaning grew out of the ones before it</em>. That second part is the risky
          claim — it is easy to assert influence and hard to show it. Lineage’s rule is that no
          relationship appears on a map unless the two papers are connected by a real citation,
          and the relationship is presented alongside a verbatim passage from each paper so you
          can judge it yourself.
        </P>
      </Section>

      <Section title="How a genealogy is built">
        <Step n={1} name="Gather the papers.">
          Starting from a concept, Lineage assembles a corpus of up to 150 papers from arXiv,
          ranked by relevance and citation weight — including ancestors that never use the
          concept’s name. (The paper that introduced soft alignment never says “attention”; it
          enters through citations, not keywords.)
        </Step>
        <Step n={2} name="Read each paper for a definition.">
          A language model reads each paper’s full text and answers one question: does this paper
          give “{"<"}concept{">"}” a meaning of its own? If yes, it must return the defining
          passage <em>verbatim</em> — not a summary. Papers that merely use the term are recorded
          and excluded.
        </Step>
        <Step n={3} name="Group definitions into meanings.">
          Definitions are embedded and clustered: papers that mean the same thing by the term form
          one “meaning” (one card on the timeline). The clustering deliberately over-splits —
          merging two meanings is a one-click curatorial act; un-merging is not.
        </Step>
        <Step n={4} name="Find and type the relationships.">
          For every pair of meanings, Lineage checks whether their papers actually cite each
          other, using citation data from Semantic Scholar. Where a real citation exists, a model
          classifies the relationship into one of six types (below), with a confidence score.
        </Step>
        <Step n={5} name="Verify every quote.">
          Finally, each relationship’s two quotes are string-matched against the extracted source
          text of their papers. Both found: the relationship is drawn solid and marked
          <strong style={{ color: "var(--verified)" }}> ● verified</strong>. Either one missing:
          it is drawn dotted and marked
          <strong style={{ color: "var(--inferred)" }}> ○ inferred</strong> — never upgraded,
          never hidden.
        </Step>
      </Section>

      <Section title="The six relationship types">
        <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
          {Object.entries(EDGE_MEANING).map(([type, meaning]) => (
            <div key={type} style={{ display: "flex", alignItems: "center", gap: ".6rem" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", textTransform: "uppercase",
                letterSpacing: ".07em", color: "#fff", background: EDGE_COLORS[type],
                padding: ".2rem .55rem", borderRadius: 4, minWidth: 76, textAlign: "center" }}>
                {type}
              </span>
              <span style={{ fontSize: ".88rem", color: "var(--ink)" }}>{meaning}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Machine draft, human judgment">
        <P>
          What the pipeline produces is a draft. The curator can rename meanings, merge
          over-split ones, delete weak ones, and reclassify or remove relationships. Every one of
          these decisions is recorded in the genealogy’s audit trail, visible at the bottom of its
          page — so a curated map always shows what a human changed, and when.
        </P>
      </Section>

      <Section title="Live traces">
        <P>
          Anyone signed in can request a genealogy for a new concept. Requests are reviewed by
          the curator; approved traces run automatically and report their progress live — which
          papers are being read, what each stage found, and what the run cost. A trace of a
          150-paper corpus takes about 15 minutes.
        </P>
      </Section>

      <Section title="Limitations, honestly">
        <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--ink)", fontSize: ".92rem", lineHeight: 1.65 }}>
          <li>
            Coverage is arXiv-only, so fields that publish elsewhere are underrepresented, and a
            concept’s pre-history outside arXiv is invisible.
          </li>
          <li>
            Quote verification is exact string matching against extracted text. When extraction
            mangles a passage (math-heavy LaTeX, scanned PDFs), a genuine quote can fail the
            check — which is why such relationships are shown as <em>inferred</em> rather than
            dropped: the failure is disclosed, not silently discarded.
          </li>
          <li>
            Relationships require citation links. Parallel discovery — two groups converging on a
            meaning without citing each other — appears as unconnected meanings, not as a link.
          </li>
          <li>
            The relationship types and confidence scores are a model’s judgment. The quotes are
            there precisely so you do not have to take that judgment on faith.
          </li>
        </ul>
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: "2rem" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.25rem",
        color: "var(--ink)", margin: "0 0 .6rem" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ margin: "0 0 .8rem", color: "var(--ink)", fontSize: ".92rem", lineHeight: 1.65 }}>
      {children}
    </p>
  );
}

function Step({ n, name, children }: { n: number; name: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: ".8rem", marginBottom: ".9rem" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: ".8rem", background: "var(--ink)",
        color: "var(--paper)", width: 24, height: 24, borderRadius: "50%", flex: "0 0 24px",
        display: "inline-flex", alignItems: "center", justifyContent: "center", marginTop: ".1rem" }}>
        {n}
      </span>
      <p style={{ margin: 0, fontSize: ".92rem", lineHeight: 1.65, color: "var(--ink)" }}>
        <strong>{name}</strong> {children}
      </p>
    </div>
  );
}

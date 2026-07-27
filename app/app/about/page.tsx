import Link from "next/link";
import { EDGE_MEANING } from "../../lib/genealogy";

/** The methods page. Written for a researcher deciding whether to trust this
 *  for their own work: what each claim on a map rests on, how it was produced,
 *  and where it breaks. Documentation, in the product's own voice — no data
 *  fetching, but the edge taxonomy is read from the same map the product uses
 *  so the two cannot drift apart. */

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
    <main style={{ maxWidth: 780, margin: "0 auto", padding: "2rem 1.5rem 5rem" }}>
      <Link href="/" style={{ fontSize: ".8rem", color: "var(--ink-soft)", textDecoration: "none" }}>
        ‹ all concepts
      </Link>

      <header style={{ borderBottom: "2px solid var(--line)", padding: "1rem 0 1.3rem", marginBottom: "1.8rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2rem", margin: 0 }}>
          How Lineage works
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".7rem 0 0", lineHeight: 1.6 }}>
          Written for someone deciding whether to rely on this. It sets out what a map claims, how
          each claim is produced, which parts are machine judgment rather than fact, and where the
          method fails. If you only read one section, read{" "}
          <a href="#trust" style={{ color: "var(--edge-extends)" }}>what you can and cannot rely on</a>.
        </p>
      </header>

      <Section title="What a map is">
        <P>
          A map answers one question: <em>how did this term get here, and which papers moved it?</em>
          It is not a literature search and not a ranking of important papers. It is an account of a
          term’s development, assembled from what the papers themselves say the term means.
        </P>
        <P>
          Three things are on it. <strong>Papers</strong>, drawn as dots, positioned by year and sized
          by how much later work built on them <em>for this term</em>. <strong>Currents</strong>, the
          parallel lines of development the idea split into. And <strong>links</strong>, typed
          relationships between two specific papers, each carrying a sentence explaining what the
          later paper did to the earlier one’s idea.
        </P>
      </Section>

      <Section title="How a map is built">
        <Step n={1} name="Select a corpus.">
          Starting from your term and its field, candidate papers come from OpenAlex, scoped to the
          discipline you chose. Candidates are ranked by embedding similarity to the term, keeping
          the top N rather than applying a similarity cutoff, because a fixed cutoff removes
          foundational papers: “Attention Is All You Need” scores only 0.567 against the query
          “attention” and a 0.62 threshold once deleted it. The corpus is then expanded one hop
          through the citation graph, and that expansion is deliberately <em>not</em> filtered by
          similarity, because ancestors do not use their descendants’ vocabulary. Bahdanau’s 2014
          paper, the origin of neural attention, never says “attention”; it says “align”. It can only
          enter through citations. Everything is metadata-only at this stage: nothing is downloaded
          and nothing is paid for until the corpus is fixed.
        </Step>
        <Step n={2} name="Fetch and extract full text.">
          Papers are fetched from arXiv, LaTeX source preferred over PDF because LaTeX extracts
          cleanly and PDFs do not. Extraction is checked against the paper’s claimed title, because
          metadata sources sometimes attach the wrong identifier to a work: two well-known models in
          our own corpus carried titles belonging to different papers. Anything below the match
          threshold is dropped rather than silently mis-attributed.
        </Step>
        <Step n={3} name="Read every paper for its own definition.">
          A language model reads each paper’s full text and answers one question: does this paper give
          the term a meaning of its own? If yes it must return the defining passage <em>verbatim</em>,
          plus the section it came from and what the paper claims it contributed. Papers that merely
          use the term are recorded as such and excluded from the map. A negative answer is a finding,
          not a failure, and is cached like any other.
        </Step>
        <Step n={4} name="Find the currents.">
          The corpus is read as a whole to identify the distinct lines of development the term
          followed, grouped by what the papers say rather than by who cites whom. Two papers can
          define a term identically without ever citing each other, and a citation can cross between
          currents; grouping by citation topology would produce a graph-theoretic artifact rather
          than a conceptual one.
        </Step>
        <Step n={5} name="Type the links between papers.">
          Where one corpus paper cites another, the sentence containing that citation is retrieved from
          Semantic Scholar and a model classifies the relationship into one of six types, with a
          confidence score and a one-sentence justification. Direction is chronological: the cited
          paper is the ancestor, the citing paper is the descendant, and the type describes what the
          descendant did. Links that point backwards in time are discarded as data errors.
        </Step>
        <Step n={6} name="Verify every quote.">
          Each quote is string-matched against our own extraction of that paper’s text. Found: marked
          <strong style={{ color: "var(--verified)" }}> ✓ verified</strong>. Not found: marked
          <strong style={{ color: "var(--inferred)" }}> ○ inferred</strong> and shown as such. A quote
          is never upgraded, never quietly rewritten to fit, and never hidden because it failed.
        </Step>
      </Section>

      <Section title="How papers are ranked">
        <P>
          Two independent measures decide what appears on a map and how it is drawn. Neither is
          displayed as a number, because a spurious precision would be worse than none.
        </P>
        <P>
          <strong>Uptake</strong> sets a paper’s size: how much later work in the corpus built on it{" "}
          <em>for this term</em>. Not raw citation count, which measures fame and puts
          famous-but-incidental papers at the centre of every map. Each citation is weighted by
          whether the citing sentence actually engages that paper’s treatment of the term. On our
          “embedding” map this is the difference between VGG, cited fourteen times but never once for
          its embedding contribution, and word2vec, cited for exactly that.
        </P>
        <P>
          <strong>Displacement</strong> marks turning points: how far a paper’s definition sits from
          the centroid of every definition before it. The two measures are close to uncorrelated in
          practice, which is the point. The most-built-on paper usually consolidates a settled
          meaning; the paper that moved a term furthest is often lightly cited within the corpus,
          because the field it moved into is a different literature. Ranking on uptake alone would
          systematically hide exactly the papers a researcher is looking for.
        </P>
      </Section>

      <Section title="The six link types">
        <div style={{ display: "flex", flexDirection: "column", gap: ".45rem", marginBottom: ".9rem" }}>
          {Object.entries(EDGE_MEANING).map(([type, meaning]) => (
            <div key={type} style={{ display: "flex", alignItems: "center", gap: ".6rem" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", textTransform: "uppercase",
                letterSpacing: ".07em", color: "var(--paper)", background: EDGE_COLORS[type],
                padding: ".2rem .55rem", borderRadius: 4, minWidth: 80, textAlign: "center" }}>
                {type}
              </span>
              <span style={{ fontSize: ".88rem", color: "var(--ink)" }}>{meaning}</span>
            </div>
          ))}
        </div>
        <P>
          The type is the model’s classification. The citing sentence beside it is not, so you can
          check the reading against the evidence in one glance.
        </P>
      </Section>

      <Section title="What you can and cannot rely on" id="trust">
        <P>
          A map mixes three kinds of statement, and they are marked differently everywhere they appear
          because conflating them is the failure mode this tool exists to avoid.
        </P>
        <div style={{ display: "flex", flexDirection: "column", gap: ".6rem" }}>
          <Tier
            label="Verified"
            color="var(--verified)"
            body="Quoted passages carrying the ✓ stamp. These were string-matched against our extraction of the source. If the stamp is there, the paper contains those words."
          />
          <Tier
            label="Sourced but unverified"
            color="var(--edge-renames)"
            body="Citation sentences from Semantic Scholar, and passages marked ○ inferred. Real text from a real source, but drawn from a different extraction than ours, so we cannot mechanically confirm it against the paper."
          />
          <Tier
            label="Machine judgment"
            color="var(--edge-narrows)"
            body="Link types, confidence scores, the current groupings, and any sentence labelled “the tool’s reading”. Generated from the evidence shown beside it. Treat as a well-informed starting point, never as a citable claim."
          />
        </div>
        <P style={{ marginTop: ".9rem" }}>
          The practical rule: <strong>quote what is verified, verify what is sourced, and check
          anything that is judgment</strong> against the evidence sitting next to it.
        </P>
      </Section>

      <Section title="Limitations and scope">
        <P>
          What a map covers, and what it does not. These are properties of the method rather than
          defects to be patched, so they are worth knowing before you rely on one.
        </P>
        <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--ink)", fontSize: ".92rem", lineHeight: 1.7 }}>
          <li>
            <strong>Coverage is arXiv-only.</strong> Fields that publish through journals, conferences
            or books are underrepresented or absent, and a term’s pre-arXiv history is invisible. If
            your field does not preprint, this is not the right tool yet.
          </li>
          <li>
            <strong>A corpus is bounded, and the bound is arbitrary.</strong> Up to 150 papers, ranked
            by relevance and citation weight. That is a defensible sample, not the literature. Papers
            outside it are not judged unimportant; they were not examined.
          </li>
          <li>
            <strong>Verification is exact string matching.</strong> When extraction mangles a passage,
            common in maths-heavy LaTeX and scanned PDFs, a genuine quote fails the check and is
            marked inferred. Some inferred quotes are perfectly real. The check is conservative on
            purpose: it fails towards disclosure.
          </li>
          <li>
            <strong>Links need a citation.</strong> Parallel discovery, where two groups reach the same
            idea without citing each other, produces no link. The map shows unconnected work as
            unconnected rather than inventing a relationship.
          </li>
          <li>
            <strong>The reading is a model’s.</strong> Link types, currents and contributions are
            generated. They are grounded in quoted evidence and shown beside it, but they are not
            peer review, and the confidence scores are calibrated judgment rather than measurement.
          </li>
          <li>
            <strong>It is a draft until a human touches it.</strong> Anything not yet curated is raw
            pipeline output. The audit trail on each map records what a person changed and when, so
            you can see how much human judgment a given map has had.
          </li>
        </ul>
      </Section>

      <Section title="Draft, then judgment">
        <P>
          What the pipeline produces is a draft. A curator can rename a current, merge over-split
          ones, delete weak groupings, and reclassify or remove links. Every such decision is appended
          to the map’s audit trail, so a curated map always carries the record of what a human changed
          and when. No edit rewrites a quote or changes a verification result: curation reorganises the
          reading, never the evidence.
        </P>
      </Section>

      <Section title="Reproducibility">
        <P>
          Every map records the corpus it examined, the extraction prompt version behind each
          definition, and the model that produced it. Re-running a term with the same prompt version
          reuses the cached per-paper extractions, so a map can be rebuilt without re-reading the
          corpus, and a changed prompt is a new version rather than a silent overwrite. If you want to
          audit a claim, each paper links to its arXiv source and the passage is quoted, so the check
          takes seconds.
        </P>
      </Section>

      <Section title="Requesting a map">
        <P>
          Anyone signed in can{" "}
          <Link href="/trace" style={{ color: "var(--edge-extends)" }}>request a term</Link>. Reading a
          corpus costs real money in model usage, so requests are reviewed before they run. Approved
          runs report progress live: which paper is being read, what each stage found, and what the run
          has cost. A 150-paper corpus takes about fifteen minutes.
        </P>
      </Section>
    </main>
  );
}

function Section({ title, id, children }: { title: string; id?: string; children: React.ReactNode }) {
  return (
    <section id={id} style={{ marginBottom: "2.2rem", scrollMarginTop: "1rem" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.3rem",
        color: "var(--ink)", margin: "0 0 .7rem" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function P({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <p style={{ margin: "0 0 .8rem", color: "var(--ink)", fontSize: ".94rem", lineHeight: 1.7, ...style }}>
      {children}
    </p>
  );
}

function Tier({ label, color, body }: { label: string; color: string; body: string }) {
  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderLeft: `3px solid ${color}`,
      borderRadius: "0 8px 8px 0", padding: ".7rem .9rem" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem", letterSpacing: ".12em",
        textTransform: "uppercase", color }}>{label}</div>
      <p style={{ margin: ".3rem 0 0", fontSize: ".88rem", lineHeight: 1.6, color: "var(--ink-soft)" }}>{body}</p>
    </div>
  );
}

function Step({ n, name, children }: { n: number; name: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: ".8rem", marginBottom: "1rem" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: ".8rem", background: "var(--card)",
        border: "1px solid var(--line)", color: "var(--ink-soft)", width: 26, height: 26, borderRadius: "50%",
        flex: "0 0 26px", display: "inline-flex", alignItems: "center", justifyContent: "center", marginTop: ".1rem" }}>
        {n}
      </span>
      <p style={{ margin: 0, fontSize: ".94rem", lineHeight: 1.7, color: "var(--ink)" }}>
        <strong>{name}</strong> {children}
      </p>
    </div>
  );
}

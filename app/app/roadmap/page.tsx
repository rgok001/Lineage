import Link from "next/link";

export const metadata = { title: "Roadmap — Lineage" };

/**
 * What is built, what is being worked on, and what is deliberately not planned.
 * Written so a researcher can judge whether the gap between what this does now
 * and what they need is likely to close.
 *
 * **These lists are hand-written and nothing recomputes them** (issue #119).
 * That is a choice, not an oversight, and the page now says so and links to the
 * live ticket list, because the alternative was worse in two ways. Deriving the
 * buckets from issue labels was measured and does not work: every open feature
 * carries the same "planned" label, so the labels cannot tell "working on next"
 * from "under consideration" and the derivation would invent an order the
 * tracker does not hold. And prose describing a moving list is exactly the
 * failure the record's own history warns about, which is why the honest framing
 * is the fix rather than a syncing mechanism nobody maintains.
 *
 * The drift this ticket found: "Bring your own corpus" sat under Under
 * consideration while issue #37 [F9] is labelled planned, and issues are
 * canonical. It has moved. "Claim-level verification" was listed as entirely
 * ahead when Stage H ships it on the thread pages wherever it has run; the entry
 * now says which part is live and which is not.
 */

type Item = { title: string; body: string };

const SHIPPED: Item[] = [
  { title: "The influence map",
    body: "Every pivotal paper placed by year and sized by how much later work built on it for the term, with the relationships between specific papers typed and named." },
  { title: "Verified quotes throughout",
    // One phrase for the verification claim across the product (issue #129).
    body: "Each definition is quoted word for word from the paper, and checked against the text this system pulled out of it. Quotes that cannot be found are marked inferred rather than dropped or quietly smoothed over." },
  { title: "Threads and their accounts",
    body: "The parallel lines of development a term followed, each readable as an ordered account of the papers that carried it." },
  { title: "Per-paper dossiers",
    body: "What a paper contributed, how it defines the term, what it drew from and what drew from it, with the reasoning behind each link shown as the tool's reading rather than as fact." },
  { title: "Curation with an audit trail",
    body: "A curator can rename, merge, reclassify and remove. Every change is recorded, so a map shows how much human judgment it has had." },
  { title: "Export for writing",
    body: "Take a map, or a single thread of it, into your draft as a Markdown scaffold with the quotes and the citations attached, plus BibTeX for exactly the papers it cites. The structure and the evidence are real; the argument is yours to write." },
];

const NEXT: Item[] = [
  { title: "Sources beyond arXiv",
    body: "The single biggest limit on who this is useful to. Finding free copies of papers by their DOI, and reading biomedical full text, would open up fields that do not post preprints to arXiv." },
  { title: "Claim-level verification, everywhere",
    body: "Part of this is already live: on a thread's account, where it has been run, each thing a paper did carries its own quote, matched against that paper's text or plainly marked as unmatched. What is left is doing that for every map and every account, so a whole reading is auditable sentence by sentence rather than paragraph by paragraph." },
  { title: "Bring your own corpus",
    body: "Point it at a folder of PDFs or a BibTeX file instead of having it choose papers for you. Finding papers and reading them are already separate steps inside the system, so this is more wiring than invention." },
  { title: "A preview before a run",
    body: "Showing the candidate papers, the year span and the cost before a map is built, so you can judge the corpus before spending on it." },
];

const CONSIDERING: Item[] = [
  { title: "Your own extraction question",
    body: "Today the question each paper is asked is fixed: how do you define this term? Letting a reviewer set that question turns the same machinery into a general extraction tool." },
  { title: "Comparing two maps",
    body: "How a term's development differs between fields, or how a map changes as new work lands." },
];

const NOT_PLANNED: Item[] = [
  { title: "A recommendation engine",
    body: "This maps how a term developed. It does not rank papers by quality, predict what to read next, or tell you what matters in your subfield." },
  { title: "A search engine",
    body: "Finding papers on a topic is well served elsewhere and served better. This starts where search ends: you have a term, and you want its development." },
  { title: "Automatic curation",
    body: "The pipeline drafts; a person decides. Removing the human step would remove the thing that makes a curated map worth more than its raw output." },
];

export default function RoadmapPage() {
  return (
    <main style={{ maxWidth: 780, margin: "0 auto", padding: "1rem 1.5rem 5rem" }}>
      <header style={{ borderBottom: "2px solid var(--line)", padding: "0 0 1.3rem", marginBottom: "1.8rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2rem", margin: 0 }}>
          Roadmap
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".7rem 0 0", lineHeight: 1.6 }}>
          Where this is, where it is going, and what it will not become. If the gap between what it
          does now and what you need sits in the first two lists, it is likely to close. If it sits in
          the last, it will not.
        </p>
        <p style={{ color: "var(--ink-faint)", margin: ".7rem 0 0", lineHeight: 1.6, fontSize: ".85rem" }}>
          This page is the owner&rsquo;s current statement of intent, written by hand and kept up to
          date by hand. The live list of open work, item by item, is on{" "}
          <a href="https://github.com/rgok001/Lineage/issues" target="_blank" rel="noopener noreferrer"
            style={{ color: "var(--edge-extends)" }}>GitHub</a>; where the two disagree, that list is
          the one to believe.
        </p>
      </header>

      <Group title="Built and in use" tint="var(--verified)" items={SHIPPED} />
      <Group title="Working on next" tint="var(--edge-extends)" items={NEXT} />
      <Group title="Under consideration" tint="var(--edge-renames)" items={CONSIDERING} />
      <Group title="Not planned" tint="var(--ink-faint)" items={NOT_PLANNED} />

      <p style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-faint)",
        lineHeight: 1.8, marginTop: "2rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}>
        Built in the open by one person, so this is an honest order of intent rather than a delivery
        schedule with dates. If something here decides whether the tool is useful to you,{" "}
        <Link href="/trace" style={{ color: "var(--edge-extends)" }}>request a concept</Link> and say so
        in the note.
      </p>
    </main>
  );
}

function Group({ title, tint, items }: { title: string; tint: string; items: Item[] }) {
  return (
    <section style={{ marginBottom: "2.2rem" }}>
      <h2 style={{ display: "flex", alignItems: "center", gap: ".55rem", fontFamily: "var(--font-display)",
        fontWeight: 600, fontSize: "1.25rem", color: "var(--ink)", margin: "0 0 .9rem" }}>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: tint, flex: "none" }} />
        {title}
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
        {items.map((it) => (
          <div key={it.title} style={{ background: "var(--card)", border: "1px solid var(--line)",
            borderLeft: `3px solid ${tint}`, borderRadius: "0 8px 8px 0", padding: ".8rem 1rem" }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1rem",
              color: "var(--ink)", marginBottom: ".25rem" }}>
              {it.title}
            </div>
            <p style={{ margin: 0, fontSize: ".88rem", lineHeight: 1.6, color: "var(--ink-soft)" }}>
              {it.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

import Link from "next/link";
import { redirect } from "next/navigation";
import { getViewer, isOwner } from "../../../lib/authz";
import { getInfluenceMap } from "../../../lib/genealogy";
import InfluenceMap from "./InfluenceMap";

export const dynamic = "force-dynamic";

export default async function GenealogyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [data, viewer] = await Promise.all([getInfluenceMap(Number(id)), getViewer()]);
  if (!data) redirect(`/g/${id}/evidence`); // maps without a generated river fall back to the evidence view
  // Only to decide what the evidence door may promise (issue #118). The
  // workbench is gated inside the evidence page and inside every action; this
  // has no authority over anything and grants nothing.
  const owner = isOwner(viewer);

  const verifiedDrawn = data.edges.filter((e) => e.stamp === "verified").length;

  /**
   * The legend is derived from the links this canvas actually drew (issue #115).
   *
   * It was four hardcoded entries against a taxonomy of six, and the canvas
   * holds a colour for all six, so a `contests` or `merges` link among the
   * pivotal papers drew in a colour the key never explained. That is the key
   * failing at exactly the moment the map says something unusual: a contested
   * idea is the most interesting line on any map and it was the unexplained one.
   *
   * Derived rather than hardcoded to six, so no map carries dead entries for
   * types it does not hold. A type with no gloss here still gets a row, named
   * and unglossed, because a drawn colour with no key is the defect and a
   * missing sentence is not.
   */
  const GLOSS: Record<string, string> = {
    extends: "built on", contests: "pushed back", narrows: "specialised",
    renames: "same idea, new name", merges: "combined ideas", migrates: "jumped fields",
  };
  const drawnTypes = [...new Set(data.edges.map((e) => e.type))];
  const legend: [string, string][] = [
    ...Object.keys(GLOSS).filter((t) => drawnTypes.includes(t)),
    ...drawnTypes.filter((t) => !(t in GLOSS)).sort(),
  ].map((t) => [t, GLOSS[t] ?? "an unrecognised kind of link"]);

  return (
    <main style={{ maxWidth: 1400, margin: "0 auto", padding: "1rem 1.5rem 4rem" }}>
      <header style={{ padding: "0 0 1.2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2.1rem", margin: 0, letterSpacing: "-.01em" }}>
            How “{data.concept}” evolved
          </h1>
          {/* Both populations named, so neither can be read as the other (issue
              #114). A reader met "320 verified relationships" on the home card,
              then "39 of 39 links shown quote-verified" here, then "320 typed
              relationships" on the evidence page, with the word "shown" as the
              only bridge; the reasonable conclusion was that the map had lost
              281. The canvas draws links between pivotal papers, a narrower
              population than the map holds, and the badge now says so and says
              where the rest are. Issue #30's reasoning is kept, not reversed: two
              counts on one page are dangerous UNLABELLED, and the fix is to
              label them rather than to show one. */}
          <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)",
            background: "var(--card)", border: "1px solid var(--line)", borderRadius: 999, padding: ".38rem .8rem", marginTop: ".4rem" }}>
            {data.papers.length} pivotal of {data.total_papers} papers ·{" "}
            {data.edges.length === 0
              ? "no links between them"
              /* Counted on the resolved stamp, not the stored boolean. A count
                 that folds "not re-checked since the text changed" into
                 "verified" is the same overclaim as the line itself. */
              : `${data.edges.length} links drawn here, ${
                  verifiedDrawn === data.edges.length
                    ? "all quote-verified"
                    : `${verifiedDrawn} quote-verified`}`}
            {data.total_edges > data.edges.length &&
              ` · the full ${data.total_edges} are in the evidence`}
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

      {/* The door promises what this reader will find behind it (issue #118).
          It read "the curation tools" to everyone, and the workbench renders for
          the owner alone: a reader told there are curation tools and finding
          none concludes "broken" or "oversold", not "owner-only". The deeper
          tension is real and is not settled here -- product rule 3 says users
          can edit, and today only the owner can -- but that is the owner's
          decision to make, and the copy should not stay wrong while it waits. */}
      <Link href={`/g/${id}/evidence`} style={{ display: "flex", alignItems: "center", gap: ".6rem",
        textDecoration: "none", marginTop: "1.5rem", padding: ".65rem .9rem", borderRadius: 8,
        border: "1px dashed var(--line)" }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: ".95rem", color: "var(--ink)" }}>
          {owner ? "The evidence and workbench →" : "The evidence →"}
        </span>
        <span style={{ fontSize: ".8rem", color: "var(--ink-soft)", marginLeft: "auto" }}>
          {owner
            ? "every typed relationship, the proof, and your curation tools"
            : "every typed relationship and the proof behind each"}
        </span>
      </Link>

      {/* Issue #103: this row was a footnote link and nobody scrolled to it. It
          carries no numbers on purpose — the header badge counts the links drawn
          on this canvas, a narrower population than any figure on the report,
          and one page holding both counts unlabelled is how they get read as
          one (issue #30's reasoning, kept). */}
      <Link href={`/g/${id}/report`} style={{ display: "flex", alignItems: "center", gap: ".6rem",
        textDecoration: "none", marginTop: ".6rem", padding: ".65rem .9rem", borderRadius: 8,
        border: "1px dashed var(--line)" }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: ".95rem", color: "var(--ink)" }}>
          What this map is made of →
        </span>
        {/* Promises what every reader is actually given (issue #112). This said
            "what the run cost", which renders for the owner alone and reads "not
            recorded" even for them on a map built from the command line: a door
            offering three things where one reader in a hundred receives three.
            If the cost figure stays owner-only, no public copy advertises it. */}
        <span style={{ fontSize: ".8rem", color: "var(--ink-soft)", marginLeft: "auto" }}>
          its own account, figure by figure: what was read, what is verified, and what rests on this tool’s reading
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

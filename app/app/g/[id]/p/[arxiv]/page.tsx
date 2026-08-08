import Link from "next/link";
import { notFound } from "next/navigation";
import { edgeAnchor } from "../../../../../lib/anchors";
import { sql } from "../../../../../lib/db";
import { getMapRow, readableQuote, TURNING_QUANTILE } from "../../../../../lib/genealogy";
import { STAMP_COLOR, STAMP_LABEL, edgeStampOf, stampOf } from "../../../../../lib/stamp";

export const dynamic = "force-dynamic";

/** A paper's dossier: what it contributed, how it moved the term (its typed
 *  links, each with the tool's reading), and the verified quote. The deepest
 *  dive of the map — every claim either verbatim-verified or labelled as the
 *  tool's reading, never blended. */
export default async function PaperPage({ params }: { params: Promise<{ id: string; arxiv: string }> }) {
  const { id, arxiv: raw } = await params;
  const arxiv = decodeURIComponent(raw);

  /**
   * Six queries used to run one after another here, and the Neon HTTP driver
   * charges a round trip for each (issue #140). Measured at 2.5 s to first
   * byte, the second slowest route on the site. They are now three rounds, set
   * by what genuinely depends on what:
   *
   *   1. the map's row, the extraction verdict, — none of these needs anything
   *   2. the definition and the displacement cut — both need only the row
   *   3. the typed links                        — needs the paper's id
   *
   * The dependency chain is three deep and cannot be shortened further without
   * merging statements, which is a bigger change than this ticket wanted.
   */
  const [g, quality] = await Promise.all([
    // The river is on this row too, and this page tolerates its absence: a map
    // whose streams job has not run still has papers, and the breadcrumb simply
    // does not name a thread.
    getMapRow(Number(id)),
    // Asked separately, and allowed to fail. The app deploys the moment master
    // moves, and migration 013 is applied by hand against a different endpoint, so
    // there is a window where this column does not exist yet. Folding it into the
    // definition query would turn that window into a broken page for every paper.
    // Failing to unknown is honest as well as safe: this note only ever appears
    // when a scan found something, and no scan has run means nothing to say.
    sql`SELECT extraction_verdict FROM papers WHERE arxiv_id = ${arxiv}`
      .then((r) => (r as { extraction_verdict: string | null }[])[0]?.extraction_verdict ?? null)
      .catch(() => null),
  ]);
  if (!g) notFound();

  const [defs, cut] = (await Promise.all([
    sql`
      SELECT p.id AS pid, p.year, p.title, d.definition, d.verbatim_quote, d.quote_verified,
             d.section, d.novelty_claims AS novelty, d.displacement,
             d.quote_text_digest, p.extracted_text_digest
      FROM definitions d JOIN papers p ON p.id = d.paper_id
      WHERE p.arxiv_id = ${arxiv} AND d.concept = ${g.concept}
        AND d.prompt_version = ${g.prompt_version} AND d.defines_concept = true
    `,
    // Judged against this concept's own spread, not a fixed number: displacement
    // is a distance from a moving centroid, so a cut that marks a tenth of one
    // corpus marks half of another (lib/genealogy.ts, TURNING_QUANTILE).
    sql`
      SELECT percentile_cont(${TURNING_QUANTILE}) WITHIN GROUP (ORDER BY displacement) AS c
      FROM definitions
      WHERE concept = ${g.concept} AND prompt_version = ${g.prompt_version}
        AND defines_concept = true AND displacement > 0
    `,
  ])) as [
    { pid: number; year: number; title: string; definition: string | null; verbatim_quote: string | null;
      quote_verified: boolean | null; section: string | null; novelty: string[] | null; displacement: number | null;
      quote_text_digest: string | null; extracted_text_digest: string | null }[],
    { c: number | null }[],
  ];
  if (!defs.length) notFound();
  const d = defs[0];
  // The stamp on this page's one quote, resolved the same way every other
  // surface resolves it (migration 015). `quote_verified === false` used to be
  // the only qualifier here, which meant a NULL read as verified and a stamp
  // taken against text that has since been replaced read as verified too.
  const quoteStamp = stampOf(d.quote_verified, d.quote_text_digest, d.extracted_text_digest);

  const linkRows = (await sql`
    SELECT sp.arxiv_id AS src, sp.title AS src_title, sp.year AS src_year,
           tp.arxiv_id AS dst, tp.title AS dst_title, tp.year AS dst_year,
           e.edge_type, e.rationale, e.verified,
           e.source_text_digest, e.target_text_digest,
           sp.extracted_text_digest AS source_current_digest,
           tp.extracted_text_digest AS target_current_digest
    FROM edges e JOIN papers sp ON sp.id = e.source_paper_id
                 JOIN papers tp ON tp.id = e.target_paper_id
    WHERE e.genealogy_id = ${Number(id)} AND (e.source_paper_id = ${d.pid} OR e.target_paper_id = ${d.pid})
    ORDER BY e.confidence DESC
  `) as { src: string; src_title: string; src_year: number; dst: string; dst_title: string; dst_year: number;
          edge_type: string; rationale: string | null; verified: boolean;
          source_text_digest: string | null; target_text_digest: string | null;
          source_current_digest: string | null; target_current_digest: string | null }[];
  const links = linkRows.map((l) => ({
    ...l,
    stamp: edgeStampOf(l.verified, l.source_text_digest, l.source_current_digest,
                       l.target_text_digest, l.target_current_digest),
  }));
  const drew = links.filter((l) => l.dst === arxiv);   // what this paper drew from
  const fed = links.filter((l) => l.src === arxiv);    // what drew from this paper

  const stream = g.river?.streams.find((s) => s.papers.some((p) => p.arxiv === arxiv));
  const claims = (d.novelty ?? []).filter((c) => c && c.trim());
  const turning = cut[0]?.c != null && (d.displacement ?? 0) >= Number(cut[0].c);

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
          {l.stamp !== "verified" && (
            <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: ".62rem",
              color: STAMP_COLOR[l.stamp] }}>
              {STAMP_LABEL[l.stamp]}
            </span>
          )}
        </div>
        {/* Straight to this relationship's own row, where both papers' quotes
            are (issue #146). The anchor is the pair, which this row already
            holds, so no query learns it; lib/anchors.ts says why it is never the
            edge's database id. Where two edges share a pair this lands on the
            first of them, which is the one that keeps the unsuffixed anchor. */}
        <Link href={`/g/${id}/evidence#${edgeAnchor(l.src, l.dst)}`}
          style={{ display: "inline-block", marginTop: ".3rem", fontFamily: "var(--font-mono)",
            fontSize: ".62rem", color: "var(--ink-soft)", textDecoration: "none",
            borderBottom: "1px solid var(--line)" }}>
          the quotes behind this link →
        </Link>
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
              What it contributed · in the tool’s words, not the paper’s
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
              How it defines “{g.concept}”{d.section ? ` · §${d.section}` : ""}
            </div>
            <blockquote style={{ margin: 0, fontFamily: "var(--font-display)", fontStyle: "italic",
              fontSize: ".95rem", lineHeight: 1.55, borderLeft: `2px solid ${STAMP_COLOR[quoteStamp]}`,
              padding: ".55rem .85rem", background: "var(--card)", borderRadius: "0 6px 6px 0" }}>
              “{readableQuote(d.verbatim_quote).length > 500 ? readableQuote(d.verbatim_quote).slice(0, 500) + "…" : readableQuote(d.verbatim_quote)}”
            </blockquote>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", marginTop: ".35rem",
              color: STAMP_COLOR[quoteStamp], lineHeight: 1.5 }}>
              {/* This caption was left behind by #129 and swept by #135: it put
                  "verbatim" on the check rather than on the passage, said "the
                  source text" where the check runs against this system's own
                  copy, and carried no `shown as` tail while both its neighbours
                  did. */}
              {quoteStamp === "verified" && "✓ found word for word in the text this system pulled out of this paper · shown as verified"}
              {/* One phrase for this claim across the product (issue #129): the
                  check is named by what it does, not by its technique, and the
                  text it runs against says who pulled it out. lib/stamp.ts holds
                  the wording these two are copied from. */}
              {quoteStamp === "inferred" && "○ the check ran against the text this system pulled out of this paper and could not find it · shown as inferred"}
              {quoteStamp === "stale" && "◌ not checked against this paper’s text as it now stands · not shown as verified"}
            </div>
            {/* The stamp above says the quote matches our reading of the paper. It
                cannot say our reading matches the paper, and when we know that
                reading is damaged, saying so is the difference between a narrow
                guarantee and an overstated one. Reported only when something was
                found: a clean scan means no evidence of damage, which is not the
                same as evidence of none, so it makes no claim here. */}
            {quality && quality !== "clean" && (
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", marginTop: ".3rem",
                color: "var(--ink-soft)", lineHeight: 1.5 }}>
                ◐ our reading of this paper lost some of its text
                {quality === "damaged" ? " in more than one place" : ""}, so
                this passage may be missing symbols or wording the paper had. Worth
                checking against the source before quoting.
              </div>
            )}
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

        {/* "Among the corpus" and "across meanings" are the team's words (issue
            #120). The ticket's rewrite said "a different thread of meaning";
            "thread" already names a stream on the front door, and lending it to
            a meaning would suggest links only ever cross threads, which is not
            true. Same sentence, with the one word left as "meaning". */}
        {drew.length === 0 && fed.length === 0 && (
          <p style={{ fontSize: ".85rem", color: "var(--ink-soft)" }}>
            No typed links are recorded for this paper. A link exists only where one paper in
            this map cites another that carries a different meaning of the term, and none was
            found here.
          </p>
        )}

        <p style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem", color: "var(--ink-faint)",
          lineHeight: 1.8, marginTop: "2rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}>
          {/* Three machine terms and a metaphor in one sentence (issue #127),
              on the page where a reader has just read a dozen model-written link
              rationales and most needs to know which parts are checked. The two
              claims are unchanged: the check is still word for word against our
              own copy, and a reading still never carries the mark.
              "Our own copy of the paper's text" was a third phrasing of one
              promise, four lines below stamp captions that say it the settled
              way, and "copy" can be read as a copy of the PDF rather than of the
              text pulled out of it, which is the distinction the rule exists to
              hold (issue #135). */}
          Every quote on this page was checked word for word against the text this system
          pulled out of the paper. Anything labelled the tool’s reading is the tool’s
          judgement, and never carries the verified mark.
        </p>
      </div>
    </main>
  );
}

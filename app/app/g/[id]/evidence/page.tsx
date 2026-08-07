import Link from "next/link";
import { notFound } from "next/navigation";
import { deleteEdge, deleteGenealogy, reclassifyEdge } from "../../../../lib/actions";
import { getViewer, isOwner } from "../../../../lib/authz";
import { EDGE_MEANING, EDGE_TYPES, editActor, editOp, editWhen, getGenealogy, type Edge, type RankedPaper, type Genealogy, type UserEdit } from "../../../../lib/genealogy";
import { STAMP_COLOR, STAMP_LABEL } from "../../../../lib/stamp";

export const dynamic = "force-dynamic";

const EDGE_COLORS: Record<string, string> = {
  extends: "var(--edge-extends)",
  contests: "var(--edge-contests)",
  narrows: "var(--edge-narrows)",
  renames: "var(--edge-renames)",
  merges: "var(--edge-merges)",
  migrates: "var(--edge-migrates)",
};

export default async function EvidencePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const g = await getGenealogy(Number(id));
  if (!g) notFound();
  const canEdit = isOwner(await getViewer());

  // A relationship whose paper row is gone still appears here (issue #79), so
  // both of these take null. `titleOf` used to fall back to the arXiv id, which
  // is null in that case, and `PaperTag` then read `.length` off it: a 500 on
  // the whole page, and there is still no error.tsx. The fallback says what is
  // true instead of naming a paper we cannot describe (CLAUDE.md rule 4).
  const MISSING_PAPER = "this paper is no longer in our records";
  const yearOf = (p: string | null) =>
    g.nodes.flatMap((n) => n.members).find((m) => m.arxiv_id === p)?.year ?? 0;
  const titleOf = (p: string | null) =>
    g.nodes.flatMap((n) => n.members).find((m) => m.arxiv_id === p)?.title
    ?? p ?? MISSING_PAPER;
  const labelOf = (nid: string) => g.nodes.find((n) => n.node_id === nid)?.label ?? nid;
  const edges = [...g.edges].sort((a, b) => yearOf(a.source_paper) - yearOf(b.source_paper));
  // Three counts, disjoint, resolved at the same unit as the stamp on each row.
  // A header that folds stale into either of the other two is the same overclaim
  // at the level of the summary, and the summary is what most readers take away.
  const verified = edges.filter((e) => e.stamp === "verified").length;
  const stale = edges.filter((e) => e.stamp === "stale").length;
  const inferred = edges.length - verified - stale;

  return (
    <main style={{ maxWidth: 940, margin: "0 auto", padding: "1rem 1.5rem 5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <Link href={`/g/${g.id}`} style={{ fontSize: ".8rem", color: "var(--ink-soft)" }}>‹ the map</Link>
        {/* Issue #103: the report is part of the trust story this page tells,
            so its door belongs here, not in a footer. */}
        <Link href={`/g/${g.id}/report`} style={{ fontSize: ".8rem", color: "var(--ink-soft)" }}>
          what this map is made of ›
        </Link>
      </div>

      <header style={{ borderBottom: "2px solid var(--line)", padding: "1rem 0 1.1rem", marginBottom: "1.5rem" }}>
        {/* "Evidence & workbench" named a room half of it does not have (issue
            #118): the reclassify controls, the delete and the danger zone are
            all behind canEdit. The banner now says what this reader gets. */}
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".14em",
          textTransform: "uppercase", color: "var(--ink-soft)" }}>
          {canEdit ? "Evidence & workbench" : "Evidence"}
        </div>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.9rem", margin: ".4rem 0 0" }}>
          “{g.concept}” · the papers and their links
        </h1>
        {/* The third of four "papers" counts on one journey, now named (issue
            #123). This is the membership of the map's stored grouping, so it is
            neither the defining papers the home card counts nor the ranked pool
            the front-door badge counts: a paper leaves it when someone deletes
            the meaning holding it, and it never held a paper the grouping was
            written without. Measured on one constructed map, the four queries
            returned four different numbers from four different populations. */}
        <p style={{ color: "var(--ink-soft)", margin: ".5rem 0 0", lineHeight: 1.5 }}>
          {g.nodes.reduce((s, n) => s + n.members.length, 0)} papers grouped into meanings ·{" "}
          <strong>{edges.length} typed relationships</strong> (
          <span style={{ color: "var(--verified)" }}>{verified} verified</span>
          {inferred > 0 && (
            <span style={{ color: "var(--inferred)" }}>, {inferred} inferred</span>
          )}
          {stale > 0 && (
            <span style={{ color: "var(--ink-soft)" }}>, {stale} not re-checked</span>
          )}
          )
        </p>
        {/* "Raw ranked papers" is pipeline dialect and "the readable account is
            the map" is a riddle on first meeting (issue #120): it is the best
            thing this page has to say and it was saying it in a form that only
            makes sense once you already know. */}
        <p style={{ color: "var(--ink-soft)", margin: ".5rem 0 0", fontSize: ".82rem", fontStyle: "italic" }}>
          Every paper and every typed relationship, with the evidence behind each.
          For the readable account, go back to the map.
        </p>
      </header>

      <PaperSpine g={g} />

      {/* ── relationships ──────────────────────────────── */}
      <SectionTitle n="2">The {edges.length} relationships between them</SectionTitle>
      {/* #127 protects this paragraph's structure -- three symbols, one clause
          each, in order -- not its vocabulary, and the vocabulary was the last
          of #129's two rules to reach it (issue #135). "Verbatim" described the
          check rather than the passage, and "the source text" named the
          published paper when what was searched is this system's own copy.
          Also "so it is marked" to "so the relationship is marked": the "it" had
          drifted from the relationship to the quote between clauses. */}
      <p style={{ color: "var(--ink-soft)", fontSize: ".85rem", margin: "0 0 1rem" }}>
        Each row is a typed relationship between two papers. ● means both quotes were found word
        for word in the text this system pulled out of those papers; ○ means one of them could not
        be found, so the relationship is marked <em>inferred</em>; ◌ means the quotes have not been
        checked against those papers’ text as it now stands, so the relationship is
        marked <em>not re-checked</em>.
        Click a row to see the evidence
        {canEdit ? ", reclassify it, or remove it." : "."}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: ".6rem" }}>
        {edges.map((e) => (
          <EdgeRow key={e.id} e={e} genealogyId={g.id} canEdit={canEdit}
            srcLabel={labelOf(e.source_node)} dstLabel={labelOf(e.target_node)}
            srcYear={yearOf(e.source_paper)} dstYear={yearOf(e.target_paper)}
            srcTitle={titleOf(e.source_paper)} dstTitle={titleOf(e.target_paper)} />
        ))}
      </div>

      {g.user_edits.length > 0 && <AuditTrail edits={g.user_edits} />}

      {canEdit && <DangerZone genealogyId={g.id} concept={g.concept} />}
    </main>
  );
}

/** Owner-only, and deliberately unhurried: the action requires the concept
 *  name typed back and verifies it server-side (see deleteGenealogy). The
 *  gating here is cosmetic — requireOwner inside the action is the lock. */
function DangerZone({ genealogyId, concept }: { genealogyId: number; concept: string }) {
  return (
    <details style={{ marginTop: "2.5rem", paddingTop: "1.2rem", borderTop: "1px solid var(--line)" }}>
      <summary style={{ cursor: "pointer", fontSize: ".85rem", color: "var(--inferred)" }}>
        Danger zone: delete this map
      </summary>
      <div style={{ marginTop: ".8rem", border: "1px solid var(--inferred)", borderRadius: 8,
        background: "var(--card)", padding: "1rem 1.1rem" }}>
        <p style={{ fontSize: ".82rem", color: "var(--ink-soft)", margin: "0 0 .7rem", lineHeight: 1.5 }}>
          Permanently removes this map and its links. The papers and their extracted evidence are
          kept, so “{concept}” can be mapped again cheaply.
        </p>
        <form action={deleteGenealogy} style={{ display: "flex", gap: ".5rem", flexWrap: "wrap", alignItems: "center" }}>
          <input type="hidden" name="genealogyId" value={genealogyId} />
          <input
            name="confirm"
            placeholder={`Type “${concept}” to confirm`}
            autoComplete="off"
            style={inputStyle}
          />
          <button type="submit" style={{ ...btnStyle, color: "var(--inferred)", borderColor: "var(--inferred)" }}>
            Delete map
          </button>
        </form>
      </div>
    </details>
  );
}

/** The opening act: which papers shaped the term, and how. Two ranked lists
 *  because attention and displacement are orthogonal (proven on the data) —
 *  the papers everyone built on, and the ones that moved the meaning, which the
 *  first list structurally misses. Order is driven by the magnitude scores; the
 *  scores themselves are never shown (they are the editor, not the content). */
function PaperSpine({ g }: { g: Genealogy }) {
  const scored = g.papers.filter((p) => p.attention !== null);
  if (scored.length === 0) return null; // no magnitude yet (un-scored trace)

  const builtOn = scored.slice(0, 8); // already attention-desc from the query
  const shown = new Set(builtOn.map((p) => p.arxiv));
  const movers = scored
    .filter((p) => p.displacement !== null && (p.attention ?? 0) >= 1 && !shown.has(p.arxiv))
    .sort((a, b) => (b.displacement ?? 0) - (a.displacement ?? 0))
    .slice(0, 6);

  return (
    <section style={{ marginBottom: "2.5rem" }}>
      <SectionTitle n="1">Which papers shaped “{g.concept}”</SectionTitle>
      {/* The second sentence carried a genuinely interesting idea inside a
          subordinate clause hanging off a relative pronoun three commas from its
          subject (issue #127). Three sentences now, same claim, and the reason
          the two lists differ is stated rather than implied. */}
      <p style={{ color: "var(--ink-soft)", fontSize: ".85rem", margin: "0 0 1.2rem", lineHeight: 1.5 }}>
        Ranked by how often later work cites each paper <em>for this term</em>, not by how often
        it is cited overall. The first list is what the field built on. The second is where the
        meaning changed, and those papers are usually missing from the first list, because a
        paper that moves a term gets cited by the field it moved into, not by the one it left.
      </p>

      <GroupHeading label="Most built on" sub={`what later work leaned on for “${g.concept}”`} />
      <div style={{ display: "flex", flexDirection: "column", gap: ".5rem", marginBottom: "1.6rem" }}>
        {builtOn.map((p, i) => <PaperRow key={p.arxiv} p={p} rank={i + 1} />)}
      </div>

      {movers.length > 0 && (
        <>
          {/* "here" was doing quiet work: it meant "within this map's papers",
              which is the whole point of the list (issue #127). Same length. */}
          <GroupHeading label="Turning points" sub="moved the term’s meaning, even if few papers in this map cite them" />
          <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
            {movers.map((p) => <PaperRow key={p.arxiv} p={p} turning />)}
          </div>
        </>
      )}
    </section>
  );
}

function PaperRow({ p, rank, turning }: { p: RankedPaper; rank?: number; turning?: boolean }) {
  const did = (p.novelty ?? []).find((c) => c && c.trim());
  return (
    <div style={{ display: "flex", gap: ".9rem", background: "var(--card)", border: "1px solid var(--line)",
      borderRadius: 8, padding: ".75rem .95rem" }}>
      <div style={{ flex: "0 0 26px", textAlign: "center", fontFamily: "var(--font-mono)", paddingTop: ".1rem",
        color: "var(--ink-soft)", fontSize: rank ? "1rem" : "1.1rem" }}>
        {turning ? "★" : rank}
      </div>
      <div style={{ flex: 1 }}>
        <a href={`https://arxiv.org/abs/${p.arxiv}`} target="_blank" rel="noopener noreferrer"
          style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.02rem", color: "var(--ink)", textDecoration: "none" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>{p.year}</span>{" "}
          {p.title}
        </a>
        {did && (
          <p style={{ margin: ".3rem 0 0", fontSize: ".88rem", lineHeight: 1.5, color: "var(--ink-soft)" }}>{did}</p>
        )}
      </div>
    </div>
  );
}

function EdgeRow({ e, genealogyId, canEdit, srcLabel, dstLabel, srcYear, dstYear, srcTitle, dstTitle }: {
  e: Edge; genealogyId: number; canEdit: boolean; srcLabel: string; dstLabel: string;
  srcYear: number; dstYear: number; srcTitle: string; dstTitle: string;
}) {
  const color = EDGE_COLORS[e.edge_type] ?? "var(--ink-soft)";
  return (
    <details style={{ border: "1px solid var(--line)", borderLeft: `4px solid ${color}`,
      borderRadius: 8, background: "var(--card)", overflow: "hidden" }}>
      <summary style={{ listStyle: "none", cursor: "pointer", padding: ".85rem 1.1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: ".6rem", flexWrap: "wrap" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", textTransform: "uppercase",
            letterSpacing: ".07em", color: "#fff", background: color, padding: ".2rem .55rem", borderRadius: 4 }}>
            {e.edge_type}
          </span>
          <span style={{ fontSize: ".78rem", color: "var(--ink-soft)" }}>{EDGE_MEANING[e.edge_type]}</span>
          {/* The stamp and the judgement, labelled apart (issue #117). This read
              "● verified · 0.87": a mechanical result and the model's confidence
              in its own classification, in one font, one line and one separator
              dot, with the number carrying no label at all. A reader does one of
              two wrong things with that -- reads 0.87 as the strength of the
              verification, which makes the stamp look probabilistic when its
              entire value is that it is not, or reads "verified" as endorsing
              the link type, which the stamp never checks. The number now names
              what it is a confidence in, sits on its own line, and is set
              smaller and fainter than the stamp, because it claims less.
              #41 [Q4] is the separate question of how many digits it deserves. */}
          <span style={{ marginLeft: "auto", display: "inline-flex", flexDirection: "column",
            alignItems: "flex-end", gap: ".12rem" }}>
            <span style={{ fontSize: ".78rem", fontFamily: "var(--font-mono)",
              color: STAMP_COLOR[e.stamp] }}>
              {e.stamp === "verified" ? "● verified" : STAMP_LABEL[e.stamp]}
            </span>
            <span style={{ fontSize: ".66rem", fontFamily: "var(--font-mono)",
              color: "var(--ink-faint)" }}>
              the tool’s confidence in the link type: {e.confidence.toFixed(2)}
            </span>
          </span>
        </div>
        <div style={{ marginTop: ".55rem", display: "flex", alignItems: "center", gap: ".5rem", flexWrap: "wrap", fontSize: ".92rem" }}>
          <PaperTag year={srcYear} title={srcTitle} sub={srcLabel} />
          <span style={{ color, fontSize: "1.3rem", fontWeight: 700 }}>→</span>
          <PaperTag year={dstYear} title={dstTitle} sub={dstLabel} />
        </div>
      </summary>

      <div style={{ borderTop: "1px solid var(--line)", padding: "1rem 1.1rem", background: "var(--paper)" }}>
        <BasisCard color={color} rationale={e.rationale} citationContext={e.citation_context} />
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem", textTransform: "uppercase",
          letterSpacing: ".06em", color: "var(--ink-soft)", margin: ".1rem 0 .5rem" }}>
          How each paper defines the concept
        </div>
        <QuoteCard role="Earlier paper says" arxiv={e.source_paper} year={srcYear} quote={e.source_quote}
          novelty={e.source_novelty} section={e.source_section} />
        <div style={{ textAlign: "center", color, fontSize: "1.3rem", margin: ".2rem 0" }}>↓ {e.edge_type}</div>
        <QuoteCard role="Later paper says" arxiv={e.target_paper} year={dstYear} quote={e.target_quote}
          novelty={e.target_novelty} section={e.target_section} />
        {e.stamp === "inferred" && (
          <p style={{ fontSize: ".78rem", color: "var(--inferred)", margin: ".7rem 0 0" }}>
            {/* One phrase for this claim across the product (issue #129):
                "word for word", never "string-matched", and "the text this
                system pulled out of the paper", never "the extracted source
                text", which named a step this reader has never been told
                exists. The claim is unchanged. lib/stamp.ts holds the wording. */}
            ○ The check ran against the text this system pulled out of the papers and could not
            find one of these quotes, so this relationship is shown as{" "}
            <strong>inferred</strong>, never as verified.
          </p>
        )}
        {/* The third state (migration 015). Not "we looked and it was not
            there", which is what inferred says: either nobody has looked since
            the text moved, or the check that ran left no record of which bytes
            it read. The copy names both, because saying only the first would be
            a claim about the corpus the data does not support. Dotted and quiet
            like inferred, in no colour of its own, because it claims less than
            either of the other two. */}
        {e.stamp === "stale" && (
          <p style={{ fontSize: ".78rem", color: "var(--ink-soft)", margin: ".7rem 0 0" }}>
            ◌ These quotes have not been checked against the papers&rsquo; text as it
            now stands, either because that text has been replaced since they were checked or
            because the check left no record of what it read. So this relationship is shown as{" "}
            <strong>not re-checked</strong>, never as verified. The check is free and can be
            re-run; until it is, this says less than either verified or inferred, not more.
          </p>
        )}

        {canEdit && (
        <div style={{ display: "flex", gap: ".8rem", marginTop: "1rem", alignItems: "center", flexWrap: "wrap" }}>
          <form action={reclassifyEdge} style={{ display: "flex", gap: ".35rem", alignItems: "center" }}>
            <input type="hidden" name="genealogyId" value={genealogyId} />
            <input type="hidden" name="edgeId" value={e.id} />
            <label style={{ fontSize: ".76rem", color: "var(--ink-soft)" }}>reclassify as</label>
            <select name="edgeType" defaultValue={e.edge_type} style={inputStyle} aria-label="Edge type">
              {EDGE_TYPES.map((t) => <option key={t} value={t}>{t} ({EDGE_MEANING[t]})</option>)}
            </select>
            <button type="submit" style={btnStyle}>Save</button>
          </form>
          <form action={deleteEdge}>
            <input type="hidden" name="genealogyId" value={genealogyId} />
            <input type="hidden" name="edgeId" value={e.id} />
            <button type="submit" style={{ ...btnStyle, color: "var(--inferred)", borderColor: "var(--inferred)" }}>
              Delete relationship
            </button>
          </form>
        </div>
        )}
      </div>
    </details>
  );
}

/** Three ways an entry can name its actor, and no stamp on any of them. The
 *  green check means one thing in this product — a quote string-matched against
 *  our own extraction — and must not acquire a second by being lent to a
 *  signed-in login. The basis is the whole of the signal here. */
function AuditTrail({ edits }: { edits: UserEdit[] }) {
  return (
    <details style={{ marginTop: "2.5rem", paddingTop: "1.2rem", borderTop: "1px solid var(--line)" }}>
      <summary style={{ cursor: "pointer", fontSize: ".85rem", color: "var(--ink)" }}>
        Audit trail: {edits.length} change{edits.length === 1 ? "" : "s"} made by hand
      </summary>
      <ul style={{ margin: ".7rem 0 0", paddingLeft: "1.1rem", fontSize: ".78rem", color: "var(--ink-soft)" }}>
        {edits.map((e, i) => {
          const { name, basis } = editActor(e);
          return (
            <li key={i} style={{ marginBottom: ".3rem", fontFamily: "var(--font-mono)" }}>
              {editWhen(e)} · <strong>{editOp(e)}</strong>
              {name ? ` · by ${name} · ${basis}` : ` · ${basis}`} {JSON.stringify(e?.detail)}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

/** `year` is 0 when this map holds no record of the paper, which is what
 *  `yearOf` returns for a relationship whose paper row is missing (issue #79)
 *  and for one naming a paper outside the map's concept-states. Printed, it
 *  reads as the year 0, so it is omitted: an absent date shown as a date is the
 *  small end of inventing metadata. */
function PaperTag({ year, title, sub }: { year: number; title: string; sub: string }) {
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.2 }}>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}>
        {year > 0 && (
          <>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>{year}</span>{" "}
          </>
        )}
        {title.length > 46 ? title.slice(0, 46) + "…" : title}
      </span>
      <span style={{ fontSize: ".72rem", color: "var(--ink-soft)", fontStyle: "italic" }}>{sub}</span>
    </span>
  );
}

/** The edge's BASIS: what the later paper did to the concept and how. The
 *  rationale is the tool's one-sentence reading; the citation context is the
 *  verbatim sentence where the later paper cites the earlier (Semantic Scholar,
 *  not string-verified). Both are deliberately styled apart from the verified
 *  QuoteCards below so neither is ever mistaken for a grounded quote. */
function BasisCard({ color, rationale, citationContext }: {
  color: string; rationale: string | null; citationContext: string | null;
}) {
  if (!rationale && !citationContext) return null;
  return (
    <div style={{ border: `1px solid ${color}`, borderRadius: 6, background: "var(--card)",
      padding: ".85rem .95rem", marginBottom: ".9rem" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem", textTransform: "uppercase",
        letterSpacing: ".06em", color, marginBottom: ".4rem" }}>
        What the later paper did with the concept
      </div>
      {rationale && (
        <p style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: ".98rem",
          lineHeight: 1.55, color: "var(--ink)" }}>
          {rationale}
          <span style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--ink-soft)",
            marginLeft: ".45rem", whiteSpace: "nowrap" }}>— the tool’s reading</span>
        </p>
      )}
      {citationContext && (() => {
        const passages = citationContext.split("\n\n").map((s) => s.trim()).filter(Boolean);
        return (
          <div style={{ marginTop: rationale ? ".7rem" : 0, paddingTop: rationale ? ".7rem" : 0,
            borderTop: rationale ? "1px dashed var(--line)" : "none" }}>
            {/* The hardest label on the page (issue #127): it must say "these
                are real words from a real paper, and we still cannot vouch for
                them the way we vouch for the quotes below". "String-verified"
                was the machine's name for the vouching, so the sentence that
                withholds the claim was the one written in the machine's terms.
                Nothing is upgraded here and nothing is downgraded. */}
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--ink-soft)", marginBottom: ".35rem" }}>
              The later paper’s own words, from the sentence where it cites the earlier one.
              Supplied by Semantic Scholar, so we could not check it against our own copy of
              the paper.
            </div>
            {passages.slice(0, 3).map((p, i) => (
              <blockquote key={i} style={{ margin: i === 0 ? 0 : ".45rem 0 0", fontFamily: "var(--font-display)",
                fontStyle: "italic", fontSize: ".9rem", lineHeight: 1.5, color: "var(--ink)", whiteSpace: "pre-wrap" }}>
                “{p.length > 360 ? p.slice(0, 360) + "…" : p}”
              </blockquote>
            ))}
            {passages.length > 3 && (
              <div style={{ fontSize: ".72rem", color: "var(--ink-soft)", marginTop: ".3rem" }}>
                +{passages.length - 3} more citing passage(s)
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}

function QuoteCard({ role, arxiv, year, quote, novelty, section }: {
  role: string; arxiv: string | null; year: number; quote: string;
  novelty?: string[] | null; section?: string | null;
}) {
  const claims = (novelty ?? []).filter((c) => c && c.trim());
  // The quote is still real text this run copied out of a paper, so it is shown
  // with the stamp it earned. What is missing is the paper's record, and the
  // line that would name it says so rather than printing "arXiv:" with nothing
  // after it (issue #79).
  const provenance = arxiv
    ? `arXiv:${arxiv}${year > 0 ? ` (${year})` : ""}`
    : "the paper this quote came from is no longer in our records";
  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 6, padding: ".8rem .9rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: ".5rem",
        fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)", marginBottom: ".4rem" }}>
        <span>{role} · {provenance}</span>
        {section && <span style={{ fontStyle: "italic", opacity: 0.85 }}>from §{section.length > 28 ? section.slice(0, 28) + "…" : section}</span>}
      </div>
      <blockquote style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: ".95rem",
        lineHeight: 1.55, color: "var(--ink)", whiteSpace: "pre-wrap" }}>
        “{quote.length > 360 ? quote.slice(0, 360) + "…" : quote}”
      </blockquote>
      {claims.length > 0 && (
        <div style={{ marginTop: ".65rem", paddingTop: ".6rem", borderTop: "1px dashed var(--line)" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--ink-soft)",
            textTransform: "uppercase", letterSpacing: ".05em", marginBottom: ".3rem" }}>
            What it contributed · in the tool’s words, not the paper’s
          </div>
          <ul style={{ margin: 0, paddingLeft: "1.05rem", fontSize: ".84rem", lineHeight: 1.5, color: "var(--ink-soft)" }}>
            {claims.slice(0, 3).map((c, i) => <li key={i} style={{ marginBottom: ".2rem" }}>{c}</li>)}
          </ul>
          {claims.length > 3 && (
            <div style={{ fontSize: ".72rem", color: "var(--ink-soft)", marginTop: ".2rem" }}>+{claims.length - 3} more</div>
          )}
        </div>
      )}
    </div>
  );
}

function SectionTitle({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <h2 style={{ display: "flex", alignItems: "center", gap: ".6rem", fontSize: "1.05rem", color: "var(--ink)", margin: "0 0 1rem" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: ".8rem", background: "var(--ink)", color: "var(--paper)",
        width: 24, height: 24, borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
        {n}
      </span>
      {children}
    </h2>
  );
}

function GroupHeading({ label, sub }: { label: string; sub: string }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: ".6rem", margin: "0 0 .7rem",
      borderBottom: "1px solid var(--line)", paddingBottom: ".35rem" }}>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.02rem", color: "var(--ink)" }}>
        {label}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>{sub}</span>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  font: "inherit", fontSize: ".8rem", padding: ".3rem .45rem",
  border: "1px solid var(--line)", borderRadius: 4, background: "var(--paper)", color: "var(--ink)",
  minWidth: 180,
};
const btnStyle: React.CSSProperties = {
  font: "inherit", fontSize: ".78rem", padding: ".32rem .7rem", cursor: "pointer",
  border: "1px solid var(--ink-soft)", borderRadius: 4, background: "var(--card)", color: "var(--ink)",
};

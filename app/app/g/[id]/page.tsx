import Link from "next/link";
import { notFound } from "next/navigation";
import SignInButton from "../../signin-button";
import { deleteEdge, deleteGenealogy, deleteNode, mergeNode, reclassifyEdge, renameNode } from "../../../lib/actions";
import { getViewer, isOwner } from "../../../lib/authz";
import { computeFamilies, EDGE_MEANING, EDGE_TYPES, getGenealogy, type Edge, type Node } from "../../../lib/genealogy";

export const dynamic = "force-dynamic";

const EDGE_COLORS: Record<string, string> = {
  extends: "var(--edge-extends)",
  contests: "var(--edge-contests)",
  narrows: "var(--edge-narrows)",
  renames: "var(--edge-renames)",
  merges: "var(--edge-merges)",
  migrates: "var(--edge-migrates)",
};

export default async function GenealogyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const g = await getGenealogy(Number(id));
  if (!g) notFound();
  const canEdit = isOwner(await getViewer());

  const yearOf = (p: string) =>
    g.nodes.flatMap((n) => n.members).find((m) => m.arxiv_id === p)?.year ?? 0;
  const titleOf = (p: string) =>
    g.nodes.flatMap((n) => n.members).find((m) => m.arxiv_id === p)?.title ?? p;
  const labelOf = (nid: string) => g.nodes.find((n) => n.node_id === nid)?.label ?? nid;
  const edges = [...g.edges].sort((a, b) => yearOf(a.source_paper) - yearOf(b.source_paper));
  const verified = edges.filter((e) => e.verified).length;
  const degree = (nid: string) =>
    edges.filter((e) => e.source_node === nid || e.target_node === nid).length;

  // A polysemous term ("kernel", "attention" across fields) yields lineages that
  // share nothing but the word. Grouping them by citation-connected family, and
  // pulling truly isolated meanings out of the timeline, keeps the page from
  // implying one story where the corpus shows several.
  const { families, unconnected } = computeFamilies(g.nodes, edges);
  const split = families.length > 1;
  const grouped = split || (families.length === 1 && unconnected.length > 0);
  const colStyle = { display: "flex", flexDirection: "column", gap: ".8rem" } as const;

  return (
    <main style={{ maxWidth: 940, margin: "0 auto", padding: "2rem 1.5rem 5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Link href="/" style={{ fontSize: ".8rem", color: "var(--ink-soft)" }}>‹ all genealogies</Link>
        <SignInButton />
      </div>

      <header style={{ borderBottom: "2px solid var(--line)", padding: "1rem 0 1.1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2.1rem", margin: 0 }}>
          How “{g.concept}” evolved
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".5rem 0 0", lineHeight: 1.5 }}>
          {g.nodes.reduce((s, n) => s + n.members.length, 0)} papers ·{" "}
          <strong>{g.nodes.length} distinct meanings</strong> ·{" "}
          <strong>{edges.length} typed relationships</strong> (
          <span style={{ color: "var(--verified)" }}>{verified} verified</span>
          {edges.length - verified > 0 && (
            <span style={{ color: "var(--inferred)" }}>, {edges.length - verified} inferred</span>
          )}
          )
        </p>
        <p style={{ color: "var(--ink-soft)", margin: ".5rem 0 0", fontSize: ".82rem", fontStyle: "italic" }}>
          Drafted automatically from the papers’ own words, then curated by hand. Every curatorial
          change is recorded in the audit trail below.
          {g.user_edits.length > 0 && ` ${g.user_edits.length} change(s) so far.`}
        </p>
      </header>

      {/* ── concept-states ─────────────────────────────── */}
      {!grouped ? (
        <>
          <SectionTitle n="1">The {g.nodes.length} meanings, earliest to latest</SectionTitle>
          <div style={{ ...colStyle, marginBottom: "2.5rem" }}>
            {g.nodes.map((n, i) => (
              <NodeCard key={n.node_id} n={n} i={i} genealogyId={g.id} others={g.nodes}
                deg={degree(n.node_id)} canEdit={canEdit} />
            ))}
          </div>
        </>
      ) : (
        <>
          <SectionTitle n="1">
            The {g.nodes.length} meanings{split ? `, in ${families.length} unrelated families` : ""}
          </SectionTitle>
          {split && <SplitBanner concept={g.concept} n={families.length} />}
          <div style={{ display: "flex", flexDirection: "column", gap: "1.7rem", marginBottom: "2.5rem" }}>
            {families.map((fam, fi) => (
              <div key={fam[0].node_id}>
                {split && (
                  <GroupHeading label={`Family ${fi + 1}`}
                    sub={`${fam.length} meaning${fam.length > 1 ? "s" : ""} · ${familyYears(fam)}`} />
                )}
                <div style={colStyle}>
                  {fam.map((n, i) => (
                    <NodeCard key={n.node_id} n={n} i={i} genealogyId={g.id} others={g.nodes}
                      deg={degree(n.node_id)} canEdit={canEdit} />
                  ))}
                </div>
              </div>
            ))}
            {unconnected.length > 0 && (
              <div>
                <GroupHeading label="Unconnected meanings"
                  sub={`${unconnected.length} not linked by any citation`} />
                <p style={{ color: "var(--ink-soft)", fontSize: ".8rem", margin: "0 0 .7rem", lineHeight: 1.5 }}>
                  No citation in this corpus links these to a family. That can mean a genuinely
                  separate sense of the term, or simply a gap in what the corpus covers.
                </p>
                <div style={colStyle}>
                  {unconnected.map((n, i) => (
                    <NodeCard key={n.node_id} n={n} i={i} genealogyId={g.id} others={g.nodes}
                      deg={degree(n.node_id)} canEdit={canEdit} />
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── relationships ──────────────────────────────── */}
      <SectionTitle n="2">The {edges.length} relationships between them</SectionTitle>
      <p style={{ color: "var(--ink-soft)", fontSize: ".85rem", margin: "0 0 1rem" }}>
        Each row is a typed relationship between two papers. ● means both quotes were verified
        verbatim against the source text; ○ means one could not be matched, so the relationship is
        marked <em>inferred</em>. Click a row to see the evidence
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
        Danger zone: delete this genealogy
      </summary>
      <div style={{ marginTop: ".8rem", border: "1px solid var(--inferred)", borderRadius: 8,
        background: "var(--card)", padding: "1rem 1.1rem" }}>
        <p style={{ fontSize: ".82rem", color: "var(--ink-soft)", margin: "0 0 .7rem", lineHeight: 1.5 }}>
          Permanently removes this map and its relationships. Source papers and extracted evidence
          are kept, and “{concept}” becomes available to trace again.
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
            Delete genealogy
          </button>
        </form>
      </div>
    </details>
  );
}

function NodeCard({ n, i, genealogyId, others, deg, canEdit }:
  { n: Node; i: number; genealogyId: number; others: Node[]; deg: number; canEdit: boolean }) {
  const span = n.year_start === n.year_end ? `${n.year_start}` : `${n.year_start}–${n.year_end}`;
  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8, padding: "0.9rem 1.1rem" }}>
      <div style={{ display: "flex", gap: "1rem" }}>
        <div style={{ flex: "0 0 62px", textAlign: "center", fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
          <div style={{ fontSize: "1.15rem", color: "var(--ink)", fontWeight: 600 }}>#{i + 1}</div>
          <div style={{ fontSize: ".72rem" }}>{span}</div>
        </div>
        <div style={{ flex: 1, borderLeft: "1px solid var(--line)", paddingLeft: "1rem" }}>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.15rem", color: "var(--ink)" }}>
            {n.label}
            {deg === 0 && (
              <span style={{ marginLeft: ".5rem", fontFamily: "var(--font-mono)", fontSize: ".65rem",
                color: "var(--ink-soft)", border: "1px solid var(--line)", borderRadius: 4, padding: ".1rem .35rem" }}>
                no relationships
              </span>
            )}
          </div>
          <ul style={{ margin: ".45rem 0 0", padding: 0, listStyle: "none" }}>
            {n.members.map((m) => (
              <li key={m.arxiv_id} style={{ fontSize: ".84rem", color: "var(--ink-soft)", lineHeight: 1.45 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem" }}>{m.year}</span> · {m.title}
              </li>
            ))}
          </ul>

          {canEdit && (
          <details style={{ marginTop: ".6rem" }}>
            <summary style={{ cursor: "pointer", fontSize: ".76rem", color: "var(--ink-soft)" }}>Edit this meaning</summary>
            <div style={{ display: "flex", flexWrap: "wrap", gap: ".8rem", marginTop: ".6rem", alignItems: "flex-end" }}>
              <form action={renameNode} style={{ display: "flex", gap: ".35rem", alignItems: "center" }}>
                <input type="hidden" name="genealogyId" value={genealogyId} />
                <input type="hidden" name="nodeId" value={n.node_id} />
                <input name="label" defaultValue={n.label} aria-label="New label" style={inputStyle} />
                <button type="submit" style={btnStyle}>Rename</button>
              </form>

              {others.length > 1 && (
                <form action={mergeNode} style={{ display: "flex", gap: ".35rem", alignItems: "center" }}>
                  <input type="hidden" name="genealogyId" value={genealogyId} />
                  <input type="hidden" name="nodeId" value={n.node_id} />
                  <label style={{ fontSize: ".76rem", color: "var(--ink-soft)" }}>merge into</label>
                  <select name="intoId" style={inputStyle} aria-label="Merge into">
                    {others.filter((o) => o.node_id !== n.node_id).map((o) => (
                      <option key={o.node_id} value={o.node_id}>{o.label}</option>
                    ))}
                  </select>
                  <button type="submit" style={btnStyle}>Merge</button>
                </form>
              )}

              <form action={deleteNode}>
                <input type="hidden" name="genealogyId" value={genealogyId} />
                <input type="hidden" name="nodeId" value={n.node_id} />
                <button type="submit" style={{ ...btnStyle, color: "var(--inferred)", borderColor: "var(--inferred)" }}>
                  Delete meaning
                </button>
              </form>
            </div>
            <p style={{ fontSize: ".7rem", color: "var(--ink-soft)", margin: ".5rem 0 0" }}>
              Merging discards any relationship that becomes internal to the merged meaning: a
              link between two papers of the <em>same</em> meaning is no longer a transition.
              Deleting a meaning removes its relationships as well.
            </p>
          </details>
          )}
        </div>
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
          <span style={{ marginLeft: "auto", fontSize: ".78rem", fontFamily: "var(--font-mono)",
            color: e.verified ? "var(--verified)" : "var(--inferred)" }}>
            {e.verified ? "● verified" : "○ inferred"} · {e.confidence.toFixed(2)}
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
        <QuoteCard role="Earlier paper says" arxiv={e.source_paper} year={srcYear} quote={e.source_quote} />
        <div style={{ textAlign: "center", color, fontSize: "1.3rem", margin: ".2rem 0" }}>↓ {e.edge_type}</div>
        <QuoteCard role="Later paper says" arxiv={e.target_paper} year={dstYear} quote={e.target_quote} />
        {!e.verified && (
          <p style={{ fontSize: ".78rem", color: "var(--inferred)", margin: ".7rem 0 0" }}>
            ○ One of these quotes could not be string-matched against the extracted source text, so
            this relationship is shown as <strong>inferred</strong>, never as verified.
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

function AuditTrail({ edits }: { edits: { op: string; detail: unknown; at: string; by?: string }[] }) {
  return (
    <details style={{ marginTop: "2.5rem", paddingTop: "1.2rem", borderTop: "1px solid var(--line)" }}>
      <summary style={{ cursor: "pointer", fontSize: ".85rem", color: "var(--ink)" }}>
        Audit trail: {edits.length} curatorial change(s)
      </summary>
      <ul style={{ margin: ".7rem 0 0", paddingLeft: "1.1rem", fontSize: ".78rem", color: "var(--ink-soft)" }}>
        {edits.map((e, i) => (
          <li key={i} style={{ marginBottom: ".3rem", fontFamily: "var(--font-mono)" }}>
            {new Date(e.at).toLocaleString()} · <strong>{e.op}</strong>
            {e.by ? ` by ${e.by}` : " (cli)"} {JSON.stringify(e.detail)}
          </li>
        ))}
      </ul>
    </details>
  );
}

function PaperTag({ year, title, sub }: { year: number; title: string; sub: string }) {
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.2 }}>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--ink-soft)" }}>{year}</span>{" "}
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
      {citationContext && (
        <div style={{ marginTop: rationale ? ".7rem" : 0, paddingTop: rationale ? ".7rem" : 0,
          borderTop: rationale ? "1px dashed var(--line)" : "none" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--ink-soft)", marginBottom: ".3rem" }}>
            Verbatim · where the later paper cites the earlier · per Semantic Scholar, not string-verified
          </div>
          <blockquote style={{ margin: 0, fontFamily: "var(--font-display)", fontStyle: "italic",
            fontSize: ".9rem", lineHeight: 1.5, color: "var(--ink)", whiteSpace: "pre-wrap" }}>
            “{citationContext.length > 480 ? citationContext.slice(0, 480) + "…" : citationContext}”
          </blockquote>
        </div>
      )}
    </div>
  );
}

function QuoteCard({ role, arxiv, year, quote }: { role: string; arxiv: string; year: number; quote: string }) {
  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 6, padding: ".8rem .9rem" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)", marginBottom: ".4rem" }}>
        {role} · arXiv:{arxiv} ({year})
      </div>
      <blockquote style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: ".95rem",
        lineHeight: 1.55, color: "var(--ink)", whiteSpace: "pre-wrap" }}>
        “{quote.length > 360 ? quote.slice(0, 360) + "…" : quote}”
      </blockquote>
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

/** Year span of a family (nodes arrive year-sorted; end is the latest end). */
function familyYears(fam: Node[]): string {
  const start = Math.min(...fam.map((n) => n.year_start));
  const end = Math.max(...fam.map((n) => n.year_end));
  return start === end ? `${start}` : `${start}–${end}`;
}

/** Shown only when a term splits into 2+ citation-disconnected families:
 *  turns silent polysemy into a disclosed finding, the same move the product
 *  makes with verified vs inferred. */
function SplitBanner({ concept, n }: { concept: string; n: number }) {
  return (
    <div style={{ border: "1px solid var(--inferred)", borderRadius: 8, background: "var(--card)",
      padding: ".8rem 1rem", margin: "0 0 1.3rem" }}>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1rem", color: "var(--ink)" }}>
        “{concept}” carries {n} unrelated meanings here
      </div>
      <p style={{ margin: ".35rem 0 0", fontSize: ".82rem", color: "var(--ink-soft)", lineHeight: 1.5 }}>
        The families below share the word but no citation links them. That usually signals distinct
        senses (the way “kernel” means one thing in operating systems and another in machine
        learning) rather than one evolving idea.
      </p>
    </div>
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

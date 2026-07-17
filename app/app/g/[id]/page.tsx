import Link from "next/link";
import { notFound } from "next/navigation";
import SignInButton from "../../signin-button";
import { deleteEdge, deleteNode, mergeNode, reclassifyEdge, renameNode } from "../../../lib/actions";
import { getViewer, isOwner } from "../../../lib/authz";
import { EDGE_MEANING, EDGE_TYPES, getGenealogy, type Edge, type Node } from "../../../lib/genealogy";

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
          A workbench, not the last word — this map is a draft you curate. Every edit is saved to the
          database and recorded below.
          {g.user_edits.length > 0 && ` ${g.user_edits.length} edit(s) applied so far.`}
        </p>
      </header>

      {/* ── concept-states ─────────────────────────────── */}
      <SectionTitle n="1">The {g.nodes.length} meanings, earliest to latest</SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: ".8rem", marginBottom: "2.5rem" }}>
        {g.nodes.map((n, i) => (
          <NodeCard key={n.node_id} n={n} i={i} genealogyId={g.id} others={g.nodes}
            deg={degree(n.node_id)} canEdit={canEdit} />
        ))}
      </div>

      {/* ── relationships ──────────────────────────────── */}
      <SectionTitle n="2">The {edges.length} relationships between them</SectionTitle>
      <p style={{ color: "var(--ink-soft)", fontSize: ".85rem", margin: "0 0 1rem" }}>
        Each row is a typed link between two papers. ● = both quotes verified against the source
        text; ○ = one couldn’t be matched, so it’s shown as <em>inferred</em>. Click a row for the
        evidence and to reclassify or delete it.
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
    </main>
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
            <summary style={{ cursor: "pointer", fontSize: ".76rem", color: "var(--ink-soft)" }}>edit this meaning</summary>
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
              Merging drops any relationship that becomes internal to the merged meaning — a link
              between two papers of the <em>same</em> state is not a transition. Deleting removes its
              relationships too.
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
              {EDGE_TYPES.map((t) => <option key={t} value={t}>{t} — {EDGE_MEANING[t]}</option>)}
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
        Audit trail — {edits.length} manual edit(s)
      </summary>
      <ul style={{ margin: ".7rem 0 0", paddingLeft: "1.1rem", fontSize: ".78rem", color: "var(--ink-soft)" }}>
        {edits.map((e, i) => (
          <li key={i} style={{ marginBottom: ".3rem", fontFamily: "var(--font-mono)" }}>
            {new Date(e.at).toLocaleString()} — <strong>{e.op}</strong>
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

function QuoteCard({ role, arxiv, year, quote }: { role: string; arxiv: string; year: number; quote: string }) {
  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 6, padding: ".8rem .9rem" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)", marginBottom: ".4rem" }}>
        {role} — arXiv:{arxiv} ({year})
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

const inputStyle: React.CSSProperties = {
  font: "inherit", fontSize: ".8rem", padding: ".3rem .45rem",
  border: "1px solid var(--line)", borderRadius: 4, background: "var(--paper)", color: "var(--ink)",
  minWidth: 180,
};
const btnStyle: React.CSSProperties = {
  font: "inherit", fontSize: ".78rem", padding: ".32rem .7rem", cursor: "pointer",
  border: "1px solid var(--ink-soft)", borderRadius: 4, background: "var(--card)", color: "var(--ink)",
};

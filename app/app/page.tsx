"use client";

import { useState } from "react";
import genealogy from "./genealogy-attention.json";

type Member = { arxiv_id: string; year: number; title: string };
type Node = {
  node_id: string;
  label: string;
  year_start: number;
  year_end: number;
  members: Member[];
};
type Edge = {
  source_node: string;
  target_node: string;
  edge_type: string;
  confidence: number;
  verified: boolean;
  source_paper: string;
  target_paper: string;
  source_quote: string;
  target_quote: string;
};

const EDGE_COLORS: Record<string, string> = {
  extends: "var(--edge-extends)",
  contests: "var(--edge-contests)",
  narrows: "var(--edge-narrows)",
  renames: "var(--edge-renames)",
  migrates: "var(--edge-migrates)",
  merges: "var(--edge-merges)",
};

const ROW_H = 168;
const TOP_PAD = 24;
const GUTTER = 150;
const RAIL_X = 44;

export default function Home() {
  const nodes = (genealogy.nodes as Node[])
    .slice()
    .sort((a, b) => a.year_start - b.year_start);
  const edges = genealogy.edges as Edge[];
  const rowOf = new Map(nodes.map((n, i) => [n.node_id, i]));
  const yCenter = (id: string) => TOP_PAD + (rowOf.get(id)! + 0.5) * ROW_H;
  const height = TOP_PAD * 2 + nodes.length * ROW_H;

  const [selected, setSelected] = useState<number | null>(null);
  const nodeById = new Map(nodes.map((n) => [n.node_id, n]));

  // offset multiple edges between the same pair so their curves don't overlap
  const pairSeen = new Map<string, number>();
  const edgeGeom = edges.map((e) => {
    const key = [e.source_node, e.target_node].sort().join("-");
    const k = pairSeen.get(key) ?? 0;
    pairSeen.set(key, k + 1);
    return { bulge: 60 + k * 34 };
  });

  return (
    <main style={{ maxWidth: 1180, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
      <header style={{ borderBottom: "1px solid var(--line)", paddingBottom: "1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2rem", margin: 0 }}>
          Lineage — the genealogy of <em>“{genealogy.concept}”</em>
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".4rem 0 0", fontSize: ".95rem" }}>
          {genealogy.stats.nodes} concept-states · {genealogy.stats.edges} relationships ·{" "}
          <span style={{ color: "var(--verified)" }}>{genealogy.stats.verified_edges} verified</span> ·{" "}
          <span style={{ color: "var(--inferred)" }}>{genealogy.stats.inferred_edges} inferred</span>
        </p>
        <p style={{ color: "var(--ink-soft)", margin: ".5rem 0 0", fontSize: ".8rem", fontStyle: "italic" }}>
          A workbench, not the last word — clustering and edges are a draft to curate, not “the” history.
        </p>
      </header>

      <Legend />

      <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start" }}>
        {/* timeline */}
        <div style={{ position: "relative", flex: "1 1 auto", minWidth: 0 }}>
          <svg
            width="100%"
            height={height}
            style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none", overflow: "visible" }}
          >
            <defs>
              {Object.entries(EDGE_COLORS).map(([t, c]) => (
                <marker key={t} id={`arrow-${t}`} viewBox="0 0 10 10" refX="8" refY="5"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill={c} />
                </marker>
              ))}
            </defs>
            {edges.map((e, i) => {
              const y1 = yCenter(e.source_node);
              const y2 = yCenter(e.target_node);
              const b = edgeGeom[i].bulge;
              const cx = GUTTER - b;
              const active = selected === i;
              const color = EDGE_COLORS[e.edge_type] ?? "var(--ink-soft)";
              return (
                <path
                  key={i}
                  d={`M ${GUTTER} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${GUTTER} ${y2}`}
                  fill="none"
                  stroke={color}
                  strokeWidth={active ? 3.5 : 2}
                  strokeDasharray={e.verified ? undefined : "5 5"}
                  markerEnd={`url(#arrow-${e.edge_type})`}
                  opacity={selected === null || active ? 1 : 0.22}
                  style={{ pointerEvents: "stroke", cursor: "pointer" }}
                  onClick={() => setSelected(i)}
                />
              );
            })}
          </svg>

          {/* year rail + node cards */}
          <div style={{ position: "relative" }}>
            {nodes.map((n) => (
              <div key={n.node_id} style={{ height: ROW_H, position: "relative", display: "flex", alignItems: "center" }}>
                <div style={{
                  position: "absolute", left: 0, width: RAIL_X, textAlign: "right",
                  fontFamily: "var(--font-mono)", fontSize: ".75rem", color: "var(--ink-soft)",
                }}>
                  {n.year_start}{n.year_end !== n.year_start ? `–${String(n.year_end).slice(2)}` : ""}
                </div>
                <div style={{ marginLeft: GUTTER + 8, flex: 1 }}>
                  <NodeCard node={n} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* evidence / detail panel */}
        <aside style={{ flex: "0 0 380px", position: "sticky", top: "1rem" }}>
          {selected === null ? (
            <div style={{ ...panelBox, color: "var(--ink-soft)" }}>
              <p style={{ margin: 0 }}>
                Click a <strong>relationship line</strong> in the timeline to see the verbatim
                evidence from both papers, and whether it was string-verified against the source text.
              </p>
              <ul style={{ margin: "1rem 0 0", paddingLeft: "1.1rem", fontSize: ".85rem" }}>
                {edges.map((e, i) => (
                  <li key={i} style={{ marginBottom: ".35rem" }}>
                    <button onClick={() => setSelected(i)} style={linkBtn}>
                      <span style={{ color: EDGE_COLORS[e.edge_type], fontWeight: 600 }}>
                        {e.edge_type}
                      </span>{" "}
                      {nodeById.get(e.source_node)?.year_start} → {nodeById.get(e.target_node)?.year_start}
                      {!e.verified && <span style={{ color: "var(--inferred)" }}> ◌</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <EvidencePanel edge={edges[selected]} nodeById={nodeById} onClose={() => setSelected(null)} />
          )}
        </aside>
      </div>
    </main>
  );
}

function NodeCard({ node }: { node: Node }) {
  return (
    <div style={{
      background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8,
      padding: ".8rem 1rem", boxShadow: "0 1px 2px rgba(28,43,51,.04)",
    }}>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.05rem", color: "var(--ink)" }}>
        {node.label}
      </div>
      <div style={{ marginTop: ".4rem", display: "flex", flexDirection: "column", gap: ".2rem" }}>
        {node.members.map((m) => (
          <div key={m.arxiv_id} style={{ fontSize: ".8rem", color: "var(--ink-soft)", lineHeight: 1.35 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem" }}>{m.year}</span>{" "}
            {m.title.length > 62 ? m.title.slice(0, 62) + "…" : m.title}
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidencePanel({
  edge, nodeById, onClose,
}: { edge: Edge; nodeById: Map<string, Node>; onClose: () => void }) {
  const src = nodeById.get(edge.source_node)!;
  const dst = nodeById.get(edge.target_node)!;
  const color = EDGE_COLORS[edge.edge_type];
  return (
    <div style={panelBox}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: ".7rem", textTransform: "uppercase",
          letterSpacing: ".08em", color: "#fff", background: color, padding: ".2rem .5rem", borderRadius: 4,
        }}>
          {edge.edge_type}
        </span>
        <button onClick={onClose} style={{ ...linkBtn, color: "var(--ink-soft)" }}>close ✕</button>
      </div>

      <div style={{ margin: ".7rem 0", fontSize: ".85rem", color: "var(--ink)" }}>
        <strong>{src.label}</strong> <span style={{ color }}>→</span> <strong>{dst.label}</strong>
      </div>

      <div style={{
        display: "inline-flex", alignItems: "center", gap: ".4rem", fontSize: ".8rem",
        fontFamily: "var(--font-mono)",
        color: edge.verified ? "var(--verified)" : "var(--inferred)",
      }}>
        {edge.verified ? "✓ verified" : "◌ inferred"} · confidence {edge.confidence.toFixed(2)}
      </div>

      <QuoteCard label={`${edge.source_paper}`} quote={edge.source_quote} />
      <div style={{ textAlign: "center", color, fontSize: "1.2rem" }}>↓</div>
      <QuoteCard label={`${edge.target_paper}`} quote={edge.target_quote} />

      {!edge.verified && (
        <p style={{ fontSize: ".75rem", color: "var(--inferred)", marginTop: ".6rem", marginBottom: 0 }}>
          One quote could not be string-matched against the extracted source text, so this edge is
          shown as inferred, never as verified.
        </p>
      )}
    </div>
  );
}

function QuoteCard({ label, quote }: { label: string; quote: string }) {
  return (
    <div style={{
      background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 6,
      padding: ".7rem .8rem", marginTop: ".6rem",
    }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-soft)", marginBottom: ".35rem" }}>
        arXiv:{label}
      </div>
      <blockquote style={{
        margin: 0, fontFamily: "var(--font-display)", fontSize: ".9rem", lineHeight: 1.5,
        color: "var(--ink)", whiteSpace: "pre-wrap",
      }}>
        “{quote.length > 320 ? quote.slice(0, 320) + "…" : quote}”
      </blockquote>
    </div>
  );
}

function Legend() {
  const items = [
    ["extends", "extends"], ["contests", "contests"], ["narrows", "narrows"],
    ["renames", "renames"], ["merges", "merges"], ["migrates", "migrates"],
  ];
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem", alignItems: "center", marginBottom: "1.25rem", fontSize: ".78rem" }}>
      {items.map(([t, l]) => (
        <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: ".35rem", color: "var(--ink-soft)" }}>
          <span style={{ width: 22, height: 0, borderTop: `3px solid ${EDGE_COLORS[t]}` }} /> {l}
        </span>
      ))}
      <span style={{ marginLeft: "auto", display: "inline-flex", gap: "1rem", color: "var(--ink-soft)" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: ".35rem" }}>
          <span style={{ width: 22, borderTop: "3px solid var(--ink-soft)" }} /> verified
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: ".35rem" }}>
          <span style={{ width: 22, borderTop: "3px dashed var(--ink-soft)" }} /> inferred
        </span>
      </span>
    </div>
  );
}

const panelBox: React.CSSProperties = {
  background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8,
  padding: "1rem 1.1rem", fontSize: ".9rem", lineHeight: 1.5,
};
const linkBtn: React.CSSProperties = {
  background: "none", border: "none", padding: 0, cursor: "pointer",
  font: "inherit", color: "var(--ink)", textAlign: "left",
};

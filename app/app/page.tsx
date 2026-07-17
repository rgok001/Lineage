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
  merges: "var(--edge-merges)",
  migrates: "var(--edge-migrates)",
};
const EDGE_MEANING: Record<string, string> = {
  extends: "builds on / generalises",
  contests: "disputes",
  narrows: "restricts to a special case",
  renames: "same idea, new name",
  merges: "fuses two ideas",
  migrates: "carries into a new field",
};

export default function Home() {
  const nodes = (genealogy.nodes as Node[]).slice().sort((a, b) => a.year_start - b.year_start);
  const edges = (genealogy.edges as Edge[]).slice();
  const nodeById = new Map(nodes.map((n) => [n.node_id, n]));
  const yearOf = (p: string) => {
    for (const n of nodes) for (const m of n.members) if (m.arxiv_id === p) return m.year;
    return 0;
  };
  const titleOf = (p: string) => {
    for (const n of nodes) for (const m of n.members) if (m.arxiv_id === p) return m.title;
    return p;
  };
  edges.sort((a, b) => yearOf(a.source_paper) - yearOf(b.source_paper) || yearOf(a.target_paper) - yearOf(b.target_paper));

  return (
    <main style={{ maxWidth: 940, margin: "0 auto", padding: "2rem 1.5rem 5rem" }}>
      <header style={{ borderBottom: "2px solid var(--line)", paddingBottom: "1.1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2.1rem", margin: 0, color: "var(--ink)" }}>
          How “{genealogy.concept}” evolved
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".5rem 0 0", fontSize: "1rem", lineHeight: 1.5 }}>
          Tracing one idea across {nodes.reduce((s, n) => s + n.members.length, 0)} papers.
          The word splits into <strong>{genealogy.stats.nodes} distinct meanings</strong> over time
          (below), linked by <strong>{genealogy.stats.edges} typed relationships</strong> — each backed
          by a verbatim quote from both papers.
        </p>
        <p style={{ color: "var(--ink-soft)", margin: ".5rem 0 0", fontSize: ".82rem", fontStyle: "italic" }}>
          A workbench, not the last word — this is an automatically-built draft to curate, not “the” history.
        </p>
      </header>

      {/* ── SECTION 1: the concept-states ───────────────────────── */}
      <SectionTitle n="1">The {nodes.length} meanings, earliest to latest</SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: ".8rem", marginBottom: "2.5rem" }}>
        {nodes.map((n, i) => (
          <div key={n.node_id} style={{
            display: "flex", gap: "1rem", background: "var(--card)",
            border: "1px solid var(--line)", borderRadius: 8, padding: "0.9rem 1.1rem",
          }}>
            <div style={{
              flex: "0 0 62px", textAlign: "center",
              fontFamily: "var(--font-mono)", color: "var(--ink-soft)",
            }}>
              <div style={{ fontSize: "1.15rem", color: "var(--ink)", fontWeight: 600 }}>#{i + 1}</div>
              <div style={{ fontSize: ".72rem" }}>
                {n.year_start}{n.year_end !== n.year_start ? `–${n.year_end}` : ""}
              </div>
            </div>
            <div style={{ flex: 1, borderLeft: "1px solid var(--line)", paddingLeft: "1rem" }}>
              <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.15rem", color: "var(--ink)" }}>
                {n.label}
              </div>
              <ul style={{ margin: ".45rem 0 0", padding: 0, listStyle: "none" }}>
                {n.members.map((m) => (
                  <li key={m.arxiv_id} style={{ fontSize: ".84rem", color: "var(--ink-soft)", lineHeight: 1.45 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem" }}>{m.year}</span>{" · "}
                    {m.title}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>

      {/* ── SECTION 2: the relationships ────────────────────────── */}
      <SectionTitle n="2">The {edges.length} relationships between them</SectionTitle>
      <p style={{ color: "var(--ink-soft)", fontSize: ".85rem", margin: "0 0 1rem" }}>
        Each row is a typed link between two papers. Solid dot = quotes verified against the source
        text; hollow dot = one quote couldn’t be matched, so it’s shown as <em>inferred</em>.
        Click any row to read the evidence.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: ".6rem" }}>
        {edges.map((e, i) => {
          const color = EDGE_COLORS[e.edge_type];
          const src = nodeById.get(e.source_node)!;
          const dst = nodeById.get(e.target_node)!;
          return (
            <details key={i} style={{
              border: "1px solid var(--line)", borderLeft: `4px solid ${color}`,
              borderRadius: 8, background: "var(--card)", overflow: "hidden",
            }}>
              <summary style={{ listStyle: "none", cursor: "pointer", padding: ".85rem 1.1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: ".6rem", flexWrap: "wrap" }}>
                  <span style={{
                    fontFamily: "var(--font-mono)", fontSize: ".68rem", textTransform: "uppercase",
                    letterSpacing: ".07em", color: "#fff", background: color, padding: ".2rem .55rem",
                    borderRadius: 4, whiteSpace: "nowrap",
                  }}>{e.edge_type}</span>
                  <span style={{ fontSize: ".78rem", color: "var(--ink-soft)" }}>{EDGE_MEANING[e.edge_type]}</span>
                  <span style={{ marginLeft: "auto", fontSize: ".78rem", fontFamily: "var(--font-mono)",
                    color: e.verified ? "var(--verified)" : "var(--inferred)", whiteSpace: "nowrap" }}>
                    {e.verified ? "● verified" : "○ inferred"} · {e.confidence.toFixed(2)}
                  </span>
                </div>
                <div style={{ marginTop: ".55rem", display: "flex", alignItems: "center", gap: ".5rem",
                  fontSize: ".92rem", color: "var(--ink)", flexWrap: "wrap" }}>
                  <PaperTag year={yearOf(e.source_paper)} title={titleOf(e.source_paper)} sub={src.label} />
                  <span style={{ color, fontSize: "1.3rem", fontWeight: 700 }}>→</span>
                  <PaperTag year={yearOf(e.target_paper)} title={titleOf(e.target_paper)} sub={dst.label} />
                </div>
              </summary>

              <div style={{ borderTop: "1px solid var(--line)", padding: "1rem 1.1rem", background: "var(--paper)" }}>
                <QuoteCard role="Earlier paper says" arxiv={e.source_paper} year={yearOf(e.source_paper)} quote={e.source_quote} />
                <div style={{ textAlign: "center", color, fontSize: "1.3rem", margin: ".2rem 0" }}>↓ {e.edge_type}</div>
                <QuoteCard role="Later paper says" arxiv={e.target_paper} year={yearOf(e.target_paper)} quote={e.target_quote} />
                {!e.verified && (
                  <p style={{ fontSize: ".78rem", color: "var(--inferred)", margin: ".7rem 0 0" }}>
                    ○ One of these quotes could not be string-matched against the extracted source text,
                    so this relationship is shown as <strong>inferred</strong>, never as verified.
                  </p>
                )}
              </div>
            </details>
          );
        })}
      </div>

      <Legend />
    </main>
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
    <h2 style={{ display: "flex", alignItems: "center", gap: ".6rem", fontFamily: "var(--font-ui)",
      fontSize: "1.05rem", color: "var(--ink)", margin: "0 0 1rem" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: ".8rem", background: "var(--ink)", color: "var(--paper)",
        width: 24, height: 24, borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
        {n}
      </span>
      {children}
    </h2>
  );
}

function Legend() {
  const items = Object.keys(EDGE_COLORS);
  return (
    <div style={{ marginTop: "2.5rem", paddingTop: "1.2rem", borderTop: "1px solid var(--line)",
      display: "flex", flexWrap: "wrap", gap: ".9rem", fontSize: ".76rem", color: "var(--ink-soft)" }}>
      <strong style={{ color: "var(--ink)" }}>Edge types:</strong>
      {items.map((t) => (
        <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: ".3rem" }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: EDGE_COLORS[t] }} />
          {t} <span style={{ opacity: 0.7 }}>({EDGE_MEANING[t]})</span>
        </span>
      ))}
    </div>
  );
}

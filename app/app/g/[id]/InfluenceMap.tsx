"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { InfluenceMapData, MapPaper } from "../../../lib/genealogy";

/** The influence map: every dot a paper, size = how much later work built on it
 *  for this term, a ring = it moved the term's meaning. Papers ride in visible
 *  current channels; typed lineage appears only on hover so the default view
 *  stays a constellation, never a hairball. Click a paper → its dossier; click
 *  a channel name → that current's account. Scores select and size, and are
 *  never shown as numbers. */
export default function InfluenceMap({ id, data }: { id: number; data: InfluenceMapData }) {
  const router = useRouter();
  const [hot, setHot] = useState<string | null>(null);
  const [sel, setSel] = useState<MapPaper | null>(null);

  const EC: Record<string, string> = {
    extends: "var(--edge-extends)", migrates: "var(--edge-migrates)",
    narrows: "var(--edge-narrows)", renames: "var(--edge-renames)",
    contests: "var(--edge-contests)", merges: "var(--edge-merges)",
  };
  const EDGE_KINDS = Object.keys(EC);

  const { bands, placed, yr0, yr1 } = useMemo(() => {
    const byStream = new Map<string, MapPaper[]>();
    for (const p of data.papers) {
      if (!byStream.has(p.stream_id)) byStream.set(p.stream_id, []);
      byStream.get(p.stream_id)!.push(p);
    }
    const bands = [...byStream.entries()]
      .map(([sid, ps]) => ({
        sid, name: ps[0].stream_name, color: ps[0].color,
        minY: Math.min(...ps.map((p) => p.year)), maxY: Math.max(...ps.map((p) => p.year)),
      }))
      .sort((a, b) => a.minY - b.minY || b.maxY - a.maxY);
    const years = data.papers.map((p) => p.year);
    const yr0 = Math.min(...years) - 0.6, yr1 = Math.max(...years) + 0.8;
    // spread same (stream, year) papers vertically so they never overlap
    const groups = new Map<string, MapPaper[]>();
    for (const p of data.papers) {
      const k = `${p.stream_id}|${p.year}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(p);
    }
    const placed = new Map<string, { p: MapPaper; dy: number }>();
    for (const g of groups.values())
      g.forEach((p, i) => placed.set(p.arxiv, { p, dy: (i - (g.length - 1) / 2) * 24 }));
    return { bands, placed, yr0, yr1 };
  }, [data]);

  const W = 1320, m = { t: 22, r: 30, b: 34, l: 250 };
  const bandH = 78, H = m.t + bands.length * bandH + m.b;
  const x = (y: number) => m.l + ((y - yr0) / (yr1 - yr0)) * (W - m.l - m.r);
  const bandIdx = new Map(bands.map((b, i) => [b.sid, i]));
  const py = (arxiv: string) => {
    const pl = placed.get(arxiv)!;
    return m.t + (bandIdx.get(pl.p.stream_id) ?? 0) * bandH + bandH / 2 + pl.dy;
  };
  const rad = (p: MapPaper) => 5 + Math.sqrt(Math.max(p.attention, 0)) * 2.8;

  // Hover previews; clicking pins. Without the pin, moving the mouse off a dot
  // toward the panel cleared it, so its button could never be reached.
  const focusId = hot ?? sel?.arxiv ?? null;

  const conn = useMemo(() => {
    const s = new Set<string>();
    if (focusId) {
      s.add(focusId);
      for (const e of data.edges) {
        if (e.from === focusId) s.add(e.to);
        if (e.to === focusId) s.add(e.from);
      }
    }
    return s;
  }, [focusId, data.edges]);

  const shown = (hot ? data.papers.find((p) => p.arxiv === hot) ?? null : null) ?? sel;

  /* The focused paper's lineage. Curves stop short of the target dot so the
     arrowhead reads clearly. Type labels slide along their own curve to the
     first position that does not collide with an already-placed one; parallel
     curves would otherwise stack every label at the same midpoint. */
  const lineage = (() => {
    if (!focusId) return [] as {
      key: string; d: string; col: string; type: string; verified: boolean;
      lx: number | null; ly: number;
    }[];
    const boxes: { x: number; y: number; w: number }[] = [];
    const out = [];
    for (const [k, e] of data.edges.entries()) {
      if (e.from !== focusId && e.to !== focusId) continue;
      const a = placed.get(e.from), b = placed.get(e.to);
      if (!a || !b) continue;
      const x1 = x(a.p.year), y1 = py(e.from), x2 = x(b.p.year), y2 = py(e.to);
      const dx = (x2 - x1) * 0.42;
      const r2 = rad(b.p) + 7;
      const len = Math.hypot(x2 - x1, y2 - y1) || 1;
      const ex = x2 - ((x2 - x1) / len) * r2, ey = y2 - ((y2 - y1) / len) * r2;
      const c1x = x1 + dx, c1y = y1, c2x = ex - dx, c2y = ey;
      const at = (t: number) => {
        const u = 1 - t;
        return {
          x: u * u * u * x1 + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t * t * t * ex,
          y: u * u * u * y1 + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t * t * t * ey,
        };
      };
      // Every curve names itself. The curves converge on the focused paper and
      // fan out towards the other end, so labels are placed near that far end
      // where there is room, walking further out until clear of the labels
      // already placed.
      const w = e.type.length * 6.4 + 8;
      const outgoing = e.from === focusId;
      const candidates = outgoing ? [0.74, 0.64, 0.84, 0.54, 0.92] : [0.26, 0.36, 0.16, 0.46, 0.08];
      let lx: number | null = null, ly = 0;
      for (const t of candidates) {
        const pt = at(t);
        const clash = boxes.some((bx) => Math.abs(bx.y - pt.y) < 15 && Math.abs(bx.x - pt.x) < (bx.w + w) / 2);
        if (!clash) {
          lx = pt.x; ly = pt.y - 5;
          boxes.push({ x: pt.x, y: pt.y, w });
          break;
        }
      }
      out.push({
        key: `${k}`, d: `M${x1},${y1} C${c1x},${c1y} ${c2x},${c2y} ${ex},${ey}`,
        col: EC[e.type] ?? "var(--ink-faint)", type: e.type, verified: e.verified, lx, ly,
      });
    }
    return out;
  })();
  const ticks: number[] = [];
  for (let y = Math.ceil(yr0); y <= yr1; y++) ticks.push(y);

  // Collision-aware labels: within a band, labels alternate above/below their
  // dot and a label that would overlap an already-placed one on both sides is
  // dropped (the paper still names itself in the reading panel on hover).
  const labels: { arxiv: string; x: number; y: number; text: string }[] = [];
  {
    const byBand = new Map<string, MapPaper[]>();
    for (const p of data.papers)
      if (p.attention >= 4.5) {
        if (!byBand.has(p.stream_id)) byBand.set(p.stream_id, []);
        byBand.get(p.stream_id)!.push(p);
      }
    for (const ps of byBand.values()) {
      ps.sort((a, b) => a.year - b.year || py(a.arxiv) - py(b.arxiv));
      let endAbove = -1e9, endBelow = -1e9;
      for (const p of ps) {
        const r = rad(p), cx = x(p.year), cyv = py(p.arxiv);
        const base = p.title.split(":")[0];
        const text = base.length > 24 ? base.slice(0, 23) + "…" : base;
        const wpx = text.length * 6.6 + 10;
        const x0 = cx + r + 5;
        const prefAbove = (placed.get(p.arxiv)?.dy ?? 0) <= 0;
        let side: "a" | "b" | null = null;
        if (prefAbove && x0 >= endAbove) side = "a";
        else if (!prefAbove && x0 >= endBelow) side = "b";
        else if (x0 >= endAbove) side = "a";
        else if (x0 >= endBelow) side = "b";
        if (!side) continue;
        if (side === "a") endAbove = x0 + wpx; else endBelow = x0 + wpx;
        labels.push({ arxiv: p.arxiv, x: x0, y: side === "a" ? cyv - r - 7 : cyv + r + 15, text });
      }
    }
  }

  return (
    <div style={{ display: "flex", gap: "0.9rem", alignItems: "flex-start", flexWrap: "wrap" }}>
      <div style={{ flex: "1 1 620px", minWidth: 0, overflowX: "auto", border: "1px solid var(--line)",
        borderRadius: 12, background: "var(--card)" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%", minWidth: 820 }}
          role="img" aria-label={`Influence map of ${data.papers.length} pivotal ${data.concept} papers.`}>
          {ticks.map((y) => (
            <g key={y}>
              <line x1={x(y)} y1={m.t} x2={x(y)} y2={H - m.b + 4} stroke="var(--line-soft)" strokeWidth={1} />
              {y % 2 === 0 && (
                <text x={x(y)} y={H - m.b + 18} textAnchor="middle" fill="var(--ink-faint)"
                  fontSize={12} fontFamily="var(--font-mono)">{y}</text>
              )}
            </g>
          ))}

          {bands.map((b, i) => {
            const yTop = m.t + i * bandH + 5, hh = bandH - 10;
            return (
              <g key={b.sid}>
                <rect x={x(b.minY) - 18} y={yTop} width={Math.max(x(b.maxY) - x(b.minY) + 36, 44)}
                  height={hh} rx={hh / 2} fill={b.color} opacity={0.14} />
                <text x={m.l - 16} y={m.t + i * bandH + bandH / 2 + 3} textAnchor="end" fill={b.color}
                  fontSize={12} fontFamily="var(--font-mono)" opacity={0.95} style={{ cursor: "pointer" }}
                  onClick={() => router.push(`/g/${id}/river/${b.sid}`)}>
                  {b.name.length > 30 ? b.name.slice(0, 29) + "…" : b.name} ›
                </text>
              </g>
            );
          })}

          <defs>
            {EDGE_KINDS.map((t) => (
              <marker key={t} id={`ah-${t}`} viewBox="0 0 10 10" refX={9} refY={5}
                markerWidth={5} markerHeight={5} orient="auto-start-reverse">
                <path d="M0,1 L10,5 L0,9 z" fill={EC[t]} />
              </marker>
            ))}
          </defs>

          {lineage.map((l) => (
            <g key={l.key} style={{ pointerEvents: "none" }}>
              <path d={l.d} fill="none" stroke={l.col} strokeWidth={l.verified ? 1.7 : 1.3}
                strokeDasharray={l.verified ? undefined : "3 3"}
                markerEnd={`url(#ah-${l.type})`} opacity={0.92} />
              {l.lx !== null && (
                <text x={l.lx} y={l.ly} textAnchor="middle" fill={l.col} fontSize={10.5}
                  fontFamily="var(--font-mono)"
                  style={{ paintOrder: "stroke", stroke: "var(--card)", strokeWidth: 4 }}>
                  {l.type}
                </text>
              )}
            </g>
          ))}

          {data.papers.map((p) => {
            const r = rad(p), cx = x(p.year), cyv = py(p.arxiv);
            const dim = focusId && !conn.has(p.arxiv);
            const pinned = sel?.arxiv === p.arxiv;
            return (
              <g key={p.arxiv} style={{ cursor: "pointer", transition: "opacity .15s", opacity: dim ? 0.16 : 1 }}
                onMouseEnter={() => setHot(p.arxiv)} onMouseLeave={() => setHot(null)}
                onClick={() => setSel(p)}>
                {pinned && (
                  <circle cx={cx} cy={cyv} r={r + 7} fill="none" stroke={p.color} strokeWidth={1.2} opacity={0.55} />
                )}
                {p.displacement >= 0.25 && (
                  <circle cx={cx} cy={cyv} r={r + 3.5} fill="none" stroke="var(--ink)" strokeWidth={1.3} opacity={0.7} />
                )}
                <circle cx={cx} cy={cyv} r={r} fill={p.color} stroke="var(--paper)" strokeWidth={1} opacity={0.95} />
              </g>
            );
          })}

          {labels.map((l) => (
            <text key={l.arxiv} x={l.x} y={l.y} fill="var(--ink)" fontSize={12.5}
              fontFamily="var(--font-ui)" pointerEvents="none"
              opacity={hot && !conn.has(l.arxiv) ? 0.16 : 1}
              style={{ paintOrder: "stroke", stroke: "var(--card)", strokeWidth: 4, transition: "opacity .15s" }}>
              {l.text}
            </text>
          ))}
        </svg>
      </div>

      <aside style={{ flex: "0 1 268px", minWidth: 220, background: "var(--card)",
        border: "1px solid var(--line)", borderRadius: 10, padding: "1rem 1.1rem",
        position: "sticky", top: "1rem", alignSelf: "flex-start" }}>
        {shown ? (
          <>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", letterSpacing: ".12em",
              textTransform: "uppercase", color: "var(--ink-faint)" }}>
              {shown.displacement >= 0.25 ? "A turning point" : "Paper"}
            </div>
            <h3 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.1rem",
              lineHeight: 1.3, margin: ".4rem 0 .3rem" }}>{shown.title}</h3>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-soft)" }}>
              {shown.year} · <span style={{ color: shown.color }}>{shown.stream_name}</span>
            </div>
            <p style={{ fontSize: ".92rem", lineHeight: 1.6, color: "var(--ink-soft)", margin: ".8rem 0 0" }}>
              {shown.contrib ?? "Open the dossier for what this paper did and its evidence."}
            </p>
            {(() => {
              const drew = data.edges.filter((e) => e.to === shown.arxiv);
              const fed = data.edges.filter((e) => e.from === shown.arxiv);
              const tally = (es: typeof drew) => {
                const m = new Map<string, number>();
                for (const e of es) m.set(e.type, (m.get(e.type) ?? 0) + 1);
                return [...m.entries()];
              };
              const Row = ({ label, es }: { label: string; es: typeof drew }) =>
                es.length === 0 ? null : (
                  <div style={{ marginTop: ".5rem" }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", letterSpacing: ".1em",
                      textTransform: "uppercase", color: "var(--ink-faint)" }}>{label}</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: ".25rem .7rem", marginTop: ".2rem",
                      fontFamily: "var(--font-mono)", fontSize: ".72rem" }}>
                      {tally(es).map(([t, n]) => (
                        <span key={t} style={{ color: EC[t] ?? "var(--ink-soft)" }}>{n} {t}</span>
                      ))}
                    </div>
                  </div>
                );
              return (
                <div style={{ marginTop: ".9rem", paddingTop: ".7rem", borderTop: "1px solid var(--line)" }}>
                  <Row label="Drew from" es={drew} />
                  <Row label="Fed into" es={fed} />
                </div>
              );
            })()}
            <button onClick={() => router.push(`/g/${id}/p/${encodeURIComponent(shown.arxiv)}`)}
              style={{ font: "inherit", fontSize: ".85rem", cursor: "pointer", marginTop: "1rem",
                background: "#1d3b31", color: "#bfe6d4", border: "1px solid #2f5f4d",
                borderRadius: 8, padding: ".5rem .95rem", width: "100%" }}>
              Read the dossier →
            </button>
            {sel && (
              <button onClick={() => setSel(null)}
                style={{ font: "inherit", fontSize: ".74rem", cursor: "pointer", marginTop: ".45rem",
                  background: "none", color: "var(--ink-faint)", border: "none", padding: 0 }}>
                clear selection
              </button>
            )}
          </>
        ) : (
          <>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", letterSpacing: ".12em",
              textTransform: "uppercase", color: "var(--ink-faint)" }}>Hover a paper</div>
            <p style={{ fontSize: ".88rem", lineHeight: 1.6, color: "var(--ink-soft)", margin: ".55rem 0 0" }}>
              Its lineage lights up on the map and its contribution appears here. Click a paper to keep
              it open, then read the dossier for the evidence.
            </p>
            <ul style={{ margin: "1rem 0 0", padding: 0, listStyle: "none", display: "flex",
              flexDirection: "column", gap: ".45rem", fontSize: ".8rem", color: "var(--ink-soft)" }}>
              <li style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
                <span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--ink-faint)", flex: "none" }} />
                size = how much the field built on it
              </li>
              <li style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
                <span style={{ width: 14, height: 14, borderRadius: "50%", border: "2px solid var(--ink)", flex: "none" }} />
                ring = it moved the meaning
              </li>
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}

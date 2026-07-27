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

  const W = 1100, m = { t: 22, r: 26, b: 34, l: 190 };
  const bandH = 78, H = m.t + bands.length * bandH + m.b;
  const x = (y: number) => m.l + ((y - yr0) / (yr1 - yr0)) * (W - m.l - m.r);
  const bandIdx = new Map(bands.map((b, i) => [b.sid, i]));
  const py = (arxiv: string) => {
    const pl = placed.get(arxiv)!;
    return m.t + (bandIdx.get(pl.p.stream_id) ?? 0) * bandH + bandH / 2 + pl.dy;
  };
  const rad = (p: MapPaper) => 5 + Math.sqrt(Math.max(p.attention, 0)) * 2.8;

  const conn = useMemo(() => {
    const s = new Set<string>();
    if (hot) {
      s.add(hot);
      for (const e of data.edges) {
        if (e.from === hot) s.add(e.to);
        if (e.to === hot) s.add(e.from);
      }
    }
    return s;
  }, [hot, data.edges]);

  const shown = sel ?? (hot ? data.papers.find((p) => p.arxiv === hot) ?? null : null);
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
    <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div style={{ width: "100%", overflowX: "auto", border: "1px solid var(--line)",
        borderRadius: 12, background: "var(--card)" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%", minWidth: 900 }}
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
                <text x={m.l - 12} y={m.t + i * bandH + bandH / 2 + 3} textAnchor="end" fill={b.color}
                  fontSize={12} fontFamily="var(--font-mono)" opacity={0.95} style={{ cursor: "pointer" }}
                  onClick={() => router.push(`/g/${id}/river/${b.sid}`)}>
                  {b.name.length > 26 ? b.name.slice(0, 25) + "…" : b.name} ›
                </text>
              </g>
            );
          })}

          {data.edges.map((e, k) => {
            const a = placed.get(e.from), b = placed.get(e.to);
            if (!a || !b) return null;
            const x1 = x(a.p.year), y1 = py(e.from), x2 = x(b.p.year), y2 = py(e.to);
            const dx = (x2 - x1) * 0.42;
            const on = hot && (e.from === hot || e.to === hot);
            return (
              <path key={k} d={`M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`}
                fill="none" stroke={EC[e.type] ?? "var(--ink-faint)"} strokeWidth={e.verified ? 1.6 : 1.2}
                strokeDasharray={e.verified ? undefined : "3 3"}
                opacity={on ? 0.9 : 0} style={{ transition: "opacity .15s" }} />
            );
          })}

          {data.papers.map((p) => {
            const r = rad(p), cx = x(p.year), cyv = py(p.arxiv);
            const dim = hot && !conn.has(p.arxiv);
            return (
              <g key={p.arxiv} style={{ cursor: "pointer", transition: "opacity .15s", opacity: dim ? 0.16 : 1 }}
                onMouseEnter={() => setHot(p.arxiv)} onMouseLeave={() => setHot(null)}
                onClick={() => router.push(`/g/${id}/p/${encodeURIComponent(p.arxiv)}`)}>
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

      <aside style={{ width: "100%", background: "var(--card)", border: "1px solid var(--line)",
        borderRadius: 10, padding: ".85rem 1.1rem", minHeight: 88 }}>
        {shown ? (
          <div style={{ display: "flex", gap: "1.2rem", alignItems: "flex-start", flexWrap: "wrap" }}>
            <div style={{ flex: "0 1 340px" }}>
              <h3 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.08rem",
                lineHeight: 1.3, margin: 0 }}>{shown.title}</h3>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-soft)", marginTop: ".25rem" }}>
                {shown.year} · <span style={{ color: shown.color }}>{shown.stream_name}</span>
                {shown.displacement >= 0.25 && " · a turning point"}
              </div>
            </div>
            <div style={{ flex: "1 1 300px", fontSize: ".92rem", lineHeight: 1.55, color: "var(--ink-soft)" }}>
              {shown.contrib ?? "Open the dossier for what this paper did and its evidence."}
            </div>
            <button onClick={() => router.push(`/g/${id}/p/${encodeURIComponent(shown.arxiv)}`)}
              style={{ font: "inherit", fontSize: ".85rem", cursor: "pointer", alignSelf: "center",
                background: "#1d3b31", color: "#bfe6d4", border: "1px solid #2f5f4d",
                borderRadius: 8, padding: ".5rem .95rem", whiteSpace: "nowrap" }}>
              Read the dossier →
            </button>
          </div>
        ) : (
          <div style={{ fontSize: ".92rem", lineHeight: 1.6, color: "var(--ink-soft)" }}>
            Bigger means more of the field built on it for this term. A ring marks a paper that moved
            the meaning. Hover a paper to trace its lineage; click it to read what it did, with the
            evidence. Click a current’s name to read that current as an account.
          </div>
        )}
      </aside>
    </div>
  );
}

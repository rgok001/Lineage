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
      g.forEach((p, i) => placed.set(p.arxiv, { p, dy: (i - (g.length - 1) / 2) * 19 }));
    return { bands, placed, yr0, yr1 };
  }, [data]);

  const W = 1000, m = { t: 20, r: 24, b: 30, l: 158 };
  const bandH = 62, H = m.t + bands.length * bandH + m.b;
  const x = (y: number) => m.l + ((y - yr0) / (yr1 - yr0)) * (W - m.l - m.r);
  const bandIdx = new Map(bands.map((b, i) => [b.sid, i]));
  const py = (arxiv: string) => {
    const pl = placed.get(arxiv)!;
    return m.t + (bandIdx.get(pl.p.stream_id) ?? 0) * bandH + bandH / 2 + pl.dy;
  };
  const rad = (p: MapPaper) => 4 + Math.sqrt(Math.max(p.attention, 0)) * 2.5;

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

  return (
    <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-start" }}>
      <div style={{ flex: "1 1 620px", minWidth: 0, overflowX: "auto", border: "1px solid var(--line)",
        borderRadius: 12, background: "var(--card)" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%", minWidth: 760 }}
          role="img" aria-label={`Influence map of ${data.papers.length} pivotal ${data.concept} papers.`}>
          {ticks.map((y) => (
            <g key={y}>
              <line x1={x(y)} y1={m.t} x2={x(y)} y2={H - m.b + 4} stroke="var(--line-soft)" strokeWidth={1} />
              {y % 2 === 0 && (
                <text x={x(y)} y={H - m.b + 18} textAnchor="middle" fill="var(--ink-faint)"
                  fontSize={10} fontFamily="var(--font-mono)">{y}</text>
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
                  fontSize={10} fontFamily="var(--font-mono)" opacity={0.95} style={{ cursor: "pointer" }}
                  onClick={() => router.push(`/g/${id}/river/${b.sid}`)}>
                  {b.name.length > 24 ? b.name.slice(0, 23) + "…" : b.name} ›
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
                {p.attention >= 4.5 && (
                  <text x={cx + r + 4} y={cyv + 3.5} fill="var(--ink-soft)" fontSize={10}
                    fontFamily="var(--font-ui)" style={{ paintOrder: "stroke", stroke: "var(--card)", strokeWidth: 3 }}>
                    {p.title.length > 26 ? p.title.slice(0, 25) + "…" : p.title.split(":")[0]}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <aside style={{ flex: "0 1 250px", minWidth: 220, background: "var(--card)", border: "1px solid var(--line)",
        borderRadius: 10, padding: ".9rem 1rem", position: "sticky", top: "1rem" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", letterSpacing: ".14em",
          textTransform: "uppercase", color: "var(--ink-faint)" }}>Reading panel</div>
        {shown ? (
          <>
            <h3 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.02rem",
              lineHeight: 1.3, margin: ".35rem 0 .1rem" }}>{shown.title}</h3>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem", color: "var(--ink-soft)", marginBottom: ".55rem" }}>
              {shown.year} · <span style={{ color: shown.color }}>{shown.stream_name}</span>
              {shown.displacement >= 0.25 && " · a turning point"}
            </div>
            <div style={{ fontSize: ".84rem", lineHeight: 1.5, color: "var(--ink-soft)" }}>
              {shown.contrib ?? "Open the dossier for what this paper did and its evidence."}
            </div>
            <button onClick={() => router.push(`/g/${id}/p/${encodeURIComponent(shown.arxiv)}`)}
              style={{ marginTop: ".7rem", font: "inherit", fontSize: ".78rem", cursor: "pointer",
                background: "#1d3b31", color: "#bfe6d4", border: "1px solid #2f5f4d",
                borderRadius: 8, padding: ".45rem .8rem" }}>
              Read the dossier →
            </button>
          </>
        ) : (
          <div style={{ fontSize: ".84rem", lineHeight: 1.55, color: "var(--ink-soft)", marginTop: ".4rem" }}>
            Bigger means more of the field built on it for this term. A ring marks a paper that moved
            the meaning. Hover a paper to trace its lineage; click it to read what it did, with the
            evidence. Click a current’s name to read that current as an account.
          </div>
        )}
      </aside>
    </div>
  );
}

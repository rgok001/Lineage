"use client";
import Link from "next/link";
import { useState } from "react";
import type { River } from "../../../../lib/genealogy";

/** Braided-timeline of the conceptual currents. Order is chronological by origin;
 *  band width encodes how many papers a current holds; dashed arcs are the
 *  cross-currents where one fed another. Hover focuses a current and its crosses;
 *  clicking a band dives into that current's grounded account. */
export default function RiverChart({ id, river }: { id: number; river: River }) {
  const [hot, setHot] = useState<string | null>(null);
  const streams = [...river.streams].sort(
    (a, b) => (a.origin_year ?? 9999) - (b.origin_year ?? 9999)
  );
  const idx = new Map(streams.map((s, i) => [s.id, i]));
  const years = streams.flatMap((s) => [s.origin_year ?? 2013, ...s.papers.map((p) => p.year)]);
  const Y0 = Math.min(...years), Y1 = Math.max(...years) + 0.5;
  const L = 224, R = 884, top = 58, laneH = 60;
  const H = top + streams.length * laneH + 42;
  const x = (y: number) => L + ((y - Y0) / (Y1 - Y0)) * (R - L);
  const cy = (i: number) => top + i * laneH + laneH / 2;
  const endYear = (s: (typeof streams)[number]) =>
    Math.max(s.origin_year ?? Y0, ...s.papers.map((p) => p.year));

  const ticks: number[] = [];
  for (let y = Math.ceil(Y0); y <= Y1 - 0.5; y++) ticks.push(y);

  return (
    <div style={{ width: "100%", overflowX: "auto", border: "1px solid var(--line)",
      borderRadius: 12, background: "var(--card)" }}>
      <svg viewBox={`0 0 900 ${H}`} style={{ display: "block", width: "100%", minWidth: 760 }}
        role="img" aria-label={`Braided-river timeline of ${streams.length} embedding currents.`}>
        {ticks.map((y) => (
          <g key={y}>
            <line x1={x(y)} y1={top - 12} x2={x(y)} y2={top + streams.length * laneH - 10}
              stroke="var(--line)" strokeWidth={1} opacity={0.5} />
            {y % 2 === 1 && (
              <text x={x(y)} y={top + streams.length * laneH + 6} fill="var(--ink-soft)"
                fontSize={11} textAnchor="middle" fontFamily="var(--font-mono)">{y}</text>
            )}
          </g>
        ))}

        {river.cross_currents.map((cc, k) => {
          const fi = idx.get(cc.from), ti = idx.get(cc.to);
          if (fi === undefined || ti === undefined || cc.year == null) return null;
          const x0 = x(cc.year), y0 = cy(fi), y1 = cy(ti);
          const on = hot === cc.from || hot === cc.to;
          const d = `M${x0},${y0} C${x0 + 42},${y0} ${x0 + 26},${y1} ${x0 + 54},${y1}`;
          return (
            <path key={k} d={d} fill="none" stroke="var(--ink-soft)" strokeWidth={1.6}
              strokeDasharray="3 3" opacity={hot ? (on ? 0.95 : 0.06) : 0.5} />
          );
        })}

        {streams.map((s, i) => {
          const h = 14 + Math.min(s.papers.length, 26) * 1.15;
          const y = cy(i) - h / 2, xa = x(s.origin_year ?? Y0), xb = x(endYear(s));
          const dim = hot && hot !== s.id ? 0.26 : 1;
          return (
            <Link key={s.id} href={`/g/${id}/river/${s.id}`}>
              <g style={{ cursor: "pointer", transition: "opacity .18s", opacity: dim }}
                onMouseEnter={() => setHot(s.id)} onMouseLeave={() => setHot(null)}>
                <rect x={xa} y={y} width={Math.max(xb - xa, 34)} height={h} rx={h / 2}
                  fill={s.color} opacity={0.82} />
                <circle cx={xa} cy={cy(i)} r={4.5} fill={s.color} />
                <text x={L - 14} y={cy(i) + 3} fill="var(--ink)" fontSize={12.5} textAnchor="end"
                  fontFamily="var(--font-sans)">{s.name}</text>
                <text x={L - 14} y={cy(i) + 17} fill="var(--ink-soft)" fontSize={10} textAnchor="end"
                  fontFamily="var(--font-mono)">{s.papers.length} papers</text>
              </g>
            </Link>
          );
        })}
      </svg>
    </div>
  );
}

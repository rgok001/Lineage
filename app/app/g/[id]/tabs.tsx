"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

/** The four places inside one map (issue #143).
 *
 *  Same pattern as `app/nav.tsx`, one step smaller: this is the section strip
 *  under the site's own tabs, and it is distinguished from them by size and
 *  position rather than by spending an edge colour on navigation chrome.
 *
 *  "Threads" is an anchor to the map's thread list, not a menu of thread names.
 *  A menu would need the map row, which means a read in the layout above the
 *  loading boundary — see the comment in `layout.tsx` for why that is refused.
 *
 *  On `/g/{id}/p/{arxiv}` no tab is current. A dossier is a place, not a
 *  section, and lighting "The map" would be a small lie about where the reader
 *  is. Do not invent an active state for it.
 */
export default function MapTabs({ id }: { id: string }) {
  const path = usePathname() ?? "";
  const base = `/g/${id}`;
  const tabs: { href: string; label: string; on: boolean }[] = [
    { href: base, label: "The map", on: path === base },
    { href: `${base}#threads`, label: "Threads", on: path.startsWith(`${base}/river`) },
    { href: `${base}/evidence`, label: "The evidence", on: path.startsWith(`${base}/evidence`) },
    { href: `${base}/report`, label: "What this map is made of", on: path.startsWith(`${base}/report`) },
  ];

  return (
    // maxWidth and side padding match the site header, not the page below: the
    // page column varies by route (1400 on the map, 940 on the evidence page,
    // 42rem on a thread) and a strip that moved sideways between tabs would
    // read as a different strip.
    <div style={{ maxWidth: 1400, margin: "0 auto", padding: "0 1.5rem" }}>
      <nav aria-label="This map" style={{ display: "flex", gap: ".2rem", flexWrap: "wrap",
        borderBottom: "1px solid var(--line-soft)" }}>
        {tabs.map((t) => (
          <Link key={t.label} href={t.href} aria-current={t.on ? "page" : undefined}
            style={{
              textDecoration: "none", fontFamily: "var(--font-ui)", fontSize: ".8rem",
              padding: ".45rem .75rem",
              color: t.on ? "var(--ink)" : "var(--ink-soft)",
              borderBottom: `2px solid ${t.on ? "var(--edge-migrates)" : "transparent"}`,
              marginBottom: -1, fontWeight: t.on ? 500 : 400,
            }}>
            {t.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

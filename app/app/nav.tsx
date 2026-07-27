"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

/** The app's one navigation bar. A tab is active when the current path is in
 *  its section, so a map, a thread and a paper all keep "Concepts" lit rather
 *  than leaving the reader with no sense of where they are. */
const TABS: { href: string; label: string; match: (p: string) => boolean }[] = [
  { href: "/", label: "Concepts", match: (p) => p === "/" || p.startsWith("/g/") },
  { href: "/trace", label: "Map a new concept", match: (p) => p.startsWith("/trace") },
  { href: "/about", label: "How it works", match: (p) => p.startsWith("/about") },
  { href: "/roadmap", label: "Roadmap", match: (p) => p.startsWith("/roadmap") },
];

export default function Nav() {
  const path = usePathname() ?? "/";
  return (
    <nav aria-label="Sections" style={{ display: "flex", gap: ".2rem", flexWrap: "wrap",
      borderBottom: "1px solid var(--line)", margin: "0 0 1.4rem" }}>
      {TABS.map((t) => {
        const on = t.match(path);
        return (
          <Link key={t.href} href={t.href} aria-current={on ? "page" : undefined}
            style={{
              textDecoration: "none", fontSize: ".86rem", padding: ".55rem .85rem",
              color: on ? "var(--ink)" : "var(--ink-soft)",
              borderBottom: `2px solid ${on ? "var(--edge-migrates)" : "transparent"}`,
              marginBottom: -1, fontWeight: on ? 500 : 400,
            }}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}

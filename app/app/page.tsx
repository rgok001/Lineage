export default function Home() {
  return (
    <main style={{ maxWidth: 640, margin: "4rem auto", padding: "0 1.5rem" }}>
      <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 500 }}>
        Lineage
      </h1>
      <p style={{ color: "var(--ink-soft)", lineHeight: 1.6 }}>
        Trace how an academic concept evolved across papers. The genealogy UI
        arrives in Phase 3 — the pipeline comes first (see CLAUDE.md build
        order).
      </p>
    </main>
  );
}

import { Bar, LoadingNote, Panel } from "../../skeleton";

/**
 * The map's front door, while it loads (issue #140).
 *
 * This boundary also covers `/g/[id]/river`, which is a redirect, and any
 * future segment under a map that does not bring its own — Next.js walks up to
 * the nearest `loading.tsx`. The four segments a reader actually clicks into
 * each have their own, because a skeleton in the wrong shape moves the page
 * under the reader's eye when the real content arrives, which is the jank this
 * ticket is trying to remove rather than relocate.
 *
 * The container matches page.tsx exactly — maxWidth 1400 and the same padding —
 * for the same reason.
 */
export default function LoadingMap() {
  return (
    <main style={{ maxWidth: 1400, margin: "0 auto", padding: "1rem 1.5rem 4rem" }}>
      <LoadingNote>Drawing the map…</LoadingNote>

      <header style={{ padding: "0 0 1.2rem" }}>
        <Bar w="22rem" h={34} radius={8} />
        <Bar w="34rem" h={16} mt="1.1rem" />
        <Bar w="30rem" h={16} mt=".4rem" />
        <div style={{ display: "flex", gap: "1.2rem", marginTop: "1.1rem", flexWrap: "wrap" }}>
          {[76, 92, 68, 84].map((w, i) => (
            <Bar key={i} w={w} h={11} />
          ))}
        </div>
      </header>

      {/* The canvas is the tall element and the one whose absence collapses the
          page, so it is reserved at a height in the band the real SVG lands in
          rather than left to zero. */}
      <div
        className="skeleton"
        style={{ height: 420, borderRadius: 12, border: "1px solid var(--line)" }}
        aria-hidden="true"
      />

      <section style={{ marginTop: "1.6rem" }}>
        <Bar w="12rem" h={11} />
        {[0, 1, 2, 3].map((i) => (
          <Panel key={i} mt=".45rem">
            <Bar w={`${11 - i}rem`} h={15} />
          </Panel>
        ))}
      </section>

      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            marginTop: i === 0 ? "1.5rem" : ".6rem",
            padding: ".65rem .9rem",
            borderRadius: 8,
            border: "1px dashed var(--line)",
          }}
          aria-hidden="true"
        >
          <Bar w="16rem" h={15} />
        </div>
      ))}
    </main>
  );
}

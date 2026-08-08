import { Bar, LoadingNote, Panel } from "../skeleton";

/**
 * The evidence page, while it loads (issue #140).
 *
 * The slowest route on the site and the one the Product Owner named first:
 * 3.2 s to first byte and 4.1 s complete, because it renders every typed
 * relationship in the map with both quotes. Nothing here can shorten that; what
 * it does is stop the click going unanswered for three seconds.
 *
 * Six pair-cards, not the map's real edge count. A skeleton that drew 320 cards
 * would be claiming a number it has not been told, and the page scrolls anyway.
 */
export default function LoadingEvidence() {
  return (
    <main style={{ maxWidth: 940, margin: "0 auto", padding: "1rem 1.5rem 5rem" }}>
      <LoadingNote>Fetching the papers and their links…</LoadingNote>

      <header
        style={{ borderBottom: "2px solid var(--line)", padding: "0 0 1.1rem", marginBottom: "1.5rem" }}
      >
        <Bar w="9rem" h={11} />
        <Bar w="26rem" h={30} mt=".7rem" radius={8} />
        <Bar w="32rem" h={15} mt=".8rem" />
      </header>

      {[0, 1, 2, 3, 4, 5].map((i) => (
        <Panel key={i} mt="1rem">
          <Bar w="8rem" h={11} />
          {/* Two facing quote-cards, which is the shape of the real row. */}
          <div style={{ display: "flex", gap: ".8rem", marginTop: ".8rem", flexWrap: "wrap" }}>
            {[0, 1].map((j) => (
              <div
                key={j}
                style={{
                  flex: "1 1 16rem",
                  background: "var(--card-2)",
                  border: "1px solid var(--line-soft)",
                  borderRadius: 8,
                  padding: ".7rem .8rem",
                }}
              >
                <Bar w="70%" h={11} />
                <Bar h={12} mt=".7rem" />
                <Bar h={12} mt=".35rem" />
                <Bar w="55%" h={12} mt=".35rem" />
              </div>
            ))}
          </div>
        </Panel>
      ))}
    </main>
  );
}

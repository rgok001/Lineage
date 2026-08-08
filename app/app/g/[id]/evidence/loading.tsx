import { Bar, LoadingNote, Panel } from "../../../skeleton";

/**
 * The evidence page, while it loads (issue #140).
 *
 * The slowest route on the site and the one the Product Owner named first:
 * 3.2 s to first byte and 4.1 s complete, because it renders every typed
 * relationship in the map with both quotes. Nothing here can shorten that; what
 * it does is stop the click going unanswered for three seconds.
 *
 * **Reshaped when section 2 was grouped by paper (issue #146).** The page is no
 * longer a flat run of pair-cards: it opens with a jump index, and then repeats
 * a paper heading, that paper's passage outside any disclosure, and the rows
 * beneath it. A skeleton drawing the old shape would be the wrong silhouette on
 * the one page whose CLS was measured at 0.000 in #140, which is the number this
 * rewrite was most likely to break.
 *
 * Three groups, not the map's real paper count, and three rows, not its real
 * edge count. A skeleton that drew 85 headings would be claiming a number it has
 * not been told, and the page scrolls anyway.
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

      {/* The jump index: one line of type counts, a line of explanation, then the
          multi-column list of papers. */}
      <Panel mt="0" pad=".9rem 1.05rem">
        <Bar w="60%" h={11} />
        <Bar w="80%" h={12} mt=".55rem" />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(15rem, 1fr))",
            gap: ".35rem .9rem",
            marginTop: ".7rem",
          }}
        >
          {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <Bar key={i} h={12} w={i % 3 === 2 ? "70%" : "90%"} />
          ))}
        </div>
      </Panel>

      {[0, 1, 2].map((i) => (
        <section key={i} style={{ marginTop: "2.2rem" }}>
          {/* The group head: the paper's line, then its passage, which is the
              thing this regrouping put outside the disclosure triangles. */}
          <div style={{ borderBottom: "1px solid var(--line)", paddingBottom: ".7rem" }}>
            <Bar w="24rem" h={16} />
            <Bar w="9rem" h={10} mt=".55rem" />
            <div
              style={{
                borderLeft: "2px solid var(--line)",
                padding: ".5rem .8rem",
                background: "var(--card)",
                borderRadius: "0 6px 6px 0",
                marginTop: ".3rem",
              }}
            >
              <Bar h={13} />
              <Bar h={13} mt=".35rem" />
              <Bar w="45%" h={13} mt=".35rem" />
            </div>
            <Bar w="18rem" h={10} mt=".35rem" />
          </div>

          <Bar w="12rem" h={10} mt=".8rem" />
          {[0, 1, 2].map((j) => (
            /* A collapsed row: the type badge line and the later paper's name.
               Both quote-cards live inside the disclosure and are not drawn,
               because the real row does not draw them until it is opened. */
            <Panel key={j} mt=".6rem" pad=".85rem 1.1rem">
              <Bar w="70%" h={12} />
              <Bar w="50%" h={14} mt=".55rem" />
            </Panel>
          ))}
        </section>
      ))}
    </main>
  );
}

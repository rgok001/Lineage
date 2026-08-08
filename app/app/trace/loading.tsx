import { Bar, LoadingNote, Panel } from "../skeleton";

/**
 * "Map a new concept", while it loads (issue #144).
 *
 * The longest unacknowledged click in the product before this: 1347 ms from the
 * global nav with the old page still on screen, measured on the live site from
 * Sydney. This route needs no route group — it has its own directory, so the
 * boundary here covers `/trace` and nothing else. The reasoning about `/` and
 * why it does need one is in `(concepts)/loading.tsx`.
 *
 * The queue below the form is deliberately not drawn. Whether anything is
 * waiting, and how much, is exactly what this page has gone to the database to
 * find out; a row of placeholders there would be asserting a queue exists. It
 * appends below the form when it arrives, which moves nothing already drawn.
 * The sign-in state is not drawn for the same reason: the form's outer shape is
 * the same either way, and its contents are not.
 */
export default function LoadingTrace() {
  return (
    <main style={{ maxWidth: 880, margin: "0 auto", padding: "1rem 1.5rem 5rem" }}>
      <LoadingNote>Opening the form…</LoadingNote>

      <header style={{ padding: "0 0 1.3rem" }}>
        <Bar w="19rem" h={34} radius={8} />
        <Bar w="38rem" h={15} mt="1rem" />
        <Bar w="38rem" h={15} mt=".5rem" />
        <Bar w="24rem" h={15} mt=".5rem" />
      </header>

      {/* The three numbered steps, which are the page's widest element and the
          one that decides where the form starts. */}
      <section style={{ display: "flex", gap: ".8rem", flexWrap: "wrap", marginBottom: "1.8rem" }}>
        {[0, 1, 2].map((i) => (
          <Panel key={i} mt={0} pad=".9rem 1rem" radius={10} grow="1 1 210px">
            <Bar w="3.4rem" h={10} />
            <Bar w="9rem" h={16} mt=".45rem" />
            <Bar h={13} mt=".6rem" />
            <Bar h={13} mt=".3rem" />
            <Bar w="64%" h={13} mt=".3rem" />
          </Panel>
        ))}
      </section>

      <Bar w="11rem" h={19} />
      <Bar w="21rem" h={13} mt=".5rem" />

      {/* The form itself: one card, a row of fields, a submit. Field widths are
          the real ones' flex bases, so the box is the height it will be. */}
      <Panel mt=".9rem" pad=".9rem 1rem">
        <div style={{ display: "flex", flexWrap: "wrap", gap: ".6rem", alignItems: "center" }}>
          <Bar w="48%" h={30} radius={4} />
          <Bar w="48%" h={30} radius={4} />
          <Bar w="100%" h={30} radius={4} />
          <Bar w="62%" h={30} radius={4} />
          <Bar w="7rem" h={27} radius={4} />
        </div>
      </Panel>

      <div style={{ marginTop: "2rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}
        aria-hidden="true">
        <Bar w="80%" h={12} />
        <Bar w="42%" h={12} mt=".4rem" />
      </div>
    </main>
  );
}

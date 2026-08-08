import { Bar, LoadingNote, Panel } from "../../../../skeleton";

/**
 * A paper's dossier, while it loads (issue #140).
 *
 * The deepest route on the map and, before this ticket, the second slowest:
 * 2.5 s to first byte, from six database queries that ran one after another.
 * Four of them now run in two rounds, and this covers what is left.
 */
export default function LoadingPaper() {
  return (
    <main style={{ padding: "2rem 1.5rem 4rem" }}>
      <div style={{ maxWidth: "44rem", margin: "0 auto" }}>
        <LoadingNote>Opening the paper…</LoadingNote>

        <Bar w="14rem" h={11} />
        <Bar w="30rem" h={26} mt=".9rem" radius={8} />
        <Bar w="22rem" h={26} mt=".35rem" radius={8} />
        <Bar w="10rem" h={12} mt=".8rem" />

        {/* The definition and its quote. */}
        <Panel mt="1.8rem">
          <Bar w="7rem" h={11} />
          <Bar h={13} mt=".8rem" />
          <Bar h={13} mt=".35rem" />
          <Bar w="58%" h={13} mt=".35rem" />
        </Panel>

        {/* What it drew from, and what drew from it. */}
        {[0, 1].map((s) => (
          <section key={s} style={{ marginTop: "2rem" }}>
            <Bar w="11rem" h={11} />
            {[0, 1, 2].map((i) => (
              <Panel key={i} mt=".5rem">
                <Bar w="9rem" h={12} />
                <Bar w="80%" h={13} mt=".5rem" />
              </Panel>
            ))}
          </section>
        ))}
      </div>
    </main>
  );
}

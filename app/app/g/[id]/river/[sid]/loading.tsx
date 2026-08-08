import { Bar, LoadingNote, Panel } from "../../skeleton";

/**
 * One thread, read as an account, while it loads (issue #140).
 *
 * "Any of the threads" was in the Product Owner's report. Measured before the
 * fix: 1.2 s to first byte on the shortest thread and 1.6 s on the longest.
 *
 * No stream colour is guessed. The left rule that carries the thread's colour
 * on the real page is drawn in `--line` here, because the colour is a fact
 * about which thread this is and we do not know it yet.
 */
export default function LoadingDive() {
  return (
    <main style={{ padding: "2rem 1.5rem 5rem" }}>
      <div style={{ maxWidth: "42rem", margin: "0 auto" }}>
        <LoadingNote>Reading the thread…</LoadingNote>

        <Bar w="8rem" h={11} />
        <Bar w="20rem" h={30} mt=".9rem" radius={8} />
        <Bar w="26rem" h={15} mt=".7rem" />

        {[0, 1, 2, 3].map((i) => (
          <div key={i} style={{ marginTop: "2rem" }} aria-hidden="true">
            <Bar w="6rem" h={11} />
            <Bar w="24rem" h={18} mt=".5rem" />
            <Bar h={14} mt=".8rem" />
            <Bar h={14} mt=".35rem" />
            <Bar w="62%" h={14} mt=".35rem" />
            <Panel mt=".9rem">
              <Bar h={12} />
              <Bar w="80%" h={12} mt=".35rem" />
            </Panel>
          </div>
        ))}
      </div>
    </main>
  );
}

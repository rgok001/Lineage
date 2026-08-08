import { Bar, LoadingNote } from "../skeleton";

/**
 * "What this map is made of", while it loads (issue #140).
 *
 * Every figure on this page is computed on read and never stored (decision 30),
 * so there is nothing to show early and nothing that may be cached. The
 * skeleton reserves the rows; it does not pre-fill a single one, which would be
 * the stored-figure defect the whole report exists to avoid, arriving through
 * the loading state instead of through the database.
 */
export default function LoadingReport() {
  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: "1rem 1.5rem 5rem" }}>
      <LoadingNote>Working out what this map is made of…</LoadingNote>

      <Bar w="24rem" h={30} radius={8} />
      <Bar w="38rem" h={15} mt=".9rem" />
      <Bar w="34rem" h={15} mt=".35rem" />

      {[0, 1, 2].map((s) => (
        <section key={s} style={{ marginTop: "2.4rem" }}>
          <Bar w="14rem" h={11} />
          {[0, 1, 2, 3].map((r) => (
            <div
              key={r}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: "1rem",
                padding: ".8rem 0",
                borderTop: "1px solid var(--line-soft)",
              }}
              aria-hidden="true"
            >
              <Bar w="15rem" h={15} />
              <div style={{ marginLeft: "auto" }}>
                <Bar w={72} h={20} radius={4} />
              </div>
            </div>
          ))}
        </section>
      ))}
    </main>
  );
}

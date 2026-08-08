import { Bar, LoadingNote, Panel } from "../skeleton";

/**
 * The front door, while it loads (issue #144).
 *
 * `/` and `/trace` were the two longest unacknowledged clicks left in the
 * product after #140: measured on the live site from Sydney, clicking the global
 * nav from `/g/13`, 1143 ms and 1347 ms with the old page sitting on screen
 * whole and unchanged for the whole of it. Both are longer than anything #140
 * fixed, and they are the two tabs on every page.
 *
 * **Why the route group.** A `loading.tsx` at `app/` is the only other way to
 * cover `/`, and it would wrap `/about` and `/roadmap` too. Those are pure text
 * and should not be waiting on anything — that they currently take ~0.6 s is
 * issue #145, and the fix there is to remove the wait, not to paper it over with
 * a skeleton. `(concepts)` is a route group: it changes no URL, and it scopes
 * this boundary to `/` alone. `/trace` needs no group because it already has its
 * own directory, so its boundary simply sits in it.
 *
 * Two card placeholders because a column of them is the shape of this page, not
 * because the map count is two. The note says nothing about how many, and
 * nothing here renders a digit; if the real list is longer it grows downwards,
 * which moves nothing already on screen.
 */
export default function LoadingHome() {
  return (
    <main style={{ maxWidth: 880, margin: "0 auto", padding: "1rem 1.5rem 4rem" }}>
      <LoadingNote>Looking up the concepts…</LoadingNote>

      {/* Matches page.tsx's header box: the same paddingBottom and marginBottom,
          so the "Concepts" heading below lands where the skeleton put it. */}
      <header style={{ paddingBottom: "1.1rem", marginBottom: "1.5rem" }}>
        <Bar w="23rem" h={36} radius={8} />
        <Bar h={15} mt=".8rem" />
        <Bar h={15} mt=".45rem" />
        <Bar h={15} mt=".45rem" />
        <Bar w="58%" h={15} mt=".45rem" />
      </header>

      <Bar w="6rem" h={16} />

      <div style={{ display: "flex", flexDirection: "column", gap: ".7rem", marginTop: ".9rem" }}>
        {[0, 1].map((i) => (
          <Panel key={i} mt={0} pad="1rem 1.1rem">
            <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
              <div style={{ flex: 1 }}>
                <Bar w={`${11 - i * 3}rem`} h={20} />
                <Bar w="26rem" h={13} mt=".45rem" />
              </div>
              <Bar w={64} h={13} />
            </div>
          </Panel>
        ))}
      </div>

      {/* The "Map a new concept" card: one row, taller radius, its own margin. */}
      <Panel mt="1.6rem" pad=".9rem 1.1rem" radius={10}>
        <div style={{ display: "flex", alignItems: "center", gap: ".8rem" }}>
          <Bar w="13rem" h={18} />
          <div style={{ marginLeft: "auto" }}>
            <Bar w="17rem" h={13} />
          </div>
        </div>
      </Panel>

      <div style={{ marginTop: "2rem" }} aria-hidden="true">
        <Bar h={12} />
        <Bar w="72%" h={12} mt=".35rem" />
      </div>
    </main>
  );
}

/**
 * The shapes a /g/[id] route shows while its data is in flight (issue #140).
 *
 * The Product Owner reported lag clicking into evidence, threads and tabs.
 * Measured before any fix, from Sydney against the iad1 functions: 2.1 s to
 * first byte on the map, 3.2 s on the evidence page, 2.5 s on a paper dossier.
 * None of that time produced a pixel — every route is force-dynamic, there was
 * no loading boundary anywhere in `app/`, and the router therefore held the old
 * page on screen until the whole answer arrived. Half the complaint is the
 * wait; the other half is that nothing acknowledged the click.
 *
 * **These are shapes and never content.** No titles, no counts, no quotes, not
 * even plausible-looking ones. A skeleton that guesses "320 relationships" is a
 * fabricated claim about a map for as long as it is on screen, which is rule 4
 * with a stopwatch on it, and it flashes wrong the instant the real number
 * lands. The only words any of these render are words about loading, which are
 * true when they are shown.
 */

/** One grey bar. `w` accepts a percentage so a row of them can suggest a
 *  paragraph's ragged edge without pretending to be one. */
export function Bar({
  w = "100%",
  h = 14,
  mt = 0,
  radius,
}: {
  w?: number | string;
  h?: number;
  mt?: number | string;
  radius?: number;
}) {
  return (
    <div
      className="skeleton"
      style={{ width: w, height: h, marginTop: mt, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}

/** A card-shaped placeholder: the border and ground of a real panel, holding
 *  bars instead of the panel's contents. */
export function Panel({
  children,
  h,
  mt = ".6rem",
}: {
  children?: React.ReactNode;
  h?: number;
  mt?: string;
}) {
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: ".8rem .9rem",
        marginTop: mt,
        height: h,
      }}
      aria-hidden="true"
    >
      {children}
    </div>
  );
}

/**
 * The one honest sentence on a skeleton, and the only thing on it a screen
 * reader is given.
 *
 * `role="status"` rather than a live region on the whole page: everything else
 * here is `aria-hidden`, because announcing a dozen empty boxes is worse than
 * announcing nothing. A reader who cannot see the pulse still hears that the
 * click was received.
 */
export function LoadingNote({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="status"
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: ".68rem",
        letterSpacing: ".14em",
        textTransform: "uppercase",
        color: "var(--ink-faint)",
        margin: "0 0 1rem",
      }}
    >
      {children}
    </p>
  );
}

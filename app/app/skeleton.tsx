/**
 * The shapes a route shows while its data is in flight (issue #140).
 *
 * It lived under `g/[id]/` until #144 gave `/` and `/trace` boundaries of their
 * own; the home page reaching into a map's directory for them would have been
 * the wrong shape of dependency, and one file is what keeps every skeleton in
 * the app on one palette and one pulse.
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
 *  bars instead of the panel's contents.
 *
 *  `pad` and `radius` are overridable because the cards on `/` and `/trace` are
 *  roomier than the ones inside a map, and a skeleton whose padding is off by
 *  a few pixels moves the page under the reader when the content lands — which
 *  is the jank these exist to remove rather than relocate. */
export function Panel({
  children,
  h,
  mt = ".6rem",
  pad = ".8rem .9rem",
  radius = 8,
  grow,
}: {
  children?: React.ReactNode;
  h?: number;
  mt?: number | string;
  pad?: string;
  radius?: number;
  grow?: string;
}) {
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: radius,
        padding: pad,
        marginTop: mt,
        height: h,
        flex: grow,
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
 *
 * It used to be `--ink-faint` at .68rem, uppercase, .14em tracked — 3.33 : 1 at
 * 10.88 px, which made the only sentence on the screen the least legible text
 * in the product and put it under WCAG AA's 4.5 : 1 (issue #147, measured on the
 * live loading state). `--ink-soft` at .8rem is 6.45 : 1 and still quiet. The
 * words are unchanged; dropping `textTransform` is what makes them sentence
 * case, which is how each note is written at its call site anyway.
 */
export function LoadingNote({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="status"
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: ".8rem",
        color: "var(--ink-soft)",
        margin: "0 0 1rem",
      }}
    >
      {children}
    </p>
  );
}

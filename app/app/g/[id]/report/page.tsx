import Link from "next/link";
import { notFound } from "next/navigation";
import { getViewer, isOwner } from "../../../../lib/authz";
import { parseMapId } from "../../../../lib/map-id";
import { EDGE_MEANING } from "../../../../lib/genealogy";
import { listMapReports, type MapReport } from "../../../../lib/report";

export const dynamic = "force-dynamic"; // computed on read, never stored

/**
 * What this map is made of (issue #30, `[F2]`).
 *
 * One screen, one column, no interactivity. Every number is selected from
 * migration 016's two views, migration 017's third (the mix of kinds of link,
 * issue #162), migration 019's fourth (what the map read, by year, issue
 * #182), migration 020's fifth (which pass of the build read a paper, issue
 * #193) and migration 023's sixth (papers a person named, issue #198),
 * so this page and `pipeline/map_report.py` read one
 * expression and cannot disagree about the same map, and nothing is stored, so
 * no figure here can survive the curatorial edit that invalidates it.
 *
 * **There is no threshold on this page and there must never be one.** No colour
 * scale, no grade, no badge, no composite score, no cell that turns red: a red
 * cell is a threshold wearing paint, and with two maps there is no distribution
 * to take a quantile from. The only reference points are the other maps in this
 * system, printed beside each figure with the sample size, and the sample size is
 * the number of rows the view returned rather than a number written into this
 * file, which would age the moment a third map exists.
 *
 * Copy obeys product rule 3 throughout: this page describes what the map is made
 * of, never how good it is, and never calls the map the history of anything.
 *
 * **This page shows a reader's tier of the figures; `pipeline/map_report.py`
 * shows every one** (the UX review, #104 and #107 to #113). Thirty-nine figures
 * rendered at one identical weight is a page of no figures: "definitions
 * verified" looked exactly like "quote slots". So counts and their shares merged
 * onto one row, a handful of rows carry the page's story in one step of larger
 * type, and figures that serve only the team were cut or demoted. The command
 * keeps all of them, because its reader is the Operator. The invariant is now
 * that the page's labels are a **subset** of the command's, with identical
 * wording wherever both print a figure — not the equality it used to be.
 */

/** A duration, in the same words in both places that print one. */
function duration(seconds: number): string {
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return s % 60 ? `${m} min ${s % 60} s` : `${m} min`;
}

const share = (v: number | null) => (v === null ? null : `${(v * 100).toFixed(1)}%`);
const count = (v: number | null) => (v === null ? null : v.toLocaleString());

/**
 * Money, under one rule: **a cost that is not zero never renders as a zero one.**
 *
 * Cents are the readable form and stay the default. But a cached re-trace can
 * genuinely cost US$0.004, and `toFixed(2)` printed that as "US$0.00" under
 * "what the run cost" — a figure that reads as free about a run that was not
 * (issue #87). So: print cents; if cents would round a non-zero amount away to
 * nothing, print four decimals instead, which is the precision the worker
 * actually keeps; and if even that is all zeros, say so in words rather than
 * print a row of them. A recorded zero is a real zero and keeps US$0.00.
 *
 * `money()` in `pipeline/map_report.py` is these same branches in the same
 * order and the two must stay identical: the page and the command publish one
 * number and a reader who saw both would have no way to tell which was rounded.
 */
const money = (v: number | null): string | null => {
  if (v === null) return null;
  const cents = v.toFixed(2);
  if (v === 0 || Number(cents) !== 0) return `US$${cents}`;
  const fine = v.toFixed(4);
  return Number(fine) !== 0 ? `US$${fine}` : "less than US$0.0001";
};

const year = (v: number | null) =>
  v === null ? null : Number.isInteger(v) ? String(v) : v.toFixed(1);

type Fmt = (v: number | null) => string | null;

/**
 * One figure, its two lines, and the same figure on every other map.
 *
 * `counts` says what the number counts, and carries any caveat about how to read
 * it. `moves` answers "what would change this", and renders on its own line
 * under a lead-in that says so (issue #137). **Nothing but an answer to that
 * question belongs in `moves`**: the two used to share one paragraph, and a
 * reading caveat sitting where an answer was expected is what made 21 of these
 * rows unparseable. A row with no answer worth giving passes the empty string
 * and prints no note line.
 *
 * `absent` is the words to print when the value is null, and it is required
 * rather than defaulted, because the two reasons a figure can be missing are
 * different claims and the page must not blur them: **"not recorded"** means
 * nothing in this system holds the number, and something like **"no edges"**
 * means the population is empty. Neither is ever printed as 0, and neither is
 * ever left blank, because a blank reads as a zero.
 *
 * `share` is the same figure as a proportion, printed beside the count instead
 * of on a row of its own (issue #107). The two carry **different** absent words
 * and both are required for the same reason as above: a count can be missing
 * because nothing recorded it while its share is missing because the population
 * it would divide by is empty, and one pair of words cannot say both.
 *
 * `tail` is a second count that belongs on the same row rather than on one of
 * its own (issue #134). The multi-type pair figures were two rows, and the
 * second told the reader to "read beside the count above", which is a self-check
 * rather than a finding; the counts matter together, because a few large pairs
 * and many small ones are different findings. It is set in the share's quiet
 * type for the same reason: it qualifies the number, it is not a second number.
 *
 * `lead` is weight and nothing else: one step of type size, so that the figures
 * carrying the page's story are not identical to the page's bookkeeping. It is
 * never a colour, a badge or a mark of quality, because those are thresholds
 * however they are spelled.
 */
function Figure({
  label, value, counts, moves, absent, others, share, tail, lead,
}: {
  label: string;
  value: string | null;
  counts: string;
  moves: string;
  absent: string;
  others: { concept: string; value: string | null; share?: string | null; tail?: string }[];
  share?: { value: string | null; absent: string };
  tail?: string;
  lead?: boolean;
}) {
  const shown = (o: { value: string | null; share?: string | null; tail?: string }) =>
    `${o.value ?? absent}${share ? ` (${o.share ?? share.absent})` : ""}${o.tail ?? ""}`;
  return (
    <div style={{ padding: ".85rem 0", borderTop: "1px solid var(--line-soft)" }}>
      <div style={{ display: "flex", gap: "1rem", alignItems: "baseline", flexWrap: "wrap" }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: ".68rem", letterSpacing: ".08em",
          textTransform: "uppercase", color: "var(--ink-faint)", minWidth: "20rem",
        }}>
          {label}
        </span>
        <span style={{ display: "inline-flex", alignItems: "baseline", gap: ".45rem",
          flexWrap: "wrap" }}>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: lead ? "1.15rem" : ".95rem",
            color: value === null ? "var(--ink-soft)" : "var(--ink)",
            fontStyle: value === null ? "italic" : "normal",
          }}>
            {value ?? absent}
          </span>
          {/* One span, so the row's own gap does not open before the tail's
              comma: "(58.2%) , across 30 pairs" is what two flex children of a
              gapped container render as. */}
          {(share || tail) && (
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: lead ? ".92rem" : ".82rem",
              color: "var(--ink-soft)",
            }}>
              {share && (
                <span style={{ fontStyle: share.value === null ? "italic" : "normal" }}>
                  ({share.value ?? share.absent})
                </span>
              )}
              {tail}
            </span>
          )}
        </span>
      </div>
      <p style={{
        fontFamily: "var(--font-display)", fontSize: ".92rem", lineHeight: 1.55,
        color: "var(--ink-soft)", margin: ".35rem 0 0", maxWidth: "44rem",
      }}>
        {counts}
      </p>
      {/* The note is an answer to a question the page never asked aloud (issue
          #137). It used to sit inside the explainer's paragraph, joined by a
          single space at one size in one colour, so 21 of the 25 rows showed a
          reader a subjectless, verbless fragment as the second sentence of a
          paragraph about something else: "Papers whose text this map has read
          ... The map being rebuilt over more papers." Unparseable, and in fact a
          careful answer to *what would change this number?*
          The lead-in supplies the missing subject, so every one of those
          fragments ships unchanged, and "the same check as above" acquires a
          visible antecedent, because the row above now has a distinguishable
          note line. It is a label and not a heading: one line break, no bold,
          one step fainter, no extra weight on a page #107 worked to flatten.
          The caveats that used to share this slot have moved onto the end of the
          explainer, where they explain the figure rather than pretending to
          answer the question. Guarded on emptiness so that a row whose only
          sentence was a caveat can never render a lead-in with nothing after
          it. */}
      {moves && (
        <p style={{
          fontFamily: "var(--font-display)", fontSize: ".92rem", lineHeight: 1.55,
          color: "var(--ink-faint)", margin: ".15rem 0 0", maxWidth: "44rem",
        }}>
          <span style={{ fontStyle: "italic" }}>What would change this:</span> {moves}
        </p>
      )}
      {others.length > 0 && (
        <p style={{
          fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--ink-faint)",
          margin: ".3rem 0 0",
        }}>
          the other maps in this system:{" "}
          {others.map((o, i) => (
            <span key={o.concept}>
              {i > 0 && " · "}
              {o.concept} {shown(o)}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

function Section({ title, lede, children }: {
  title: string; lede: string; children: React.ReactNode;
}) {
  return (
    <section style={{ marginTop: "2.2rem" }}>
      <h2 style={{
        fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.25rem",
        margin: 0, color: "var(--ink)",
      }}>
        {title}
      </h2>
      <p style={{
        fontFamily: "var(--font-display)", fontSize: ".95rem", lineHeight: 1.6,
        color: "var(--ink-soft)", margin: ".3rem 0 .4rem", maxWidth: "44rem",
      }}>
        {lede}
      </p>
      {children}
    </section>
  );
}

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // This page never survived a bad id on purpose: it selects every map and
  // matches in memory, so `Number("abc")` matched nothing and 404'd by luck
  // (issue #100 hardened the empty state, not the id). It parses like its
  // siblings now so that one rule covers the whole subtree and nobody reading
  // one route has to work out why the next one is different (issue #159).
  const gid = parseMapId(id);
  if (gid === null) notFound();
  const [all, viewer] = await Promise.all([listMapReports(), getViewer()]);
  const r = all.find((m) => m.genealogy_id === gid);
  if (!r) notFound();
  const rest = all.filter((m) => m.genealogy_id !== r.genealogy_id);
  const owner = isOwner(viewer);

  /** The same figure on every other map. `n` below is `rest.length + 1`, which
   *  is the number of rows the view returned. */
  const others = (pick: (m: MapReport) => number | null, fmt: Fmt) =>
    rest.map((m) => ({ concept: m.concept, value: fmt(pick(m)) }));

  /** The same, for a row that prints a count and its share together (#107). */
  const othersPair = (pick: (m: MapReport) => number | null,
                      pickShare: (m: MapReport) => number | null) =>
    rest.map((m) => ({ concept: m.concept, value: count(pick(m)), share: share(pickShare(m)) }));

  /** A count with the population it came out of, in the row rather than in the
   *  explainer (issues #123, #134). Both arrive from `lib/report.ts` as counts
   *  the view coalesces, so neither can be null; when the population is empty
   *  the count stands alone, because "0 of 0" is not a population. */
  const outOf = (v: number, total: number) =>
    total > 0 ? `${v.toLocaleString()} of ${total.toLocaleString()}` : v.toLocaleString();
  /** `outOf` where either count may be absent (issue #193). `outOf` takes plain
   *  numbers because `map_report`'s counts are coalesced by the view and cannot
   *  be null; the pass counts CAN be, on every map built in one pass, and a
   *  `?? 0` here would print "0 of 15" about a second pass that never ran. */
  const outOfMaybe = (v: number | null, total: number | null) =>
    v === null || total === null ? null : outOf(v, total);
  const acrossPairs = (v: number) => `, across ${v.toLocaleString()} pairs`;

  const defBuckets = r.buckets.filter((b) => b.unit === "definition");
  const edgeBuckets = r.buckets.filter((b) => b.unit === "edge");

  /**
   * Three sentences on this page used to state counts of the world in fixed
   * prose, and nothing recomputed any of them (issue #89). Rendered against six
   * maps, two of them with run records, all three were false and nothing failed:
   * "Both maps that exist today were built from the command line", "Today the
   * classification never proposes one, so this reads zero on every map", and
   * "Every paper this system reads today comes from arXiv".
   *
   * They are derived below from the same rows the figures come from, so they
   * move when the system does. **A sentence the honesty page cannot recompute
   * does not ship on it** — the second was the worst of the three, because F3
   * (#31) is precisely the change that makes `edges_within_one_node` non-zero
   * and this page is the instrument that is supposed to show it.
   */
  const n = all.length;
  const maps = (k: number) => `${k} of the ${n} maps in this system`;

  /**
   * What the per-source table is about to show, counted from its own rows. The
   * labels are read out rather than named, because the label is measured from
   * the paper row and F7 is what makes a second one appear.
   *
   * **The table renders only when the rows carry more than one label** (issue
   * #109), which is exactly the moment it starts saying something. Until then it
   * is a six-column restatement of the Evidence totals split by nothing a reader
   * can see, followed by a lede explaining that it exists for a source that has
   * not arrived. It collapses to one sentence in Evidence instead. The view and
   * the command keep the per-source grain either way, so nothing is lost and F7
   * still changes this table visibly rather than changing one number quietly.
   *
   * **This makes #98 the thing that reveals the table.** A map holding an edge
   * whose paper row is missing gets a second bucket labelled "arxiv + no paper
   * row", which is a data-integrity artefact and not a source, and it trips this
   * condition. That is the wrong trigger and #98 is where it is fixed: the
   * label-counting has to separate a source from an integrity bucket. Rendered
   * here rather than suppressed, because a table that appears is at least
   * visible, where a condition that silently swallowed the artefact would hide
   * it.
   */
  const sourceLabels = Array.from(new Set(r.buckets.map((b) => b.source)));
  const splitBySource = sourceLabels.length > 1;
  const sourceSentence =
    sourceLabels.length === 0
      ? "This map holds no definitions and no relationships, so there is nothing to split by source."
      : sourceLabels.length === 1
        ? `Every paper in this map came from the same place, “${sourceLabels[0]}”. When a second source is added, these figures will be split by source here.`
        : `This map’s rows carry ${sourceLabels.length} different labels.`;

  // Only ever read on a map that has at least one (issue #110), so the "no map
  // in this system has one" branch this used to carry could not be reached: if
  // this map has one, the count of maps that do is at least one. Still derived
  // from the rows rather than written down, for the reason in #89.
  const selfEdgeMaps = all.filter((m) => m.edges_within_one_node > 0).length;
  const selfEdgeSentence =
    `${maps(selfEdgeMaps)} ${selfEdgeMaps === 1 ? "has" : "have"} at least one.`;

  /**
   * What the map's relationships actually rest on, as two sentences at the foot
   * of Evidence rather than a section of its own (issue #132).
   *
   * The section this replaces failed the owner four times ("this is still not
   * obvious any of this means"), and three rewrites did not move it. Two of its
   * three figures served nobody's task: "different papers on relationships"
   * existed only to be read against the line above it, which is a self-check the
   * team would run and not a question a researcher asks, and "different quotes
   * the map stands on" meant nothing until it was divided by the relationship
   * count, which the page never did. The division is done here, in words. All
   * three figures still print in `pipeline/map_report.py`, which is the same
   * page/command subset the "quote slots" rows left under #108.
   *
   * **It renders only when all three numbers are positive.** A null is the view
   * saying nothing recorded it, and a zero would make the sentence claim a map
   * rests on no evidence; either way the reader is better served by no sentence
   * than by a number that is not a count. Grammar at n=1 ("1 relationships rest
   * on 1 different quoted passages") is #99's, with the rest of the pluralising.
   *
   * No score, no threshold, no colour: three counted facts and one consequence.
   */
  const reuseSentence =
    r.most_repeated_quote_uses !== null && r.most_repeated_quote_uses > 0 &&
    r.edges_total > 0 && r.distinct_quote_strings > 0
      ? `These ${count(r.edges_total)} relationships rest on ` +
        `${count(r.distinct_quote_strings)} different quoted passages, because each ` +
        `paper shows the same key quote wherever it appears. One passage is behind ` +
        `${count(r.most_repeated_quote_uses)} of them, so the number of relationships ` +
        `is not a count of separate pieces of evidence.`
      : null;

  /**
   * The mix of kinds of link (issue #162, designing #35).
   *
   * **The gap this fills.** Until now nothing on any surface said how a map's
   * relationships divide across the six kinds. A map whose 300 relationships are
   * 290 "extends" and 10 everything else reads as an excellent map on every
   * other figure here — definitions verified, relationships verified, evidence
   * all present — while a classification that returns one label out of six is
   * not classifying, and the map is a fan of arrows saying "came after". That is
   * the shape a literature which does not move the way these six kinds assume
   * would produce, and every figure above it would stay green while it happened.
   *
   * **A table rather than six figures.** The page's own history is a fight
   * against rendering everything at one weight (#104, #107 to #113), and six
   * more full-width rows each with an explainer, a note and a comparison line
   * would have added a third of a screen to say one thing. The comparison the
   * figures make in prose is made here by a column per map, this map first,
   * which is the same claim in the shape a table already makes.
   *
   * **Nothing here decides anything.** No kind is better than another, there is
   * no expected mix and no share is marked (decisions 24 and 25). The reader is
   * given the counts and the sentence that says what they add up to.
   *
   * The six names are not written down in this file. They arrive as rows from
   * `map_report_by_type` in the view's own order, so a seventh kind would appear
   * here as a seventh row rather than going missing from a hardcoded six, and
   * the columns would still add up to the total below.
   */
  const typeTable = r.types;
  const typeCell = (t: { edges: number; edges_share: number | null } | undefined) => {
    // A kind with no row on another map is a real zero rather than an absence:
    // the view emits all six for every map and emits a seventh kind only where
    // one exists, so "no row" means "that map has none of these".
    if (!t) return "0";
    const s = share(t.edges_share);
    return s === null ? count(t.edges)! : `${count(t.edges)} (${s})`;
  };

  /**
   * The two year series, and the window (issue #182, designing #33, F5).
   *
   * **What was missing.** Every year figure on this page counted the papers that
   * *define* the term, so "the newest paper is 2016" could mean either that
   * nothing recent was ever selected to read, or that recent papers were read
   * and none of them defined the term. Those are a defect in how papers are
   * chosen and a finding about the literature, they need opposite fixes, and
   * nothing in this system could tell them apart.
   *
   * The chart now draws both: the papers read set each column's height, the
   * papers that define the term are drawn over them from the same baseline, so
   * **the exposed part of a column is exactly the papers read that year that did
   * not define the term**. That gap is the whole figure; two separate charts
   * would have made a reader hold one in their head while reading the other.
   *
   * `rd === null` means migration 019 has not landed on this deployment yet, and
   * the page falls back to the single series it drew before, which is why the
   * chart is written to take a missing read series rather than assuming one.
   */
  const rd = r.reading;
  const readCounts = rd?.read_year_counts ?? null;
  const defCounts = r.year_counts ?? null;
  const chartYears = Array.from(new Set([
    ...Object.keys(readCounts ?? {}), ...Object.keys(defCounts ?? {}),
  ])).map(Number).sort((a, b) => a - b);
  // Every year in the defining series is in the read series and never larger
  // (the view carries `defines_concept` as a column rather than as a filter), so
  // this peak is the read series' peak whenever there is one. It is taken over
  // both anyway: a peak taken from a series that turned out to be missing would
  // silently rescale the other one.
  const chartPeak = Math.max(1, ...chartYears.map((y) => Math.max(
    readCounts?.[String(y)] ?? 0, defCounts?.[String(y)] ?? 0)));
  const barPx = (v: number) => (v > 0 ? Math.max(2, (v / chartPeak) * 62) : 0);

  /** The recency window, printed rather than implied: a window a reader cannot
   *  see is a threshold in disguise. Both ends come from the view, which reads
   *  the date when the page loads, so they are never written down here. */
  const windowYears =
    rd && rd.recent_window_start !== null && rd.recent_window_end !== null
      ? `${rd.recent_window_start} to ${rd.recent_window_end}`
      : null;

  /**
   * Which pass of the build read a paper (issue #193, designing #184).
   *
   * **Every map in this system reads "built in one pass" today, and that is a
   * fact about the record rather than a zero.** Nothing in the schema marks a
   * paper's pass yet — the orchestration that runs two passes is #192 — so
   * migration 020 ships the question over an empty seam and every count here is
   * absent. Printing "0 papers read in the second pass" instead would be this
   * page reporting a second pass that ran and found nothing, over four maps that
   * never had one: the #30 defect the whole page is a reaction to.
   *
   * The comparison sentence is counted from the rows rather than written down
   * (issue #89), so the day a two-stage map lands it moves on its own and this
   * file does not have to.
   */
  const pv = r.passes;
  const twoPassMaps = all.filter(
    (m) => m.passes !== null && m.passes.passes_recorded !== null
           && m.passes.passes_recorded > 1).length;
  const onePassSentence =
    `This map was built in one pass: nothing in its record marks a paper as read ` +
    `in a second one. ${maps(twoPassMaps)} ` +
    `${twoPassMaps === 1 ? "was" : "were"} built in more than one pass, so a ` +
    `second pass’s reading is not yet something this page can show you.`;

  /**
   * Papers a person named at request time (issue #198, condition 2 of the design).
   *
   * **Zero is a real zero here and there is no absent case**, which is what makes
   * this block different from the two-passes block above. A map with no rows in
   * the record had no paper named by a person, and that is equally true of a map
   * built before the field existed and of one built after it with the field left
   * empty, so `nobody named a paper for this map` is a measurement rather than a
   * silence dressed as one. The only genuine absence is `an === null`, which
   * means migration 023 has not landed on this deployment yet, and that branch
   * says so instead.
   *
   * The comparison sentence is counted from the rows rather than written down
   * (issue #89), so it moves on its own the day a second anchored map lands.
   */
  const an = r.anchors;
  const anchoredMaps = all.filter(
    (m) => m.anchors !== null && m.anchors.papers_named > 0).length;
  const noneNamedSentence =
    `Nobody named a paper for this map: every paper in it was chosen by this ` +
    `system. ${maps(anchoredMaps)} ` +
    `${anchoredMaps === 1 ? "has" : "have"} a paper somebody named.`;

  const noRunMaps = all.filter((m) => m.runs_recorded === 0).length;
  const runRecordSentence =
    noRunMaps === 0
      ? `Every map in this system has a run record, so nothing reads not recorded for want of one.`
      : noRunMaps === n
        ? `No map in this system has a run record at all, so those cells read not recorded rather than zero on every one of the ${n}.`
        : `${maps(noRunMaps)} ${noRunMaps === 1 ? "has" : "have"} no run record at all, so those cells read not recorded rather than zero.`;

  const mono = { fontFamily: "var(--font-mono)" as const };
  const prose = {
    fontFamily: "var(--font-display)", fontSize: ".95rem", lineHeight: 1.65,
    color: "var(--ink-soft)", maxWidth: "44rem",
  } as const;

  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: "1rem 1.5rem 5rem" }}>
      <header style={{ paddingBottom: ".8rem" }}>
        <div style={{ ...mono, fontSize: ".68rem", letterSpacing: ".14em",
          textTransform: "uppercase", color: "var(--ink-faint)" }}>
          What this map is made of
        </div>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2rem",
          margin: ".3rem 0 0", letterSpacing: "-.01em" }}>
          “{r.concept}”
        </h1>
        {/* One paragraph, not three (issue #106). The page opened with roughly
            170 words of what it is not — not a score, not a baseline, not an
            expectation — before its first number, so a reader learned it was
            about liability rather than about their map. Every claim those three
            paragraphs made is still here: the mechanical check is still
            described mechanically, the shape is still labelled a reading, the
            map is still not the history of the term, and the no-score clause
            still lands before any figure. The reference-point caveat moved
            down to where it applies, beside n= and above the first section. */}
        <p style={{ ...prose, margin: ".7rem 0 0" }}>
          This page says what the “{r.concept}” map is made of, counted from the map
          itself at the moment you loaded it. Two kinds of claim sit in a map: quotes,
          which are checked word for word against the text this system pulled out of
          each paper,
          and the <em>shape</em> (which papers were grouped together, which
          relationships exist and which way round they point, which paper matters
          most), which is this tool’s reading and not the history of the term. The
          figures below say how much of each this map holds; none of them is a score,
          and there is no grade, no colour and no pass mark anywhere on the page.
        </p>
        <p style={{ ...mono, fontSize: ".72rem", color: "var(--ink-faint)", marginTop: ".9rem" }}>
          <Link href={`/g/${id}`} style={{ color: "var(--edge-extends)" }}>← the map</Link>
          {" · "}
          {/* The third door promising a workbench to a reader who will not be
              shown one (issue #124, item 10). #118 scoped the front-door card
              and the evidence banner and missed this one, so a signed-out reader
              clicked "the evidence and workbench" and landed on a page headed
              "Evidence" with no tools. Same fix, same viewer test. */}
          <Link href={`/g/${id}/evidence`} style={{ color: "var(--edge-extends)" }}>
            {owner ? "the evidence and workbench" : "the evidence"}
          </Link>
        </p>
      </header>

      {/* The reference-point caveat, at the point where it first applies rather
          than in the header (issue #106), in the words issue #111 asked for. */}
      <p style={{ ...mono, fontSize: ".72rem", color: "var(--ink-faint)", lineHeight: 1.7,
        margin: "1.6rem 0 0", maxWidth: "44rem" }}>
        Beside each figure is the same figure for every other map in this system.
        With only a few maps to compare against, read those as points of comparison,
        not as an average or as what a map should show. n={n}
      </p>

      {/* "Reading" carried two meanings four inches apart (issue #124, item 3):
          the header calls the shape "this tool's reading", a judgement, and this
          section called a paper's extracted text a "reading" too, on the one page
          that turns on keeping judgement and mechanical fact apart. The phrase
          "this tool's reading" keeps the word; everything mechanical says
          "read". */}
      <Section
        title="How much was read"
        lede="How many papers this map has read, and how many of those define the term.
              These figures count only the papers that were
              actually read. A paper the run tried and failed to read is not counted
              anywhere on this page, so the number of papers the run set out to read
              may be higher than any figure here."
      >
        <Figure
          label="papers read" lead
          value={count(r.papers_with_a_reading)} absent="not recorded"
          counts="Papers whose text this map has read, whether or not a definition was found in them. A paper whose text could not be downloaded or read is not counted here at all."
          moves="The map being rebuilt over more papers."
          others={others((m) => m.papers_with_a_reading, count)}
        />
        <Figure
          label="papers that define the term" lead
          value={count(r.papers_defining)} absent="not recorded"
          counts="Of those, the papers that give the term a definition of their own. Every percentage about definitions below is a share of this number."
          moves="The map being rebuilt, and a paper being read differently the second time, in either direction."
          others={others((m) => m.papers_defining, count)}
        />
        {/* The one row whose whole note was a caveat, so labelling the slot
            would have made this row's label an outright lie (issue #137).
            Nothing but a rebuild changes it, and that is what the note now says,
            rather than an empty line under a lead-in. */}
        <Figure
          label="papers that do not define the term"
          value={count(r.papers_not_defining)} absent="not recorded"
          counts="Papers read and found not to define the term. That is a finding, not a gap, and it is reported here rather than folded away. Shown so the percentages below can be read honestly: they are percentages of the papers that define the term, not of every paper read."
          moves="The map being rebuilt."
          others={others((m) => m.papers_not_defining, count)}
        />

        {/* Papers a person named (issue #198), at the foot of this section
            because the question it answers is the one this section raises: these
            figures say how much was read, and a reader is owed the difference
            between a paper this system went and found and a paper somebody
            handed it. Decision 16 keeps kinds of claim in separate tiers and has
            so far governed quotes; this extends the same discipline to corpus
            membership.
            Set like "the two passes" at the foot of the years section: its own
            quiet label, its own paragraph naming what it counts, its own note
            answering what would change it, then figures or a sentence. */}
        <div style={{ padding: ".85rem 0", marginTop: ".4rem",
          borderTop: "1px solid var(--line-soft)" }}>
          <div style={{ ...mono, fontSize: ".68rem", letterSpacing: ".08em",
            textTransform: "uppercase", color: "var(--ink-faint)" }}>
            papers a person named
          </div>
          <p style={{ fontFamily: "var(--font-display)", fontSize: ".92rem",
            lineHeight: 1.55, color: "var(--ink-soft)", margin: ".35rem 0 0",
            maxWidth: "44rem" }}>
            Whoever asks for a map may name up to three papers it should not miss.
            A named paper is added to what gets read and is then treated exactly like
            every other paper: it is read, its quotes are checked the same way, and a
            relationship to it is drawn only where one paper really does cite the
            other. Being named buys a reading and nothing else, so a named paper can
            end up defining nothing and connected to nothing, and this block says when
            one has.
          </p>
          <p style={{ fontFamily: "var(--font-display)", fontSize: ".92rem",
            lineHeight: 1.55, color: "var(--ink-faint)", margin: ".15rem 0 0",
            maxWidth: "44rem" }}>
            <span style={{ fontStyle: "italic" }}>What would change this:</span>{" "}
            Only mapping the term again, and somebody naming different papers when
            they do.
          </p>
          {an === null ? (
            /* The #92 fallback again (see the mix of kinds of link below): the
               app is live for a few minutes against a schema one migration
               behind, and losing one block is honest where a 500 would take the
               whole page. It must not print "nobody named a paper" here, which
               is a claim this page cannot make when it could not read. */
            <p style={{ ...prose, fontSize: ".9rem", margin: ".8rem 0 0" }}>
              Whether anybody named a paper for this map is not counted on this page
              at the moment. That is this page&rsquo;s reach and not a fact about the
              map.
            </p>
          ) : an.papers_named === 0 ? (
            <p style={{ ...prose, fontSize: ".9rem", margin: ".8rem 0 0" }}>
              {noneNamedSentence}
            </p>
          ) : (
            <>
              <Figure
                label="papers named by the person who asked for this map" lead
                value={count(an.papers_named)} absent="not recorded"
                tail={an.papers_named_read === an.papers_named
                  ? `, all of which were read`
                  : `, ${an.papers_named_read.toLocaleString()} of which were read`}
                counts="Papers a person asked this map to include, out of the papers read above. They did not take a place from a paper the system chose: naming a paper adds it to the reading list rather than swapping it for something else. Where fewer were read than were named, an id named a paper this system could not fetch, and it is left in this count rather than dropped so that nobody is told a paper is here when it is not."
                moves="Only mapping the term again, and somebody naming different papers when they do."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: count(m.anchors?.papers_named ?? null),
                }))}
              />
              <Figure
                label="named papers that define the term"
                value={outOfMaybe(an.papers_named_defining, an.papers_named_read)}
                absent="none were read"
                counts="Of the named papers this map read, the ones found to give the term a definition of their own. It is decided by reading the paper, in the same words and by the same step as for every other paper here, and being named changes nothing about it. A named paper that defines nothing is counted among the papers that do not, above."
                moves="The map being rebuilt, and a paper being read differently the second time, in either direction."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: outOfMaybe(m.anchors?.papers_named_defining ?? null,
                                    m.anchors?.papers_named_read ?? null),
                }))}
              />
              <Figure
                label="named papers carrying a relationship"
                value={outOfMaybe(an.papers_named_linked, an.papers_named_read)}
                absent="none were read"
                counts="Of the named papers this map read, the ones with at least one relationship touching them. A relationship is only ever drawn where one of the two papers really does cite the other, so naming a paper cannot give it one. This is the tool's reading and not a checked fact, like every relationship count on this page."
                moves="The map being rebuilt, or someone editing the map deleting a relationship."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: outOfMaybe(m.anchors?.papers_named_linked ?? null,
                                    m.anchors?.papers_named_read ?? null),
                }))}
              />
              {/* The list, because a count alone does not let a reader tell WHICH
                  paper a person supplied, and that is what condition 2 of the
                  design asks for. Same table furniture as "By source". */}
              {an.named_papers && an.named_papers.length > 0 && (
                <table style={{ ...mono, fontSize: ".78rem", borderCollapse: "collapse",
                  width: "100%", marginTop: ".9rem" }}>
                  <thead>
                    <tr style={{ color: "var(--ink-faint)", textAlign: "left" }}>
                      {["arXiv id", "year", "read", "defines the term", "relationships", ""]
                        .map((h) => (
                          <th key={h} style={{ padding: ".35rem .6rem", fontWeight: 400,
                            borderBottom: "1px solid var(--line)" }}>{h}</th>
                        ))}
                    </tr>
                  </thead>
                  <tbody>
                    {an.named_papers.map((p) => (
                      <tr key={p.arxiv_id}>
                        <td style={{ padding: ".3rem .6rem", color: "var(--ink)" }}>
                          <a href={`https://arxiv.org/abs/${p.arxiv_id}`}
                            style={{ color: "var(--edge-extends)" }}>{p.arxiv_id}</a>
                        </td>
                        <td style={{ padding: ".3rem .6rem" }}>{p.year ?? "no year"}</td>
                        <td style={{ padding: ".3rem .6rem" }}>
                          {p.read ? "yes" : "could not be read"}
                        </td>
                        <td style={{ padding: ".3rem .6rem" }}>
                          {p.read ? (p.defines ? "yes" : "no") : "not read"}
                        </td>
                        <td style={{ padding: ".3rem .6rem" }}>
                          {p.relationships.toLocaleString()}
                        </td>
                        <td style={{ padding: ".3rem .6rem", color: "var(--ink-soft)",
                          fontFamily: "var(--font-display)" }}>
                          {p.title ?? "title not recorded"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      </Section>

      {/* "Extracted text" and "string-matched" are the sentences that carry the
          verification claim, and both named a step the reader has not been told
          exists (issue #124, item 11). The claim is unchanged in every one:
          still mechanical, still word for word, still against this system's own
          copy and never against the published PDF. The reader is now told who
          did the pulling out. */}
      <Section
        title="Evidence"
        lede="How much of this map's evidence is currently matched against the text this
              system pulled out of each paper. Every quote is in exactly one of three
              states.
              Verified: found word for word in the text this system pulled out of the
              paper.
              Inferred: the check ran and could not find it. Not re-checked: the check
              has not yet run against the paper's current text. The three always add
              up to the total."
      >
        <Figure
          label="definitions verified" lead
          value={count(r.definitions_verified)} absent="not recorded"
          share={{ value: share(r.definitions_verified_share), absent: "no papers define the term" }}
          counts="Definition quotes found word for word in the text this system pulled out of that paper, as that text stands now, with the share of the papers that define the term beside it. The share reads absent rather than 0% when no paper defines the term, because a share of nothing is not zero."
          moves="The map being rebuilt. Also the text of a paper changing: any quote checked against the old text goes back to not re-checked."
          others={othersPair((m) => m.definitions_verified, (m) => m.definitions_verified_share)}
        />
        <Figure
          label="definitions inferred"
          value={count(r.definitions_inferred)} absent="not recorded"
          counts="Definition quotes where the check ran against the current text and did not find the passage."
          moves="The map being rebuilt and the passage being found this time. Or the system reading the paper's text differently and losing it."
          others={others((m) => m.definitions_inferred, count)}
        />
        {/* The second sentence here used to explain a one-off moment in this
            system's own history ("every stamp made before that record existed")
            to a reader who was not there. Deleted rather than rewritten: the
            description above already says "or that have no record of a check at
            all", which covers the same ground without the archaeology. */}
        <Figure
          label="definitions not re-checked"
          value={count(r.definitions_stale)} absent="not recorded"
          counts="Quotes whose last check ran against an older copy of the paper's text, or that have no record of a check at all. They are not claimed as verified until the check runs again."
          moves="The check being run again, which costs nothing, because it only compares text with text."
          others={others((m) => m.definitions_stale, count)}
        />
        <Figure
          label="typed relationships"
          value={count(r.edges_total)} absent="not recorded"
          counts="Relationships between two of this map's meanings, each carrying a quote from both papers."
          moves="The map being rebuilt, or someone editing the map deleting a relationship."
          others={others((m) => m.edges_total, count)}
        />
        <Figure
          label="relationships verified" lead
          value={count(r.edges_verified)} absent="not recorded"
          share={{ value: share(r.edges_verified_share), absent: "no relationships" }}
          counts="Relationships where both quotes were matched word for word against their papers' current text, with the share of every relationship in the map beside it. Both sides, not one: half a checked relationship is not a checked relationship. It counts relationships, not quotes: many relationships rest on the same quote. The share reads absent rather than 0% on a map with no relationships."
          moves="The same check as above."
          others={othersPair((m) => m.edges_verified, (m) => m.edges_verified_share)}
        />
        <Figure
          label="relationships inferred"
          value={count(r.edges_inferred)} absent="not recorded"
          counts="Relationships where the check ran against both papers' current text and at least one quote was not found."
          moves="The check running again and finding both quotes this time."
          others={others((m) => m.edges_inferred, count)}
        />
        <Figure
          label="relationships not re-checked"
          value={count(r.edges_stale)} absent="not recorded"
          counts="Relationships whose last check ran against an older copy of a paper's text, or that have no record of a check at all. A relationship whose paper is missing from our records sits here too, because a missing paper cannot support a check. On an older map this can read as the whole map, which is honest rather than broken."
          moves="The check being run again."
          others={others((m) => m.edges_stale, count)}
        />
        {/* Where the six-column table used to stand while it split by nothing
            (issue #109). Derived from the map's own rows, never a named source:
            what makes a second label appear is F7, and a sentence this page
            cannot recompute does not ship on it (issue #89). */}
        {!splitBySource && (
          <p style={{ ...prose, fontSize: ".9rem", margin: "1rem 0 0" }}>
            {sourceSentence}
          </p>
        )}
        {/* Same position and shape as the by-source sentence above, and for the
            same reason (issue #132): it inherits "Evidence", where the reader is
            already asking how much of the map is checked, and what it changes is
            that they stop reading the relationship count as that many separate
            pieces of evidence. */}
        {reuseSentence && (
          <p style={{ ...prose, fontSize: ".9rem", margin: "1rem 0 0" }}>
            {reuseSentence}
          </p>
        )}
      </Section>

      {splitBySource && (
      <Section
        title="By source"
        lede={`The same counts, split by where each paper came from. A relationship is
              grouped by the pair of its two ends, so every relationship lands in
              exactly one row and the rows add up to the totals above.
              ${sourceSentence}`}
      >
        <table style={{ ...mono, fontSize: ".78rem", borderCollapse: "collapse",
          width: "100%", marginTop: ".6rem" }}>
          <thead>
            <tr style={{ color: "var(--ink-faint)", textAlign: "left" }}>
              {["", "source", "total", "verified", "inferred", "not re-checked"].map((h) => (
                <th key={h} style={{ padding: ".35rem .6rem", borderBottom: "1px solid var(--line)",
                  fontWeight: 400 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[["definitions", defBuckets], ["relationships", edgeBuckets]].map(
              ([name, rows]) => (rows as typeof defBuckets).map((b, i) => (
                <tr key={`${name}-${b.source}`}>
                  <td style={{ padding: ".3rem .6rem", color: "var(--ink-faint)" }}>
                    {i === 0 ? (name as string) : ""}
                  </td>
                  <td style={{ padding: ".3rem .6rem", color: "var(--ink)" }}>{b.source}</td>
                  <td style={{ padding: ".3rem .6rem" }}>{b.total.toLocaleString()}</td>
                  <td style={{ padding: ".3rem .6rem" }}>{b.verified.toLocaleString()}</td>
                  <td style={{ padding: ".3rem .6rem" }}>{b.inferred.toLocaleString()}</td>
                  <td style={{ padding: ".3rem .6rem" }}>{b.stale.toLocaleString()}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </Section>
      )}

      <Section
        title="Shape"
        lede="How the map's meanings and relationships are distributed. All of this is
              the tool's reading rather than anything checked against a paper: a
              grouping is a judgement, and so is the direction of a relationship."
      >
        <Figure
          label="meanings" lead
          value={count(r.nodes_total)} absent="not recorded"
          counts="Groups of papers this map treats as holding one meaning of the term."
          moves="This changes if the map is rebuilt, or if someone editing the map splits, merges or deletes a group."
          others={others((m) => m.nodes_total, count)}
        />
        {/* A diagnostic row, shown when it has something to report (issue #110).
            This is not the absent-versus-zero rule bending. That rule governs a
            figure whose value is MISSING, and this figure cannot be missing:
            `lib/report.ts` reads it as a count the view coalesces, so it is a
            number or the row does not exist. What is skipped is a known zero on
            an alarm that has never once fired, which is the team talking to
            itself on the reader's page. */}
        {r.nodes_unreadable !== 0 && (
          <Figure
            label="meanings that could not be read"
            value={count(r.nodes_unreadable)} absent="not recorded"
            counts="Entries in the stored grouping that do not carry an identifier and a list of members. They are dropped from every other figure here and counted here instead of being guessed at."
            moves="Nothing should. Anything above zero means something wrote the grouping in a shape this system does not understand, which is why this line appears only on a map that has one."
            others={others((m) => m.nodes_unreadable, count)}
          />
        )}
        <Figure
          label="meanings holding one paper"
          value={count(r.nodes_with_one_member)} absent="not recorded"
          share={{ value: share(r.nodes_with_one_member_share), absent: "no meanings" }}
          counts="Meanings with a single paper in them, with the share of every meaning in the map beside it. The share reads absent rather than 0% on a map with no meanings."
          moves="Rebuilding the map, or someone editing it merging two meanings into one."
          others={othersPair((m) => m.nodes_with_one_member, (m) => m.nodes_with_one_member_share)}
        />
        <Figure
          label="meanings with no link to another meaning"
          value={count(r.nodes_with_no_edge_to_another_node)} absent="not recorded"
          counts="Meanings that no relationship connects to a different meaning. These are what the evidence page lists as unconnected."
          moves="A new relationship reaching one of them, or the map being rebuilt."
          others={others((m) => m.nodes_with_no_edge_to_another_node, count)}
        />
        <Figure
          label="largest meaning, papers in it"
          value={count(r.largest_node_members)} absent="no meanings"
          counts={`The biggest single group${r.largest_node_id ? ` (${r.largest_node_id})` : ""}, by how many papers it holds.`}
          moves="Rebuilding the map, or someone editing it splitting this group in two."
          others={others((m) => m.largest_node_members, count)}
        />
        <Figure
          label="relationships touching the largest meaning" lead
          value={count(r.largest_node_edges)} absent="not recorded"
          share={{ value: share(r.largest_node_edges_share), absent: "no relationships" }}
          counts="Relationships with the largest meaning at either end, with the share of every relationship in the map beside it. It says how much of the map hangs off one group. The share reads absent rather than 0% on a map with no relationships."
          moves="The same things as above, plus anything that adds or removes a relationship."
          others={othersPair((m) => m.largest_node_edges, (m) => m.largest_node_edges_share)}
        />
        {/* Three rows about node pairs became one (issue #134), applying the
            owner's measure test: a figure earns its place by having a use, and
            what it measures has to be apparent without knowing how the system
            works. "Pairs of meanings that are linked" had no use anyone could
            name and spent its second sentence teaching the counting; it is cut
            from the page and still prints in `pipeline/map_report.py`. The other
            two had a use the page never stated, split across two rows, the
            second of which said "read beside the count above" — the same
            self-check #132 cut a whole section for.

            The wording is deliberate about what it does NOT claim. More than one
            kind of link between two meanings is not the tool contradicting
            itself: the relationships on a pair come from different papers, and
            two papers can genuinely have done different things to the same idea.
            So the innocent reading is given first and in full. This is a count
            and a share, not a quality signal, and nothing here grades it
            (decisions 24 and 25, issue #30). */}
        <Figure
          label="relationships between meanings linked in more than one way"
          value={outOf(r.edges_on_disagreeing_pairs, r.edges_total)} absent="not recorded"
          share={{ value: share(r.edges_on_disagreeing_pairs_share), absent: "no relationships" }}
          tail={acrossPairs(r.node_pairs_disagreeing)}
          counts="Where two groups of papers are linked more than once, the links do not always say the same thing: one paper may extend an idea while another narrows it. These are the relationships to read first if you are checking the tool's reading. The share reads absent rather than 0% on a map with no relationships."
          moves="Someone editing the map changing what kind of link a relationship is, or the map being rebuilt."
          others={rest.map((m) => ({
            concept: m.concept,
            value: outOf(m.edges_on_disagreeing_pairs, m.edges_total),
            share: share(m.edges_on_disagreeing_pairs_share),
            tail: acrossPairs(m.node_pairs_disagreeing),
          }))}
        />
        {/* Zero by construction until F3 (#31) lets papers inside one meaning be
            related to each other, and its explainer used to say so in the words
            "queued work", which mean nothing to a reader (issue #110). Shown
            when there is one to report; the instrument F3 is measured on is
            still this row, and the run that first makes it non-zero is the run
            that makes it appear. */}
        {r.edges_within_one_node !== 0 && (
          <Figure
            label="relationships inside one meaning"
            value={count(r.edges_within_one_node)} absent="not recorded"
            counts={`Relationships whose two ends are the same meaning. ${selfEdgeSentence}`}
            moves="Allowing papers within one meaning to be related to each other. This line appears only on a map that has at least one, so a map with none does not print it as a zero."
            others={others((m) => m.edges_within_one_node, count)}
          />
        )}

        {/* Placed last in Shape, and immediately after the row about pairs
            linked in more than one way, because that row is where the page
            first says "kind of link" to a reader. Set like the papers-per-year
            block above it: its own quiet label, its own paragraph naming what
            it counts, its own note answering what would change it. */}
        <div style={{ padding: ".85rem 0", borderTop: "1px solid var(--line-soft)" }}>
          <div style={{ ...mono, fontSize: ".68rem", letterSpacing: ".08em",
            textTransform: "uppercase", color: "var(--ink-faint)" }}>
            kinds of link
          </div>
          <p style={{ fontFamily: "var(--font-display)", fontSize: ".92rem",
            lineHeight: 1.55, color: "var(--ink-soft)", margin: ".35rem 0 0",
            maxWidth: "44rem" }}>
            Every one of this map’s {count(r.edges_total)} typed relationships, counted
            by which kind of link it was given. A relationship carries exactly one kind,
            so these add up to that total. A kind no relationship was given reads 0
            rather than being left out: having none of a kind is a finding, and a
            missing line is not.
          </p>
          <p style={{ fontFamily: "var(--font-display)", fontSize: ".92rem",
            lineHeight: 1.55, color: "var(--ink-faint)", margin: ".15rem 0 0",
            maxWidth: "44rem" }}>
            <span style={{ fontStyle: "italic" }}>What would change this:</span>{" "}
            The map being rebuilt, or someone editing the map changing what kind a
            relationship is, or deleting one.
          </p>
          {typeTable === null ? (
            /* Migration 017 has not landed on this deployment yet
               (`lib/report.ts` explains the guard). Words, never a zero and never
               a blank: a table of noughts here would say this map has no links of
               any kind, over a map holding hundreds. */
            <p style={{ ...mono, fontSize: ".78rem", color: "var(--ink-soft)",
              fontStyle: "italic", marginTop: ".6rem" }}>
              not counted on this page at the moment, which is this page’s reach and
              not a fact about the map
            </p>
          ) : r.edges_total === 0 ? (
            <p style={{ ...mono, fontSize: ".78rem", color: "var(--ink-soft)",
              fontStyle: "italic", marginTop: ".6rem" }}>
              this map holds no relationships, so there is no mix of kinds to count
            </p>
          ) : (
            <table style={{ ...mono, fontSize: ".78rem", borderCollapse: "collapse",
              width: "100%", marginTop: ".6rem" }}>
              <thead>
                <tr style={{ color: "var(--ink-faint)", textAlign: "left" }}>
                  {["kind", "what it means", "this map",
                    ...rest.map((m) => m.concept)].map((h) => (
                    <th key={h} style={{ padding: ".35rem .6rem",
                      borderBottom: "1px solid var(--line)", fontWeight: 400 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {typeTable.map((t) => (
                  <tr key={t.edge_type}>
                    <td style={{ padding: ".3rem .6rem", color: "var(--ink)" }}>
                      {t.edge_type}
                    </td>
                    {/* `EDGE_MEANING`, which `/about` and the evidence page
                        already read, so this adds no home for the six sentences.
                        It is not the only one: `/g/[id]`'s legend has a shorter
                        `GLOSS` of its own, which is a second wording of the same
                        six and is out of this ticket's scope. A kind the taxonomy
                        does not contain is named as such from the view's own rank
                        rather than inferred from the gloss being missing, so the
                        two facts stay independent. */}
                    <td style={{ padding: ".3rem .6rem", color: "var(--ink-faint)" }}>
                      {t.taxonomy_rank === null
                        ? "not one of the six kinds this tool uses"
                        : EDGE_MEANING[t.edge_type] ?? ""}
                    </td>
                    <td style={{ padding: ".3rem .6rem" }}>{typeCell(t)}</td>
                    {rest.map((m) => (
                      <td key={m.genealogy_id} style={{ padding: ".3rem .6rem",
                        color: "var(--ink-soft)" }}>
                        {m.types === null
                          ? "not counted"
                          : typeCell(m.types.find((o) => o.edge_type === t.edge_type))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Section>

      {/* "Corpus" was the team's word and this heading was its last appearance
          on the page (issue #124, item 5). The lede's date clause needed two
          reads and one of them was pure machinery. */}
      <Section
        title="When the papers were written"
        lede="Each paper is dated by the earliest date we can trust for it: whichever is
              earlier of the date the catalogue gives and the date built into its arXiv
              number. Read it as when the work first appeared, not as a publication
              date. A paper with no year is counted separately and never guessed at.
              Two things are counted here and they are not the same: every paper this
              map read, and the ones that define the term."
      >
        {/* The chart leads, and the three quantile rows it summarised are gone
            (issue #113). "A quarter of the defining papers are this old or
            older" is a statistician's sentence about something the picture
            below it showed directly, on a page already over-supplied with
            figures. The median was offered as a sentence under the chart and is
            not taken: `percentile_cont` interpolates, so half the maps would
            read "half the papers are from 2019.5 or earlier", and a page that
            exists to keep figures honest should not print a half year as a
            date. All three still print in `pipeline/map_report.py`.
            "Papers with no year" survives below the chart, because those papers
            are invisible in it and a chart that quietly omits them is the same
            defect as a blank reading as a zero. */}
        <div style={{ marginTop: ".2rem" }}>
          <div style={{ ...mono, fontSize: ".68rem", letterSpacing: ".08em",
            textTransform: "uppercase", color: "var(--ink-faint)" }}>
            papers per year
          </div>
          {/* The key, which a two-series chart cannot do without. It renders
              only when there are two series: on a deployment one migration
              behind, the chart is the single series it always was, and a key
              naming a bar that is not drawn would be worse than none. */}
          {readCounts && (
            <div style={{ ...mono, fontSize: ".62rem", color: "var(--ink-faint)",
              display: "flex", gap: "1.1rem", flexWrap: "wrap", marginTop: ".4rem",
              alignItems: "center" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: ".35rem" }}>
                <span style={{ width: 10, height: 10, background: "var(--line-soft)",
                  border: "1px solid var(--line-soft)", display: "inline-block" }} />
                papers read
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: ".35rem" }}>
                <span style={{ width: 10, height: 10, background: "var(--line)",
                  border: "1px solid var(--line)", display: "inline-block" }} />
                of those, papers that define the term
              </span>
              <span>the number above each column is how many papers were read that year</span>
            </div>
          )}
          {chartYears.length > 0 ? (
            <div style={{ display: "flex", alignItems: "flex-end", gap: "2px",
              marginTop: ".5rem", height: 90 }}>
              {chartYears.map((yr) => {
                const key = String(yr);
                // `null`, not 0, when there is no read series at all: the column
                // then reports the defining count above it, exactly as it did
                // before this ticket, rather than announcing that nothing was
                // read that year.
                const readN = readCounts ? readCounts[key] ?? 0 : null;
                const defN = defCounts?.[key] ?? 0;
                const readH = readN === null ? 0 : barPx(readN);
                const defH = barPx(defN);
                return (
                  <div key={key} style={{ display: "flex", flexDirection: "column",
                    alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
                    <span style={{ ...mono, fontSize: ".58rem", color: "var(--ink-faint)" }}>
                      {readN ?? defN}
                    </span>
                    {/* One column, two series drawn from one baseline, so the
                        exposed part is the papers read that year that did not
                        define the term. Two side-by-side bars would have made
                        that a subtraction the reader has to do. */}
                    <div
                      title={readN === null
                        ? `${yr}: ${defN} define the term`
                        : `${yr}: ${readN} read, ${defN} define the term`}
                      style={{
                        position: "relative", width: 16,
                        height: `${Math.max(readH, defH)}px`,
                        background: "var(--line-soft)",
                        border: "1px solid var(--line-soft)",
                      }}
                    >
                      {defH > 0 && (
                        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0,
                          height: `${defH}px`, background: "var(--line)" }} />
                      )}
                    </div>
                    <span style={{ ...mono, fontSize: ".55rem", color: "var(--ink-faint)",
                      writingMode: "vertical-rl", marginTop: 3 }}>
                      {yr}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p style={{ ...mono, fontSize: ".78rem", color: "var(--ink-soft)",
              fontStyle: "italic", marginTop: ".4rem" }}>
              no years recorded
            </p>
          )}
        </div>

        <div style={{ marginTop: "1.1rem" }}>
          <Figure label="earliest year" value={year(r.year_min)} absent="no years recorded"
            counts="The oldest paper in the map that defines the term. The chart above can start further left, where a paper was read and did not define the term."
            moves="The map being rebuilt and reaching further back, or a wrong year being corrected."
            others={others((m) => m.year_min, year)} />
          <Figure label="latest year" value={year(r.year_max)} absent="no years recorded"
            counts="The newest paper in the map that defines the term. Read it beside the newest paper read, below: if that one is later, this map read newer work and did not find the term defined in it."
            moves="Only mapping the term again brings in newer work."
            others={others((m) => m.year_max, year)} />
          {/* The three figures #182 added, and the reason they are three rows
              and not one. `read_year_max` against `latest year` says whether
              recent work was read at all; the window count says how much;
              the last says how much of it defined the term. The first two can
              only be made to move by changing what gets read, and the third is
              the one an independent judge can still answer no to. */}
          {rd ? (
            <>
              <Figure label="newest paper read" value={year(rd.read_year_max)}
                absent="no years recorded"
                counts="The newest paper in the map, whether or not it defines the term, which is the right end of the chart above. It is never earlier than the latest year above, because the papers that define the term are some of the papers read."
                moves="The map being rebuilt over papers chosen differently."
                others={others((m) => m.reading?.read_year_max ?? null, year)} />
              <Figure
                label="papers read from the last five years" lead
                value={count(rd.papers_read_recent)} absent="not recorded"
                tail={windowYears ? `, written ${windowYears}` : undefined}
                counts={`How many of this map's papers were written in the last five years${
                  windowYears ? `, which is ${windowYears} as this page was loaded` : ""
                }. This is what the map chose to read, before anything was found in them. It is a count of what was selected and not a result: changing how papers are chosen moves it by construction, so it can say what this map read and it cannot say whether the reading was any good.`}
                moves="The map being rebuilt, and the way papers are chosen for it changing. The window moves too: it is the five calendar years ending in the year you loaded this page."
                others={others((m) => m.reading?.papers_read_recent ?? null, count)} />
              <Figure
                label="of those, papers that define the term" lead
                value={outOf(rd.papers_defining_recent, rd.papers_read_recent)}
                absent="not recorded"
                counts="Of the papers above, the ones found to give the term a definition of their own. A paper read and found not to define the term is a finding about the literature, not a gap in the map. Unlike the figure above, this one can come back lower after more recent papers are read, because whether a paper defines the term is decided by reading it."
                moves="The map being rebuilt, and a paper being read differently the second time, in either direction."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: m.reading
                    ? outOf(m.reading.papers_defining_recent, m.reading.papers_read_recent)
                    : null,
                }))} />
            </>
          ) : (
            /* The #92 fallback again (see the mix of kinds of link above): the
               app is live for a few minutes against a schema one migration
               behind, and losing three figures is honest where a 500 would take
               the whole page. */
            <p style={{ ...prose, fontSize: ".9rem", margin: "1rem 0 .4rem" }}>
              Which years the papers this map read were written in, beyond the ones
              that define the term, is not counted on this page at the moment. That
              is this page&rsquo;s reach and not a fact about the map.
            </p>
          )}
          <Figure label="papers with no year" value={count(r.papers_with_no_year)}
            absent="not recorded"
            counts="Papers that define the term and have no year at all. They are nowhere in the chart above and in none of the figures here, rather than being given a guessed date."
            moves="Only better publication dates for those papers. Nothing about the map itself moves this."
            others={others((m) => m.papers_with_no_year, count)} />
        </div>

        {/* The two passes (issue #193), at the foot of this section rather than
            in a section of its own, because the question it answers is the one
            the window figures above raise: a map can read recent work because
            somebody reserved seats for it before the map existed, or because the
            finished map went looking. Those are different claims and they belong
            within one glance of each other.
            Set like the "kinds of link" block in Shape: its own quiet label, its
            own paragraph naming what it counts, its own note answering what
            would change it, then figures or a sentence. */}
        <div style={{ padding: ".85rem 0", marginTop: ".4rem",
          borderTop: "1px solid var(--line-soft)" }}>
          <div style={{ ...mono, fontSize: ".68rem", letterSpacing: ".08em",
            textTransform: "uppercase", color: "var(--ink-faint)" }}>
            the two passes
          </div>
          <p style={{ fontFamily: "var(--font-display)", fontSize: ".92rem",
            lineHeight: 1.55, color: "var(--ink-soft)", margin: ".35rem 0 0",
            maxWidth: "44rem" }}>
            A map can be built in two passes: the first reads papers chosen before
            anything is known about the term, and the second asks the map it has just
            built what came after its turning points, then reads those too. Both
            happen before the map is shown to anyone. What follows says what the
            second pass read and what was found in it, separately from the first, so
            that what the second pass bought can be told apart from what the first
            would have found anyway.
          </p>
          <p style={{ fontFamily: "var(--font-display)", fontSize: ".92rem",
            lineHeight: 1.55, color: "var(--ink-faint)", margin: ".15rem 0 0",
            maxWidth: "44rem" }}>
            <span style={{ fontStyle: "italic" }}>What would change this:</span>{" "}
            Only mapping the term again. A map is built in one pass or two and is
            never added to afterwards.
          </p>
          {pv === null ? (
            /* The #92 fallback again (see the mix of kinds of link above): the
               app is live for a few minutes against a schema one migration
               behind, and losing one block is honest where a 500 would take the
               whole page. */
            <p style={{ ...prose, fontSize: ".9rem", margin: ".8rem 0 0" }}>
              How many passes this map was built in is not counted on this page at
              the moment. That is this page&rsquo;s reach and not a fact about the
              map.
            </p>
          ) : pv.passes_recorded === null ? (
            <p style={{ ...prose, fontSize: ".9rem", margin: ".8rem 0 0" }}>
              {onePassSentence}
            </p>
          ) : (
            <>
              <Figure
                label="why the second pass ended"
                value={pv.pass_two_outcome} absent="not recorded"
                counts="Which of four things happened: it filled every seat it reserved, it filled some of them, it found nothing to read, or it was abandoned before spending anything because what it would have cost did not fit in what was left of the map's budget. It is never blank, because each of those four is a different thing to know."
                moves="Only mapping the term again."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: m.passes?.pass_two_outcome ?? null,
                }))}
              />
              <Figure
                label="papers read in the second pass" lead
                value={outOfMaybe(pv.papers_read_pass_two, r.papers_with_a_reading)}
                absent="built in one pass"
                tail={pv.pass_two_seats !== null && pv.papers_read_pass_two !== null
                  ? `, filling ${pv.papers_read_pass_two.toLocaleString()} of the ${pv.pass_two_seats.toLocaleString()} seats it reserved`
                  : undefined}
                counts="Papers this map read only because the first pass of the map pointed at them. This is a count of what was selected and not a result: changing how papers are chosen moves it by construction, so it can say what this map read and it cannot say whether the reading was any good. The two figures below are the ones that can still answer no."
                moves="The map being rebuilt, and the second pass being given more or fewer seats."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: outOfMaybe(m.passes?.papers_read_pass_two ?? null,
                                    m.papers_with_a_reading),
                }))}
              />
              <Figure
                label="second-pass papers that define the term" lead
                value={outOfMaybe(pv.papers_defining_pass_two,
                                  pv.papers_read_pass_two)}
                absent="built in one pass"
                counts="Of the papers the second pass read, the ones found to give the term a definition of their own. Whether a paper defines the term is decided by reading it, so this one can come back lower after more papers are read, however they were chosen."
                moves="The map being rebuilt, and a paper being read differently the second time, in either direction."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: outOfMaybe(m.passes?.papers_defining_pass_two ?? null,
                                    m.passes?.papers_read_pass_two ?? null),
                }))}
              />
              <Figure
                label="second-pass papers linked to a first-pass meaning"
                value={outOfMaybe(pv.papers_linking_into_pass_one,
                                  pv.papers_read_pass_two)}
                absent="built in one pass"
                counts="Of the papers the second pass read, the ones this tool then linked to a group of papers the first pass had already gathered. This is the tool's reading and not a checked fact: which papers were grouped together and which way a relationship points are judgements, the same ones the Shape figures above are made of. It is the closest thing here to saying the idea moved recently, and it is not that claim."
                moves="The map being rebuilt, or someone editing the map deleting a relationship."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: outOfMaybe(m.passes?.papers_linking_into_pass_one ?? null,
                                    m.passes?.papers_read_pass_two ?? null),
                }))}
              />
              <Figure
                label="recent papers that cite this map"
                value={count(pv.pass_two_candidates)} absent="built in one pass"
                tail={pv.pass_two_candidates_cleared !== null
                  ? `, ${pv.pass_two_candidates_cleared.toLocaleString()} of which the second pass could have read`
                  : undefined}
                counts="How many recent papers cite this map's papers at all, and how many of those passed both of the tests the second pass applies before it will read one. These come from the citation record rather than from anything this tool judged. They are here so that a second pass which read nothing can say whether there was nothing to read or whether there was no budget left for it."
                moves="Time passing, and other people citing these papers. Nothing about this map moves it."
                others={rest.map((m) => ({
                  concept: m.concept,
                  value: count(m.passes?.pass_two_candidates ?? null),
                }))}
              />
              {/* Shown only when there is one, like "meanings that could not be
                  read" above. It counts papers a two-pass build recorded as
                  belonging to neither of its passes, which is what keeps the
                  three counts adding up to the papers read whatever the build
                  wrote down; above zero it means the build's own record of
                  itself is incomplete. */}
              {pv.papers_read_pass_unmarked !== null
                && pv.papers_read_pass_unmarked !== 0 && (
                <Figure
                  label="papers the record puts in neither pass"
                  value={count(pv.papers_read_pass_unmarked)} absent="built in one pass"
                  counts="Papers this map read that its own record of the build does not place in either pass. They are counted here rather than folded into one of the two, so the two figures above always add up to the papers read."
                  moves="Nothing should. Anything above zero means the build recorded itself incompletely, which is why this line appears only on a map that has one."
                  others={rest.map((m) => ({
                    concept: m.concept,
                    value: count(m.passes?.papers_read_pass_unmarked ?? null),
                  }))}
                />
              )}
            </>
          )}
        </div>
      </Section>

      {/* Where "Quote reuse", later "The evidence behind the map", stood until
          issue #132 cut it. It was moved below the years (#108), had its lede
          halved, and was retitled on the owner's own suggestion (#124), and on
          the fourth reading the owner still said "this is still not obvious any
          of this means". The argument for the cut and for the two sentences that
          replace it, at the foot of Evidence, is on `reuseSentence` above. All
          three figures still print in `pipeline/map_report.py`. */}

      <Section
        title="The run"
        lede="What building this map took. These come from the record kept while a
              map is being built for someone who asked for it, so a map built directly
              by the team, rather than through a request on this site, has none of them
              and says so. Where a figure reads not
              recorded, nothing in this system holds it; it is not zero and it is not
              an estimate."
      >
        {/* "A map built from the command line" appeared three times and assumed
            a reader who knows what a command line is, and that some maps are
            built without anybody asking (issue #124, item 6). All three now say
            who built it in the reader's terms. */}
        <Figure
          label="runs recorded"
          value={count(r.runs_recorded)} absent="not recorded"
          counts="Completed runs this system has a record of for this map. The figures below describe the most recent one, not the map's whole life. A map the team built directly, rather than through a request on this site, has no run record, and every figure below then reads not recorded."
          moves="Mapping the term again."
          others={others((m) => m.runs_recorded, count)}
        />
        <Figure
          label="time the run took" lead
          value={r.run_wall_clock === null ? null : duration(r.run_wall_clock)}
          absent="not recorded"
          counts="From the run starting to the run finishing, for the most recent completed run."
          moves="How many papers the run had to read, and how many of those this system had already read for an earlier map."
          others={rest.map((m) => ({
            concept: m.concept,
            value: m.run_wall_clock === null ? null : duration(m.run_wall_clock),
          }))}
        />
        <Figure
          label="time from asking to finished"
          value={r.requester_wait === null ? null : duration(r.requester_wait)}
          absent="not recorded"
          counts="From the map being asked for to the run finishing, which includes waiting in the queue."
          moves="Everything above, plus how long the request waited before it started."
          others={rest.map((m) => ({
            concept: m.concept,
            value: m.requester_wait === null ? null : duration(m.requester_wait),
          }))}
        />
        {owner && (
          <Figure
            label="what the run cost"
            value={money(r.run_cost_usd)} absent="not recorded"
            counts={`Model spend on the most recent completed run, ${r.run_cost_basis}. It is read from what the run's own stages printed as they went, it covers only the stages that print a spend line, and it is one run rather than everything this map has cost.`}
            moves="How many papers the run had to read, and how many of them had already been read. A repair or a second run does not add to it."
            others={rest.map((m) => ({ concept: m.concept, value: money(m.run_cost_usd) }))}
          />
        )}
      </Section>

      <Section
        title="What this page cannot tell you"
        lede="Three things a reader would reasonably want that nothing in this system
              records. They are named here rather than left as blanks, because a blank
              reads as a zero."
      >
        <ul style={{ ...prose, paddingLeft: "1.1rem", margin: ".2rem 0 0" }}>
          <li style={{ margin: ".4rem 0" }}>
            <strong>How many candidate links were considered and dropped, and why.</strong>{" "}
            When the map was built, many possible links between papers were considered
            and rejected, for several different reasons. Nothing counts them, so this
            page cannot say how much evidence never reached the map. Counting it has
            not been built yet.
          </li>
          <li style={{ margin: ".4rem 0" }}>
            <strong>What the map cost and how long it took, when it was not built
            from a request.</strong>{" "}
            A map built directly by the team, rather than through a request on this
            site, leaves no run record, and nothing
            else in this system holds either figure. {runRecordSentence}
          </li>
          <li style={{ margin: ".4rem 0" }}>
            <strong>Whether the map is right.</strong>{" "}
            Every number here is counted from the map itself. Deciding whether the
            account it gives is correct needs the papers and a reader, which is what
            the quotes on the evidence page are for.
          </li>
        </ul>
      </Section>

      <p style={{ ...mono, fontSize: ".68rem", color: "var(--ink-faint)", lineHeight: 1.8,
        marginTop: "2.4rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}>
        Every figure here was counted from the map when you loaded this page. None of
        them is stored, so an edit to the map changes them at once, and nothing here
        can be out of date.
      </p>
    </main>
  );
}

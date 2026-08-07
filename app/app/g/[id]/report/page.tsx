import Link from "next/link";
import { notFound } from "next/navigation";
import { getViewer, isOwner } from "../../../../lib/authz";
import { listMapReports, type MapReport } from "../../../../lib/report";

export const dynamic = "force-dynamic"; // computed on read, never stored

/**
 * What this map is made of (issue #30, `[F2]`).
 *
 * One screen, one column, no interactivity. Every number is selected from
 * migration 016's views, so this page and `pipeline/map_report.py` read one
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
  const [all, viewer] = await Promise.all([listMapReports(), getViewer()]);
  const r = all.find((m) => m.genealogy_id === Number(id));
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
      </Section>

      {/* "Corpus" was the team's word and this heading was its last appearance
          on the page (issue #124, item 5). The lede's date clause needed two
          reads and one of them was pure machinery. */}
      <Section
        title="When the papers were written"
        lede="Each paper is dated by the earliest date we can trust for it: whichever is
              earlier of the date the catalogue gives and the date built into its arXiv
              number. Read it as when the work first appeared, not as a publication
              date. A paper with no year is counted separately and never guessed at."
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
          {r.year_counts && Object.keys(r.year_counts).length > 0 ? (
            <div style={{ display: "flex", alignItems: "flex-end", gap: "2px",
              marginTop: ".5rem", height: 90 }}>
              {Object.entries(r.year_counts)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([y, n]) => {
                  const peak = Math.max(...Object.values(r.year_counts!));
                  return (
                    <div key={y} style={{ display: "flex", flexDirection: "column",
                      alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
                      <span style={{ ...mono, fontSize: ".58rem", color: "var(--ink-faint)" }}>
                        {n}
                      </span>
                      <div title={`${y}: ${n}`} style={{
                        width: 16, height: `${Math.max(2, (n / peak) * 62)}px`,
                        background: "var(--line)", border: "1px solid var(--line)",
                      }} />
                      <span style={{ ...mono, fontSize: ".55rem", color: "var(--ink-faint)",
                        writingMode: "vertical-rl", marginTop: 3 }}>
                        {y}
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
            counts="The oldest defining paper in the map, which is the left end of the chart above."
            moves="The map being rebuilt and reaching further back, or a wrong year being corrected."
            others={others((m) => m.year_min, year)} />
          <Figure label="latest year" value={year(r.year_max)} absent="no years recorded"
            counts="The newest defining paper in the map, which is the right end of the chart above."
            moves="Only mapping the term again brings in newer work."
            others={others((m) => m.year_max, year)} />
          <Figure label="papers with no year" value={count(r.papers_with_no_year)}
            absent="not recorded"
            counts="Defining papers with no year at all. They are nowhere in the chart above and in neither figure, rather than being given a guessed date."
            moves="Only better publication dates for those papers. Nothing about the map itself moves this."
            others={others((m) => m.papers_with_no_year, count)} />
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

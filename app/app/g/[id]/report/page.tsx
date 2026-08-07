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
 * One figure, its two sentences, and the same figure on every other map.
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
 * `lead` is weight and nothing else: one step of type size, so that the figures
 * carrying the page's story are not identical to the page's bookkeeping. It is
 * never a colour, a badge or a mark of quality, because those are thresholds
 * however they are spelled.
 */
function Figure({
  label, value, counts, moves, absent, others, share, lead,
}: {
  label: string;
  value: string | null;
  counts: string;
  moves: string;
  absent: string;
  others: { concept: string; value: string | null; share?: string | null }[];
  share?: { value: string | null; absent: string };
  lead?: boolean;
}) {
  const shown = (o: { value: string | null; share?: string | null }) =>
    `${o.value ?? absent}${share ? ` (${o.share ?? share.absent})` : ""}`;
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
          {share && (
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: lead ? ".92rem" : ".82rem",
              color: "var(--ink-soft)",
              fontStyle: share.value === null ? "italic" : "normal",
            }}>
              ({share.value ?? share.absent})
            </span>
          )}
        </span>
      </div>
      <p style={{
        fontFamily: "var(--font-display)", fontSize: ".92rem", lineHeight: 1.55,
        color: "var(--ink-soft)", margin: ".35rem 0 0", maxWidth: "44rem",
      }}>
        {counts} {moves}
      </p>
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

  // What the per-source table is about to show, counted from its own rows. The
  // labels are read out rather than named, because the label is measured from
  // the paper row and F7 is what makes a second one appear.
  const sourceLabels = Array.from(new Set(r.buckets.map((b) => b.source)));
  const sourceSentence =
    sourceLabels.length === 0
      ? "This map holds nothing to split."
      : sourceLabels.length === 1
        ? `Every row of this map’s table carries the same label, “${sourceLabels[0]}”.`
        : `This map’s rows carry ${sourceLabels.length} different labels.`;

  const selfEdgeMaps = all.filter((m) => m.edges_within_one_node > 0).length;
  const selfEdgeSentence =
    selfEdgeMaps === 0
      ? `No map in this system has one: this reads zero on all ${n} of them.`
      : `${maps(selfEdgeMaps)} ${selfEdgeMaps === 1 ? "has" : "have"} at least one.`;

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
          which are checked word for word against the text extracted from each paper,
          and the <em>shape</em> (which papers were grouped together, which
          relationships exist and which way round they point, which paper matters
          most), which is this tool’s reading and not the history of the term. The
          figures below say how much of each this map holds; none of them is a score,
          and there is no grade, no colour and no pass mark anywhere on the page.
        </p>
        <p style={{ ...mono, fontSize: ".72rem", color: "var(--ink-faint)", marginTop: ".9rem" }}>
          <Link href={`/g/${id}`} style={{ color: "var(--edge-extends)" }}>← the map</Link>
          {" · "}
          <Link href={`/g/${id}/evidence`} style={{ color: "var(--edge-extends)" }}>
            the evidence and workbench
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

      <Section
        title="Coverage of the reading"
        lede="How many papers this map holds a reading of, and how many of those said
              they define the term. A paper that was selected but never fetched, or
              fetched but never read, leaves no row at all, so these count what was
              read and are a floor under what the run set out to read rather than the
              size of the corpus."
      >
        <Figure
          label="papers with a reading" lead
          value={count(r.papers_with_a_reading)} absent="not recorded"
          counts="Papers this map holds an extracted reading for, whether or not that reading found a definition."
          moves="Reading more papers moves it; so does a paper whose text could not be fetched or extracted, which never appears here at all."
          others={others((m) => m.papers_with_a_reading, count)}
        />
        <Figure
          label="papers that define the term" lead
          value={count(r.papers_defining)} absent="not recorded"
          counts="Of those, the ones whose reading found a definition of this term. This is the denominator of every definition figure below."
          moves="A re-read that changes a paper's verdict moves it, in either direction."
          others={others((m) => m.papers_defining, count)}
        />
        <Figure
          label="papers that do not define the term"
          value={count(r.papers_not_defining)} absent="not recorded"
          counts="Papers read and found not to define the term. That is a finding, not a gap, and it is reported here rather than folded away."
          moves="The same re-read. A verified fraction that quietly excluded these would read as a fraction of the corpus while being a fraction of the definers."
          others={others((m) => m.papers_not_defining, count)}
        />
      </Section>

      <Section
        title="Evidence"
        lede="How much of this map's evidence is currently string-matched against the
              papers' own extracted text. Three states, one per item, and they add up
              to the total by construction: verified, inferred (the check ran and did
              not match), and not re-checked (nothing has compared this quote to the
              text as it now stands)."
      >
        <Figure
          label="definitions verified" lead
          value={count(r.definitions_verified)} absent="not recorded"
          share={{ value: share(r.definitions_verified_share), absent: "no papers define the term" }}
          counts="Definition quotes found verbatim in that paper's own extracted text, against the text as it stands now, with the share of the papers that define the term beside it."
          moves="Re-reading the papers moves it, and so does the text itself changing, which makes a stamp not re-checked until the check is run again. The share reads absent rather than 0% when no paper defines the term, because a share of nothing is not zero."
          others={othersPair((m) => m.definitions_verified, (m) => m.definitions_verified_share)}
        />
        <Figure
          label="definitions inferred"
          value={count(r.definitions_inferred)} absent="not recorded"
          counts="Definition quotes where the check ran against the current text and did not find the passage."
          moves="A re-read that finds the passage, or an extraction change that loses it."
          others={others((m) => m.definitions_inferred, count)}
        />
        <Figure
          label="definitions not re-checked"
          value={count(r.definitions_stale)} absent="not recorded"
          counts="Definition quotes carrying no record of which bytes they were checked against, or a record that no longer matches the paper's text."
          moves="Re-running the free check moves them out of this state. Every stamp made before that record existed sits here until it is re-made."
          others={others((m) => m.definitions_stale, count)}
        />
        <Figure
          label="typed relationships"
          value={count(r.edges_total)} absent="not recorded"
          counts="Relationships between two of this map's states, each carrying a quote from both papers."
          moves="Re-running the classification, and deleting a relationship in the workbench."
          others={others((m) => m.edges_total, count)}
        />
        <Figure
          label="relationships verified" lead
          value={count(r.edges_verified)} absent="not recorded"
          share={{ value: share(r.edges_verified_share), absent: "no relationships" }}
          counts="Relationships where both quotes are string-matched against their papers' current text, with the share of every relationship in the map beside it. Both sides, not one: half a checked relationship is not a checked relationship."
          moves="The same re-check. This counts relationships, not quotes, and many relationships rest on the same quote. The share reads absent rather than 0% on a map with no relationships."
          others={othersPair((m) => m.edges_verified, (m) => m.edges_verified_share)}
        />
        <Figure
          label="relationships inferred"
          value={count(r.edges_inferred)} absent="not recorded"
          counts="Relationships where the check ran against both papers' current text and at least one quote was not found."
          moves="A re-check that finds both quotes."
          others={others((m) => m.edges_inferred, count)}
        />
        <Figure
          label="relationships not re-checked"
          value={count(r.edges_stale)} absent="not recorded"
          counts="Relationships with no record of the bytes they were checked against, or a record that no longer matches. A relationship whose paper is missing from our records sits here too, because a missing paper cannot support a check."
          moves="Re-running the free check. This can read as the whole map immediately after the records were introduced, which is honest rather than broken."
          others={others((m) => m.edges_stale, count)}
        />
      </Section>

      <Section
        title="By source"
        lede={`The same counts, split by where each paper came from. The split exists
              so that adding a source later changes this table visibly instead of
              changing one number quietly. A relationship is grouped by the pair of
              its two ends, so every relationship lands in exactly one row and the
              rows add up to the totals above. ${sourceSentence}`}
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
            {r.buckets.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: ".5rem .6rem", color: "var(--ink-soft)",
                  fontStyle: "italic" }}>
                  nothing to split: this map holds no definitions and no relationships
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Section>

      <Section
        title="Quote reuse"
        lede="A relationship carries each paper's own definition quote, so a paper on
              forty relationships contributes its one quote forty times. Far fewer
              distinct quotes than relationships is therefore the expected shape and
              not a fault; what it says is that a relationship does not carry evidence
              of its own. The number worth reading it against is how many distinct
              papers those relationships touch."
      >
        <Figure
          label="quote slots"
          value={count(r.quote_slots)} absent="no relationships"
          counts="Two per relationship, one for each end."
          moves="Only the number of relationships."
          others={others((m) => m.quote_slots, count)}
        />
        <Figure
          label="quote slots holding no text"
          value={count(r.quote_slots_empty)} absent="no relationships"
          counts="Slots whose quote is empty once whitespace is trimmed. A quote holding no text of the paper is not evidence, so these are excluded from the distinct count below."
          moves="A re-read that finds a passage for that paper."
          others={others((m) => m.quote_slots_empty, count)}
        />
        <Figure
          label="distinct quote strings"
          value={count(r.distinct_quote_strings)} absent="no quotes"
          counts="How many different passages the relationships actually rest on."
          moves="Reading more papers, and any change to how a paper's defining passage is chosen."
          others={others((m) => m.distinct_quote_strings, count)}
        />
        <Figure
          label="distinct papers on relationships"
          value={count(r.distinct_papers_on_edges)} absent="no relationships"
          counts="How many different papers appear at either end of a relationship. Read it beside the line above: the two should be close."
          moves="The same things. If the distinct quotes fall materially below this, two different papers are carrying the same passage, which is worth knowing."
          others={others((m) => m.distinct_papers_on_edges, count)}
        />
        <Figure
          label="most reused quote, uses"
          value={count(r.most_repeated_quote_uses)} absent="no quotes"
          counts="How many slots the single most repeated passage fills."
          moves="How central one paper is to the map, and nothing else."
          others={others((m) => m.most_repeated_quote_uses, count)}
        />
      </Section>

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
          moves="Re-running the grouping, and every split, merge or delete in the workbench."
          others={others((m) => m.nodes_total, count)}
        />
        <Figure
          label="meanings that could not be read"
          value={count(r.nodes_unreadable)} absent="not recorded"
          counts="Entries in the stored grouping that do not carry an identifier and a list of members. They are dropped from every other figure here and counted here instead of being guessed at."
          moves="Nothing should. Anything above zero means something wrote the grouping in a shape this system does not understand."
          others={others((m) => m.nodes_unreadable, count)}
        />
        <Figure
          label="meanings holding one paper"
          value={count(r.nodes_with_one_member)} absent="not recorded"
          share={{ value: share(r.nodes_with_one_member_share), absent: "no meanings" }}
          counts="Meanings with a single paper in them, with the share of every meaning in the map beside it."
          moves="Re-running the grouping, and merging two meanings by hand. The share reads absent rather than 0% on a map with no meanings."
          others={othersPair((m) => m.nodes_with_one_member, (m) => m.nodes_with_one_member_share)}
        />
        <Figure
          label="meanings with no link to another meaning"
          value={count(r.nodes_with_no_edge_to_another_node)} absent="not recorded"
          counts="Meanings that no relationship connects to a different meaning. These are what the evidence page lists as unconnected."
          moves="A new relationship reaching one of them, and any regrouping."
          others={others((m) => m.nodes_with_no_edge_to_another_node, count)}
        />
        <Figure
          label="largest meaning, papers in it"
          value={count(r.largest_node_members)} absent="no meanings"
          counts={`The biggest single group${r.largest_node_id ? ` (${r.largest_node_id})` : ""}, by how many papers it holds.`}
          moves="Re-running the grouping, and splitting it by hand."
          others={others((m) => m.largest_node_members, count)}
        />
        <Figure
          label="relationships touching the largest meaning" lead
          value={count(r.largest_node_edges)} absent="not recorded"
          share={{ value: share(r.largest_node_edges_share), absent: "no relationships" }}
          counts="Relationships with the largest meaning at either end, with the share of every relationship in the map beside it. It says how much of the map hangs off one group."
          moves="The same things, plus anything that changes which relationships exist. The share reads absent rather than 0% on a map with no relationships."
          others={othersPair((m) => m.largest_node_edges, (m) => m.largest_node_edges_share)}
        />
        <Figure
          label="pairs of meanings that are linked"
          value={count(r.node_pairs)} absent="not recorded"
          counts="Distinct ordered pairs of meanings carrying at least one relationship. Ordered, because a relationship says the later paper did something to the earlier one's idea, and the reverse is a different claim."
          moves="Any new or deleted relationship between two meanings that were not otherwise linked."
          others={others((m) => m.node_pairs, count)}
        />
        <Figure
          label="pairs carrying more than one kind of link"
          value={count(r.node_pairs_disagreeing)} absent="not recorded"
          counts="Pairs where the relationships between the same two meanings do not all say the same thing."
          moves="Reclassifying a relationship in the workbench, and re-running the classification."
          others={others((m) => m.node_pairs_disagreeing, count)}
        />
        <Figure
          label="relationships on those pairs"
          value={count(r.edges_on_disagreeing_pairs)} absent="not recorded"
          share={{ value: share(r.edges_on_disagreeing_pairs_share), absent: "no relationships" }}
          counts="How many relationships sit on a pair that carries more than one kind of link, with the share of every relationship in the map beside it. Read beside the count above: a few large pairs and many small ones are different findings."
          moves="The same things. The share reads absent rather than 0% on a map with no relationships."
          others={othersPair((m) => m.edges_on_disagreeing_pairs, (m) => m.edges_on_disagreeing_pairs_share)}
        />
        <Figure
          label="relationships inside one meaning"
          value={count(r.edges_within_one_node)} absent="not recorded"
          counts={`Relationships whose two ends are the same meaning. ${selfEdgeSentence}`}
          moves="Allowing papers within one meaning to be related to each other, which is queued work and is exactly what this line is here to measure before and after."
          others={others((m) => m.edges_within_one_node, count)}
        />
      </Section>

      <Section
        title="Corpus age"
        lede="When the papers behind this map appeared. The year stored for a paper is
              the earliest credible date we have for it, which is the earlier of the
              catalogue's date and the date encoded in the arXiv identifier; read it
              as when the work first appeared rather than as a publication date. A
              paper with no year is counted separately and never guessed at."
      >
        <Figure label="earliest year" value={year(r.year_min)} absent="no years recorded"
          counts="The oldest defining paper in the map."
          moves="Reading further back, and any correction to a stored year."
          others={others((m) => m.year_min, year)} />
        <Figure label="lower quartile" value={year(r.year_p25)} absent="no years recorded"
          counts="A quarter of the defining papers are this old or older."
          moves="The distribution of what was read."
          others={others((m) => m.year_p25, year)} />
        <Figure label="median year" value={year(r.year_median)} absent="no years recorded"
          counts="Half the defining papers are this old or older."
          moves="The distribution of what was read."
          others={others((m) => m.year_median, year)} />
        <Figure label="upper quartile" value={year(r.year_p75)} absent="no years recorded"
          counts="Three quarters of the defining papers are this old or older."
          moves="The distribution of what was read."
          others={others((m) => m.year_p75, year)} />
        <Figure label="latest year" value={year(r.year_max)} absent="no years recorded"
          counts="The newest defining paper in the map."
          moves="Re-running the search, which is the only thing that brings in newer work."
          others={others((m) => m.year_max, year)} />
        <Figure label="papers with no year" value={count(r.papers_with_no_year)}
          absent="not recorded"
          counts="Defining papers with no year at all. They are left out of the five figures above rather than being given a guessed date."
          moves="Better metadata for those papers."
          others={others((m) => m.papers_with_no_year, count)} />

        <div style={{ marginTop: ".9rem" }}>
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
      </Section>

      <Section
        title="The run"
        lede="What building this map took. These come from the record kept while a
              map is being built for someone who asked for it, so a map built from the
              command line has none of them and says so. Where a figure reads not
              recorded, nothing in this system holds it; it is not zero and it is not
              an estimate."
      >
        <Figure
          label="runs recorded"
          value={count(r.runs_recorded)} absent="not recorded"
          counts="Completed runs this system has a record of for this map. The figures below describe the most recent one, not the map's whole life."
          moves="Mapping the term again. A map built from the command line has none, and every figure below then reads not recorded."
          others={others((m) => m.runs_recorded, count)}
        />
        <Figure
          label="time the run took" lead
          value={r.run_wall_clock === null ? null : duration(r.run_wall_clock)}
          absent="not recorded"
          counts="From the run starting to the run finishing, for the most recent completed run."
          moves="The size of the corpus, and how much of it was already read and cached."
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
            moves="The size of the corpus and how much of it was already read. A repair or a second run does not add to it."
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
            The classification discards candidate pairs for several different reasons
            and counts none of them, so the amount of evidence that did not reach the
            map is not knowable from here. That counting is queued work.
          </li>
          <li style={{ margin: ".4rem 0" }}>
            <strong>What the map cost and how long it took, when it was not built
            from a request.</strong>{" "}
            A map built from the command line leaves no run record, and nothing
            else in this system holds either figure. {runRecordSentence}
          </li>
          <li style={{ margin: ".4rem 0" }}>
            <strong>Whether the map is right.</strong>{" "}
            Every number here comes from the map’s own rows. Deciding whether the
            account it gives is correct needs the papers and a reader, which is what
            the quotes on the evidence page are for.
          </li>
        </ul>
      </Section>

      <p style={{ ...mono, fontSize: ".68rem", color: "var(--ink-faint)", lineHeight: 1.8,
        marginTop: "2.4rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}>
        Counted from this map’s own rows when you loaded the page. Nothing on it is
        stored, so a change to the map changes these figures immediately and no figure
        here can outlive what it describes.
      </p>
    </main>
  );
}

import Link from "next/link";

/** The terms of use (issue #160). Fixed prose, no data, so it prerenders like
 *  /about and /roadmap and costs the reader nothing.
 *
 *  Two sentences on this page are the product's central promise restated in a
 *  place a reader may treat as binding, so they are the settled words and not
 *  new ones: "the tool's reading" for the shape (product rule 3) and "found word
 *  for word in the text this system pulled out of the paper" for the stamp
 *  (rule 2, and the wording law of issues #129 and #135, recorded in
 *  lib/stamp.ts). A terms page is the last surface that may state the promise
 *  more strongly than the product supports, and it must never be the one that
 *  quietly widens it. If the wording law moves, this page moves with it. */

export const metadata = { title: "Terms of use" };

/** Shown at the top and in the closing line. One constant, because a terms page
 *  whose date disagrees with itself is worse than one with no date. */
const VERSION_DATE = "8 August 2026";

export default function TermsPage() {
  return (
    <main style={{ maxWidth: 780, margin: "0 auto", padding: "1rem 1.5rem 5rem" }}>
      <header style={{ borderBottom: "2px solid var(--line)", padding: "0 0 1.3rem", marginBottom: "1.8rem" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "2rem", margin: 0 }}>
          Terms of use
        </h1>
        <p style={{ color: "var(--ink-soft)", margin: ".7rem 0 0", lineHeight: 1.6 }}>
          What you agree to by using Lineage, what it promises, and what it does not. It is short
          because this is a research tool built and paid for by one person, not a service you are
          buying.
        </p>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-faint)",
          margin: ".8rem 0 0", letterSpacing: ".04em" }}>
          CURRENT VERSION · {VERSION_DATE}
        </p>
      </header>

      <Section title="What Lineage is">
        <P>
          You name a term. Lineage reads papers on arXiv around it and lays out how the term
          developed: the lines of work it split into, the papers that moved it, and typed
          relationships between specific papers, with a quote from each paper behind every claim.
        </P>
        <P>
          Two things are stated precisely here, because everything else on this page rests on them
          and because they are the whole of what the product guarantees.
        </P>
        <div style={{ display: "flex", flexDirection: "column", gap: ".6rem", margin: ".2rem 0 .9rem" }}>
          <Claim label="The shape of a map is the tool’s reading" color="var(--edge-narrows)">
            Which papers group together, which relationships exist and in which direction, which
            papers mattered most: those are produced by a machine from the evidence shown beside
            them, and they are labelled as the tool&rsquo;s reading wherever they appear. A map is one
            reconstruction of how a term developed. It is not the history of the term, it is not peer
            review, and it is not a systematic review of a literature.
          </Claim>
          <Claim label="The verified stamp means one thing" color="var(--verified)">
            A quote marked <strong style={{ color: "var(--verified)" }}>✓ verified</strong> was found
            word for word in the text this system pulled out of the paper. That check is mechanical
            and it holds. It is not a check against the published paper, and it says nothing about
            whether the quote was well chosen or whether the reading beside it is right. Quotes the
            check could not find are marked and shown, never hidden and never upgraded.
          </Claim>
        </div>
        <P>
          Nothing on this site promises more than those two boxes do. Treat a map as a starting point
          you can check in seconds rather than as an answer, and when you cite something, cite the
          paper.{" "}
          <Link href="/about" style={{ color: "var(--edge-extends)" }}>How it works</Link> sets out
          the method and its limits in full, and is the honest place to start if you are deciding
          whether to rely on this.
        </P>
      </Section>

      <Section title="Whose words these are">
        <P>
          The papers and every quote taken from them belong to their authors. Lineage claims no
          rights in them and grants you none. Full text comes from arXiv, and the metadata and
          citation sentences from OpenAlex and Semantic Scholar. Your use of that material is subject
          to those services&rsquo; own terms and to whatever license each author chose for their paper;
          arXiv carries several, and some are more restrictive than others.
        </P>
        <P>
          Quotes appear here so a claim can be checked against the paper that made it, in the amount
          that takes and no more. The export exists so you can carry a map&rsquo;s structure and its
          citations into your own research writing. Use it for that. Check anything you intend to
          publish against the paper itself, and credit the paper rather than this site.
        </P>
      </Section>

      <Section title="Signing in">
        <P>
          Every map can be read without an account. Signing in with GitHub does two things: it lets
          you request a map of a new term, and it tells the site whether you are the owner, who is
          the only person able to edit a map today.
        </P>
        <P>
          What that stores: your GitHub login, with the display name and picture GitHub returns
          alongside it, held in a session cookie in your browser. A request you submit is recorded
          with your login, the term, and the note you wrote with it. An edit to a map is recorded
          with the login of whoever made it and stays in that map&rsquo;s audit trail, which is
          permanent on purpose: it is what lets a reader see how much human judgment a map has had.
          Lineage asks GitHub for nothing beyond who you are, and writes nothing to your GitHub
          account.
        </P>
        <P>
          Requests are reviewed before they run, because reading a set of papers costs real money in
          model usage and the owner pays for it. A request can be declined, and there is no
          undertaking that any request will run or that a map will be kept once built.
        </P>
      </Section>

      <Section title="No warranty, no liability">
        <P>
          Lineage is provided as is and as available, with no warranty of any kind. It may be wrong,
          incomplete, offline, or withdrawn. Maps can be rebuilt, changed or removed. Nothing on it
          is professional advice.
        </P>
        <P>
          The owner accepts no liability of any kind, to the maximum extent the law permits, for
          anything arising from your use of this site or of anything taken from it, including
          anything you wrote or published on the strength of a map. Checking what you use is yours to
          do, and the quotes, the stamps and the links back to arXiv are here so that it takes
          seconds.
        </P>
      </Section>

      <Section title="The code’s license is a separate thing">
        <P>
          The source is public at{" "}
          <a href="https://github.com/rgok001/Lineage" target="_blank" rel="noopener noreferrer"
            style={{ color: "var(--edge-extends)" }}>github.com/rgok001/Lineage</a>{" "}
          under the PolyForm Noncommercial License 1.0.0. That license governs what you may do with a
          copy of the code. It does not govern this site, and using this site is governed by this
          page instead. Neither one grants you any rights in the papers or in anything quoted from
          them.
        </P>
      </Section>

      <Section title="These terms can change">
        <P>
          They can, and this page is always the current version, dated {VERSION_DATE} at the top.
          No notice is sent and no archive of older versions is kept here; the repository&rsquo;s
          history holds every earlier wording of this page, as it does for the rest of the site.
        </P>
      </Section>

      <p style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-faint)",
        lineHeight: 1.8, marginTop: "2rem", paddingTop: "1rem", borderTop: "1px solid var(--line-soft)" }}>
        These terms are written in ordinary language on purpose: terms nobody reads protect nobody,
        and a tool whose whole point is that you can check it should be able to say what it promises
        in sentences you can check too. If something here is unclear, or looks wrong, ask on the{" "}
        <a href="https://github.com/rgok001/Lineage/issues" target="_blank" rel="noopener noreferrer"
          style={{ color: "var(--edge-extends)" }}>repository&rsquo;s issues</a>.
      </p>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: "2.2rem" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.3rem",
        color: "var(--ink)", margin: "0 0 .7rem" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ margin: "0 0 .8rem", color: "var(--ink)", fontSize: ".94rem", lineHeight: 1.7 }}>
      {children}
    </p>
  );
}

/** The two guarantees, drawn like /about's trust tiers so a reader who has seen
 *  that page recognises them as the same claim rather than a new one. */
function Claim({ label, color, children }: { label: string; color: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderLeft: `3px solid ${color}`,
      borderRadius: "0 8px 8px 0", padding: ".7rem .9rem" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem", letterSpacing: ".12em",
        textTransform: "uppercase", color }}>{label}</div>
      <p style={{ margin: ".3rem 0 0", fontSize: ".88rem", lineHeight: 1.6, color: "var(--ink-soft)" }}>
        {children}
      </p>
    </div>
  );
}

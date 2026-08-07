import { sql } from "./db";
import { actorTally, curatorialEdits, getRiver, readableQuote, type River, type RiverStream, type UserEdit } from "./genealogy";
import { stampOf, type StampState } from "./stamp";

/**
 * Export for writing: the thread account as a related-work scaffold, plus the
 * BibTeX for exactly the papers it cites.
 *
 * A *scaffold*, deliberately. It supplies the real structure, real citations and
 * real quotes, and leaves the argument to the author. Nothing is invented
 * (CLAUDE.md rule 4): papers whose authors are unknown are reported and omitted
 * from BibTeX rather than guessed, and the three tiers stay apart on the page,
 * because this text is going into someone's paper. A quote is verbatim and
 * string-verified, a "what it did" line is the tool's reading, and neither is
 * allowed to look like the other.
 *
 * This mirrors what a reader sees at /g/[id] and /g/[id]/river/[sid]. The older
 * CLI export (pipeline/export_related_work.py) still writes the sense-shaped
 * document from nodes and edges; it is kept because the pipeline is CLI-first.
 */

type PaperMeta = {
  title: string; year: number | null; authors: string[];
  quote: string | null; verified: boolean | null; stamp: StampState;
};

const STOP = new Set(["a", "an", "the", "on", "of", "in", "for", "and", "with", "is", "are", "to", "by"]);

const asciiKey = (s: string) =>
  s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9]/g, "").toLowerCase();

/** Sources mix "Surname, Given" and "Given Surname", sometimes within one author
 *  list, so a naive last-token split yields keys like `alex2013`. Particles stay
 *  with the surname: "Aaron van den Oord" gives "van den Oord". */
function surnameOf(name: string): string {
  if (name.includes(",")) return name.split(",", 1)[0].trim();
  const parts = name.trim().split(/\s+/);
  if (!parts.length) return name;
  let i = parts.length - 1;
  while (i > 0 && /^[a-z]/.test(parts[i - 1])) i--;
  return parts.slice(i).join(" ");
}

function citeKey(authors: string[], year: number | null, title: string, taken: Set<string>): string {
  const surname = authors.length ? asciiKey(surnameOf(authors[0])) : "anon";
  const word =
    (title || "").match(/[A-Za-z]+/g)?.find((w) => !STOP.has(w.toLowerCase()) && w.length > 2) ?? "paper";
  const base = `${surname}${year ?? ""}${asciiKey(word)}`;
  let key = base;
  let i = 0;
  while (taken.has(key)) key = base + String.fromCharCode(97 + i++);
  taken.add(key);
  return key;
}

const texEscape = (s: string) =>
  s.replace(/\\/g, "\\textbackslash{}").replace(/([&%$#_])/g, "\\$1");

/** The river is generated JSON, so a field typed as a string is not guaranteed
 *  to be one. The thread page guards the same way; anything that is not a
 *  string is treated as absent rather than rendered as "[object Object]". */
const clean = (s: unknown) => (typeof s === "string" ? s.replace(/\s+/g, " ").trim() : "");

const slug = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "thread";

/**
 * One line about who curated this map, for a document going into a paper.
 * Empty string when nobody curated it, and the caller writes nothing.
 *
 * This used to read "Curated by hand: N workbench edit(s) applied", which claims
 * human agency from a count that cannot support it — the same claim the as-built
 * had to retract about the embedding map, travelling into somebody else's
 * manuscript. Two things carry the honesty now. The count is of curatorial ops
 * only, so a restore after an incident is not reported as somebody's editorial
 * work. And the claim is carried by the actors, each with the basis on which its
 * name is known, with the entries that name nobody counted as naming nobody.
 */
export function curationNote(edits: unknown): string {
  const curated = curatorialEdits(edits);
  if (!curated.length) return "";
  // "(s)" is the machine's plural and "workbench" is a word the reader meets
  // only if they are the owner, in the document that lands in somebody else's
  // manuscript (issue #130). #120 settled on "changes by hand" for this same
  // count on the home card; its twin in pipeline/export_related_work.py says the
  // same words, because the two move together or not at all.
  const head = `> ${curated.length} change${curated.length === 1 ? "" : "s"} by hand applied`;
  const { parts, anyKnown } = actorTally(curated);
  return anyKnown ? `${head}: ${parts.join(", ")}.`
                  : `${head}. No actor is recorded for any of them.`;
}

const span = (s: RiverStream) => {
  const years = s.papers.map((p) => p.year).filter((y): y is number => typeof y === "number");
  if (!years.length) return "";
  const lo = Math.min(...years), hi = Math.max(...years);
  return lo === hi ? ` (${lo})` : ` (${lo}\u2013${hi})`;
};

export type ExportResult = { markdown: string; bibtex: string; basename: string };

/**
 * Build the two files for a whole map, or for one thread of it.
 * Returns null when the map has no generated threads, which is the same
 * condition that sends /g/[id] to the evidence view.
 */
export async function buildExport(id: number, threadId?: string): Promise<ExportResult | null> {
  const data = await getRiver(id);
  if (!data) return null;
  const { concept, river } = data;

  const g = (await sql`
    SELECT concept, prompt_version, COALESCE(user_edits, '[]'::jsonb) AS edits
    FROM genealogies WHERE id = ${id}
  `) as { concept: string; prompt_version: string; edits: UserEdit[] }[];
  if (!g.length) return null;
  const pv = g[0].prompt_version;

  const scope: RiverStream[] = threadId
    ? river.streams.filter((s) => s.id === threadId)
    : river.streams;
  if (!scope.length) return null;
  const one = threadId ? scope[0] : null;

  const arxivs = [...new Set(scope.flatMap((s) => s.papers.map((p) => p.arxiv)))];
  const rows = (await sql`
    SELECT p.arxiv_id AS arxiv, p.title, p.year, p.authors,
           d.verbatim_quote, d.quote_verified,
           d.quote_text_digest, p.extracted_text_digest
    FROM papers p
    LEFT JOIN definitions d ON d.paper_id = p.id
      AND d.concept = ${g[0].concept} AND d.prompt_version = ${pv} AND d.defines_concept = true
    WHERE p.arxiv_id = ANY(${arxivs})
  `) as { arxiv: string; title: string; year: number | null; authors: string[] | null;
          verbatim_quote: string | null; quote_verified: boolean | null;
          quote_text_digest: string | null; extracted_text_digest: string | null }[];

  const meta = new Map<string, PaperMeta>();
  for (const r of rows)
    meta.set(r.arxiv, {
      title: r.title, year: r.year,
      authors: Array.isArray(r.authors) ? r.authors : [],
      quote: r.verbatim_quote, verified: r.quote_verified,
      stamp: stampOf(r.quote_verified, r.quote_text_digest, r.extracted_text_digest),
    });

  // Keys are assigned in the order the papers are read, so a reader following
  // the document sees them appear in that order too.
  const taken = new Set<string>();
  const keys = new Map<string, string>();
  for (const s of scope)
    for (const p of s.papers) {
      if (keys.has(p.arxiv)) continue;
      const m = meta.get(p.arxiv);
      keys.set(p.arxiv, citeKey(m?.authors ?? [], m?.year ?? p.year ?? null, m?.title ?? p.title, taken));
    }

  /* ── BibTeX ─────────────────────────────────────────────────────────── */
  const bib: string[] = [
    "% Generated by Lineage. Every entry below is real metadata from OpenAlex/arXiv.",
    "% Nothing here is invented; papers with unknown authors are omitted, not guessed.",
    "",
  ];
  const noAuthors: string[] = [];
  for (const [arxiv, key] of keys) {
    const m = meta.get(arxiv);
    if (!m || !m.authors.length) { noAuthors.push(arxiv); continue; }
    bib.push(`@misc{${key},`);
    bib.push(`  title         = {{${texEscape(m.title)}}},`);
    bib.push(`  author        = {${m.authors.map(texEscape).join(" and ")}},`);
    if (m.year) bib.push(`  year          = {${m.year}},`);
    bib.push(`  eprint        = {${arxiv}},`);
    bib.push("  archivePrefix = {arXiv},");
    bib.push("}\n");
  }
  if (noAuthors.length)
    bib.push(`% Omitted for want of author metadata: ${noAuthors.join(", ")}`);

  /* ── Markdown ───────────────────────────────────────────────────────── */
  const md: string[] = [];
  const paperCount = arxivs.length;

  md.push(one ? `# ${clean(one.name) || one.id}\n` : `# How "${concept}" developed\n`);

  // "(s)" is the machine talking, in the one output the reader takes away and
  // pastes into their own draft (issue #128). It is the defect #120 removed from
  // the home card and the audit trail, in the highest-visibility surface the
  // product has, and it was not in that ticket. Pluralised in both directions,
  // driven by the count rather than sidestepped.
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  // **A count under the bare word "papers" says which papers it means** (issues
  // #123, #133). This was the fifth surface printing one and the only one the
  // reader keeps: a researcher who quotes "Lineage read 84 papers" in a
  // literature review has written a number whose population nothing states, in
  // the one file read away from every page that would explain it. `arxivs` is
  // built from the papers in `scope`, so the population to name is exactly what
  // the reader is holding. No number changes and no claim is added.
  const threads = river.streams.length;
  const provenance = one
    ? `> One thread of ${threads} from the "${concept}" map, covering ` +
      `the ${plural(paperCount, "paper")} in it. The other threads are not represented here.`
    : `> Generated by Lineage from the ${plural(paperCount, "paper")} in ` +
      `${threads === 1 ? "this thread" : `these ${threads} threads`}.`;
  md.push(provenance);
  // The not-re-checked clause was protected by #128 and is changed here on the
  // UX ruling that superseded it (issue #129): the export is read furthest from
  // any page that could explain "extracted", so it needs the plainest wording of
  // the three surfaces, not the most protected. The claim is unchanged.
  md.push(
    ">\n" +
      "> Every quotation was copied word for word from the paper's own text, and\n" +
      "> checked against that text. Quotes marked *inferred* failed that check and\n" +
      "> must be re-checked before use. Quotes marked *not re-checked* have not been\n" +
      "> matched against the paper's text as it now stands, so they carry no current\n" +
      "> verification either. Lines labelled *the tool's reading* are\n" +
      "> model judgment, not quotation, and carry no verification.\n" +
      ">\n" +
      "> **This is a scaffold, not prose.** The citations, quotes and structure are\n" +
      "> real; the argument is yours to write.",
  );
  const note = curationNote(g[0].edits);
  if (note) md.push(`>\n${note}`);
  md.push("");

  if (one) {
    // Name the threads this one connects to, so a slice never reads as the whole
    // story of the term.
    const nameOf = (sid: string) => clean(river.streams.find((s) => s.id === sid)?.name) || sid;
    const touching = river.cross_currents.filter((c) => c.from === one.id || c.to === one.id);
    if (touching.length) {
      const others = [...new Set(touching.map((c) => (c.from === one.id ? c.to : c.from)))];
      md.push(`> Connects to: ${others.map(nameOf).join(", ")}.\n`);
    }
    if (clean(one.arc)) md.push(`${clean(one.arc)}\n`);
  } else {
    if (clean(river.through_line)) md.push(`${clean(river.through_line)}\n`);
    md.push("_[Write your framing paragraph here: which thread matters for your work, and why.]_\n");
  }

  scope.forEach((s, i) => {
    if (!one) {
      md.push(`\n## ${i + 1}. ${clean(s.name)}${span(s)}\n`);
      if (clean(s.tagline)) md.push(`*${clean(s.tagline)}*\n`);
      if (clean(s.arc)) md.push(`${clean(s.arc)}\n`);
    }
    for (const p of s.papers) {
      const key = keys.get(p.arxiv)!;
      const m = meta.get(p.arxiv);
      const move = clean(p.move), prose = clean(p.prose);
      // The evidence is the paper's own definition span, the one Stage E
      // string-matched against the extracted source. The river's own "quote"
      // field is NOT used: it is generated paraphrase, and nothing that has not
      // passed the string match may leave here wearing a verified stamp.
      const quote = readableQuote(clean(m?.quote));
      // A paper with no author metadata has no BibTeX entry, so its key would
      // not resolve. Say so where the citation is, not only in the .bib.
      const dangling = m?.authors.length ? "" : "  *(citation incomplete: no author metadata for this paper)*";
      md.push(`\n**${m?.title ?? clean(p.title)}** (${p.year}) \\cite{${key}}${dangling}\n`);
      if (move) md.push(`What it did: ${move}  *(the tool's reading)*\n`);
      if (prose) md.push(`${prose}  *(the tool's reading)*\n`);
      if (quote) {
        // The stamp never over-claims: a quote is only marked verified when the
        // paper's definition quote passed the string match against text that is
        // still what the paper's row describes. Anything else downgrades it,
        // because an unverified quote in someone's paper is the failure this
        // tool exists to avoid.
        //
        // A stale quote is exported rather than dropped (open question 3,
        // answered as the design proposed): it is still real text a real paper
        // contains, and omitting it would quietly narrow the account, which is
        // the mistake Stage H already refuses to make. It goes out under its own
        // caveat and never under the verified wording.
        // The verified stamp matches the document it sits in rather than the
        // pages (issue #135): the preamble and the other two stamps say "the
        // paper's own text", and a document read away from every page needs one
        // vocabulary inside itself above all. It said "verbatim against the
        // paper's own source text", which put the word on the check and named
        // the published paper as what was searched.
        const stamp = {
          verified: "\u2713 verified: found word for word in the paper's own text",
          inferred: "*(inferred: the check ran against the paper's text and could not find "
                  + "this passage, so re-check it before citing)*",
          stale: "*(not re-checked: this quote has not been matched against the "
               + "paper's text as it now stands, so it carries no current "
               + "verification. Check it against the paper before citing.)*",
        }[m?.stamp ?? "stale"];
        md.push(`> \u201C${quote}\u201D\n>\n> ${stamp}\n`);
      }
    }
    md.push(`\n_[Your synthesis${one ? "" : " of this thread"}: what it enabled, what it left unsolved.]_\n`);
  });

  const crossings = one
    ? river.cross_currents.filter((c) => c.from === one.id || c.to === one.id)
    : river.cross_currents;
  if (crossings.length) {
    const nameOf = (sid: string) => clean(river.streams.find((s) => s.id === sid)?.name) || sid;
    md.push(one ? "\n## Where this thread connects\n" : "\n## Where threads crossed\n");
    md.push("Each crossing is where one line of work fed another. These are the tool's reading of\n" +
            "the corpus, not quotations.\n");
    for (const c of crossings)
      md.push(`- **${nameOf(c.from)}** \u2192 **${nameOf(c.to)}**${c.year ? ` (${c.year})` : ""}: ${clean(c.label)}`);
    md.push("");
    if (!one) md.push("_[Your paragraph tying these crossings into a narrative.]_\n");
  }

  const stem = one
    ? `thread_${slug(clean(one.name) || one.id)}_${slug(concept)}_${pv}`
    : `related_work_${slug(concept)}_${pv}`;

  return { markdown: md.join("\n") + "\n", bibtex: bib.join("\n"), basename: stem };
}

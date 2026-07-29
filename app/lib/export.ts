import { sql } from "./db";
import { getRiver, readableQuote, type River, type RiverStream } from "./genealogy";

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
  quote: string | null; verified: boolean | null;
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
    SELECT concept, prompt_version, jsonb_array_length(COALESCE(user_edits, '[]'::jsonb)) AS edits
    FROM genealogies WHERE id = ${id}
  `) as { concept: string; prompt_version: string; edits: number }[];
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
           d.verbatim_quote, d.quote_verified
    FROM papers p
    LEFT JOIN definitions d ON d.paper_id = p.id
      AND d.concept = ${g[0].concept} AND d.prompt_version = ${pv} AND d.defines_concept = true
    WHERE p.arxiv_id = ANY(${arxivs})
  `) as { arxiv: string; title: string; year: number | null; authors: string[] | null;
          verbatim_quote: string | null; quote_verified: boolean | null }[];

  const meta = new Map<string, PaperMeta>();
  for (const r of rows)
    meta.set(r.arxiv, {
      title: r.title, year: r.year,
      authors: Array.isArray(r.authors) ? r.authors : [],
      quote: r.verbatim_quote, verified: r.quote_verified,
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

  const provenance = one
    ? `> One thread of ${river.streams.length} from the "${concept}" map, covering ` +
      `${paperCount} paper(s). The other threads are not represented here.`
    : `> Scaffold generated by Lineage from ${paperCount} paper(s) across ` +
      `${river.streams.length} thread(s).`;
  md.push(provenance);
  md.push(
    ">\n" +
      "> Every quotation was copied verbatim from the paper's own source text and\n" +
      "> string-verified against it. Quotes marked *inferred* failed that check and\n" +
      "> must be re-checked before use. Lines labelled *the tool's reading* are model\n" +
      "> judgment, not quotation, and carry no verification.\n" +
      ">\n" +
      "> **This is a scaffold, not prose.** The citations, quotes and structure are\n" +
      "> real; the argument is yours to write.",
  );
  if (g[0].edits) md.push(`>\n> Curated by hand: ${g[0].edits} workbench edit(s) applied.`);
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
        // paper's definition quote passed the string match. An explicit false
        // downgrades it, because an unverified quote in someone's paper is the
        // failure this tool exists to avoid.
        const stamp = m?.verified === true
          ? "\u2713 verified verbatim against the paper's own source text"
          : "*(inferred: could not be string-matched, re-check before citing)*";
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

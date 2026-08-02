# Lineage: As-Built Documentation

CLASS: derived
RECOMPUTED BY: the Developer, in the same commit as any behaviour change. This
is the only class of record that can go stale, and this is the largest file in
it — if a section cannot be checked against the code in a few minutes, that is a
reason to split it, not a reason to trust it.

This is the as-built record: a description of the system as it actually exists,
including the deviations and hard-won rules that shaped it.

Product law — what the system must do — lives in [CLAUDE.md](../CLAUDE.md), and
is decided rather than observed. This file says what is true of the system today
and is derived from the code, so this is the file that can go stale. Where the
two disagree, either the system is violating its own law or the law has moved:
say which, and fix whichever is wrong. Do not quietly edit this file to describe
intent the system does not actually have.

**What changed since 2026-07-19 (the paper-centric turn).** The product's face
moved twice in a week. It left the drift map (senses as the spine, a wall of
typed relationships) for a "river" of the concept's parallel currents, then left
the river metaphor as well: a map now opens on an **influence map** of the
papers themselves, and a current is called a **thread**, the word researchers
already use for a line of work and one that accommodates threads crossing. Four
things made that possible, all live: edges now keep the *basis* they used to
discard (what each paper did and how, with the citing sentence, migration 010);
every paper carries two magnitude scores that decide which papers appear on the
map and how large (migration 011); each map stores a generated set of threads
with per-thread accounts (migration 012, still named `streams` in the schema and
in `lib/genealogy.ts`); and a paper has its own dossier route. The old
sense-taxonomy and the raw relationship list still exist, demoted to a secondary
`/g/[id]/evidence` layer. See sections 3, 4, and 6 for the detail; what remains
is in GitHub Issues. Magnitude and thread generation ran as one-off scripts
against the showcase map until 2026-07-29; they are now stages F and G, and the
worker runs them, so a requested map arrives with a front door.

**This file is sections 1 to 7 only, as of 2026-08-02: current state, for
agents.** The rest of what used to be here moved out by reader. How to operate
the system is [RUNBOOK.md](RUNBOOK.md) (was section 8). Why the load-bearing
choices were made is [DECISIONS.md](DECISIONS.md) (was section 9). What went
wrong is [INCIDENTS.md](INCIDENTS.md) (was section 10). Open work is
[GitHub Issues](https://github.com/rgok001/Lineage/issues) (was section 11).
Section numbers and decision and incident numbers did not change, because they
are cited from commit messages and from other records.

---

## 1. The system at a glance

Lineage traces how an academic concept evolved across arXiv papers and
publishes the result as an interactive, evidence-backed account. A map opens as
an influence map: the pivotal papers placed by year, sized by how much later
work built on them for that term, riding in the threads the idea split into.
Underneath it still holds the typed relationships between papers, each backed by
verbatim quotes from both papers verified against the extracted source text. The
showcase map is "embedding" (`/g/10`, 134 defining papers of 187, 27
concept-states, 305 relationships, 9 threads, 476 claims; **never curated**, and
earlier drafts of this document said otherwise because that was the plan rather
than the record). Its `user_edits` is **not** empty, which this document, the
actor design and two rounds of testing all assumed: read against the live
database on 2026-08-01 it holds exactly one entry, incident 12's restore, dated
2026-07-31T13:13:24Z and carrying no actor key, correctly, being older than
decision 18. A restore is not curation (`CURATORIAL_OPS`, decision 18), so the
map is uncurated and now says so rather than counting that entry.
It sits **half-repaired** as
of 2026-07-31: its papers were re-extracted with the fixed extractor, its
definitions were not (incident 12 stopped the refresh), so its quotes were
copied from text that is no longer on disk and grounding now reports **201
verified of 305**, down from 286. That is the truth about the quotes it holds,
not a regression; finishing the refresh (~$8.45) is what returns them.
"attention" (`/g/13`, 88 definitions all verified, 287 relationships, 286
verified) is the second, the first built end to end by the worker, and **the
only map in the system built entirely on correctly extracted text**. The earlier "dropout"
map was deleted on 2026-07-26.

| Component | Technology | Where it runs | Cost |
|---|---|---|---|
| Web app | Next.js 15, Auth.js v5 | Vercel (Hobby), prod alias `lineage-green.vercel.app` | free |
| Database | Neon serverless Postgres, pgvector 0.8 | Neon (Vercel-linked account) | free tier |
| Pipeline | Python 3.12 CLI scripts | Anywhere with the repo and `.env` | LLM spend only |
| Trace worker | Python 3.12, single process | Render Background Worker (declared in `render.yaml`; the owner's laptop until the Render console setup is done) | ~$8/mo |
| LLM | Claude Sonnet (`claude-sonnet-5`) for extraction, classification and claim evidence; Claude Haiku (`claude-haiku-4-5`) for magnitude scoring and thread generation | n/a | ~$6 per 150-paper trace; +~$0.7 magnitude and threads; +~$3 claim checking on Sonnet (decision 17) |

External data sources, all keyless: **arXiv** (paper source, LaTeX-first,
throttled 1 request/3s), **OpenAlex** (corpus metadata and citation counts,
polite pool via mailto), **Semantic Scholar** (citation contexts on the public
`/graph/v1` endpoint; no API key needed, verified empirically).

The two runtime halves never talk to each other. The app writes and reads
Postgres; the worker reads and writes Postgres. Every interaction between them
is a row changing state, which is why either side can crash, redeploy, or move
machines without the other noticing.

**What the product cannot do, stated where it is true rather than where it is
planned** (also disclosed on `/about` under "Limitations and scope", and shaped
for the reader on `/roadmap`): arXiv-only coverage; a bounded corpus, so the map
is the scope of what was read and not of the field; exact string matching fails
closed to "inferred" when extraction mangles a passage; parallel discovery
without citation appears as unconnected meanings; edge types, confidences and
rationales are model judgment, mitigated by the quotes being shown and the
judgment being labelled. Moved here from section 11 on 2026-08-02: these are
properties of the system as built, not open work.

---

## 2. Repository layout

```
CLAUDE.md            product spec and non-negotiable rules
README.md            setup and CLI usage
render.yaml          Render blueprint for the trace worker
docs/                AS-BUILT.md (this file, sections 1-7: current state),
                     RUNBOOK.md (how to operate it), DECISIONS.md (why the
                     load-bearing choices were made), INCIDENTS.md (what went
                     wrong), ROADMAP.md (what to build next),
                     design/ (one file per design that needed writing down)
pipeline/            stages A-H + auxiliaries (Python, CLI-first; the worker
                     runs thirteen steps, see section 4)
  common.py          env loading, polite HTTP session, data_dir()
  check_extraction.py  audit of extracted-text fidelity (no model, no network)
  db/migrate.py      ordered SQL migrations, schema_migrations table
  db/migrations/     001..014
.claude/agents/      architect, developer, tester (Claude Code subagents)
worker/run.py        the trace worker (queue consumer)
app/                 Next.js app (Vercel root directory is app/)
  app/               routes: /, /trace (request a map), /about, /roadmap,
                     /g/[id] (the influence map), /g/[id]/river/[sid] (a thread's
                     account), /g/[id]/p/[arxiv] (a paper's dossier),
                     /g/[id]/evidence (the old detailed view + workbench),
                     /api/traces, /api/auth
                     layout.tsx + nav.tsx hold the one tab bar
  lib/               db.ts, authz.ts, genealogy.ts, traces.ts, actions
data/                DATA_DIR (gitignored): raw papers, texts, exports, models
```

Two environment files exist and are both gitignored: the repo root `.env`
(pipeline and worker) and `app/.env.local` (Next.js app). They intentionally
hold different `DATABASE_URL` values; see [RUNBOOK.md](RUNBOOK.md).

---

## 3. Data model

Six tables, migrations `001` through `014`, applied by
`python pipeline/db/migrate.py` (tracked in `schema_migrations`). Migrations
`008`-`009` are data fixes (paths relative to `DATA_DIR`; correcting future
publication years OpenAlex mis-dated). `010`-`012` carry the paper-centric turn
and are described inline below.

**papers** (001, 002): one row per fetched arXiv paper. Notable columns:
`raw_path` and `extracted_text_path` point into `DATA_DIR`;
`text_title_match` (002) records how well the extracted text matches the
claimed title. This guard exists because OpenAlex sometimes attaches the wrong
arXiv id to a work: the fetch succeeds but the text belongs to a different
paper. Real observed cases: arXiv 1810.04805 (BERT) and 1907.11692 (RoBERTa)
both carried unrelated titles. Downstream stages must filter
`text_title_match >= 0.5`.

**definitions** (001, 003, 004, 011): Stage B output, one row per
(paper, concept, prompt_version). That triple is the cache key, deliberately
excluding the model so a model switch does not re-bill an extracted corpus;
`model` (004) records provenance instead. `defines_concept` (003) exists
because a negative verdict ("this paper does not define the concept") is a
finding: before 003, negatives wrote no row, so every re-run re-paid the LLM
for most of the corpus. `embedding vector(1024)` holds the Stage C embedding.
`novelty_claims` (JSONB, from Stage B) lists what the paper claims it
contributed; it was extracted from the start and sat unused until the paper
dossier surfaced it as "what it contributed". `attention` and `displacement`
(REAL, migration 011) are the two per-paper magnitude scores that decide which
papers reach the influence map and how large they sit there (section 4):
attention is on-term weighted uptake (how much later work built on this paper
*for this term*), displacement is how far the paper moved the term's meaning
(embedding distance from the centroid of earlier definitions). Both are per
(paper, concept, prompt_version) because magnitude is relative to the term
being traced, and both are nullable (computed by a post-Stage-D job; the
earliest paper has no earlier work to be displaced from).

**genealogies** (001, 007, 012): the map itself. `nodes` is JSONB
(concept-states with members and year ranges), `user_edits` is the append-only
curatorial audit trail (each entry `{op, detail, at}` plus at most one of `by`
and `by_asserted`; decision 18), `spend_usd` accumulates cost, `status` is loosely one of
pending/running/complete/failed/aborted_spend_cap. Migration 007 adds
`UNIQUE (concept, prompt_version)`: Stage C now upserts on that key (stable id
across re-runs, in place), where it used to DELETE then INSERT and mint a new
id every run. That old pattern broke `/g/<id>` links on re-trace and orphaned a
`running` row when a run crashed between Stage C and Stage E (see section 10,
incident 4). Migration 012 adds `streams` JSONB: the generated threads (a
through-line, an array of threads each with its papers and a per-paper passage,
and the cross-currents where one thread fed another). The column and the types
in `lib/genealogy.ts` still carry the river vocabulary the interface has since
dropped; the reader sees "threads". Null until the generation job has run for
that map, and `/g/[id]` redirects to `/g/[id]/evidence` when it is null.

**edges** (001, 010): typed relationships between nodes, with FK to both papers,
both verbatim quotes, `confidence`, and `verified` (the grounding verdict).
`ON DELETE CASCADE` from genealogies. Migration 010 adds `rationale` and
`citation_context`: the *basis* of the edge. Stage D already generated a
one-sentence rationale (what the newer paper did to the concept and how) and
fetched the citing sentence from Semantic Scholar to make the classification,
then discarded both, keeping only the type label. It now stores them. The
rationale is model prose (labelled in the UI as the tool's reading, never
verified); the citation context is a verbatim S2 sentence but from S2's PDF
extraction, so it cannot pass our string-match grounding and is labelled
"per Semantic Scholar, not string-verified". Neither wears the verified stamp
the definition quotes carry.

The request also carries a **subject field** and an optional **sense gloss**
(migration 006): `field_id` (an OpenAlex field, default `fields/17` = Computer
Science) scopes corpus selection to a discipline; `gloss` disambiguates a
polysemous sense and flows into both the relevance query and Stage B's
extraction question. The field is not a disambiguator (polysemy collides
within a field: OS vs ML "kernel" are both CS); the gloss is. The worker reads
both from the row and passes them through as CLI args. The picker is at *field*
granularity (26 fields); a finer *topic*-level picker (~4500 topics) was
deferred as unnecessary for scoping.

**papers**, continued (013, 014): `extraction_verdict` (clean/suspect/damaged),
`extraction_signals`, `extraction_check_version` and `extraction_checked_at`
record what `check_extraction.py --write` found in that paper's extracted text
and which calibration found it. NULL means
unchecked, and `clean` means nothing was found rather than nothing is wrong: the
scan is a lower bound, so the column is never read as a certificate. The paper
dossier shows the note only when something *was* found, which is the honest
asymmetry. All four are cleared by `extract_text.py` whenever it rewrites the
paper's text, since the measurement describes the file that was just replaced
(decision 21), and `extraction_signals` empties to `'[]'` rather than nulling
because it is `NOT NULL`.
`extraction_check_version` (014) is a 12-character digest of the audit's own
thresholds, patterns and signal levels, computed at import. It closes the other
half of decision 21: a verdict is invalidated by the code that computes it as
well as by the text it describes, and only the second had a path back.
`--only-unchecked` now selects `extraction_checked_at IS NULL OR
extraction_check_version IS DISTINCT FROM <this version>`, so moving a threshold
re-measures the corpus at the worker's next start with nobody remembering to ask
(decision 25).

**trace_requests** (005, 006): the request inbox and the job queue in one table.
Status flow: `requested -> approved -> running -> complete`, plus `rejected`
and `failed`. `progress` JSONB is written live by the worker; `updated_at`
doubles as the worker heartbeat; `genealogy_id` links the finished map. A
partial unique index allows only one open request per concept, enforced at the
database level because app-level checks can be raced by simultaneous submits.

---

## 4. The pipeline

Eight lettered stages, A to H, each a standalone CLI script reading root `.env`.
The pipeline is CLI-first by rule: the worker orchestrates these same commands
and adds nothing to them.

**The worker runs thirteen steps, not eight**, and the difference is not
decoration: three things that began as optional auxiliaries are now part of a
finished trace. `check_extraction.py` audits the text the grounding check is
about to rest on (incident 11), `stage_b_extract.py --reground` recomputes the
definition stamps against the text actually on disk (decision 19), and
`enrich_authors.py` fills the author metadata the export cannot invent. In
order: select corpus, fetch papers, extract text, audit extracted text,
extract definitions (B), cluster concept-states (C), classify edges (D),
re-check definition quotes, ground and assemble (E), fill author metadata,
score magnitude (F), compose threads (G), check each claim (H). Earlier drafts
of this section said "eight stages plus auxiliaries", which was true of the
letters and wrong about what a trace actually consists of.

**Stage A part 1: corpus selection**
(`corpus_select.py <concept> --limit N --field fields/K --gloss "..." --json PATH`).
Metadata only; nothing is fetched or paid for before the corpus is chosen.
`--field` scopes to an OpenAlex field (default `fields/17` = Computer Science,
`all` disables) via `primary_topic.field.id`, replacing the old hardcoded CS
*concept* filter (concepts are deprecated). `--gloss` is an optional sense
clarification used as the relevance embedding query instead of the bare
concept, so a polysemous word ("kernel") retrieves the intended sense first;
the SEARCH still uses the bare concept for recall. Wide word, tight meaning.
Seeds come from OpenAlex relevance search (an OpenAlex "concept" mode exists
but the default is search: OpenAlex has no ML "attention" concept). Seeds are
filtered by an embedding relevance check (Voyage hosted API; the concept is
embedded as a "query", papers as "documents") with
**top-K retention, never an absolute cosine cutoff**: a 0.62 threshold once
deleted "Attention Is All You Need", which scores 0.567 (rank 21 of 400)
against the query "attention". The corpus then expands one hop through
citations, and expansion is **never relevance-filtered**: Bahdanau 2014, the
origin of attention, never says "attention" (it says "align") and scores lower
than the Adam optimizer paper against the query. Ancestors enter via
citations only. Stage A is recall; Stage B is the semantic gate. Output: a
ranked corpus JSON.

**Acquisition** (`fetch_papers.py <corpus.json>`, `extract_text.py`).
LaTeX source preferred, PDF fallback, 1 request per 3 seconds against arXiv.
Gotcha: some arXiv "LaTeX" source is really a PDF inside an `\includepdf`
stub; the extractor detects and unwraps this. Citation and cross-reference
macros are normalised before parsing: pylatexenc knows `\cite` but not natbib,
biblatex or a paper's own `
ewcommand`, and an unknown macro is dropped in
silence, taking the citation with it and stranding the punctuation around it
(section 10, incident 10). Any macro whose name contains "cite", in any case,
is folded to one mark first, so the rule covers names nobody has listed. **The
paper's own macros are expanded before that** (`expand_own_macros`, incident
11): `\newcommand`, `\renewcommand`, `\providecommand`, `\def` and
`\DeclareMathOperator` are collected with a brace-balanced scanner, their uses
substituted with arguments, the definitions themselves stripped, and the pass
repeated up to four times so a macro defined in terms of another resolves while
a self-referential one cannot spin. Expansion runs *before* the citation rule,
so a paper's own `\mycite` wrapper expands to the real citation command and then
folds to a mark. Extraction uses pylatexenc for
LaTeX and pymupdf with de-hyphenation for PDF, computes `text_title_match`,
and warns loudly below the 0.5 guard.

**A parse failure now costs a paragraph, not a paper.** pylatexenc raises on
some real arXiv sources (17 of attention's 146, every one an IndexError), and
`diagnose_parse.py` confirmed on 1512.08756 that it raises on the untouched
source too: not our preprocessing, and not fixable by a flag, since its
tolerant mode is already the default. The old fallback dropped the WHOLE file
to a regex that leaves braces and dollars standing and loses every heading, so
one unreadable construct cost a paper its entire text. `_parse_or_bisect` now
splits at a paragraph break and retries each half, to a depth of 6, stripping
only the piece that actually defeats the parser. Measured on a document with a
single bad paragraph: 8% stripped where it used to be 100%. A healthy paper
still parses in one pass and pays nothing.

**Audit** (`check_extraction.py [--concept C] [--sample N] [--write]`). The
extracted text is what the grounding check rests on, and its fidelity went
unmeasured until 2026-07-31. This scans for the marks damage leaves behind:
macros the parser still drops, `$`/`{`/`}` residue from a parse that fell back
to the raw strip, short inline symbols that left no trace, sections lost to a
dropped `\input`, undecodable bytes, and the punctuation an eaten token strands.
No model, no network. Macro loss is reported twice, before and after expansion,
so the fix's worth is measured rather than argued. It is a lower bound and says
so: it finds damage that leaves a mark, and the worst damage leaves none.
**Three of its signals are reported and do not decide the verdict**: `stale`,
`gaps`, and the package half of the macro count. Each is true and useful to an
operator, and none of them means what the dossier note says, which is that the
passage a reader is looking at may be missing wording (decision 25).
`--write` stores the verdict on the paper (migration 013) together with a digest
of the calibration that produced it (migration 014), and `--only-unchecked`
treats a verdict written by a different calibration as unchecked, so a threshold
change re-measures itself.
`--clear-verdicts [--concept C] [--only IDS] [--dry-run]` does the opposite and
is the only mode that needs no corpus: it removes the stored verdict, signals
and checked-at from the papers in scope so the free `--only-unchecked --write`
pass measures them again at the worker's next start. For rows whose verdict was
frozen before `extract_text.py` learned to clear its own (decision 21), and for
a machine that holds the database but not the papers. `--dry-run` prints the
tally and the range of dates it would clear, and renders a `SELECT` rather than
the `UPDATE`.
`--compare-verdicts` is the instrument for the fifth calibration, added
2026-08-01 and described under "The fifth attempt" below. It stores nothing and
refuses `--write`, `--clear-verdicts` and `--dry-run`. The fifth calibration has
since shipped, so its proposal set is empty and the mode says so rather than
printing a crosstab of no movement; the sole-cause table stands on its own and is
what the sixth round will read.

**First real measurement (2026-07-31, "embedding", 187 papers, 182 LaTeX).**
The macro fix was worth more than the incident that prompted it suggested.
**22,039 uses of the papers' own macros, across 133 of 182 papers (73%), would
have been dropped in silence before it**; 378 uses across 12 papers (7%) still
escape, mostly delimited `\def` parameters the expander declines to guess at.
Separately, 1,411 of 11,763 short inline symbols (12%) leave no trace in the
extracted text. Against that, only 10 of 187 stored quotes (5.3%) carry a
visible damage tell, which is the number that matters to a reader and the
reason the product was not obviously broken: the loss is broad across the
corpus and thin in the passages Stage B chose to quote.

The first run also invalidated this file's own thresholds. At the guessed
values, 160 of 182 papers came back "damaged", driven almost entirely by
dropped *package* macros, which this same file argues cost a reader nothing.
A verdict that fires on 88% of a corpus is not a verdict, and it would have put
a warning on nearly every paper page. Package macros can no longer reach
"damaged", and the residue bars moved from 4/30 to 25/150.

The second run then failed the same way for a different reason: 73% "suspect",
driven by a gap detector that guessed at *words* which "never" take a following
comma. On real papers it flagged "the batch size.", "And," and "a fixed number
of dimensions." as damage. It now tests shape rather than vocabulary: a space
before punctuation, an empty group, a group missing its front, a run of spaces
that tidy_marks would have closed. Those same signatures found "vectors of
dimension .", "a neural ranking model ()." and "( 200 dimensions)" in real
stored quotes, so the strictness cost nothing that mattered.

The third run failed too, and worse: 100% flagged, with gap counts in the
hundreds per paper. The structural patterns were written with `\s`, which
matches a newline, so `\s{2,}` meant "any indented line" and a paper's own
layout became evidence against it. Anchored to `\w` and literal spaces, the
same patterns find every real case from the corpus and score zero on wrapped,
indented, list-bearing text. **Whitespace that spans a line break is layout;
only whitespace inside a line can be a hole where a token stood.**

The fourth run answered the question the first three were really asking. The
marks that kept firing were fed back through the current extractor, and it
removes every one of them: it closes a space before punctuation, collapses runs
of spaces, deletes an emptied bracket pair. **A file containing them was
therefore not written by the current extractor.** The corpus on the Render disk
is text an older pipeline produced and nothing has re-extracted, so the audit
was not crying wolf and the thresholds were not the problem: it was reporting,
in the only vocabulary it had, that the fixes have never reached these files.
That is now its own signal, kept out of the verdict, because the answer to it is
re-extraction and that is a decision about the corpus rather than a warning
about a paper.

The counts never changed through any of this; only what the tool is willing to
call damage did. **Thresholds guessed against a synthetic sample are a
hypothesis, and the first real corpus is the test.** Twice now the corpus has
said the hypothesis was wrong, and both times the tell was the same: a check
that fires on most of its input is measuring itself.

**The fifth attempt does not adjust anything, it measures first**
(`--compare-verdicts`, 2026-08-01). Four rounds of calibration went 88%, 73%,
100%, 76%, and every one of them read the corpus rate, disliked it and moved a
pattern or a number. A rate can only say the check is wrong. It cannot say which
signal is wrong, so each round had to guess and find out afterwards, and the
thing that made the loop possible was that a signal had no name: it was a
sentence written for a reader, with counts in it, and nothing could group by it.

Three changes, none of which alters a verdict:

- **Every signal now carries a machine key.** A signal is `(level, key, prose)`.
  The prose is unchanged and is still what `--write` stores; the key is what the
  comparison groups by. The prose is deliberately not the identifier: it carries
  counts and percentages, and parsing it back would make every wording change a
  silent behaviour change.
- **`verdict_from(signals, demoted, source_scan)`** is the tail of `scan_paper`
  lifted out, so today's verdict and a proposed one are one implementation given
  two inputs rather than two copies that drift. `source_scan` is a parameter and
  not a convenience: without it, demoting a paper's last signal would return
  `clean` for a paper whose archive was never read, which is decision 23's
  failure reappearing in a preview.
- **`PROPOSED_NOTE_SIGNALS = frozenset({"gaps", "package_macros"})`**, a module
  constant. One hypothesis, hardcoded and reviewable, rather than a config file
  or a `--what-if` taking arbitrary thresholds, neither of which leaves a record
  of what was proposed on the day the measurement was taken.

`--compare-verdicts` prints two tables and writes nothing. The cross-tab is
today's verdict against the proposal's, per source format, with the count of
papers that would carry the dossier note under each. **The sole-cause table is
the one all four previous attempts lacked**: for each signal, how many papers it
fires on and on how many it is the only reason that paper is not clean. It also
prints the quote tells twice, as counted today and with a literal `...` folded
to `…`, so that effect is previewed rather than assumed.

Two causes of near-equal size sit behind the 76%, which is why the ticket that
does the measuring is separate from the ticket that changes the calibration:
fixing either alone lands around 63% and reads as failure. The measurement that
decides it has to be taken on the Render disk, which is the only machine holding
the corpus the 76% was measured on.

**And then it was taken, and the change is what it said** (2026-08-01, Render
shell, all 304 papers). The proposal was demoting `gaps` and `package_macros`
together, and all three criteria set before the run were met:

```
  all       304 papers          proposed →
      current ↓             clean    suspect    damaged    no text
      clean                    74          ·          ·          ·
      suspect                 105         98          ·          ·
      damaged                   ·          ·         15          ·
      no text                   ·          ·          ·         12
      would show the dossier note:  now 218 (72%)   proposed 113 (37%)
```

**72% to 37%, against 38% predicted offline. Nothing moved stricter: every
occupied cell is on or above the diagonal.** The largest remaining sole cause is
`symbols` at 16 of 304 (5.3%), well under the 15% bar that would have argued for
touching it, so the change is exactly the two demotions. **No threshold moved.**

The sole-cause table is also the live demonstration of why 1a's caption had to be
corrected. `gaps` was the only reason 33 papers carried a warning and
`package_macros` the only reason for 44, which sums to 77; the joint effect is
105. The 28-paper difference is co-occurrence, and an operator who added the two
columns would have concluded that demoting both buys 77 and that demoting one
buys half of that. It buys neither.

Shipped with it, and measured in the same run: a literal `...` is folded to `…`
before the shape tests, in the paper scan and in the quote tells alike. Gap tells
in stored quotes fall from 5 to 2 and quotes carrying any tell from 11 to 10.

**The verdict now records which calibration produced it** (migration 014,
decision 25). Nothing else in the change is visible to a reader: the two demoted
signals are still emitted, still stored in `extraction_signals` (as `note: ...`
rather than `suspect: ...`) and still printed by the audit, and
`app/app/g/[id]/p/[arxiv]/page.tsx` was not touched, because `quality !== "clean"`
was already the right condition once the tiers meant the right thing.

**What was verified about the gap detector while building this** (2026-08-01,
synthetic fixtures through the real extractor, plus 40 papers fetched fresh from
arXiv to a scratch directory and deleted afterwards; that scratch corpus is
today's extractor on today's papers and is therefore a **different population**
from the 32 papers of older text on the Render disk, so no rate from it is
comparable to the corpus rate):

- `GAP_STRONG`'s paren branch fires on faithful renderings of `\left(`, `\big(`,
  `\Big(`, a literal `$( x )$` and a thin space `$(\,x\,)$`. All four extract to
  `( x` and none of them lost anything.
- Its true positives are narrower than assumed. **A bare dropped macro consumes
  the space after its own name**, so `(\dmodel dimensions)` extracts to
  `(dimensions)` and `about (\dmodel 200 dimensions)` to `about (200 dimensions)`
  — no gap in either, which is the commonest shape of the loss. The branch only
  fires when the drop leaves the space standing, which needs math delimiters or
  empty braces: `($\dmodel$ 200 dimensions)` does extract to `( 200 dimensions)`.
- The second branch, two marks with nothing between them, has ordinary true
  positives: `x, $\dmodel$, y` extracts to `x,, y`.
- A literal `...` reaches that second branch, because `tidy_marks` closes the
  space in front of the dots first: `$x_1, ..., x_n$` extracts to `x_1,..., x_n`
  and `,.` matches. `\ldots` and `\dots` already render as `…` and score no hit,
  so folding the literal form to the same character is the shape of the fix, and
  it shipped in 1b.
  **Deleting the dots instead is not**: it turns `a,..., z` into `a,, z`, which
  the same branch then matches, so it manufactures the false positive it was
  removing. Confirmed through the real extractor: `x, $\dmodel$, y` extracts to
  `x,, y` and scores a hit, which is exactly the string the deletion would
  manufacture.

**And a finding about a different signal, not yet fixed.** `tidy_marks` is not
idempotent: rule 4 deletes an emptied bracket pair after rule 3 has already
closed the spaces before punctuation, so `word ( ) .` becomes `word .` in one
pass and `word.` only in a second. The `stale` signal's premise is that these
are marks today's extractor cannot make. It can. **Measured on the 40 freshly
fetched papers: 5 of 40 carry stale marks, 25 marks in total, and a second
`tidy_marks` pass removes every one of them.** `stale` stays out of the verdict
so no reader sees this, but it is the signal behind backlog item 4's count of
32 papers holding older text, and that count is therefore an upper bound.

**Stage B: definition extraction** (`stage_b_extract.py <concept> [--corpus JSON] [--dry-run]`).
For each paper with usable text, Claude answers: does this paper give the
concept a meaning of its own? If yes it must return the defining passage
verbatim, plus section and novelty claims (structured output via
`messages.parse()` and Pydantic). Negatives are cached (migration 003).
`--dry-run` estimates cost across models without an API call, using real
`count_tokens` when a key exists and a calibrated 2.6 chars/token heuristic
when not. A spend cap (`TRACE_SPEND_CAP_USD`) aborts cleanly mid-run.
`--refresh` re-extracts papers that already have a row, UPDATEing in place: `genealogies.nodes` holds definition_ids, so a delete-and-reinsert would mint new ids and orphan the curated node membership on every map built from that concept. It nulls the embedding, because the text it encodes has changed and stale is worse than absent: absent is visible to the re-embed step, stale is visible to nothing. Scope it with `--only <arxiv ids>`, which is what an audit hands you.
`--reground` is the free half of that repair: it re-checks the quotes already stored against the extracted text as it is now and rewrites `quote_verified` alone, leaving the quote, the embedding and everything else untouched. It calls the same `quote_is_grounded` Stage E calls, makes no model call and needs no API key, prints the verified count before and after, and reports separately the definitions it could not check because the paper's text is not on this disk. The worker runs it immediately before Stage E on every trace, so a definition's stamp is never older than the text it describes (decision 18).
`--corpus` scopes extraction to one trace's papers; without it the query takes
every extracted paper in the shared papers table, which is correct for
single-concept research use and wrong for the worker (section 10, incident 3).

**Stage C: clustering** (`stage_c_cluster.py <concept>`).
Embeds definitions via the Voyage hosted API (1024-dim, cached in
`definitions.embedding`), then agglomerative clustering with cosine distance
and no fixed k. `DEFAULT_THRESHOLD = 0.16` was calibrated on bge-large
distances back when embeddings were local, so it may want re-tuning for Voyage
vectors; clustering granularity is a curatable draft either way. `--embed-only` fills missing vectors and stops before clustering: Stage C writes `nodes` wholesale on conflict, so a re-run costs a curated map its labels and merges. It is the second step of the repair path after `stage_b_extract.py --refresh`, and the reason that path does not simply re-run the pipeline.
The original calibration:
the soft-alignment and self-attention cores sit ~0.16 apart, and a bridge pair
(Show-Attend-Tell / Transformer) is 0.161, so 0.19 would merge the two senses
the product exists to distinguish. 0.16 over-splits weak singletons on
purpose: merge is a one-click curatorial act, un-merge is not. Stage C output
is a draft for curation, not a result. Claude labels each cluster (pennies).
**Stage C no longer clears the map's edges unconditionally** (decision 20). Per
edge endpoint, it compares what each node id denoted before against what it
denotes now, and removes only the edges whose concept-states have changed
underneath them; the rest are left for Stage D to replace on its first success.
When nothing about the previous concept-states could be read, every edge clears
and it says *that* rather than reporting a clustering change it cannot support.
A re-run at the same threshold on an unchanged corpus **with cached embeddings**
reproduces the same clustering and so keeps every edge. Not with `--force`,
which re-embeds: vectors are stored at six decimal places, so a pair sitting on
the threshold can cross it and the clustering can move. The read, the node
upsert and the edge decision are one transaction.

**Stage D: edge classification** (`stage_d_edges.py <concept>`).
Pulls references and citation contexts from Semantic Scholar (public endpoint,
disk-cached in `data/s2_cache`; the shared anonymous pool throttles hard on
repeat runs and the client backs off through 429s). Finds citations that cross
node boundaries, then Claude classifies each into the six-type taxonomy with a
confidence score. The LLM classifies only: edge quotes are the two papers'
Stage B definition quotes, never the S2 citation context, because S2's text
comes from its own PDF extraction and will not string-match our LaTeX-derived
text. Direction convention: cited = ancestor = source; citing = descendant =
target.

**Stage E: grounding and assembly** (`stage_e_ground.py <concept>`).
First sweeps out any edge naming a concept-state `genealogies.nodes` no longer
contains (decision 20), before the quote re-sync and before anything is judged,
so nothing is repaired, stamped or assembled for an edge that is about to go and
the reported verified count describes the map that will actually be published.
The count is printed, and a sweep that would remove *every* edge of a map that
has more than one refuses and exits non-zero instead, on the same reasoning as
the `--reground` guard and with the same lower bound (`total > 1` there is
`checked > 1`): no edge surviving is what an empty or swapped `nodes` blob looks
like, not what a re-clustered map looks like, while a one-edge map gives "all of
them" nothing to mean and refusing there would abort a trace at step 9 of 13,
after every paid step, over one removable edge.
Then re-derives each edge's quote pair from `definitions.verbatim_quote` before
judging anything. An edge's quotes ARE the two papers' definition quotes
(decision 6); Stage D copies them onto the edge when it classifies, and that copy
can go stale. Refreshing attention's definitions against re-extracted text did
exactly that: the definitions were all correct and individually verified, the
edges still held quotes taken from the text before the fix, and grounding them
against the new text failed 77 edges that had nothing wrong with them (287 of 287
verified fell to 210). A value defined as a copy of another value must never be
older than what it copies, so it is now re-copied every run. Empty definitions are
skipped rather than blanked, so a paper that no longer defines the concept fails
honestly instead of being emptied into a pass.
The mandatory grounding check: an edge is `verified` (rendered solid) iff both
quotes are found verbatim in the extracted source text. The comparison
(`quote_is_grounded` in `common.py`, shared with Stage B) folds away exactly two
things, both of them ours rather than the paper's: whitespace, which is an
artifact of line wrapping, and citation marks, which stand where the paper had a
citation. Nothing else is folded, so a paraphrase, a dropped word or an altered
figure still fails. A raw substring test was rejecting roughly a quarter of
good quotes on where a line happened to break, and a rejection renders as
"inferred", which tells a reader the tool cannot stand behind a passage it
copied correctly; otherwise it renders
dotted and is labelled inferred, never upgraded, never hidden. Writes the
genealogy JSON export to `data/genealogy_<concept>_<pv>.json` and marks the
genealogy complete. **These exports are the de-facto backups** (section 10,
incident 4). Re-run Stage E after curating.

**Auxiliaries.**
`workbench.py`: CLI curation (merge, rename, split-out, delete, reclassify);
every edit appends to `user_edits`, carrying `by_asserted` (decision 18): this
script authenticates nobody, so the name is what the process says about itself,
`LINEAGE_ACTOR` if set and `user@host` otherwise. The append is done in the
database with `||`, not by reading the array and writing it back, so a
concurrent web edit is not erased. The actor is resolved before anything is
mutated, because resolving it afterwards meant a failure there rolled the
transaction back after the command had already printed its success line. The web
workbench (section 6) does the same operations via Server Actions and is the
only writer of `by`. **Merging drops any edge that becomes a self-loop**: once
two states are one state, a relationship between them is not a transition.
`enrich_authors.py`: fills author lists, arXiv first and OpenAlex only as
fallback, because a stored openalex_id can be wrong while the arxiv_id was
proven by the title-match guard. Missing authors are omitted from BibTeX, not
guessed. No longer optional: the worker runs it with `--concept` after Stage E,
because nothing upstream needs authors and the export needs them absolutely. A
corpus that skips it produces a document whose `\cite` keys do not resolve, which
is how the attention map's first export came out with 14 entries for 85 papers.
`export_related_work.py`: related-work skeleton (Markdown) + BibTeX from a
curated genealogy. Real structure, real citations, real verified quotes, no
invented prose.
`snapshot_map.py`: the whole of one map to a timestamped JSON, before anything
rewrites it. Stage E's export is the documented backup and holds `nodes` and
`edges`; it does not hold `streams` (threads and their claims), `user_edits` (the
curatorial audit trail), or the definitions the edges quote, which a repair
overwrites in place. Incident 4 was recovered from that export with its audit
trail lost, which is the same gap. Restoring is deliberately not automated: the
file is plain JSON and a restore is a decision. It prints the curatorial edits
rather than counting them, and since decision 18 it prints each one's actor with
the basis for the name: this is the forensic tool for "who changed this map", so
the answer belongs where the owner is already looking. Entries written before
decision 18 print as `actor not recorded`, which is the whole truth about them.
`restore_snapshot.py`: puts a map back the way `snapshot_map.py` found it, by id
so nothing is orphaned: concept-states, threads, every edge, and each
definition's quote, verdict and magnitude scores. `user_edits` is the one thing
not overwritten; the restore appends itself to it with `||` in the database,
because a restore is an event in a map's history rather than a way to un-happen
one, and because read-modify-write on that array loses a concurrent web edit. It cannot restore the
extracted text, so a map re-extracted since the snapshot comes back with verdicts
describing a document no longer on disk: run Stage E afterwards, which is free and
re-grounds every quote against the text that is actually there.
`restore_genealogy.py`: the inverse of Stage E's export; re-inserts a
genealogies row and its edges from a JSON export and records the restoration
in the audit trail. Written during incident 4 and kept as the recovery path.

**Stage F: magnitude** (`stage_f_magnitude.py <concept> [--prompt-version PV]`).
Fills `definitions.attention` and `definitions.displacement` (migration 011),
which is what the influence map selects and sizes by. Attention is on-term
weighted uptake: not a raw citation count, which rewards famous-but-incidental
work, but each corpus-internal citation scored 0-2 by the model for whether the
citing sentence engages that paper's contribution to *this* term, weighted by
S2's citation intent. It reads the S2 cache Stage D populates, so it must run
after D. Displacement is the cosine distance of a paper's definition embedding
from the centroid of every earlier definition, marking turning points that
attention structurally misses (a paper that moves a term is cited by the field
it moved into, not by this corpus). The two were measured uncorrelated on
`/g/10` (Spearman +0.05), which is the point: they answer different questions
and neither substitutes for the other. Every paper gets an attention number
including zero, because the map selects on `attention IS NOT NULL` and a null
would drop a paper off the map rather than rank it last. Displacement is null
for the earliest paper, which has nothing to be displaced from.

**Stage G: threads** (`stage_g_threads.py <concept> [--prompt-version PV]
[--threads N]`). Fills `genealogies.streams` (migration 012) in two phases:
detect the threads and assign every paper to one, then compose each thread's
account. The target count scales with the corpus (`papers / 18`, clamped to
4..9) and is a guide rather than a range: a hardcoded "6-9" asked the model to
fill a quota and it returned 9 every time, which was right for embedding's 134
papers and too many for attention's 85. The prompt also refuses a thread for
work *about* the concept (surveys, interpretability) as opposed to development
*of* it. It reads the
corpus's content (definitions and novelty claims), not its citation topology,
which is why it is a stored artifact rather than something derived at render
time. **It generates no quotes.** An earlier version asked for a verbatim
fragment per paper and stored it, and the model returned paraphrase, which the
thread page then rendered under a verified stamp (section 10, incident 8).
Evidence is not regenerated: the app reads `definitions.verbatim_quote`, the
span Stage E actually matched.

**Stage H: claim-level evidence** (`stage_h_claims.py <concept> [--thread SID]`).
Asks each paper for 2-4 things it did for the term, each with the passage that
shows it, then checks every passage against our own extracted text with
`quote_is_grounded`. A claim whose passage fails keeps the claim and loses the
stamp, saying plainly that nothing was matched, rather than disappearing and
narrowing the account in silence. Written into the existing threads rather than
generated with them: thread membership is non-deterministic, so re-running
Stage G to improve prose reshuffles which papers sit where, and evidence should
be regenerable without disturbing a shape a curator has judged. It is the second
most expensive stage after extraction and roughly doubles what a map costs,
which buys the difference between an account a reader must trust paragraph by
paragraph and one they can audit sentence by sentence.
`--recheck` re-grounds the stored quotes without asking the model for new ones,
and costs nothing. A stamp is computed once, at generation, against the text of
that moment: re-extracting a corpus leaves every stamp on the map asserting a
check that ran against a document no longer on disk. A claim that stops checking
out keeps its text and loses its stamp and its quote, which is what generation
would have done with it. Regenerating instead would cost $4-6 to rewrite prose
that was never the problem.

Stages F and G were one-off scripts hardcoded to the showcase map until 2026-07-29, which
meant no other map could have a front door. They are stages now, the worker runs
them after Stage E, and both were proven on a second concept (`attention`,
`/g/13`) before being committed.

---

## 5. The trace worker

`worker/run.py`, ~230 lines, one process, no threads. Full walkthrough
knowledge condensed:

- **Startup housekeeping.** Before polling, the worker applies database
  migrations and runs the extraction audit over papers nobody has audited
  yet (`--only-unchecked --write`). Since migration 014 "nobody has audited yet"
  also covers a paper audited by a different calibration, so the boot after a
  calibration change re-measures the corpus with no command from anybody. That is
  intended and it is still a live rewrite of reader-facing state, which is why
  the runbook puts a dump and a lenient-only check in front of that deploy
  (decision 25). Both were manual commands, which meant
  they were commands for a machine the owner does not have: everything runs
  on Render and Neon, and there is no laptop in the loop. The worker is the
  only process holding the disk, the database and the repo at once, so it is
  the only honest home for them. Both are idempotent, and neither can stop
  the worker booting: a worker that will not start processes no traces,
  which is worse than an unapplied migration, and the next restart retries.
- **Claiming.** Polls every 10s for `status = 'approved'` only (the money
  gate: a request nobody approved is invisible to it). The claim is a single
  `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING`, so
  two workers can never take the same job and Postgres itself is the queue.
- **Execution.** Runs the pipeline stages as subprocesses (`python -u`,
  unbuffered) in order, passing `--corpus` to Stage B. Subprocesses were
  chosen over imports so the pipeline stays CLI-first, a stage crash cannot
  kill the loop, and stdout is a parseable stream.
- **Progress.** Stages already print `[i/N]` counters and `spend $X` lines;
  two regexes lift these into `trace_requests.progress` JSONB, flushed at most
  once per second. Each flush bumps `updated_at`, which is the heartbeat.
  Spend accounting: stages report cumulatively within themselves, so the
  worker tracks completed-stage spend plus current-stage spend.
- **Failure paths, all first-class.** Stage exits nonzero: job marked
  `failed` with the message and the last 30 output lines (shown only to the
  owner in the UI). Ctrl-C: job requeued to `approved`, because every
  expensive stage caches and a re-run is nearly free. Sudden death: the next
  poll's sweep marks any `running` row with a heartbeat older than 10 minutes
  as failed, so a zombie spinner cannot outlive its worker by more than that.
- **Completion.** Looks up the genealogy Stage E wrote for
  (concept, PROMPT_VERSION), stamps the job `complete` with `genealogy_id`.

- **Heartbeat.** A background thread bumps `updated_at` every ~30 s while a
  stage runs, on its own connection. Without it the heartbeat only moved when a
  stage printed a line, so genuinely silent stretches (an embedding batch, a
  slow LLM call) looked like a stall to both the UI and the sweeper. The
  heartbeat now means "worker alive", not "stdout active".

Deployment is declared in `render.yaml`: a Render Background Worker plus a
5 GB persistent disk at `/data` for `DATA_DIR` (fetched papers, extracted text,
exports). Since embeddings moved to the Voyage API the worker loads no models,
so its footprint is ~250 MB and the disk holds only data.

---

## 6. The web application

Next.js 15 App Router, all server components except where interactivity
requires a client component. Reads Postgres through the Neon HTTP driver
(`lib/db.ts`), which wants the **pooled** endpoint: each query is a fetch,
which suits serverless.

One tab bar lives in `layout.tsx` (`nav.tsx`): Concepts, Map a new concept, How
it works, Roadmap. A map, a thread and a paper all keep Concepts lit, so a
reader deep in the evidence still knows where they are. Before it, navigation
was a back-link in whatever corner each page happened to use.

**Routes.**
- `/` : the map list, with a link to `/trace` showing how many runs are in
  flight. Its closing line used to read "then curated by hand", unconditionally,
  on a page whose only curated map was the one this document had already
  retracted that claim about. It is now gated on `edit_count` across the listed
  maps and says the truthful thing when none has been curated (decision 18).
- `/trace` : requesting a map. Three steps that set expectations (name a term,
  it reads up to 150 papers in about fifteen minutes, you get the map), then
  the form, the queue and live progress. The panel (`trace-panel.tsx`, client)
  polls `/api/traces` every 3 s while any run is active. Sign-in returns to the
  page you started on, and request/approve/reject revalidate `/trace` as well
  as `/`, because a request that appears to vanish is worse than a slow one.
- `/g/[id]` : the front door, an influence map (`InfluenceMap.tsx`, client).
  Two header claims are counted rather than assumed (decision 18): the badge
  reads "*X* of *Y* links quote-verified" instead of a flat "quote-verified",
  which on `embedding` sat above 201 verified of 305; and the footer states the
  map's actual `edit_count` instead of asserting it was curated by hand.
  **The badge counts the links *drawn on the map*, not all of the map's
  relationships**, which is why it says "links shown" — one word doing a lot of
  work. The full figure lives on `/g/<id>/evidence`.
  `getInfluenceMap()` picks the top 20 papers by attention plus the 8 strongest
  movers by displacement, preferring movers that have some uptake and topping up
  from the rest; every thread is then guaranteed its strongest paper, so the
  channels and the thread list below cannot disagree. A dot is a paper, its
  radius is `5 + sqrt(attention) * 2.8`. Papers sharing a thread and a year sit
  at the same x, because x is the year and nothing else, so they fan vertically
  24px apart and **the lane is sized to hold its tallest such column** rather
  than being a fixed height. Six papers from 2020 in one attention thread stack
  120px and broke out of the old 78px lane, and a dot outside its tinted band
  reads as belonging to the neighbouring thread, which is the one thing the
  lanes exist to say. Clearance around a column is measured from the largest dot
  on that map rather than chosen, since dot size scales with a corpus's own
  uptake: 19px on attention, 15px on embedding. A ring means it moved the term's
  meaning: the top 15% of the scored corpus by displacement (`TURNING_QUANTILE`),
  judged against the whole corpus rather than the handful drawn, and relative
  rather than absolute. A fixed `>= 0.25` ringed 9% of embedding's papers and
  44% of attention's, so one legend meant two things on two pages. The dossier
  asks Postgres for the same percentile so both surfaces agree. Papers ride in visible per-thread channels ordered by
  first year, same-year collisions are spread vertically, and typed lineage
  appears only on hover or after a click pins it, so the resting state is a
  constellation rather than a hairball. **The scores select and size, and are
  never rendered as numbers.** Edges pointing backwards in time are dropped:
  arXiv revisions let two papers cite each other and the stored year is the v1
  date, so a reverse leg is a data artefact, not a lineage. Below the map: the
  through-line, the thread list, and a link into the evidence layer.
- `/g/[id]/river/[sid]` : a thread's account. Its arc, then its papers in the
  order the idea moved, each with what it did, the grounded prose, and the
  paper's own definition quote carrying its true verdict. The quote comes from
  `definitions.verbatim_quote`, not from the river's own `quote` field, which
  is generated summary rather than a passage from the paper (section 10,
  incident 8). Quotes render through `readableQuote()`, which shows the LaTeX
  extractor's `<cit.>` and `<ref>` markers as `[…]`, the elision a scholar
  already writes for a citation dropped from a quotation. Display only: about one
  quote in five carries a marker, the stored span stays byte-identical to the one
  Stage E matched, and the same helper is used by the dossier and the export so a
  reader meets one rendering everywhere. (`/g/[id]/river` redirects to the map; the path is kept working
  because it was the front door for a day.)
- `/g/[id]/export` : the writing scaffold, built by `lib/export.ts`.
  `?thread=<id>` scopes it to one thread, `?format=bib` returns the BibTeX
  instead of the Markdown. Two formats rather than one archive: no zip
  dependency, and a `.bib` wants to land in a reference manager while the `.md`
  wants to land in a draft. The document keeps the three tiers apart, because
  this text is going into someone's paper: the definition quote is stamped
  verified or inferred from `quote_verified`, and the river's "what it did" and
  prose lines are labelled the tool's reading. Papers with no author metadata
  are named as incomplete citations at the point of use, not only in the `.bib`.
  The curation line is a fourth such tier: both exports used to write "Curated by
  hand: N workbench edit(s) applied", which claims human agency from a count that
  cannot support it. They now state the count and, per actor, the name and the
  basis for it, and say when no actor is recorded rather than implying one
  (decision 18).
  The CLI export (`export_related_work.py`) still writes the older sense-shaped
  document, and is kept because the pipeline is CLI-first.
- `/g/[id]/p/[arxiv]` : a paper's dossier. What it contributed (novelty claims,
  labelled extracted rather than verbatim), how it defines the term with the
  verified-or-inferred stamp, a note where we know our reading of that paper lost text (migration 013; shown only when something was found, since a clean scan is not a certificate), and its typed links in both directions ("what it
  drew from", "what drew from it") each carrying the edge rationale labelled as
  the tool's reading.
- `/g/[id]/evidence` : the former genealogy page, now the evidence and
  workbench layer. Timeline of concept-state cards, typed relationship rows
  with evidence panels (both quotes, verification stamp, confidence), workbench
  edit controls (owner only), audit trail, danger zone (owner only). Meanings
  are grouped into citation-connected families (`computeFamilies()`, union-find
  over edges): a term whose senses do not cite each other (polysemy like
  "kernel") renders as separate families under a disclosure banner, with
  citation-isolated meanings pulled into an "Unconnected meanings" section. A
  single-family map renders flat and unchanged.
- `/about` : the public methods page, written for a researcher deciding whether
  to rely on this. What a map is, how one is built, how papers are ranked (and
  why ranking on uptake alone hides the papers that moved a term), the six link
  types (rendered from the same `EDGE_MEANING` map the product uses, so it
  cannot drift), "What you can and cannot rely on" separating verified quotes
  from sourced-but-unverified text from machine judgment, "Limitations and
  scope", draft-then-judgment, and reproducibility.
- `/roadmap` : built / working on next / under consideration / not planned,
  so a researcher can judge whether the gap between this and what they need is
  likely to close. "Not planned" is load-bearing: not a recommender, not a
  search engine, not automatically curated.
- `/api/traces` : read-only JSON: `{ now, rows }`. `now` is Postgres `now()`;
  the client computes its clock skew from it and measures elapsed time and
  heartbeat staleness against database time, never the viewer's clock.
- `/api/auth/*` : Auth.js GitHub OAuth.

**Server Actions** (`lib/actions.ts`, `lib/trace-actions.ts`): renameNode,
mergeNode, deleteNode, reclassifyEdge, deleteEdge, deleteGenealogy,
requestTrace, approveTrace, rejectTrace. Every one authorises itself on its
first line (section 7). requestTrace normalises and whitelists the concept
(2..60 chars, letters/digits/spaces/hyphens; the string becomes a subprocess
argument and a filename), refuses already-traced concepts for everyone
(re-running Stage C would overwrite curated nodes), applies non-owner quotas
(1 open request, 3 per week), and inserts owner submissions directly as
`approved`. deleteGenealogy requires the concept name typed back and verifies
it server-side, nulls `trace_requests.genealogy_id` (trace history outlives
the map), and lets edges cascade; papers and definitions survive, so deletion
re-opens the concept for cheap re-tracing.

**Progress transport is polling, not SSE**, a deliberate deviation from the
original plan: progress lives in Postgres anyway, serverless cannot hold
streams open cheaply, and a 3 s poll of a tiny route gives the same live feel
while surviving reconnects and redeploys for free.

**Copy rules.** No internal jargon in public view (worker, polls, prompt
versions, databases), no cost talk aimed at visitors, "curator" language
throughout, raw failure output visible to the owner only, and **no em dashes
anywhere in user-facing content**. "Genealogy" and "trace" were internal words a
first visitor cannot be expected to know: maps are maps, runs are runs, and
buttons say what happens. The schema and `lib/` still use the old names, which
is fine, and is why the mapping is recorded here.

---

## 7. Security model

Authentication is GitHub OAuth via Auth.js (`app/auth.ts`); it establishes
who someone is and nothing more. Authorisation is ours alone and lives in
`lib/authz.ts`:

- `isOwner()` compares the GitHub login to `OWNER_GITHUB_LOGIN` (rgok001) and
  **fails closed**: unset means nobody is owner.
- `requireOwner()` is the first line of every mutating Server Action. A
  Server Action compiles to a public HTTP endpoint; hiding a button removes
  it from the page, not from the internet. Button-hiding is courtesy, the
  throw is the lock.
- `requireViewer()` (signed in at all) gates trace *requests*; running a
  trace additionally requires the owner's approval row-state, enforced by the
  worker polling `approved` only.

Adversarially verified at commit `3aceaf0`: 7 action ids harvested from the
build manifest, 35 unauthenticated mutation attempts, all rejected, database
unchanged. Rejections currently surface as HTTP 500 (fail-closed throw);
semantically they should be 403, accepted as open polish.

Money controls, layered: owner approval before any run; per-user request
quotas; `TRACE_SPEND_CAP_USD` aborts a stage mid-run; Stage B `--corpus`
scoping prevents cross-corpus billing; and an account-level cap at
console.anthropic.com (owner action, recommended, not yet confirmed set).

Secrets: never committed. Root `.env` and `app/.env.local` are gitignored;
Vercel and Render hold their own copies (`sync: false` in render.yaml means
Render prompts in-dashboard). The prod `AUTH_SECRET` is distinct from local.
GitHub OAuth needs one app per callback URL, so local and prod are two
separate GitHub OAuth apps.

---

## 8. Operations runbook

Moved to [RUNBOOK.md](RUNBOOK.md) on 2026-08-02. A procedure read by the owner
while operating the system is a different document from a description read by an
agent before changing it, and merging the two meant neither could be loaded
whole. References to "section 8" elsewhere mean that file.

## 9. Decision record

Moved to [DECISIONS.md](DECISIONS.md) on 2026-08-02. It is the owner's
progression record and is history: dated claims about choices, where the rest of
this file is derived from the code and has to be recomputed when behaviour
changes. **The decision numbers did not change**, because commit messages,
`INCIDENTS.md`, issue bodies and agent memory cite them. References to "section
9, decision N" elsewhere mean that file.

## 10. Incidents and lessons

Moved to [INCIDENTS.md](INCIDENTS.md) on 2026-08-02. Incidents are history:
dated, append-only and immortal, where the rest of this file is derived from the
code and has to be recomputed when behaviour changes. Keeping the two classes in
one file meant the immortal part was re-read every time the derived part was
checked. References to "section 10" elsewhere mean that file.

## 11. Known limitations and open work

Removed on 2026-08-02. It was a fourth list of open work in a repository that
had just made [GitHub Issues](https://github.com/rgok001/Lineage/issues)
canonical, after `ARCHITECTURE.md`, `FIX-LOG.md` and `BACKLOG.md` were deleted
for exactly that. Every item was confirmed present as an issue or filed as one
before the section went; the map is below so that a reference to "item N of
section 11" still resolves.

| Was | Now |
|---|---|
| 1. Stage B is a sequential loop | [#27](https://github.com/rgok001/Lineage/issues/27) [B24], scheduled as [#38](https://github.com/rgok001/Lineage/issues/38) [Q1] |
| 2. Extraction cost varies more than it should | [#47](https://github.com/rgok001/Lineage/issues/47) [B29], filed 2026-08-02 |
| 3. ~~Maths is the next artifact family~~ (fixed) | [INCIDENTS.md](INCIDENTS.md) incident 11; the deferred map repair is [#5](https://github.com/rgok001/Lineage/issues/5) [B4] and [#29](https://github.com/rgok001/Lineage/issues/29) [F1] |
| 4. Proper 403s instead of fail-closed 500s | [#43](https://github.com/rgok001/Lineage/issues/43) [Q6] |
| 5. Notifications, both directions | [#34](https://github.com/rgok001/Lineage/issues/34) [F6] for the half being built; `docs/ROADMAP.md` declines the email half. The design is preserved as a comment on #34 |
| 6. `genealogies.status` is loose and vestigial | [#48](https://github.com/rgok001/Lineage/issues/48) [B30], filed 2026-08-02 |
| 7. A free OpenAlex pre-flight probe | [#39](https://github.com/rgok001/Lineage/issues/39) [Q2] |
| 8. The two public roadmap commitments | Sources beyond arXiv is [#35](https://github.com/rgok001/Lineage/issues/35) [F7]; claim-level verification **shipped as Stage H** (section 4), and the stamps it writes going stale on re-extraction is [#29](https://github.com/rgok001/Lineage/issues/29) [F1] |
| 9. ~~Topic-scoped traces~~ (done) | Section 3, which now also carries the field-versus-topic granularity note |
| 10(a). `--reground --limit` is rejected | [#20](https://github.com/rgok001/Lineage/issues/20) [B14] |
| 10(b). `workbench.py` prints success before it commits | [#21](https://github.com/rgok001/Lineage/issues/21) [B15] |
| 10(c). The map badge counts links drawn | Not a defect. Moved into section 6, where it is current state |
| 11. ~~Verdicts predate the re-extraction~~ (fixed in code) | [#49](https://github.com/rgok001/Lineage/issues/49) [B31], filed 2026-08-02, carrying the entry whole because `INCIDENTS.md` incident 14 cites its totals |
| 12. The parked `embedding` refresh | [#50](https://github.com/rgok001/Lineage/issues/50) [B32], filed 2026-08-02; sub-item (e) is [#49](https://github.com/rgok001/Lineage/issues/49) |
| 13. The home page lists every map | [#6](https://github.com/rgok001/Lineage/issues/6) [B5] |

The "Done since first draft" list that opened this section is progression rather
than open work, and moved to [DECISIONS.md](DECISIONS.md). The product
limitations paragraph moved to section 1, where it describes the system as built.

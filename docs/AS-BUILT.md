# Lineage: As-Built Documentation

**As of 2026-08-01.**

This is the as-built record: a description of the system as it actually exists,
including the deviations, incidents, and hard-won rules that shaped it. The
design intent lives in [CLAUDE.md](../CLAUDE.md) (product spec) and
[ARCHITECTURE.md](ARCHITECTURE.md) (design architecture). Where those documents
say what was planned, this one says what is true. When they disagree, trust
this one, then update it.

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
`/g/[id]/evidence` layer. See sections 3, 4, and 6 for the detail, and section
11 for what remains. Magnitude and thread generation ran as one-off scripts
against the showcase map until 2026-07-29; they are now stages F and G, and the
worker runs them, so a requested map arrives with a front door.

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

---

## 2. Repository layout

```
CLAUDE.md            product spec and non-negotiable rules
README.md            setup and CLI usage
render.yaml          Render blueprint for the trace worker
docs/                ARCHITECTURE.md (design), AS-BUILT.md (this file)
pipeline/            stages A-H + auxiliaries (Python, CLI-first; the worker
                     runs thirteen steps, see section 4)
  common.py          env loading, polite HTTP session, data_dir()
  check_extraction.py  audit of extracted-text fidelity (no model, no network)
  db/migrate.py      ordered SQL migrations, schema_migrations table
  db/migrations/     001..013
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
hold different `DATABASE_URL` values; see section 8.

---

## 3. Data model

Six tables, migrations `001` through `013`, applied by
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
both from the row and passes them through as CLI args.

**papers**, continued (013): `extraction_verdict` (clean/suspect/damaged),
`extraction_signals` and `extraction_checked_at` record what
`check_extraction.py --write` found in that paper's extracted text. NULL means
unchecked, and `clean` means nothing was found rather than nothing is wrong: the
scan is a lower bound, so the column is never read as a certificate. The paper
dossier shows the note only when something *was* found, which is the honest
asymmetry.

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
`--write` stores the verdict on the paper (migration 013).

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
only writer of `by`.
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
  yet (`--only-unchecked --write`). Both were manual commands, which meant
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

**Environment variables.**

| Variable | Where | Value/notes |
|---|---|---|
| `DATABASE_URL` | root `.env`, worker/Render | Neon **direct** endpoint (no `-pooler`): pipeline and worker hold real connections |
| `DATABASE_URL` | `app/.env.local`, Vercel | Neon **pooled** endpoint (`-pooler` host): serverless wants per-query fetches |
| `ANTHROPIC_API_KEY` | root `.env`, Render | pays for stages B, C labels, D |
| `VOYAGE_API_KEY` | root `.env`, Render | embeddings for Stage A relevance and Stage C clustering. **Required**; the pipeline fails fast without it |
| `VOYAGE_MODEL` | optional | defaults to `voyage-3` (1024-dim, matches the column) |
| `LLM_MODEL` | root `.env` | `claude-sonnet-5` (see decision record) |
| `PROMPT_VERSION` | root `.env` | `v2`; part of the Stage B cache key |
| `TRACE_SPEND_CAP_USD` | root `.env` | 15 |
| `DATA_DIR` | root `.env`, Render (`/data`) | absolute paths honoured |
| `OPENALEX_MAILTO` | root `.env`, Render | polite-pool contact |
| `AUTH_SECRET`, `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET`, `OWNER_GITHUB_LOGIN` | `app/.env.local`, Vercel | Auth.js reads exactly these names |

**Local development.** App: `cd app && npm run dev` (port 3000). Worker:
`python worker/run.py --once` for one job, no flag to poll forever. Pipeline:
run stages directly per README. Python is not on PATH on the dev machine;
invoke `C:\Users\GGPC\AppData\Local\Programs\Python\Python312\python.exe`.

**Migrations.** Add `pipeline/db/migrations/NNN_name.sql`, run
`python pipeline/db/migrate.py`. Applied set is recorded in
`schema_migrations`. Migrations run against the direct endpoint.

**Deploying the app.** Push to `master`; Vercel auto-deploys (root directory
is `app/`). Env var changes in Vercel do not reach an existing build: redeploy
after changing them.

**Deploying the worker.** Render dashboard -> New -> Blueprint -> this repo;
Render reads `render.yaml` and prompts for the three secrets. Success looks
like "Worker up. Polling every 10s for approved trace requests" in the logs.

**Backup and restore.** Stage E's JSON exports under `data/` are the map
backups; re-export after curating. Restore with
`python pipeline/restore_genealogy.py data/genealogy_<concept>_<pv>.json`
(refuses if the genealogy already exists). Papers, texts, and definitions are
not covered by exports; they live in Postgres and `DATA_DIR` and are cheap to
regenerate except for LLM spend, which the caches mostly protect.

**Observing a trace.** The queue and progress panel on `/trace` is the primary
view.
Direct SQL: `SELECT id, concept, status, progress, updated_at FROM
trace_requests ORDER BY id DESC`. A `running` row whose `updated_at` is
minutes old means the worker died; the sweeper will mark it failed within 10
minutes.

---

## 9. Decision record

The why behind the load-bearing choices, in one place:

1. **Neon over local Docker Postgres.** Docker was not installed, Neon was
   already in use on another project, and Vercel-linked Neon removed a whole
   class of deploy friction. docker-compose.yml is kept as an optional local
   fallback only.
2. **Sonnet over Opus for extraction.** Head-to-head on 5 papers produced
   identical verdicts and the same quote spans at ~60% of the cost.
   `definitions.model` records provenance; switching models deliberately means
   bumping `PROMPT_VERSION`.
3. **Top-K seed retention, not a cosine threshold** (Stage A): thresholds
   deleted the field's most important paper.
4. **Never relevance-filter citation expansion** (Stage A): ancestors do not
   use their descendants' vocabulary.
5. **Clustering threshold 0.16, over-splitting on purpose** (Stage C):
   merge is cheap and auditable, un-merge is not.
6. **Edge quotes come from Stage B definitions, not S2 contexts** (Stage D):
   only text we extracted can pass our own grounding check.
7. **Postgres as the job queue** (`FOR UPDATE SKIP LOCKED`): one fewer
   system, atomic claims, and the request inbox and queue are the same table
   with the same audit trail.
8. **Worker runs stages as subprocesses**: CLI-first pipeline, crash
   isolation, stdout as the progress stream.
9. **Polling over SSE for progress**: identical UX on a 3 s poll, none of the
   serverless streaming fragility.
10. **Database time as the only clock**: `/api/traces` returns `now()`;
    clients compute skew. Viewer clocks are not trusted for elapsed time or
    heartbeat staleness.
11. **Server-side type-the-name confirmation for deletion**: a client-side
    confirm() decorates the button, not the endpoint.
12. **Already-traced concepts refused for everyone**: protects curated maps
    from silent Stage C overwrite; deletion is the deliberate re-open path.
13. **Embeddings via a hosted API, not local models** (2026-07-23). Running
    1024-dim embedding models in-process is what made the small worker
    unrunnable: onnxruntime spikes past 2 GB building its optimised copy at
    load, and the 1+ GB model download stalled on both Render and a laptop.
    Voyage removes the model from the process entirely (~250 MB footprint,
    nothing to download), which is what the `vector(1024)` schema was designed
    for. The lesson generalises: on small deployments, call an embedding API
    rather than hosting the model.
14. **Robustness at every external boundary.** Upstream sources fail
    individually and must not be fatal: arXiv 403s a minority of papers, the
    shared DB can disagree with a per-machine disk, a stage can go silent for
    minutes. Each is now skipped, guarded or heartbeat-covered rather than
    aborting a whole run.
15. **Two magnitude scores, and neither is ever displayed** (2026-07-26).
    Ranking on uptake alone hides the papers that moved a term, so
    displacement exists as its own axis rather than as a tiebreaker. Both then
    stay behind the interface: they select which papers appear and how large
    the dot is, and no number is shown. A number invites the reader to treat a
    model's weighting as a measurement, which is the failure this tool exists
    to avoid.
17. **Sonnet for claim evidence, measured not assumed** (2026-07-31). Stage H
    ran on Haiku because it was the cheap post-pipeline stage. On thread s0 of
    attention, same prompt and same papers, Haiku got 16 of 22 passages to check
    out and Sonnet got 22 of 22; one paper went from 0 of 4 to 4 of 4, meaning
    its entire account had rested on prose with nothing under it. ~3.7c a paper
    against ~1.2c, so roughly $2 more per map. The mirror of decision 2: there,
    a cheaper model gave identical verdicts and was the right call; here it does
    not, and the difference is only visible because every passage is checked.
    **A model that paraphrases when told to copy fails silently in any system
    that does not verify, and this one verifies.**

16. **Three tiers of trust, never blended** (migration 010, `/about`). A
    verified quote is string-matched against our own extraction. A citation
    context is verbatim but from Semantic Scholar's PDF extraction, so it is
    sourced and unverifiable here. A rationale is the model's reading. Each is
    labelled as what it is, everywhere it appears; only the first wears the
    verified stamp.

18. **An actor on every curatorial edit, and the basis for it** (2026-08-01,
    `docs/design/actor-on-edits.md`). In `genealogies.user_edits`, **`by` is
    authenticated**: a GitHub login the app obtained from a session, and the web
    workbench is its only writer. **`by_asserted` is not authenticated**: a name
    the running process asserts about itself (`LINEAGE_ACTOR`, else `user@host`),
    which is all a CLI script running for whoever holds the `.env` can honestly
    claim. An entry carries one, or the other, or **neither, which is what every
    entry predating this change carries**. There is no backfill: that set is
    fixed at deploy time and must never grow, so an entry with neither key is by
    construction a legacy entry rather than a new failure.
    **Absence is never rendered as a claim about origin.** The evidence page used
    to print "(cli)" when `by` was missing, manufacturing a positive claim out of
    a silence; it now reads `actor not recorded`, and the exports say the same
    where they used to say "Curated by hand".
    Two properties are load-bearing. `recordEdit`'s actor parameter is typed
    `Viewer`, and **`Viewer` is branded with a `unique symbol` that only
    `lib/authz.ts` can name**, so it is nominal rather than structural.
    **What that buys, exactly: a hand-built object literal is a compile error at
    every call site** — `{ login: "anyone" }`, the same with every optional field
    filled, one annotated `: Viewer`, a bare string, and the argument omitted.
    `login`, `name` and `image` are `readonly`, so relabelling a real viewer in
    place is an error too.
    **What it does not stop, and no brand could.** A value typed `any` reaching
    the parameter is accepted in silence, with no cast written and nothing that
    looks like forgery: `JSON.parse(body)`, or any helper whose return type is
    unannotated. A genuine viewer can be spread and its login replaced,
    `{ ...viewer, login: other }`, because `readonly` does not survive a spread.
    And `as unknown as Viewer` always works, as it does for every type.
    None of those has a live path today: all five call sites take the actor
    straight from `requireOwner()`, and `getViewer()` is the only function in the
    codebase that produces a `Viewer`. The boundary is kept as an executable
    probe rather than as this paragraph, because this paragraph has been wrong
    twice (incident 13).
    The brand is not decoration: without it the type was a plain shape alias,
    structural typing accepted any matching literal, and this entry asserted an
    enforced invariant that was not enforced at all.
    And the split fails safe: any reader not updated for
    `by_asserted` sees no `by` on a CLI entry and degrades to unattributed, never
    to authenticated. That is `isOwner()` failing closed, applied to attribution.
    The rejected alternative worth naming is a single `by` plus a
    `by_verified` boolean, which fails open the moment a reader ignores the flag.
    Nothing here wears the verified stamp: the green check means a quote was
    string-matched against extracted text and must keep meaning only that
    (decision 16).
    **Both readers treat malformed entries as unattributed rather than
    crashing.** `user_edits` is JSONB and really does accept `"by": 42`,
    `"by": []`, a blank string, a missing `op`, or an element that is not an
    object at all. `editActor`/`edit_actor` and their `op` sibling agree on the
    actor, the basis and the op for every one of those, in both languages, and
    return "actor not recorded" rather than raising. **The `at` sibling is the
    one deliberate divergence**: `editWhen` formats for a viewer's locale and so
    must parse, so an unparseable date string reads "date not recorded" there
    while `edit_when` echoes it. Neither invents a date, and any divergence
    beyond that one is a bug. `app/` has no `error.tsx`, so an exception inside
    the audit trail is a 500 on `/g/<id>/evidence` and `/g/<id>/export` for that
    map until somebody edits the row by hand; `getGenealogy` therefore checks
    `Array.isArray` on `user_edits` rather than `?? []`, since a JSONB string has
    a `.length` and no `.map`. Junk degrades downwards only; nothing junk can
    become "signed in".
    **A stored name is folded before it is rendered, not only before it is
    stored.** `LINEAGE_ACTOR` is free text on a public page and in a Markdown
    document, and React escapes where Markdown does not: an interior newline
    used to break out of the export's `> ` blockquote into body prose in a
    researcher's paper. Whitespace collapses, control characters go, the name is
    capped at 64 characters, and `(`, `)` and `·` are removed.
    **What the fold guarantees is narrow and worth stating exactly: a label
    cannot emit this product's own delimiters or break its own line.** It does
    **not** guarantee that a label cannot read like a trust level. `rgok001 •
    signed in` with U+2022 goes straight through, as do `・`, `（ ）`, `[ ]`,
    U+200B and U+202E. Chasing those is homoglyph enumeration, which is
    unwinnable and is the shape of fault incidents 10 and 11 are about, so it is
    deliberately not attempted. The defence that does hold is structural: the
    true basis is always printed last, in the delimiters only the renderer can
    produce. A misleading operator label is possible in the same way a misleading
    GitHub username is possible, and it is why the name is in `by_asserted`.
    **`LINEAGE_ACTOR` unset degrades honestly.** Both `getpass.getuser()` and
    `socket.gethostname()` can fail, and either half being unnameable yields
    `unknown@host` or `user@unknown` rather than the plausible junk `@host`;
    both failing yields `unnamed process`. The return is never empty, because an
    entry with no actor key would join the legacy set this decision froze.
    **Both writers append with `||` in the database.** `workbench.py` and
    `restore_snapshot.py` used to read the whole array at process start and
    write it back, so a web edit landing in between was silently erased. This
    decision is what made that array load-bearing, so the latent race was closed
    with it.
    **A restore is not a curatorial change.** `CURATORIAL_OPS` — rename, merge,
    delete-node, delete-edge, reclassify — is the closed list of operations the
    workbench performs, defined once per language (`lib/genealogy.ts`,
    `pipeline/common.py`) and used by both exports and both pages. `restore` is
    written by the two recovery scripts and is excluded: `/g/10` carries exactly
    one entry, incident 12's restore, and the first version of this change
    announced it as "1 curatorial change ... recorded with who made it", which
    is two false claims in one sentence — nobody curated that map, and the entry
    names nobody. The list is closed rather than "everything except restore", so
    an op nobody adds to it is undercounted rather than overclaimed. The pages
    now print the same actor tally the exports do, so where entries name nobody
    they say "N with no actor recorded" instead of asserting attribution.

19. **Every verification stamp gets a free recompute** (2026-08-01).
    `definitions.quote_verified` was the last stamp in the system without one.
    Stage E re-grounds every edge on every run and Stage H's `--recheck`
    re-grounds every claim, both for nothing, while a definition's stamp could
    only be refreshed by paying Stage B for a fresh extraction, so in practice
    it never was. `embedding` is what that costs: its papers were re-extracted
    on 2026-07-31 and its definitions were not, so its definition quotes were
    copied out of text that is no longer on disk while their stamps still said
    the text had been searched for them. Stage E, which does recompute, put a
    number on it in passing: 286 verified edges down to 201.
    `stage_b_extract.py --reground` runs the same `quote_is_grounded` every
    other stage runs, rewrites `quote_verified` and nothing else, prints the
    count before and after, and the worker runs it immediately before Stage E on
    every trace. **A stamp that cannot be recomputed is a claim about the past
    written in the present tense.** It lowers `/g/10`'s definition verified
    count visibly, and that is the point: the count is wrong in the optimistic
    direction, and it is the number that says what finishing the refresh buys.
    A definition whose paper has no extracted text on this disk is **skipped,
    counted and printed, never flipped.** `quote_verified` is
    `NOT NULL DEFAULT false`, so there is no "unknown" to write: leaving it true
    perpetuates exactly the stale claim the flag exists to kill, and writing
    false asserts a check that never ran, which would mass-flip stamps on any
    worker whose disk is incomplete. Choosing between those two is a decision
    about the product; the script's job is to make the number impossible to
    miss rather than to take it. That choice is still open.
    **An empty text file is treated as missing text, not as text the quote is
    absent from.** A zero-byte or whitespace-only file is what an interrupted
    `extract_text.py` or a full `DATA_DIR` leaves behind, and grounding a quote
    against it would assert a check that never ran. That is a distinction of
    kind, not a threshold on file size.
    **And the run as a whole is refused if nothing at all grounded.** If more
    than one definition was checked and not one quote grounded, the stage writes
    nothing and exits non-zero. One definition failing is a finding; every
    definition failing is what a broken disk looks like, and this stage cannot
    tell the two apart — a 5 GB Render disk plus a truncated extraction produces
    exactly that shape, and the job would otherwise go green on a mass flip.
    The boundary is zero, deliberately, not a percentage: decision 3, incident 9
    and the turning-point cutoff are three bad calibrations already, and a
    guessed fraction here would be the fourth. This is incident 12's rule (a
    per-item fallback needs a global sanity check) applied to a stage that
    publishes a verdict rather than spends money. Every verdict is now decided
    before any is written, and the writes go in one transaction, because the
    connection is autocommit and the stage used to commit the first rows before
    it had looked at the last.
    There is deliberately **no override flag**: Stage D and Stage F took the same
    all-failed abort with no escape, and if the loss is genuinely real the answer
    is to re-extract rather than to mass-flip stamps from here. The cost of that
    choice is that a map whose every quote is honestly stale cannot be corrected
    by this tool; that is the trade, taken in the direction that changes nothing.

20. **Stage D owns the edge lifecycle, and Stage C clears only what it has
    invalidated** (2026-08-01). `stage_c_cluster.py` used to run
    `DELETE FROM edges` unconditionally straight after the node upsert, on the
    reasoning that re-clustering invalidates the old edges and Stage D rebuilds
    them. **That is the reasoning Stage D itself held before incident 12**, and
    it made incident 12's fix worthless: Stage D now defers its own DELETE until
    the first successful classification, but the edges were already gone before
    Stage D was reached, so a Stage D that failed for any reason left a map with
    fresh concept-states and no relationships while its guard reported that
    nothing had been touched.
    **Node ids are positional, and that is what makes this more than a
    tidy-up.** Stage C names clusters `n1..nk` by their earliest member year, so
    an id is a name for a slot rather than for a concept-state, and two runs can
    both produce `n3` and mean different things by it. So "the old edges are
    stale" has two quite different meanings: an edge naming an id that is gone,
    which is merely dangling, and an edge naming an id that survived and now
    denotes different definitions, which is a **wrong displayed edge** between
    two concept-states nobody ever claimed were related. `/g/<id>/evidence`
    renders the second one in full, with both quotes and a verified stamp if the
    quotes ground, and shows the raw id where the label should be. Under product
    rule 1 that is worse than a missing edge.
    So the condition is the clustering itself, **per endpoint rather than per
    map**. An edge survives iff both the ids it names still denote the
    definitions they denoted; anything else clears. Whole-map equality was the
    first attempt and it over-cleared: a re-cluster that merely APPENDS a
    concept-state leaves every existing edge valid and every existing id
    untouched, and comparing the maps wholesale threw all of them away. Labels,
    year ranges and `representative_arxiv_id` are not compared, because none of
    them changes what a node groups; renaming is in fact the only curatorial act
    that leaves denotation intact, and the only one that does not invalidate an
    edge. Clearing in the changed case is not incident 12 again: what is
    destroyed there is already invalid, and incident 12's rule is about not
    destroying something valid before its replacement exists.
    **The gate is one transaction**, covering the read of the old blob, the
    upsert and the DELETE. The connection is autocommit, so without that the new
    clustering commits the moment the upsert runs, and anything raising between
    there and the edge decision produces precisely the state this decision
    exists to prevent. That window is the gate's own creation — the old code had
    the upsert and an unconditional DELETE back to back — so the gate owns it. It
    was reachable without hand-edited SQL: `restore_genealogy.py` validates no
    shape, so pointing it at a truncated JSON gives a malformed `nodes` blob with
    a full edge set, and a plain re-cluster then walks into it.
    A malformed blob is also no longer a raise. `node_denotation` in `common.py`
    is the single reader of `genealogies.nodes` for both stages, with one posture
    on malformed input: dropped, never guessed at and never raised on.
    **The posture is shared; the response is not, and the difference is
    deliberate.** Stage C clears the edges it cannot vouch for. Stage E, faced
    with a blob so bad that every edge would go, refuses, deletes nothing and
    names the cause. That is not an inconsistency to be tidied away: in Stage C
    the unreadable blob is the *previous* one, already being replaced, with Stage
    D to rebuild behind it, so clearing costs a rebuild; in Stage E it is the
    *current* one, about to be published, so deleting on its authority would
    destroy a map on the word of something unreadable. Each stage fails in the
    direction that is cheap for it.
    The two also answer differently about the same node, and correctly: a node
    with a usable id and unreadable `definition_ids` exists, so Stage E vouches
    for it and an edge naming it is not dangling, while Stage C cannot say it
    denotes what it denoted, so that edge clears. Stage E asks whether a
    concept-state is there; Stage C asks whether it still means the same.
    A node that does not say which definitions it holds denotes
    **unknown, and unknown is never equal to unknown** — each gets a fresh
    sentinel. Reading absence as the empty set would have made two silent blobs
    compare equal and KEEP their edges, which is the one direction this must not
    fail in.
    The dangling case is settled in Stage E, which sweeps edges naming absent
    concept-states before it grounds anything, reports the count, and refuses if
    more than one edge exists and every one of them would go. That refusal is the
    twin of the `--reground` guard (decision 19), not of anything in Stage C.
    Stage C for its part reports the cause it actually has: when nothing about
    the previous concept-states could be read it says so, rather than reporting a
    clustering change it never established. A corrupt restore and an ordinary
    wholesale re-cluster used to print byte-identical lines, and the cost of that
    was an operator re-running Stage D, which spends, on a diagnosis nobody had
    made.
    **What this buys.** Driven directly against the code: the gate block executed
    over synthetic node blobs and edge sets, showing an appended cluster now
    keeps all its edges where whole-map equality cleared them, a single changed
    cluster clears only the edges touching it, and a forced raise inside the gate
    rolls back rather than committing new nodes over old edges. Reasoned, not
    measured: that a re-run at the same threshold reproduces the same clustering,
    since Stage C cannot run here (`cluster()` needs sklearn and real vectors) —
    what was executed is `node_denotation` on stored blobs, not the clustering
    that produces them. The sweep alone, as originally scoped, would have left
    the changed-clustering case showing misattributed edges; that is why Stage C
    still has a DELETE.

---

## 10. Incidents and lessons

Recorded because the system's shape is partly their consequence.

1. **OpenAlex metadata mismatches (build phase).** BERT and RoBERTa arXiv ids
   carried unrelated titles. Consequence: the `text_title_match` guard and the
   arXiv-first author enrichment rule.
2. **Negative results re-billed (build phase).** Stage B's cache only stored
   positives; re-runs re-paid for most of the corpus. Consequence: migration
   003, negatives as first-class cached findings. The caching claim is now
   tested behaviour, not an assumption.
3. **Cross-corpus billing (first live trace, 2026-07-18).** The 12-paper
   dropout trace scanned 40 papers because Stage B's query took every
   extracted paper in the shared table. Caught live by the end-to-end test;
   consequence: Stage B `--corpus`, passed by the worker. Side finding: some
   attention-corpus papers genuinely define dropout, and their definitions
   legitimately joined the dropout genealogy.
4. **Curated genealogy deleted (2026-07-19).** The new danger-zone delete was
   used on the curated attention map (id 2), likely while hunting an
   already-removed orphan row. Restored from the Stage E export as id 5 with
   curated labels intact; the original audit trail entries were lost.
   Consequences: `restore_genealogy.py`, the exports-are-backups rule, and
   this document's insistence on re-exporting after curation.
5. **Worker spend-parser crash (first live trace).** The regex `[0-9.]+`
   captured the trailing period of "spend $0.0093." and `float()` crashed;
   the job failed cleanly, was requeued, and completed for $0.10 thanks to
   caching. The failure handling design was validated by its first real
   failure.
6. **The five-hour false alarm.** A "5h ago" timestamp looked like a clock
   bug; investigation proved the session's background waits had genuinely
   spanned five hours and every clock was correct. The DB-time design (#10
   above) was kept anyway because it makes the heartbeat check robust against
   viewer clocks that really are wrong.
7. **The first cloud trace: seven deployment-only bugs (2026-07-21..23).**
   Nothing here could surface locally, where `DATA_DIR` sits inside the repo
   and RAM is plentiful. In order: (a) unbounded embedding batch: fastembed
   defaults to 256 and allocated ~2.4 GB of activations for a 130 MB model,
   OOM-killing the worker; capped to 8 (measured 2440 MB -> 342 MB). (b) Paths
   stored relative to the repo root broke when `DATA_DIR` became a separate
   mounted disk. (c) A shared DB with per-machine disks: papers flagged
   extracted elsewhere had no local text file. (d) Those same papers were
   silently dropped from the corpus until extraction learned to re-run on a
   missing file. (e) An invalid `ANTHROPIC_API_KEY` on the worker. (f) The
   1024-dim model itself could not load in 2 GB, and the fix was not a bigger box
   but removing local models entirely (decision 13). (g) A single arXiv 403
   aborted a 150-paper fetch. **Lesson: a first real cloud run is a test in
   its own right; local success proves very little about a deployed
   environment.** Two wrong diagnoses along the way (blaming instance size,
   then model file size) were corrected only by measuring rather than
   reasoning; the batch-size measurement in fresh processes was decisive.
8. **Generated paraphrase wearing the verified stamp (2026-07-28).** Building
   the export surfaced it: migration 012 specifies that each river paper's
   `quote` is a string-verified span, and the generation wrote a summary of the
   paper instead. All 102 were checked against the definition spans Stage E
   actually matched, and **none** was a passage from its paper. The thread page
   had been rendering them under a green "verified" check since the river
   shipped. Both the page and the export now read `definitions.verbatim_quote`
   with its real `quote_verified` verdict, the same source the dossier already
   used. **Lesson: a stamp must be derived from the check, never from the
   field's documented intent.** The contract said verified; nothing verified it.
   The generated prose was never the problem: it is honest as an account and
   stays, labelled as the tool's reading. The problem was one field claiming a
   grounding it never had, in the one place the product cannot afford to be
   wrong.
9. **An absolute threshold silenced the signal it was guarding (2026-07-29).**
   The influence map added "movers" by displacement but only from papers with
   `attention >= 1`. Displacement exists to catch papers the citation graph
   misses, so gating it behind a citation-derived score was self-defeating, and
   the number 1 is meaningless across corpora of different citation density. On
   the second map ever built (`attention`, 85 papers) exactly 20 papers cleared
   the bar and all 20 were already selected, so no mover was ever added and four
   of nine threads had no paper on the map while still being listed beneath it.
   Caught by the owner counting channels against the list. **Lesson: this is
   decision 3 again.** A cosine threshold once deleted the field's most important
   paper and the rule that came out of it was rank, never threshold. The rule was
   right and was not applied here, because the flaw is invisible on the corpus
   you tune against and only appears on the second one.
10. **The extractor ate the citations, and the papers looked illiterate
    (2026-07-29).** pylatexenc knows `\cite` and renders it `<cit.>`. It does
    not know natbib, biblatex, or a paper's own `
ewcommand`, and an unknown
    macro is dropped in silence: the citation vanished and its punctuation
    stayed, so a stored quote read "a model should, detect the objects, and ,
    segment them" and the paper wore the blame for our parser. Found by the
    owner reading a quote on a thread page. The fix is a rule, not a list: any
    macro whose name contains "cite" is folded to one mark before parsing, so
    names nobody has enumerated are covered too. **The knock-on was the
    interesting part.** Cleaning the text would have un-grounded every quote
    copied out of the dirty text, and re-grounding would have reported a
    collapse in verified counts as the result of a fix. 66 definition quotes and
    367 edge-quote copies were re-anchored to their new spans instead: an exact
    match modulo whitespace and citation marks, never a guess, leaving anything
    not confidently located untouched. But re-anchoring makes the later check
    pass by construction, so the check was moved to where it belongs:
    `quote_is_grounded` now folds whitespace and citation marks itself, and the
    grounding is honest without any repair step. Verified edges went from 233 to
    286 of 305 on embedding and 211 to 287 of 287 on attention, most of which
    was never a quoting problem at all: it was where a line happened to break.
    **Lesson: when a check fails on things that are yours rather than the
    source's, it is the check that is wrong, and repairing the data to satisfy
    it hides that.**
11. **The recorded diagnosis was wrong, and the bug was incident 10 again
    (2026-07-31).** Open item 3 had said for days that *Attention Is All You
    Need* reads "vectors of dimension ." because `$d_{model}$` extracted to
    nothing. It does not. Run against the extractor we actually ship,
    `$d_{model}$` extracts correctly to `d_model`. What extracts to nothing is
    `$\dmodel$`, because the paper writes `\newcommand{\dmodel}{d_{model}}` in
    its preamble and pylatexenc drops an unknown macro in silence along with its
    content. **That is incident 10 exactly, one class wider.** The rule drawn
    from incident 10 covered every macro whose name contains "cite". The general
    case is every macro a paper defines for itself, and it was sitting in the
    same document, correctly described, while the fix was scoped to citations.
    The fix has the shape the last one should have had: expand the definitions
    rather than enumerate the names.
    **Two lessons, and the second is the uncomfortable one.** First, a diagnosis
    written from a plausible reading is not a measurement: two minutes running
    both forms through the extractor would have shown maths mode works, and
    nobody spent them, because the explanation sounded right. Second, incident
    10's own text names `
ewcommand` as a thing pylatexenc does not know, and the fix that followed
    covered only "cite". **A lesson recorded at the width of the symptom will be
    applied at that width.** The habit this argues for is asking, of every fix,
    what class the failure belongs to and whether the fix covers the class.
    Consequence: `expand_own_macros`, and `check_extraction.py`, which exists
    because none of this was visible from inside the system. Every quote passed.

12. **An empty credit balance rebuilt the showcase map into nothing
    (2026-07-31).** Mid-repair of `embedding`, the Anthropic balance ran out. Every
    call returned `400 invalid_request_error: Your credit balance is too low`, and
    four stages in a row treated that as ordinary per-item failure, because each
    had been written to survive one bad item (decision 14). Stage B's refresh died.
    Stage D **deleted all 305 edges before classifying a single one**, classified
    none, and left the map with 27 concept-states and no edges. Stage E dutifully
    grounded zero edges. Stage F scored all 533 citations neutral and **persisted
    them**, overwriting the real uptake ranking with a uniform number that looks
    like data. Stage G crashed, which is the only one that behaved well, because
    it is the only one that did not have a fallback.
    **Three lessons, and the third is the general one.** Destroy nothing until you
    can replace something: Stage D now defers its DELETE until the first successful
    classification, so a run that classifies nothing leaves the previous map
    untouched. A per-item fallback needs a global sanity check: "one failure is
    neutral" is right, "every failure is neutral" is a broken call wearing a
    result's clothes, so Stage D and Stage F now abort when nothing at all has
    succeeded. And an error swallowed to its class name is not a log: 305 lines
    reading `BadRequestError` said nothing, while one line of `str(exc)` would have
    named the cause immediately. All three now print the message.
    Recovery is from `snapshot_map.py`, taken minutes earlier, which is the only
    reason this is an incident rather than a loss.

13. **This document asserted a compiler-enforced invariant that the compiler did
    not enforce, and it propagated within hours (2026-08-01).** Decision 18
    shipped saying that `recordEdit`'s actor parameter is a `Viewer`, that a
    `Viewer` can only come from `getViewer()` or `requireOwner()`, and that the
    compiler therefore keeps unauthenticated text out of `by`. `Viewer` was
    `{ login: string; name?: string | null; image?: string | null }`. TypeScript
    compares object types by shape, so
    `recordEdit(1, "rename", {}, { login: "attacker" })` compiled clean under
    `--strict` with no cast, no `any`, and no import from `authz.ts`. The
    guarantee was a comment wearing a compiler's clothes, and the same sentence
    was in the design, in the commit message and here. Caught by the tester with
    a `@ts-expect-error` control, which reported the directive as *unused* —
    the cheapest possible probe and one nobody had run. By then an architecture
    review had already read the claim out of this document and repeated it back
    verbatim, so the false invariant had a second source before it had a fix.
    **Two lessons.** A claim about what a type system enforces is a testable
    claim, and `@ts-expect-error` tests it in one line; a security property
    asserted without such a probe has not been checked, it has been hoped for.
    And this document is load-bearing enough to be quoted, which means an
    over-claim in it does not stay in it. The fix is a `unique symbol` brand on
    `Viewer` (decision 18), whose whole purpose is to make the sentence already
    written here true.

---

## 11. Known limitations and open work

Product limitations (also disclosed on `/about` under "Limitations and scope",
and shaped for the reader on `/roadmap`): arXiv-only coverage; a bounded corpus,
so the map is the scope of what was read and not of the field; exact string
matching fails closed to "inferred" when extraction mangles a passage; parallel
discovery without citation appears as unconnected meanings; edge types,
confidences and rationales are model judgment, mitigated by the quotes being
shown and the judgment being labelled.

Done since first draft: Render worker deployed and verified live
(2026-07-21); Stage C genealogy upsert (migration 007, stable id); account
Anthropic billing cap (owner, confirmed set); topic picker + sense gloss
(item 9 below); family grouping on the evidence page; the showcase "embedding"
map traced (`/g/10`; not curated, see section 1); the influence-map front door, thread accounts
and paper dossiers; requests moved to their own page; one tab bar and a public
roadmap; export for writing (`/g/[id]/export`, whole map or one thread) with
the author backfill run over the showcase corpus so its citations resolve;
magnitude and threads promoted from one-off scripts to stages F and G, which the
worker now runs, giving a second map (`attention`, `/g/13`) a real front door.

Open engineering work, in priority order:

1. Stage B is a sequential loop: one LLM call per paper, awaited before the
   next. On a 118-paper corpus that is most of the wall-clock time of a trace,
   and every paper is independent with a per-paper cache, so it parallelises
   cleanly. The two things wanting care are `TRACE_SPEND_CAP_USD`, which
   currently aborts cleanly mid-loop and would overshoot slightly, and the API
   rate limit.
2. Extraction cost varies more than it should: `embedding` cost about a cent
   per paper on 2026-07-22 and `attention` about four cents on 2026-07-28, on
   the same model and prompt version, with attention getting *more* cache help.
   That points at how much extracted text Stage B sends per paper. Worth
   measuring, because it is the largest single lever on what a trace costs.
3. ~~Maths is the next artifact family~~ **FIXED, and it was never maths
   (2026-07-31).** See incident 11. The 19 inferred edges on embedding, 17 of
   them from *Attention Is All You Need*, are the visible end of a paper-defined
   macro being dropped in silence, not of maths mode. The extractor now expands
   a paper's own macros; `check_extraction.py` measures what still escapes.
   **The repair of the existing maps is deliberately not done**, and the reason
   is worth stating: re-extracting changes the text under stored quotes, and the
   showcase map was believed to be hand-curated and is not: its `user_edits` is
   empty, so nothing on it is hand work and a full rebuild costs only money.
   The safe path exists anyway (`stage_b_extract.py
   --refresh`, then `stage_c_cluster.py --embed-only`, then Stage E) and should
   be exercised on `attention` (`/g/13`, uncurated) before it goes near `/g/10`.
   The affected quotes stay as they are, labelled, until then. What must never
   happen is re-anchoring a quote to the new text: a lost symbol is content, and
   unlike whitespace it cannot be folded into the check, so there is no honest
   way to make those pass (incident 10's lesson, second application).
4. Proper 403s instead of fail-closed 500s on unauthorised writes.
5. **Notifications, both directions.** Nothing tells anyone anything: a
   stranger's request is visible only if the owner happens to visit, and the
   requester has no way to learn their map was built short of returning to
   check. Three events, each fired where the state already changes: a request
   landing (app, `requestTrace`) to the owner; approval or rejection (app,
   `approveTrace` / `rejectTrace`) to the requester; completion or failure
   (worker, where it stamps the row) to the requester. Migration 013 would add
   `requester_email` (the session carries it from GitHub already and it is
   simply not stored) plus `owner_notified_at` and `requester_notified_at`. The
   timestamps are load-bearing, not decoration: the worker requeues jobs, and
   without them a retry sends the same mail twice.
   **The blocker is not code.** Sending to a stranger requires a verified
   sending domain, and `lineage-green.vercel.app` cannot be verified. Every
   reputable provider will deliver to the owner's own address immediately and
   refuse third parties until a domain is proven, so the owner half is an hour's
   work and the requester half waits on a domain (about $15 a year plus DNS
   records). A researcher would bin mail from a Vercel subdomain anyway.
   Cheap fallback that needs no domain: show a signed-in visitor the status of
   their own requests on `/trace`, which is also the right behaviour for anyone
   whose email bounces.
6. `genealogies.status` semantics are loose and partly vestigial. The failed
   `attention` run left genealogy 13 at `running` with a `failed` request
   pointing nowhere, which is harmless but says nothing true.
7. Optional: a free OpenAlex pre-flight probe at approval time (show the
   curator the would-be corpus before they approve). This is also promised
   publicly on `/roadmap` as "a preview before a run".
8. The public roadmap commits to two further items this document should track
   when they start: sources beyond arXiv (DOI-resolved open access), and
   claim-level verification so every assertion in an account carries its own
   matched span rather than the paragraph resting on the definition quote.
   Incident 8 is the argument for the second one.
9. ~~Topic-scoped traces~~ **DONE (2026-07-21).** The request form now has an
   OpenAlex field picker (populated live from a `group_by` of arXiv works,
   `lib/openalex.ts`), and corpus selection scopes to the chosen field. A
   sense gloss was shipped alongside it (polysemy prevention at intake). Both
   flow request form -> `trace_requests` (migration 006) -> worker -> pipeline.
   Remaining refinement: the picker is at *field* granularity (26 fields); a
   finer *topic*-level picker (~4500 topics) was deferred as unnecessary for
   scoping.

10. **Filed 2026-08-01, from the third review of decision 18 and decision 19.**
    None of these is a live defect; all are recorded so they are not rediscovered.
    (a) `--reground --limit` is rejected on the grounds that a partial count
    would misdescribe the concept, but `--only` and `--corpus` scope the same
    query and are allowed. The guard is right about the risk and wrong about
    which flags carry it; either all three should print a "this is a subset"
    banner or `--limit` should be allowed with one.
    (b) `workbench.py` resolves the actor before mutating, which fixes the
    reported failure, but its success lines are still printed inside the `cmd_*`
    functions before the commit. Any later failure — a database error in
    `record()` or at `commit()` — still prints "Deleted n5 and 3 attached
    edge(s)." to an operator whose transaction then rolls back. Closing it means
    returning the message rather than printing it, in three functions and two
    inline branches.
    (c) The map badge counts the links *drawn on the map*, not all of the map's
    relationships; it now says "links shown" for that reason, which is one word
    doing a lot of work. The full figure lives on `/g/<id>/evidence`.

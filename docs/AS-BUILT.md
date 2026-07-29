# Lineage: As-Built Documentation

**As of 2026-07-29.**

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
showcase map is "embedding" (`/g/10`, 134 papers, 305 relationships, 286
verified); "attention" (`/g/13`, 85 papers, 287 relationships, all verified) is
the second, and the first built end to end by the worker. The earlier "dropout"
map was deleted on 2026-07-26.

| Component | Technology | Where it runs | Cost |
|---|---|---|---|
| Web app | Next.js 15, Auth.js v5 | Vercel (Hobby), prod alias `lineage-green.vercel.app` | free |
| Database | Neon serverless Postgres, pgvector 0.8 | Neon (Vercel-linked account) | free tier |
| Pipeline | Python 3.12 CLI scripts | Anywhere with the repo and `.env` | LLM spend only |
| Trace worker | Python 3.12, single process | Render Background Worker (declared in `render.yaml`; the owner's laptop until the Render console setup is done) | ~$8/mo |
| LLM | Claude Sonnet (`claude-sonnet-5`) for extraction/classification; Claude Haiku (`claude-haiku-4-5`) for the cheaper post-pipeline scoring and thread generation | n/a | ~$6 per 150-paper trace; +~$0.7 for magnitude + threads on one map |

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
pipeline/            the seven stages + auxiliaries (Python, CLI-first)
  common.py          env loading, polite HTTP session, data_dir()
  db/migrate.py      ordered SQL migrations, schema_migrations table
  db/migrations/     001..012
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

Six tables, migrations `001` through `012`, applied by
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
curatorial audit trail, `spend_usd` accumulates cost, `status` is loosely one of
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

**trace_requests** (005, 006): the request inbox and the job queue in one table.
Status flow: `requested -> approved -> running -> complete`, plus `rejected`
and `failed`. `progress` JSONB is written live by the worker; `updated_at`
doubles as the worker heartbeat; `genealogy_id` links the finished map. A
partial unique index allows only one open request per concept, enforced at the
database level because app-level checks can be raced by simultaneous submits.

---

## 4. The pipeline

Seven stages plus auxiliaries, each a standalone CLI script reading root
`.env`. The pipeline is CLI-first by rule: the worker orchestrates these same
commands and adds nothing to them.

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
is folded to one mark first, so the rule covers names nobody has listed. Extraction uses pylatexenc for
LaTeX and pymupdf with de-hyphenation for PDF, computes `text_title_match`,
and warns loudly below the 0.5 guard.

**Stage B: definition extraction** (`stage_b_extract.py <concept> [--corpus JSON] [--dry-run]`).
For each paper with usable text, Claude answers: does this paper give the
concept a meaning of its own? If yes it must return the defining passage
verbatim, plus section and novelty claims (structured output via
`messages.parse()` and Pydantic). Negatives are cached (migration 003).
`--dry-run` estimates cost across models without an API call, using real
`count_tokens` when a key exists and a calibrated 2.6 chars/token heuristic
when not. A spend cap (`TRACE_SPEND_CAP_USD`) aborts cleanly mid-run.
`--corpus` scopes extraction to one trace's papers; without it the query takes
every extracted paper in the shared papers table, which is correct for
single-concept research use and wrong for the worker (section 10, incident 3).

**Stage C: clustering** (`stage_c_cluster.py <concept>`).
Embeds definitions via the Voyage hosted API (1024-dim, cached in
`definitions.embedding`), then agglomerative clustering with cosine distance
and no fixed k. `DEFAULT_THRESHOLD = 0.16` was calibrated on bge-large
distances back when embeddings were local, so it may want re-tuning for Voyage
vectors; clustering granularity is a curatable draft either way.
The original calibration:
the soft-alignment and self-attention cores sit ~0.16 apart, and a bridge pair
(Show-Attend-Tell / Transformer) is 0.161, so 0.19 would merge the two senses
the product exists to distinguish. 0.16 over-splits weak singletons on
purpose: merge is a one-click curatorial act, un-merge is not. Stage C output
is a draft for curation, not a result. Claude labels each cluster (pennies).

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
every edit appends to `user_edits`. The web workbench (section 6) does the
same operations via Server Actions.
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

Both were one-off scripts hardcoded to the showcase map until 2026-07-29, which
meant no other map could have a front door. They are stages now, the worker runs
them after Stage E, and both were proven on a second concept (`attention`,
`/g/13`) before being committed.

---

## 5. The trace worker

`worker/run.py`, ~230 lines, one process, no threads. Full walkthrough
knowledge condensed:

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
  flight.
- `/trace` : requesting a map. Three steps that set expectations (name a term,
  it reads up to 150 papers in about fifteen minutes, you get the map), then
  the form, the queue and live progress. The panel (`trace-panel.tsx`, client)
  polls `/api/traces` every 3 s while any run is active. Sign-in returns to the
  page you started on, and request/approve/reject revalidate `/trace` as well
  as `/`, because a request that appears to vanish is worse than a slow one.
- `/g/[id]` : the front door, an influence map (`InfluenceMap.tsx`, client).
  `getInfluenceMap()` picks the top 20 papers by attention plus the 8 strongest
  movers by displacement, preferring movers that have some uptake and topping up
  from the rest; every thread is then guaranteed its strongest paper, so the
  channels and the thread list below cannot disagree. A dot is a paper, its
  radius is `5 + sqrt(attention) * 2.8`, a ring means it moved the term's
  meaning. Papers ride in visible per-thread channels ordered by
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
  The CLI export (`export_related_work.py`) still writes the older sense-shaped
  document, and is kept because the pipeline is CLI-first.
- `/g/[id]/p/[arxiv]` : a paper's dossier. What it contributed (novelty claims,
  labelled extracted rather than verbatim), how it defines the term with the
  verified-or-inferred stamp, and its typed links in both directions ("what it
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
16. **Three tiers of trust, never blended** (migration 010, `/about`). A
    verified quote is string-matched against our own extraction. A citation
    context is verbatim but from Semantic Scholar's PDF extraction, so it is
    sourced and unverifiable here. A rationale is the model's reading. Each is
    labelled as what it is, everywhere it appears; only the first wears the
    verified stamp.

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
map traced and curated (`/g/10`); the influence-map front door, thread accounts
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
3. Maths is the next artifact family, and the reason 19 of embedding's 305
   edges are still inferred. 17 of them trace to one paper, *Attention Is All
   You Need*, whose quote reads "vectors of dimension ." because `$d_{model}$`
   extracted to nothing. Unlike a citation, a symbol is content, so it cannot be
   folded away in the comparison the way whitespace and citation marks are, and
   grounding correctly refuses to verify a sentence missing part of itself.
   Found the same way incident 10 was: by reading a quote that looked wrong.
4. Proper 403s instead of fail-closed 500s on unauthorised writes.
5. Some notification when a stranger's request lands (currently visible only
   by visiting the site).
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

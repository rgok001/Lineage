# Lineage: As-Built Documentation

**As of commit `18c9d33`, 2026-07-19.**

This is the as-built record: a description of the system as it actually exists,
including the deviations, incidents, and hard-won rules that shaped it. The
design intent lives in [CLAUDE.md](../CLAUDE.md) (product spec) and
[ARCHITECTURE.md](ARCHITECTURE.md) (design architecture). Where those documents
say what was planned, this one says what is true. When they disagree, trust
this one, then update it.

---

## 1. The system at a glance

Lineage traces how an academic concept evolved across arXiv papers and
publishes the result as an interactive, evidence-backed genealogy. Every
relationship on a map is backed by verbatim quotes from both papers, verified
against the extracted source text.

| Component | Technology | Where it runs | Cost |
|---|---|---|---|
| Web app | Next.js 15, Auth.js v5 | Vercel (Hobby), prod alias `lineage-green.vercel.app` | free |
| Database | Neon serverless Postgres, pgvector 0.8 | Neon (Vercel-linked account) | free tier |
| Pipeline | Python 3.12 CLI scripts | Anywhere with the repo and `.env` | LLM spend only |
| Trace worker | Python 3.12, single process | Render Background Worker (declared in `render.yaml`; the owner's laptop until the Render console setup is done) | ~$8/mo |
| LLM | Claude Sonnet (`claude-sonnet-5`) via the Anthropic API | n/a | ~$6 per 150-paper trace |

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
pipeline/            the five stages + auxiliaries (Python, CLI-first)
  common.py          env loading, polite HTTP session, data_dir()
  db/migrate.py      ordered SQL migrations, schema_migrations table
  db/migrations/     001..005
worker/run.py        the trace worker (queue consumer)
app/                 Next.js app (Vercel root directory is app/)
  app/               routes: /, /about, /g/[id], /api/traces, /api/auth
  lib/               db.ts, authz.ts, genealogy.ts, traces.ts, actions
data/                DATA_DIR (gitignored): raw papers, texts, exports, models
```

Two environment files exist and are both gitignored: the repo root `.env`
(pipeline and worker) and `app/.env.local` (Next.js app). They intentionally
hold different `DATABASE_URL` values; see section 8.

---

## 3. Data model

Six tables, migrations `001` through `005`, applied by
`python pipeline/db/migrate.py` (tracked in `schema_migrations`).

**papers** (001, 002): one row per fetched arXiv paper. Notable columns:
`raw_path` and `extracted_text_path` point into `DATA_DIR`;
`text_title_match` (002) records how well the extracted text matches the
claimed title. This guard exists because OpenAlex sometimes attaches the wrong
arXiv id to a work: the fetch succeeds but the text belongs to a different
paper. Real observed cases: arXiv 1810.04805 (BERT) and 1907.11692 (RoBERTa)
both carried unrelated titles. Downstream stages must filter
`text_title_match >= 0.5`.

**definitions** (001, 003, 004): Stage B output, one row per
(paper, concept, prompt_version). That triple is the cache key, deliberately
excluding the model so a model switch does not re-bill an extracted corpus;
`model` (004) records provenance instead. `defines_concept` (003) exists
because a negative verdict ("this paper does not define the concept") is a
finding: before 003, negatives wrote no row, so every re-run re-paid the LLM
for most of the corpus. `embedding vector(1024)` holds the Stage C embedding.

**genealogies** (001): the map itself. `nodes` is JSONB (concept-states with
members and year ranges), `user_edits` is the append-only curatorial audit
trail, `spend_usd` accumulates cost, `status` is loosely one of
pending/running/complete/failed/aborted_spend_cap. Known defect: Stage C
inserts a new row per run instead of reusing the (concept, prompt_version)
row. This produced an orphan after a crashed run (see section 10) and remains
open work.

**edges** (001): typed relationships between nodes, with FK to both papers,
both verbatim quotes, `confidence`, and `verified` (the grounding verdict).
`ON DELETE CASCADE` from genealogies.

**trace_requests** (005): the request inbox and the job queue in one table.
Status flow: `requested -> approved -> running -> complete`, plus `rejected`
and `failed`. `progress` JSONB is written live by the worker; `updated_at`
doubles as the worker heartbeat; `genealogy_id` links the finished map. A
partial unique index allows only one open request per concept, enforced at the
database level because app-level checks can be raced by simultaneous submits.

---

## 4. The pipeline

Five stages plus auxiliaries, each a standalone CLI script reading root
`.env`. The pipeline is CLI-first by rule: the worker orchestrates these same
commands and adds nothing to them.

**Stage A part 1: corpus selection** (`corpus_select.py <concept> --limit N --json PATH`).
Metadata only; nothing is fetched or paid for before the corpus is chosen.
Seeds come from OpenAlex relevance search (an OpenAlex "concept" mode exists
but the default is search: OpenAlex has no ML "attention" concept). Seeds are
filtered by a local embedding relevance check (fastembed bge-small, free) with
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
stub; the extractor detects and unwraps this. Extraction uses pylatexenc for
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
Embeds definitions with bge-large-en-v1.5 (1024-dim, local, free; cached in
`definitions.embedding`), then agglomerative clustering with cosine distance
and no fixed k. `DEFAULT_THRESHOLD = 0.16` was calibrated on real distances:
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
quotes are found verbatim in the extracted source text; otherwise it renders
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
guessed.
`export_related_work.py`: related-work skeleton (Markdown) + BibTeX from a
curated genealogy. Real structure, real citations, real verified quotes, no
invented prose.
`restore_genealogy.py`: the inverse of Stage E's export; re-inserts a
genealogies row and its edges from a JSON export and records the restoration
in the audit trail. Written during incident 4 and kept as the recovery path.

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

Deployment is declared in `render.yaml`: a Render Background Worker plus a
5 GB persistent disk at `/data` holding `DATA_DIR` and the embedding model
cache. Both `TextEmbedding` call sites pass `cache_dir` under `DATA_DIR`
because fastembed's default cache is a temp directory, which on a deployed box
means re-downloading ~1.3 GB of models every restart.

---

## 6. The web application

Next.js 15 App Router, all server components except where interactivity
requires a client component. Reads Postgres through the Neon HTTP driver
(`lib/db.ts`), which wants the **pooled** endpoint: each query is a fetch,
which suits serverless.

**Routes.**
- `/` : genealogy list plus the Live traces panel (request form, queue,
  progress). Server component fetches initial state; the panel
  (`trace-panel.tsx`, client) polls `/api/traces` every 3 s while any trace is
  active.
- `/g/[id]` : the genealogy page. Timeline of concept-state cards, typed
  relationship rows with evidence panels (both quotes, verification stamp,
  confidence), workbench edit controls (owner only), audit trail, danger zone
  (owner only).
- `/about` : the public methods page. Claims, pipeline steps, edge taxonomy
  (rendered from the same `EDGE_MEANING` map the product uses, so it cannot
  drift), curation model, and an explicit limitations section.
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
anywhere in user-facing content**.

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

**Observing a trace.** The UI's Live traces panel is the primary view.
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

---

## 11. Known limitations and open work

Product limitations (also disclosed on `/about`): arXiv-only coverage; exact
string matching fails closed to "inferred" when extraction mangles a passage;
parallel discovery without citation appears as unconnected meanings; edge
types and confidences are model judgment, mitigated by the quotes being shown.

Open engineering work, in priority order:

1. Finish the Render console setup (owner action) and verify a live trace
   through the deployed worker.
2. Stage C should upsert its genealogy row per (concept, prompt_version)
   instead of inserting a new one per run.
3. Account-level Anthropic billing cap (owner action, console).
4. Curate the dropout genealogy (12 draft nodes want merging to ~5).
5. Proper 403s instead of fail-closed 500s on unauthorised writes.
6. Some notification when a stranger's request lands (currently visible only
   by visiting the site).
7. `genealogies.status` semantics are loose and partly vestigial.
8. **Topic-scoped traces (backlog idea, 2026-07-19).** Corpus selection
   currently hardcodes the OpenAlex "Computer science" concept filter
   (`C41008148`), and OpenAlex has deprecated concepts in favour of Topics
   (verified live: `topics.field.id:fields/17` and `primary_topic.field.id`
   filters work; the any-topic variant suits a recall stage best). The idea:
   let the person requesting a trace choose the subject area from a
   selectable list of OpenAlex Topics, restricted to Topics that actually
   have arXiv-indexed papers (or a similar availability signal), instead of
   silently assuming computer science. Touches `corpus_select.py` (a
   `--topic` argument replacing the fixed filter), the trace request form
   (a topic picker populated from the OpenAlex Topics API), and
   `trace_requests` (store the chosen topic with the request). Folds the
   concepts-to-Topics migration into a user-facing feature instead of a
   silent swap.

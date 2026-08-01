# Lineage

Concept genealogy engine — traces how an academic concept evolved across arXiv
papers. See [CLAUDE.md](CLAUDE.md) for the full spec, scope, and build order.

## Layout

- `pipeline/` — Python CLI scripts, one per pipeline stage (Stage A–E). Each
  runs standalone before any UI exists.
- `pipeline/db/` — migrations + tiny migration runner.
- `app/` — Next.js front end + API (Phase 3+).
- `docker-compose.yml` — optional local Postgres 16 + pgvector fallback.

## Setup

Database is Neon (serverless Postgres, pgvector supported). Create a project at
neon.tech, then use its connection string. Local Docker Postgres is an optional
fallback — see `docker-compose.yml`.

```sh
# 1. Secrets / config
cp .env.example .env        # set DATABASE_URL to your Neon string + API keys

# 2. Python env + migrate (creates the four tables in Neon)
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r pipeline/requirements.txt
python pipeline/db/migrate.py

# 3. App (later phases)
cd app && npm install && npm run dev
```

## Pipeline CLI

```sh
# Stage A part 1: ranked candidate corpus (metadata only, no downloads)
python pipeline/corpus_select.py "attention" --limit 150 --json corpus.json
#   --field fields/N : scope to an OpenAlex field (default fields/17 = Computer
#                      Science; 'all' drops the field filter)
#   --gloss "..."    : disambiguate a polysemous sense; becomes the relevance
#                      query (e.g. "kernel" --gloss "kernel methods in SVMs")

# Acquisition: download arXiv source (LaTeX-first) into DATA_DIR + papers table
python pipeline/fetch_papers.py corpus.json --dry-run   # preview, no downloads
python pipeline/fetch_papers.py corpus.json --limit 10  # fetch (1 req / 3s)

# Text extraction: LaTeX/PDF source -> clean text (reads papers table)
python pipeline/extract_text.py

# Stage B: per-paper definition extraction (needs ANTHROPIC_API_KEY)
python pipeline/stage_b_extract.py "attention" --dry-run   # cost estimate, no API call
python pipeline/stage_b_extract.py "attention" --limit 5   # model from LLM_MODEL / .env
python pipeline/stage_b_extract.py "attention" --model claude-haiku-4-5

# Stage C: embed definitions + cluster into concept-states (nodes)
python pipeline/stage_c_cluster.py "attention"                     # LLM-labelled nodes
python pipeline/stage_c_cluster.py "attention" --no-label          # offline, free

# Stage D: classify edges from cross-node citations (Semantic Scholar, no key)
python pipeline/stage_d_edges.py "attention" --dry-run             # show citation links
python pipeline/stage_d_edges.py "attention"

# Stage E: grounding check + assemble genealogy JSON
python pipeline/stage_e_ground.py "attention"

# Workbench: curate the draft (every edit is recorded in genealogies.user_edits,
# attributed to LINEAGE_ACTOR if set, else user@host, and always as unverified)
python pipeline/workbench.py "attention" list
python pipeline/workbench.py "attention" merge n6 --into n4
python pipeline/workbench.py "attention" delete-node n5
python pipeline/workbench.py "attention" rename n4 "Self-attention as the whole architecture"
python pipeline/stage_e_ground.py "attention"          # re-ground + re-export after edits

# Export: related-work skeleton (Markdown) + BibTeX
python pipeline/enrich_authors.py --concept "attention"   # real authors (arXiv first)
python pipeline/export_related_work.py "attention"
```

## Trace worker (live trace requests)

The deployed app lets signed-in visitors *request* a trace and shows live
progress; the owner approves requests (each run costs real LLM spend). The
queue is the `trace_requests` table itself — the worker claims `approved` rows
with `FOR UPDATE SKIP LOCKED`, runs the pipeline stages above as subprocesses,
and streams their stdout into `trace_requests.progress` for the UI to poll.

```bash
python worker/run.py           # poll forever (10s interval)
python worker/run.py --once    # process at most one job, then exit
```

Needs the same root `.env` as the pipeline (direct DB endpoint, API key,
DATA_DIR). Vercel never runs traces — a trace takes ~15 min and needs a disk,
so the worker runs on any long-lived box (a laptop counts).

### Deploying the worker (Render)

`render.yaml` declares the production worker: a Render Background Worker with
a 5 GB persistent disk mounted at `/data` for papers, exports, and the
embedding-model cache. Deploy: Render dashboard -> New -> Blueprint -> pick
this repo; Render reads `render.yaml` and prompts for the three secrets
(DATABASE_URL = the DIRECT/unpooled Neon string, ANTHROPIC_API_KEY,
OPENALEX_MAILTO). First build downloads the embedding models to the disk;
later restarts reuse them. Pushes to master auto-deploy the worker.

## Extraction audit

Everything the grounding check guarantees rests on the extracted text under
`DATA_DIR`. This scans it for the marks damage leaves behind (macros the parser
drops in silence, residue from a degraded parse, symbols that left no trace,
sections that vanished). No model, no network, no cost.

```sh
python pipeline/check_extraction.py                          # every extracted paper
python pipeline/check_extraction.py --concept "embedding"    # one corpus
python pipeline/check_extraction.py --concept "embedding" --sample 8
python pipeline/check_extraction.py --json data/extraction_audit.json
python pipeline/check_extraction.py --compare-verdicts            # read-only
```

It is a lower bound: it finds damage that leaves a mark, and the worst damage
leaves none. Papers it flags are papers worth opening on arXiv. `--write` stores
each verdict on the paper (migration 013) so the app can tell a reader what it
knows about the text a quote was matched against, along with a digest of the
calibration that produced it (migration 014). `--only-unchecked` counts a verdict
written by a different calibration as unchecked, so moving a threshold here
re-measures the corpus at the worker's next start and nobody has to remember to
clear anything.

Three signals are reported and deliberately do not decide the verdict: text that
predates the current extractor, gaps where a token was, and dropped package
macros. Each is true and useful to an operator, and none of them means what the
reader-facing note says, which is that the passage in front of you may be missing
wording the paper had. That split took the note from 218 papers of 304 (72%) to
113 (37%) with nothing becoming stricter.

`--compare-verdicts` prints today's verdicts against the ones a named proposal
would give, and a table of how often each signal is the sole reason a paper is
not clean. It changes no threshold and stores nothing, and it refuses `--write`,
`--clear-verdicts`, `--dry-run`, `--only-unchecked` and `--sample`. It exists
because this check has been recalibrated four times off its own corpus rate, and
a rate says the check is wrong without pointing at a signal.

Read the two tables for different things. The sole cause columns are per signal
and tell you which one to suspect; they do not add up, because a paper carrying
two of them is counted in neither. The joint effect of demoting several at once
is the crosstab. With no proposal named it prints the sole-cause table and says
there is nothing on trial, rather than a crosstab of no movement.

### Repairing a map after the extracted text changes

Fixing the extractor changes the text under stored quotes. Re-running the
pipeline is the wrong move: Stage C rewrites `genealogies.nodes` wholesale, so a
curated map loses its labels and merges. The safe path updates definitions in
place, keeping the ids the nodes point at:

```sh
python pipeline/extract_text.py --concept "attention" --force  # scoped: the papers
                                                               # table is shared, so
                                                               # --force alone would
                                                               # re-extract every map
python pipeline/stage_b_extract.py "attention" --refresh       # fresh quotes, ids kept
python pipeline/stage_c_cluster.py "attention" --embed-only    # vectors, no re-clustering
python pipeline/stage_e_ground.py "attention"                  # re-ground, honestly
python pipeline/stage_h_claims.py "attention"                  # re-check claim quotes
python pipeline/check_extraction.py --concept "attention"      # confirm staleness gone
```

Exercise it on an uncurated map first. Never re-anchor a stored quote to the new
text to make it pass: a lost symbol is content, and unlike whitespace it cannot
be folded into the grounding check.

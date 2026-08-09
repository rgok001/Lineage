# Lineage

CLASS: derived
RECOMPUTED BY: the Developer, in the same commit as any change to setup, the
CLI, or how the pipeline is run.

Concept genealogy engine — traces how an academic concept evolved across arXiv
papers. See [CLAUDE.md](CLAUDE.md) for the full spec, scope, and build order.

## License

Source-available under the
[PolyForm Noncommercial License 1.0.0](LICENSE.md): the code is public to
read and free to use for any noncommercial purpose; commercial rights stay
with the owner (decision 33, issue 142).

## Layout

- `pipeline/` — Python CLI scripts, one per pipeline stage. Each runs standalone
  before any UI exists. What each stage does, and the thirteen steps the worker
  actually runs, is [docs/PIPELINE.md](docs/PIPELINE.md); this file is how to
  invoke them.
- `pipeline/db/` — migrations + tiny migration runner.
- `worker/` — the trace worker: claims approved requests and runs the stages.
- `app/` — Next.js front end + API. Vercel deploys from here.
- `.githooks/` — the pre-commit record check. Enabled per clone, see Setup.
- `docker-compose.yml` — optional local Postgres 16 + pgvector fallback.

## Setup

Database is Neon (serverless Postgres, pgvector supported). Create a project at
neon.tech, then use its connection string. Local Docker Postgres is an optional
fallback — see `docker-compose.yml`.

```sh
# 1. Secrets / config
cp .env.example .env        # set DATABASE_URL to your Neon string + API keys

# 2. Python env + migrate (applies every pending migration; safe to re-run)
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r pipeline/requirements.txt
python pipeline/db/migrate.py

# 3. App
cd app && npm install && npm run dev

# 4. Record check on commit (once per clone; git does not clone hooks)
git config core.hooksPath .githooks
```

## Pipeline CLI

```sh
# Stage A part 1: ranked candidate corpus (metadata only, no downloads)
python pipeline/corpus_select.py "attention" --limit 150 --json corpus.json
#   --field fields/N : scope to an OpenAlex field (default fields/17 = Computer
#                      Science; 'all' drops the field filter)
#   --gloss "..."    : disambiguate a polysemous sense; becomes the relevance
#                      query (e.g. "kernel" --gloss "kernel methods in SVMs")
#   --anchor ID      : a paper the map should not miss, by arXiv id. Repeatable,
#                      at most 3, and additive: it takes no seat from a paper
#                      that earned one. It skips SELECTION and nothing else, so
#                      Stage B still decides whether it defines the term and
#                      Stage D still needs a real citation link. An id OpenAlex
#                      cannot resolve stops the run by name, before anything is
#                      fetched or spent

# Pass two's selection: the recent papers an ALREADY-BUILT map nominates.
# Reads the map (nodes + edges), writes files, changes no row. No LLM call, with
# or without --dry-run. The worker runs this as the first step of pass two
# (#192); by hand it is a read-only instrument, safe against a live map.
python pipeline/pass_two_select.py "dark energy" --field fields/31 \
    --recent-since 2021 --pass-two-seats 15 --json corpus_pass2.json \
    --stats-json pass2_stats.json
python pipeline/pass_two_select.py "attention" --dry-run   # select, print, write nothing
#   the output is a corpus file --corpus reads, with pass/nominators_cited added
#   --stats-json : the funnel counts, which the build records on the map

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
python pipeline/stage_c_cluster.py "attention" --corpus corpus.json  # only these papers
                                                                   # may be in the map
python pipeline/stage_c_cluster.py "attention" --no-label          # no LLM labels; still
                                                                   # embeds via Voyage

# Stage D: classify edges from cross-node citations (Semantic Scholar, no key)
python pipeline/stage_d_edges.py "attention" --dry-run             # links, and how many
                                                                   # are already cached
python pipeline/stage_d_edges.py "attention"

# Stage E: grounding check + assemble genealogy JSON, and publish the map
python pipeline/stage_e_ground.py "attention"
python pipeline/stage_e_ground.py "attention" --no-publish   # assemble, leave it
                                                             # unpublished and unasked
                                                             # (a two-stage build's
                                                             # intermediate assemblies)

# The two passes' corpora, joined into the file the union re-cluster is scoped by
python pipeline/corpus_union.py --json corpus_union.json corpus.json corpus_pass2.json

# Which pass read which papers, and how the second pass ended (the report's
# pass figures read this; migration 022)
python pipeline/record_pass.py "attention" --pass 1 --corpus corpus.json
python pipeline/record_pass.py "attention" --pass 2 --corpus corpus_pass2.json
python pipeline/record_pass.py "attention" --build --passes 2 \
    --outcome "The second pass filled all 15 of its seats and read them." \
    --seats 15 --candidates 611 --cleared 45
python pipeline/record_pass.py "attention" --show   # what is recorded; writes nothing

# Which of a map's papers a person named (the report's disclosure; migration 023).
# Run on every build: it also clears what the previous build recorded, so a map
# rebuilt with nobody named comes back saying nobody named a paper
python pipeline/record_anchors.py "attention" --corpus corpus.json --named-by rgok001
python pipeline/record_anchors.py "attention" --show  # writes nothing

# Stage F: per-paper magnitude (attention + displacement). Run after Stage D,
# which populates the citation cache it reads
python pipeline/stage_f_magnitude.py "attention"

# Stage G: compose the threads the map's front door opens on (needs Stage E)
python pipeline/stage_g_threads.py "attention"
python pipeline/stage_g_threads.py "attention" --threads 6   # target count; default scales with corpus

# Stage H: a checked quote under each claim in a thread's account (needs Stage G)
python pipeline/stage_h_claims.py "attention"
python pipeline/stage_h_claims.py "attention" --thread s0    # one thread, to try it first
python pipeline/stage_h_claims.py "attention" --recheck      # re-ground stored quotes, no model, free

# F, G and H all spend: none of them has a --dry-run, and --model overrides each
# stage's own default (Haiku for F and G, Sonnet for H) rather than LLM_MODEL.

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

## Does a map still satisfy the rules that built it?

Six clauses about a stored map — that every definition a concept-state names is
one the clustering would admit today, that its members and its definitions
describe the same papers, that every relationship names two concept-states this
map has and is evidenced by papers those concept-states hold, and that the
threads name no paper the map does not hold. They live in one SQL view
(migration 021) and are read by this command and by Stage E, which refuses to
publish a map that fails one. No model, no network, no cost, no writes.

```sh
python pipeline/check_map.py "attention"       # one map
python pipeline/check_map.py --all             # every map
python pipeline/check_map.py --all --json      # always an array, empty included
```

It reads `LINEAGE_READ_URL` (the read-only role) and issues nothing but
`SELECT`, so it is safe to point at production, and its exit status is its
verdict: 0 if every map asked about satisfies all six clauses, 1 if any does
not. Every finding names what to repair. Nothing is stored, so the answer is
always about the map as it is now.

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

Needs the same root `.env` as the pipeline; every variable it reads, and which
Neon endpoint each wants, is in the environment table in
[docs/RUNBOOK.md](docs/RUNBOOK.md). Vercel never runs traces: a trace takes
roughly 18 to 23 minutes (two runs measured on 2026-08-01: 18.3 and 23.3
minutes) and needs a disk, so the worker runs on any long-lived box (a laptop
counts).

### Deploying the worker (Render)

`render.yaml` declares the production worker: a Render Background Worker with
a 5 GB persistent disk mounted at `/data`. The disk holds `DATA_DIR` and
nothing else: fetched papers, extracted text, exports. Nothing is downloaded
into it at build time, because embeddings are the Voyage hosted API and the
worker loads no models.

Deploy: Render dashboard -> New -> Blueprint -> pick this repo. Render reads
`render.yaml` and prompts for the four secrets it marks `sync: false`:
`DATABASE_URL` (the DIRECT, unpooled Neon string), `ANTHROPIC_API_KEY`,
`VOYAGE_API_KEY` and `OPENALEX_MAILTO`. All four are required, including
`ANTHROPIC_API_KEY`, which no code reads by name because the Anthropic SDK
takes it from the environment itself. A worker missing `VOYAGE_API_KEY` boots
and looks healthy, then fails every trace at corpus selection. Pushes to master
auto-deploy the worker; the rest of the procedure is
[docs/RUNBOOK.md](docs/RUNBOOK.md).

## Record check

The documents in `docs/` describe code that moves underneath them, and until
2026-08-02 nothing checked that they still matched it. This resolves the record's
claims against the code and fails when they disagree. No model, no network, no
database, no cost.

```sh
python pipeline/check_record.py            # what the pre-commit hook runs
python pipeline/check_record.py --all      # also fail on .claude/memory/, for
                                           # the Manager and the Tester
python pipeline/check_record.py --counts   # resolution counts, exit 0
```

It runs in both directions. Documents to code: a backticked
`` `IDENT = literal` `` in a `law` or `derived` file must match what the code
assigns, a `path:NNN` citation must carry a commit-ish, and every record file
must declare its class. Code to documents: every `pipeline/*.py`, every
migration number and every stage the worker runs must be named by a tracked
`derived` document. That second direction is what catches the code growing
something no document noticed.

`git config core.hooksPath .githooks` installs it as a pre-commit hook. It is
bypassable with `--no-verify`, deliberately: a bypass is an act, visible in the
reflog and nameable in review, and forgetting is neither. Findings in
`.claude/memory/` are warnings, because that directory is gitignored and cannot
be in a commit; blocking a commit on it would only teach people to bypass.

**A run that resolves zero claims fails**, naming the check that resolved
nothing. A restructure that breaks the claim parser would otherwise leave every
check green over an empty set. There is no threshold anywhere in it, and adding
one is the change to argue about rather than make: every check is exact equality
or existence, and the reasoning is in issue 54's design and in the file's own
comments.

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
python pipeline/stage_h_claims.py "attention" --recheck        # re-ground stored claim
                                                               # quotes, free; without
                                                               # --recheck it rewrites the
                                                               # accounts for $4-6
python pipeline/check_extraction.py --concept "attention"      # confirm staleness gone
```

Exercise it on an uncurated map first. Never re-anchor a stored quote to the new
text to make it pass: a lost symbol is content, and unlike whitespace it cannot
be folded into the grounding check.

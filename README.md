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

# Workbench: curate the draft (every edit is recorded in genealogies.user_edits)
python pipeline/workbench.py "attention" list
python pipeline/workbench.py "attention" merge n6 --into n4
python pipeline/workbench.py "attention" delete-node n5
python pipeline/workbench.py "attention" rename n4 "Self-attention as the whole architecture"
python pipeline/stage_e_ground.py "attention"          # re-ground + re-export after edits

# Export: related-work skeleton (Markdown) + BibTeX
python pipeline/enrich_authors.py --concept "attention"   # real authors (arXiv first)
python pipeline/export_related_work.py "attention"
```

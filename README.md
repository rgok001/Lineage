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
python pipeline/stage_b_extract.py "attention" --limit 5   # default model: claude-opus-4-8
python pipeline/stage_b_extract.py "attention" --model claude-haiku-4-5
```

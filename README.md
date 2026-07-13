# Lineage

Concept genealogy engine — traces how an academic concept evolved across arXiv
papers. See [CLAUDE.md](CLAUDE.md) for the full spec, scope, and build order.

## Layout

- `pipeline/` — Python CLI scripts, one per pipeline stage (Stage A–E). Each
  runs standalone before any UI exists.
- `pipeline/db/` — migrations + tiny migration runner.
- `app/` — Next.js front end + API (Phase 3+).
- `docker-compose.yml` — Postgres 16 with pgvector.

## Setup

```sh
# 1. Secrets / config
cp .env.example .env        # then fill in API keys

# 2. Database
docker compose up -d
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r pipeline/requirements.txt
python pipeline/db/migrate.py

# 3. App (later phases)
cd app && npm install && npm run dev
```

## Pipeline CLI

```sh
# Stage A part 1: ranked candidate corpus (metadata only, no downloads)
python pipeline/corpus_select.py "attention" --limit 150
```

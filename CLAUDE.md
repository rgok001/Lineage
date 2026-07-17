# Lineage — concept genealogy engine

## What this is
A web app that traces how an academic concept evolved across papers. User enters a concept (e.g. "attention"), the system reads ~150 arXiv papers and produces an interactive genealogy: a timeline of concept-states (nodes) connected by typed, evidence-backed relationships (edges).

This is a **real application, not a portfolio demonstrator** (revised — it began as the latter). The app is database-backed: it reads and writes live Postgres, and the workbench edits persist. Still prefer boring tech and shipping over speculative generality — but robustness, correctness and a usable UI are now in scope, not deferred. The four core product rules below were always non-negotiable and remain so.

## Core product rules (do not violate)
1. Every edge displayed carries verbatim evidence quotes from both papers.
2. GROUNDING CHECK is mandatory: every quote must be string-verified against the extracted source text. Verified edges render solid; failed/inferred edges render dotted and are labelled "inferred". Never display an unverified quote as verified.
3. The product is a workbench, not an oracle: users can split, merge, rename, delete nodes and reclassify/delete edges. UI copy never claims the map is "the" history.
4. Never fabricate paper metadata, quotes, or citations in any output, including the export.

## Edge taxonomy (exactly six)
extends · contests · narrows · renames · merges · migrates

## Scope: IN
- arXiv ML/CS papers only, English only
- One showcase concept pre-built: "attention"
- Custom trace builds (async job, live progress feed)
- Timeline genealogy UI, evidence panel, workbench editing
- Export: related-work skeleton (Markdown) + BibTeX
- Minimal accounts: save/load maps

## Scope: OUT (do not build, do not scaffold "for later")
Reference-manager integration, collaboration/sharing, PDF annotation, non-arXiv sources, browser extension, mobile apps, social features, formal eval harness/golden set.

## Architecture (4 zones)
1. ACQUISITION (metadata-first: never fetch full text before corpus selection)
   - OpenAlex API: citation graph, metadata, concept tags, OA locations. Free, no key. Use polite pool (mailto param).
   - Semantic Scholar API: citation contexts (sentences around citations). Free key. Respect rate limits.
   - arXiv fetcher: LaTeX source preferred, PDF fallback. HARD RULE: rate-limit to 1 request per 3 seconds, identify with a proper User-Agent, exponential backoff on 429/5xx.
   - Text extraction: LaTeX → structured text; PDF fallback via pymupdf.
2. PIPELINE (all LLM calls via Anthropic API)
   - Stage A corpus selection: OpenAlex tagged papers → 1-hop citation expansion → embedding relevance filter → ranked, capped at 150.
   - Stage B definition extraction: per paper, structured JSON {definition, verbatim_quote, section, novelty_claims}. CACHED PER PAPER (keyed by arXiv ID + prompt version), reused across traces.
   - Stage C drift detection: embed definitions, cluster → concept-states (nodes).
   - Stage D edge classification: citation-linked pairs across clusters + citation contexts → one of six edge types + evidence quote from each paper + confidence 0–1.
   - Stage E grounding check (see rule 2), then graph assembly → genealogy JSON.
3. STORAGE: Postgres + pgvector (papers, definitions, embeddings, edges, genealogies, user edits). Object store or local disk for raw tex/pdf + extracted text.
4. APP: Next.js front end + API. Trace builds run on a job queue with server-sent progress events ("Reading paper 47 of 132…").

## Engineering rules
- Cost discipline from day one: log token spend per pipeline stage; enforce a per-trace spend cap (env var, default US$10) that aborts the job cleanly; provide a --dry-run mode that estimates cost without calling the LLM.
- Cache aggressively: per-paper extractions and full trace outputs are immutable once built (invalidate only on prompt-version bump).
- All pipeline stages runnable as standalone CLI scripts before any UI exists.
- Secrets in .env, never committed. Keys needed: ANTHROPIC_API_KEY, SEMANTIC_SCHOLAR_API_KEY.
- Prefer boring tech. No microservices, no Kubernetes, no message brokers. One repo, one Postgres, one Next.js app, one worker process.

## UI design tokens (from approved mockup — keep consistent)
- Palette: paper #EDF0F1, card #FBFCFC, ink #1C2B33, ink-soft #5A6B74, line #D8DEE1
- Edge colours: extends #33628C · contests #A34A3A · narrows #6B5B95 · renames #8A7433 · migrates #3E7257
- Type: Spectral (display/quotes, serif), IBM Plex Sans (UI), IBM Plex Mono (data/years/labels)
- Evidence panel: two facing quote-cards, verification stamp (green ✓ verified / red ◌ inferred + confidence)
- Solid edges = verified, dotted = inferred. Legend always visible.

## Build phases (work in this order)
1. Acquisition CLI: given a concept, produce the ranked 150-paper corpus (metadata only) and print it. Then the fetcher + extraction for those papers.
2. Pipeline CLI: stages B–E end-to-end on "attention"; output genealogy JSON. Inspect by hand, iterate prompts.
3. UI: timeline canvas + evidence panel rendering the genealogy JSON (match tokens above), then workbench editing + export.
4. Trace-build UX: job queue, live progress feed, save/load.

## Definition of done for the demonstrator
The pre-built "attention" map loads instantly, is hand-curated to be defensible, every solid edge's quotes verify, a custom trace on a new concept completes in under ~15 min and under the spend cap, and export produces a usable related-work skeleton with valid BibTeX.

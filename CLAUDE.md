# Lineage — concept genealogy engine

CLASS: law
RECOMPUTED BY: nothing. The owner decides this file. It is not derived from the
code, so a change to the code cannot make it stale. Where the system disagrees
with it, either the system is violating its law or the law has moved: say which.

## What this is
A web app that traces how an academic concept evolved across papers. User enters a concept (e.g. "attention"), the system reads ~150 arXiv papers and produces an interactive genealogy: a timeline of concept-states (nodes) connected by typed, evidence-backed relationships (edges).

This is a **real application, not a portfolio demonstrator** (revised — it began as the latter). The app is database-backed: it reads and writes live Postgres, and the workbench edits persist. Still prefer boring tech and shipping over speculative generality — but robustness, correctness and a usable UI are now in scope, not deferred. The four core product rules below were always non-negotiable and remain so.

## Where the work lives

**GitHub Issues is the only list of open work**, and is canonical: https://github.com/rgok001/Lineage/issues
If a document and an issue disagree, the issue is right. Titles carry the original item id (`[B21]`, `[F3]`, `[Q7]`) because commit messages and
the `docs/` record cite those numbers; they are never reused.
`docs/ROADMAP.md` holds direction and sequencing, not items. `docs/AS-BUILT.md` holds what is true today, `docs/PIPELINE.md` holds how the pipeline works stage by stage, `docs/DECISIONS.md` holds why, and `docs/RUNBOOK.md` holds how to operate it.

**No design and no code without a ticket.** Before an Architect designs, before
a Developer edits a file, there must be a GitHub issue for the work. If none
exists, create it first and say so. This is not bureaucracy: it is what stops
the fifth undocumented fix, and it is why the item numbers in this repository
can be cited from a commit message years later. Reference the issue in the
commit, so the ticket and the change that closed it stay attached.

## The need this answers

**The need.** Someone writing a literature review needs to know how a concept
actually developed: which papers moved it, and what each one changed. A search
returns a pile of papers ranked by relevance, not the shape of the idea. Asking a
language model returns a fluent paragraph nobody can check, occasionally citing
work that does not exist. The only reliable method is to reconstruct it by hand
from the papers, which takes weeks, and every researcher who needs it does it
again from scratch.

**What Lineage does about it.** It reads the literature around a term and lays
out the lines of work the idea split into, in order, with a verbatim quote from
the source behind each claim. The reconstruction is the product; the checking is
what makes it worth having. A reader who doubts a claim can verify it in seconds
rather than taking it on trust.

**What is guaranteed and what is not.** A quote carrying the verified stamp is
checked word for word against this system's own extraction of that paper's
text. That is mechanical and it
holds. The shape — which papers cluster together, which relationships exist and
in which direction, which papers matter most — is the tool's reading, and is
labelled as such wherever it appears. See `docs/ROADMAP.md` for why that
distinction governs what gets built next.

**Who it is for, and what it is not.** The product is the generator, not a
curated collection: it provides the capability to make a map, and does not claim
expertise in any field a map covers. It reads arXiv only, so it is useful for
machine learning and adjacent preprint fields and not yet for anything else.

## Core product rules (do not violate)
1. Every edge displayed carries evidence quotes from both papers, shown word for word as the papers wrote them.
2. GROUNDING CHECK is mandatory: every quote must be checked word for word against this system's own extraction of the paper's text. Verified edges render solid; failed/inferred edges render dotted and are labelled "inferred". Never display an unverified quote as verified. (Wording aligned with the shipped copy on the owner's instruction, 2026-08-08, after issue 135: "verbatim" describes a passage, never a check, and the check is named as running against our own extraction, not "the source".)
3. The product is a workbench, not an oracle: users can split, merge, rename, delete nodes and reclassify/delete edges. UI copy never claims the map is "the" history.
4. Never fabricate paper metadata, quotes, or citations in any output, including the export.

## Edge taxonomy (exactly six)
extends · contests · narrows · renames · merges · migrates

## Scope: IN
- All arXiv papers, every field, English only (owner decision 36, 2026-08-08, issue 161: "we should not discriminate" — the ML/CS restriction is lifted; quality per field is measured on each map's report after it builds, not gated before)
- One showcase concept pre-built: "attention"
- Custom trace builds (async job, live progress feed)
- Timeline genealogy UI, evidence panel, workbench editing
- Export: related-work skeleton (Markdown) + BibTeX
- Minimal accounts: save/load maps

## Scope: OUT (do not build, do not scaffold "for later")
Reference-manager integration, collaboration/sharing, PDF annotation, browser extension, mobile apps, social features, formal eval harness/golden set.

**Non-arXiv sources came off this list on 2026-08-02** (Product Owner). It is the
single biggest limit on who the product is useful to, and the public roadmap page
had been promising it while this list forbade it. It is now roadmap item F7 and is
sequenced after the map can report on its own quality, not before: a new source
changes extraction quality, and adding one before there is an instrument to see
that produces more maps nobody can assess. Coming off the OUT list means it may
be designed and built when it is reached. It does not mean scaffolding for it now.

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
- Database access is refused by default. `.claude/settings.json` sets `LINEAGE_NO_DB=1`, so `env("DATABASE_URL")` raises rather than connecting. Pipeline runs against Neon happen from a terminal outside Claude Code, or through the worker. No agent shell reaches production directly.
- Deployments are fully automatic, migrations included (owner decision 31, 2026-08-07, issue 102): a push to `master` deploys the app via Vercel and the worker via Render, whose pre-deploy step runs `pipeline/db/migrate.py`. Because the app can go live minutes before the worker applies a migration, migrations must be additive and the app must tolerate a schema one migration behind.
- `LINEAGE_READ_URL` is the read-only connection: the `lineage_ro` Postgres role, SELECT and nothing else. It is the only database access any agent may use, and the Operator is the only role that uses it. It is deliberately not named DATABASE_URL so that no existing code path can route through it by accident.
- Prefer boring tech. No microservices, no Kubernetes, no message brokers. One repo, one Postgres, one Next.js app, one worker process.

## The record: one destination per kind of thing

Every record file declares its class in its first two lines. A fact lives in
exactly one file and everywhere else links to it. Two homes for one fact is how
this record goes stale, and it has already cost us: the deleted
`docs/ARCHITECTURE.md` still forbade non-arXiv sources weeks after this file
released them, and the public roadmap page was promising them meanwhile.

| Kind of thing | Destination | Class |
|---|---|---|
| Product law, scope, non-negotiable rules | `CLAUDE.md` | law |
| What to build next, and why | `docs/ROADMAP.md` | law |
| How the system actually works today | `docs/AS-BUILT.md` | derived |
| How the pipeline works, stage by stage | `docs/PIPELINE.md` | derived |
| How to operate it: env vars, deploys, procedures | `docs/RUNBOOK.md` | derived |
| Why a load-bearing choice was made | `docs/DECISIONS.md` | history |
| What went wrong and what it taught | `docs/INCIDENTS.md` | history |
| Setup and CLI usage | `README.md` | derived |
| Open work, one item per ticket | GitHub Issues (https://github.com/rgok001/Lineage/issues) | ticket |
| A lesson a role earned | `.claude/memory/<role>/` | derived |
| One role's note to another, not yet known to be work | `.claude/memory/board.md` | inbox |
| Which lessons were actually used | `.claude/memory/verdicts.md` | history |
| Whether the team is working | `.claude/memory/dashboard.md` | derived |
| The team's prompts and memory, backed up | `rgok001/agent-cluster` (private) | derived |

**law** — decided, not observed. Only the owner edits it. Cannot go stale,
because it is a choice rather than a description of something that moves.

**history** — dated and append-only. Never edit an entry after the fact; a
correction is a new entry naming the one it corrects. Cannot go stale, because
an entry is a claim about a moment.

**derived** — describes something that changes underneath it. **Must name what
recomputes it and on what trigger, in its own header. A derived file with no
named recomputer is deleted, not fixed** — nothing is keeping it true, so it is
a liability wearing a document's clothes.

**ticket** — born with the work and removed when it closes. Cannot age, because
it does not outlive the thing it describes.

**inbox** — a note from one role to another that is not yet known to be work.
Cannot go stale, because the Curator ages it on a fixed rule: promoted to an
issue or deleted, and two passes without action means deletion. An entry that
turns out to be work stops being an inbox note the moment it becomes a ticket.

Staleness is therefore possible in exactly one class, and that class names its
owner. The whole exposure is one command:

```sh
grep -A1 "^CLASS: derived" CLAUDE.md README.md docs/*.md .claude/memory/*.md
```

If something you want to write fits no row above, it does not get written. Add
the row first, deliberately, or put the content in the file that already owns it.

## UI design tokens (owner-blessed 2026-08-07, decision 32 — keep consistent)
The shipped dark palette is the law; the light values from the original mockup
were retired when the owner blessed what the site actually ships (issue 116).
- Palette: paper #0d1317, card #121a20, card-2 #182126, ink #e8eef1, ink-soft #8b9aa2, ink-faint #5a6a72, line #223038, line-soft #18232a
- Edge colours: extends #6b9bd0 · contests #c9776a · narrows #9a8ac4 · renames #c9a84e · migrates #5cb389 · merges #d0895c
- Stamp colours: verified #5cb389 · inferred #f0605f
- Type: Georgia (display/quotes, serif) · system UI sans (UI) · system monospace (data/years/labels). Named for what ships (owner decision 35, 2026-08-08, issue 148): no webfonts — their cost lands on the render path the speed work paid down.
- Evidence panel: two facing quote-cards, verification stamp (green ✓ verified / red ◌ inferred + confidence)
- Solid edges = verified, dotted = inferred. Legend always visible.

## Build phases (work in this order)
1. Acquisition CLI: given a concept, produce the ranked 150-paper corpus (metadata only) and print it. Then the fetcher + extraction for those papers.
2. Pipeline CLI: stages B–E end-to-end on "attention"; output genealogy JSON. Inspect by hand, iterate prompts.
3. UI: timeline canvas + evidence panel rendering the genealogy JSON (match tokens above), then workbench editing + export.
4. Trace-build UX: job queue, live progress feed, save/load.

## Definition of done for the demonstrator
The pre-built "attention" map loads instantly, is hand-curated to be defensible, every solid edge's quotes verify, a custom trace on a new concept completes in under ~15 min and under the spend cap, and export produces a usable related-work skeleton with valid BibTeX.

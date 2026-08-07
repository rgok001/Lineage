# Lineage: As-Built Documentation

CLASS: derived
RECOMPUTED BY: the Developer, in the same commit as any behaviour change. This
is the only class of record that can go stale, and this is the largest file in
it — if a section cannot be checked against the code in a few minutes, that is a
reason to split it, not a reason to trust it.

This is the as-built record: a description of the system as it actually exists,
including the deviations and hard-won rules that shaped it.

Product law — what the system must do — lives in [CLAUDE.md](../CLAUDE.md), and
is decided rather than observed. This file says what is true of the system today
and is derived from the code, so this is the file that can go stale. Where the
two disagree, either the system is violating its own law or the law has moved:
say which, and fix whichever is wrong. Do not quietly edit this file to describe
intent the system does not actually have.

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
`/g/[id]/evidence` layer. See sections 3 and 6 here and
[PIPELINE.md](PIPELINE.md) (section 4) for the detail; what remains
is in GitHub Issues. Magnitude and thread generation ran as one-off scripts
against the showcase map until 2026-07-29; they are now stages F and G, and the
worker runs them, so a requested map arrives with a front door.

**This file is sections 1 to 3 and 5 to 7, as of 2026-08-02: current state, for
agents.** The rest of what used to be here moved out — first by reader, then by
size. How the pipeline works, stage by stage, is
[PIPELINE.md](PIPELINE.md) (was section 4, and 47% of this file). How to operate
the system is [RUNBOOK.md](RUNBOOK.md) (was section 8). Why the load-bearing
choices were made is [DECISIONS.md](DECISIONS.md) (was section 9). What went
wrong is [INCIDENTS.md](INCIDENTS.md) (was section 10). Open work is
[GitHub Issues](https://github.com/rgok001/Lineage/issues) (was section 11).
Section numbers and decision and incident numbers did not change, because they
are cited from commit messages and from other records.

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

**What the product cannot do, stated where it is true rather than where it is
planned** (also disclosed on `/about` under "Limitations and scope", and shaped
for the reader on `/roadmap`): arXiv-only coverage; a bounded corpus, so the map
is the scope of what was read and not of the field; exact string matching fails
closed to "inferred" when extraction mangles a passage; parallel discovery
without citation appears as unconnected meanings; edge types, confidences and
rationales are model judgment, mitigated by the quotes being shown and the
judgment being labelled. Moved here from section 11 on 2026-08-02: these are
properties of the system as built, not open work.

---

## 2. Repository layout

```
CLAUDE.md            product spec and non-negotiable rules
README.md            setup and CLI usage
render.yaml          Render blueprint for the trace worker
docs/                AS-BUILT.md (this file, sections 1-3 and 5-7: current
                     state), PIPELINE.md (the pipeline stage by stage, was
                     section 4), RUNBOOK.md (how to operate it), DECISIONS.md
                     (why the load-bearing choices were made), INCIDENTS.md
                     (what went wrong), ROADMAP.md (what to build next),
                     design/ (one file per design that needed writing down)
pipeline/            stages A-H + auxiliaries (Python, CLI-first; the worker
                     runs thirteen steps, see PIPELINE.md)
  common.py          env loading, polite HTTP session, data_dir()
  check_extraction.py  audit of extracted-text fidelity (no model, no network)
  db/migrate.py      ordered SQL migrations, schema_migrations table
  db/migrations/     001..015
  recheck_stamp.py   re-checks stored stamps against the papers (read-only)
.claude/            settings.json (carries the LINEAGE_NO_DB guard; tracked),
                     launch.json, and memory/ (agents' lessons, boards and
                     verdicts; gitignored). The role prompts are NOT here
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
hold different `DATABASE_URL` values; see [RUNBOOK.md](RUNBOOK.md).

**The agent role prompts are not in this repository.** Until 2026-08-02 this
block listed `.claude/agents/` as holding "architect, developer, tester", which
was wrong about the location and, since the cluster grew to seven roles, about
the roster. There are seven — architect, developer, tester, operator, security,
curator, manager — and they live in the user-level Claude directory on the
owner's machine (`~/.claude/agents/`), alongside the user-tier memory, so that a
lesson earned here is available on the next project. They are backed up to the
private repository `rgok001/agent-cluster`, which is the row `CLAUDE.md`'s
destinations table added for them.

---

## 3. Data model

Six tables and two views, migrations `001` through `016`, applied by
`python pipeline/db/migrate.py` (tracked in `schema_migrations`). Migrations
`008`-`009` are data fixes (paths relative to `DATA_DIR`; correcting future
publication years OpenAlex mis-dated). `010`-`012` carry the paper-centric turn
and are described inline below. `016` adds no table and no column at all: it is
the two report views, described at the end of this section.

**papers** (001, 002, 015): one row per fetched arXiv paper. Notable columns:
`raw_path` and `extracted_text_path` point into `DATA_DIR`;
`text_title_match` (002) records how well the extracted text matches the
claimed title. This guard exists because OpenAlex sometimes attaches the wrong
arXiv id to a work: the fetch succeeds but the text belongs to a different
paper. Real observed cases: arXiv 1810.04805 (BERT) and 1907.11692 (RoBERTa)
both carried unrelated titles. Downstream stages must filter
`text_title_match >= 0.5`.
`extracted_text_digest` and `extractor_version` (015) say which bytes are at
that path and which code produced them. The digest is
`TEXT_DIGEST_ALGO = "sha256"` followed by the hex of the file's bytes, so a
stranger reproduces it with `sha256sum` and no platform's newline handling
enters into it. It is written by `extract_text.py` in the same statement as the
path, and recomputed by its skip path on every run: a file changed by anything
else — a hand edit, a truncated write, a restored disk — is caught there and the
column is corrected, which makes the stamps against the old bytes go stale. That
recompute is the reason this derived value cannot age.
`extractor_version` is a 12-character digest of the extractor's own curated
inputs, and it is written **only** when this code produced the file, never on the
skip path: a skip knows the bytes and not who made them. NULL therefore means
"this text predates the column", and since NULL IS DISTINCT FROM any version,
`WHERE extractor_version IS DISTINCT FROM <EXTRACTOR_VERSION>` is the
re-extraction queue that unblocks backlog item 4. It is provenance and never an
invalidator: if the bytes have not changed, a stamp against them still describes
that text (decision 30).

**definitions** (001, 003, 004, 011, 015): Stage B output, one row per
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
papers reach the influence map and how large they sit there (section 4, now
[PIPELINE.md](PIPELINE.md), Stage F):
attention is on-term weighted uptake (how much later work built on this paper
*for this term*), displacement is how far the paper moved the term's meaning
(embedding distance from the centroid of earlier definitions). Both are per
(paper, concept, prompt_version) because magnitude is relative to the term
being traced, and both are nullable (computed by a post-Stage-D job; the
earliest paper has no earlier work to be displaced from).
`quote_start`, `quote_end`, `quote_text_digest` and `quote_extractor_version`
(015) are the re-checkable half of `quote_verified`: half-open character offsets
into the UTF-8 decoding of the file — **Unicode code points, as Python indexes
them, not UTF-16 code units, so JavaScript must not slice with these directly**
(issue #61) — the digest of the bytes the match actually
read, and the extractor version of that text, copied from the paper's row rather
than from the running extractor because this stage did not produce the file. All
four are nullable and **NULL is meaningful: it means this stamp was never made
in a re-checkable way, and it renders stale.** Written together with the boolean
by Stage B's creation path and by `--reground`, which since 015 rewrites a row
whenever anything about the stamp moved rather than only when the verdict
flipped. The span is deliberately not read as a second confirmation of the
boolean — the same matcher put it there — so it exists for a human to look at
and for somebody to one day measure where matches land.

**edges** (001, 010, 015): see below; the eight `source_`/`target_`-prefixed
stamp columns are the same four facts twice, one per quote.

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

**edges** (001, 010, 015): typed relationships between nodes, with FK to both papers,
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
Migration 015 adds the two stamps, `source_`- and `target_`-prefixed to match the
quote columns already there: `source_quote_start`, `source_quote_end`,
`source_text_digest`, `source_extractor_version` and the four `target_`
equivalents. Flat columns rather than one JSONB blob, because the staleness test
is a join predicate against `papers` and the table already carries its evidence
in this shape. They are not derived by joining to the definition's stamp: Stage
E's quote re-sync deliberately skips empty definitions, so an edge quote can
legitimately differ from the definition quote, and a joined stamp would then be
a verdict about a different string.

**The three render states, in one place.** `stamp_state` in `pipeline/common.py`
and `stampOf` in `app/lib/stamp.ts` are the same three lines in two languages:
**stale** when either digest is absent or they differ, **verified** when the
boolean is true, **inferred** otherwise. Stale dominates the boolean in both
directions, because a failed check against text that has since changed is no more
about today's text than a passing one. `edge_stamp_state` / `edgeStampOf` apply
it to a unit carrying two stamps: either side stale makes the edge stale. A third
expression of the rule exists in SQL, **in migration 016's
`map_report_by_source` since issue #30**, and only because the home page needs it
as an aggregate per map; the three move together. It was two subqueries inside
`listGenealogies`, which now selects `edges_verified` and `edges_stale` from
`map_report` instead, so the app and `pipeline/map_report.py` read one expression
rather than two — the count of implementations is unchanged at three, which was
the condition for building the view at all. The SQL form is **one `CASE`
producing one label per row**, not three predicates, so the three states are
disjoint and sum to the edge count by construction; Stage E's `stats` block did
it the other way and its counts summed to more than the edge count (issue #59).
It tests `COALESCE(..., '') = ''` as well as NULL because `'' = ''` otherwise
counted an edge verified where both languages say stale (issue #60), and it
`LEFT JOIN`s `papers` rather than joining it, so that it ranges over the same
edges `edge_count` does: `edges.source_paper_id` is nullable, an inner join
dropped such an edge from both state counts while the card still counted it a
relationship, and a missing paper row yields a NULL digest, which is what the
other two copies of the rule are handed and both call stale (issue #60 again).
`listGenealogies` still counts `paper_count` and `edge_count` itself rather than
taking them from the view, so that "the report and the card agree about the size
of a map" stays a check that can fail instead of an identity.
**The queries that fetch an edge's papers LEFT JOIN them, for the same reason**
(issue #79): `listGenealogies` was the only one that did for one commit, so the
home card counted an edge with a missing paper row and `getGenealogy` dropped it,
and the card said "3 relationships" over a page listing 2. `getGenealogy`,
`getInfluenceMap` and `pipeline/export_related_work.py` now join the same way, so
such an edge appears on those surfaces and resolves stale on them. The paper
dossier (`app/app/g/[id]/p/[arxiv]/page.tsx`) is the one remaining inner join and
still drops it; that is issue #80, open, and it needs a rendering decision this
change did not make. It arrives carrying a NULL
arXiv id, which each consumer states rather than fills in: the evidence page says
the paper is no longer in our records instead of reading `.length` off a null,
and the export writes that same sentence where a `\cite` would go rather than
minting a key with no BibTeX entry behind it (rule 4). On the influence map the
change is uniformity only, measured: that query selects edges between two papers
it has already drawn by arXiv id, and a missing paper has no id, so the predicate
excludes the row either way. Every
surface that shows a stamp resolves it this way: the evidence page and its header
count, the influence map's solid-versus-dotted lines and its header count, the
paper dossier, the thread page, the home page's per-map counts, both exports.
`recheck_stamp.py` is the deliberate exception and resolves against the digest of
the bytes it has just read, because it is the only consumer that holds the file
and that difference is the whole reason it exists.

The request also carries a **subject field** and an optional **sense gloss**
(migration 006): `field_id` (an OpenAlex field, default `fields/17` = Computer
Science) scopes corpus selection to a discipline; `gloss` disambiguates a
polysemous sense and flows into both the relevance query and Stage B's
extraction question. The field is not a disambiguator (polysemy collides
within a field: OS vs ML "kernel" are both CS); the gloss is. The worker reads
both from the row and passes them through as CLI args. The picker is at *field*
granularity (26 fields); a finer *topic*-level picker (~4500 topics) was
deferred as unnecessary for scoping.

**papers**, continued (013, 014): `extraction_verdict` (clean/suspect/damaged),
`extraction_signals`, `extraction_check_version` and `extraction_checked_at`
record what `check_extraction.py --write` found in that paper's extracted text
and which calibration found it. NULL means
unchecked, and `clean` means nothing was found rather than nothing is wrong: the
scan is a lower bound, so the column is never read as a certificate. The paper
dossier shows the note only when something *was* found, which is the honest
asymmetry. All four are cleared by `extract_text.py` whenever it rewrites the
paper's text, since the measurement describes the file that was just replaced
(decision 21), and `extraction_signals` empties to `'[]'` rather than nulling
because it is `NOT NULL`.
`extraction_check_version` (014) is a 12-character digest of the audit's own
thresholds, patterns and signal levels, computed at import. It closes the other
half of decision 21: a verdict is invalidated by the code that computes it as
well as by the text it describes, and only the second had a path back.
`--only-unchecked` now selects `extraction_checked_at IS NULL OR
extraction_check_version IS DISTINCT FROM <this version>`, so moving a threshold
re-measures the corpus at the worker's next start with nobody remembering to ask
(decision 25).

**trace_requests** (005, 006): the request inbox and the job queue in one table.
Status flow: `requested -> approved -> running -> complete`, plus `rejected`
and `failed`. `progress` JSONB is written live by the worker; `updated_at`
doubles as the worker heartbeat; `genealogy_id` links the finished map. A
partial unique index allows only one open request per concept, enforced at the
database level because app-level checks can be raced by simultaneous submits.

**map_report_by_source and map_report** (016, `016_map_report.sql`): the map
report (issue #30, `[F2]`), and the only two views in the schema. They store
nothing. `CREATE VIEW` writes no row, takes no rewrite lock and is reversed by
`DROP VIEW map_report; DROP VIEW map_report_by_source;`, and the whole point of
computing rather than storing is that a quality figure written to a column
survives the curatorial edit that invalidates it.

`map_report_by_source` is the base: one row per (genealogy, unit, source), where
`unit` is `'definition'` or `'edge'`, carrying `total`, `verified`, `inferred`
and `stale`. `map_report` is one row per map, and its per-unit verification
counts are `SUM`s over the base view, so the per-source figures adding up to the
map figure is true by construction rather than by test. Every other figure —
coverage of the reading, quote reuse, the shape of the node graph, the corpus
year distribution, the last completed run's cost and wall clock — is computed
directly from `edges`, `definitions`, `papers`, `genealogies.nodes` and
`trace_requests`. Every share is a `NULLIF(denominator, 0)` division and is
**absent** rather than zero when the denominator is zero: zero percent is a claim
about a population, and there is no population.

**There is no threshold anywhere in these views and there must never be one.**
The only numeric literals are `0.25`, `0.5`, `0.75` (the quantiles that define
the quartiles and the median) and `2` (quote slots per edge); each defines a
statistic and none decides anything. A colour scale, a grade, a badge or a
composite score would be a threshold with the evidence removed.

The per-source grain is built in from the first row because F7 (non-arXiv
sources) needs a before-and-after comparison against a number of the same shape.
`papers.source` does not exist yet, so the label is **measured from the row**
(`p.id IS NULL` -> `no paper row`, `p.arxiv_id IS NOT NULL` -> `arxiv`, else
`source not recorded`) rather than asserted as a literal, which is an expression
that can fail rather than one that cannot; F7's migration replaces it with
`p.source` in the same migration that creates the column. An edge is grouped by
the pair of its two endpoint labels, sorted and joined, so every edge lands in
exactly one bucket and the buckets sum to the edge count.

Three figures the report is asked for have no input in this database and each
renders as an explicit "not recorded", never a zero and never a blank: run cost
(`genealogies.spend_usd` exists and is written by nothing, reading `0.0000` on
both live maps, so the view reads `trace_requests.progress->>'spend_usd'` from
the last completed run and **must never `COALESCE` to that column or to 0** —
issues #85 and #47), wall clock (recorded for worker runs only, and neither live
map is one), and Stage D's discarded citation pairs (counted nowhere; issue #86).
`run_cost_basis` carries which of those two states the cost figure is in.

Both joins from `edges` to `papers` are `LEFT`, for the reason the rest of this
section gives at length (issues #60, #79, #83): the join must not decide whether
an edge exists, and a missing paper row yields a NULL digest, which every copy of
the stamp rule calls stale. `definitions.paper_id` cannot dangle, so its
`LEFT JOIN` is uniformity rather than behaviour.

`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or reorder
columns, so any later change beyond appending trailing columns is a `DROP VIEW`
and a `CREATE VIEW`. **No consumer may `SELECT *`**: every reader names every
column it reads, so a redefinition cannot silently change what a page renders.
The migration also issues a `GRANT SELECT` to `lineage_ro`, guarded by a `DO`
block that checks `pg_roles` so a local database without that role still
migrates; without it the read-only CLI would fail against production while
working perfectly for the owner.

---

## 4. The pipeline

Moved to [PIPELINE.md](PIPELINE.md) on 2026-08-02. At 469 lines it was 47% of
this file on its own, where the other six sections averaged 71, and it is the
part an agent reads before changing anything under `pipeline/`. Splitting the
other six was considered and rejected: a file per topic is not organisation, and
six files each shorter than the note explaining where they went is sprawl. It
keeps its original heading, so references to "section 4" elsewhere mean that
file.

---

## 5. The trace worker

`worker/run.py`, ~230 lines, one process, no threads. Full walkthrough
knowledge condensed:

- **Startup housekeeping.** Before polling, the worker applies database
  migrations and runs the extraction audit over papers nobody has audited
  yet (`--only-unchecked --write`). Since migration 014 "nobody has audited yet"
  also covers a paper audited by a different calibration, so the boot after a
  calibration change re-measures the corpus with no command from anybody. That is
  intended and it is still a live rewrite of reader-facing state, which is why
  the runbook puts a dump and a lenient-only check in front of that deploy
  (decision 25). Both were manual commands, which meant
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
  Each card counts papers, threads or relationships, **verified relationships**
  and not-re-checked. That middle count read "N verified quotes" until issue #73,
  where N is edges: on the shipped exports 287 verified edges of "attention" rest
  on 79 distinct quote strings and 286 of "embedding" on 107, so the noun
  overstated the evidence three- to fourfold on the number the product's central
  promise rests on. The noun moved to what is counted rather than the count to
  the noun; a quote count would have to be a `DISTINCT` count of quote strings.
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
  **The badge counts the links *drawn on the map*, not all of the map's
  relationships**, which is why it says "links shown" — one word doing a lot of
  work. The full figure lives on `/g/<id>/evidence`.
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
- `/g/[id]/report` : what this map is made of (issue #30, `[F2]`). One screen,
  one column, no interactivity, every figure selected from migration 016's two
  views by `lib/report.ts` and computed nowhere else, so this page and
  `pipeline/map_report.py` cannot disagree about the same map. Sections: coverage
  of the reading, evidence (the three stamp states for definitions and for
  relationships), the same counts split by source, quote reuse, shape, corpus
  age with a per-year histogram, the run, and a closing list of the three things
  the page cannot tell you. **No threshold, no colour scale, no grade, no badge
  and no composite score**, because each of those is a threshold however it is
  spelled; the only colours on the page are the ink, line and card tokens plus
  the one link colour, which is checked rather than asserted. Beside every figure
  is the same figure for every other map, labelled "the other maps in this
  system" rather than a baseline, with the sample size taken from the number of
  rows the view returned rather than written into the page.
  Every figure carries two sentences: what it counts and what would move it.
  **An absent figure prints words, never a zero and never a blank**, and the
  words distinguish "not recorded" (nothing in this system holds it) from an
  empty population ("no relationships", "no years recorded"). The cost figure is
  the sharp case: `genealogies.spend_usd` reads `0.0000` on every map and is
  written by nothing, so a `$0.00` there would be the exact defect this page
  exists to avoid; nothing in the path from the view to the page coalesces it.
  Pending the owner's answer to the report design's open question 1 — the roadmap
  says a stranger should see what a map cost, this file's copy rules say no cost
  talk aimed at visitors, and the two cannot both hold — the cost figure renders
  for the owner only and every other figure renders for everyone.
  `/g/[id]` links to it from the footer beside the curation line and shows no
  report figures itself, because that header's "X of Y links quote-verified"
  counts only the links drawn on the canvas and is a narrower population.
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
console.anthropic.com (owner action, recommended, **attestation pending**).

That last one is an **attested claim**, and this file is its one home. It is a
setting in a vendor console, so nothing in this repository can settle it and
`RECOMPUTED BY:` above can never fire for it: there is no commit that changes
it. The form is a marker written on the line itself,
`console.anthropic.com (attested: owner, YYYY-MM-DD)`, <!-- record-check: the form, not an attestation --> which
`pipeline/check_record.py` parses and prints the age of. It never fails on age,
because there is no corpus of attested facts here to measure decay against and
a number would be guessed.

It is pending rather than written because the record disagrees with itself and
neither an agent nor this repository can break the tie: the shipped list in
`docs/DECISIONS.md` records the cap as confirmed set on the day it was written,
and this section has said the opposite since. Both are honest, one is stale, and
only somebody who opens the console can say which. When the owner looks, the
attestation is written here and the other copy stays what it always was, a dated
claim about its own moment.

Secrets: never committed. Root `.env` and `app/.env.local` are gitignored;
Vercel and Render hold their own copies (`sync: false` in render.yaml means
Render prompts in-dashboard). The prod `AUTH_SECRET` is distinct from local.
GitHub OAuth needs one app per callback URL, so local and prod are two
separate GitHub OAuth apps.

---

## 8. Operations runbook

Moved to [RUNBOOK.md](RUNBOOK.md) on 2026-08-02. A procedure read by the owner
while operating the system is a different document from a description read by an
agent before changing it, and merging the two meant neither could be loaded
whole. References to "section 8" elsewhere mean that file.

## 9. Decision record

Moved to [DECISIONS.md](DECISIONS.md) on 2026-08-02. It is the owner's
progression record and is history: dated claims about choices, where the rest of
this file is derived from the code and has to be recomputed when behaviour
changes. **The decision numbers did not change**, because commit messages,
`INCIDENTS.md`, issue bodies and agent memory cite them. References to "section
9, decision N" elsewhere mean that file.

## 10. Incidents and lessons

Moved to [INCIDENTS.md](INCIDENTS.md) on 2026-08-02. Incidents are history:
dated, append-only and immortal, where the rest of this file is derived from the
code and has to be recomputed when behaviour changes. Keeping the two classes in
one file meant the immortal part was re-read every time the derived part was
checked. References to "section 10" elsewhere mean that file.

## 11. Known limitations and open work

Removed on 2026-08-02. It was a fourth list of open work in a repository that
had just made [GitHub Issues](https://github.com/rgok001/Lineage/issues)
canonical, after `ARCHITECTURE.md`, `FIX-LOG.md` and `BACKLOG.md` were deleted
for exactly that. Every item was confirmed present as an issue or filed as one
before the section went; the map is below so that a reference to "item N of
section 11" still resolves.

| Was | Now |
|---|---|
| 1. Stage B is a sequential loop | [#27](https://github.com/rgok001/Lineage/issues/27) [B24], scheduled as [#38](https://github.com/rgok001/Lineage/issues/38) [Q1] |
| 2. Extraction cost varies more than it should | [#47](https://github.com/rgok001/Lineage/issues/47) [B29], filed 2026-08-02 |
| 3. ~~Maths is the next artifact family~~ (fixed) | [INCIDENTS.md](INCIDENTS.md) incident 11; the deferred map repair is [#5](https://github.com/rgok001/Lineage/issues/5) [B4] and [#29](https://github.com/rgok001/Lineage/issues/29) [F1] |
| 4. Proper 403s instead of fail-closed 500s | [#43](https://github.com/rgok001/Lineage/issues/43) [Q6] |
| 5. Notifications, both directions | [#34](https://github.com/rgok001/Lineage/issues/34) [F6] for the half being built; `docs/ROADMAP.md` declines the email half. The design is preserved as a comment on #34 |
| 6. `genealogies.status` is loose and vestigial | [#48](https://github.com/rgok001/Lineage/issues/48) [B30], filed 2026-08-02 |
| 7. A free OpenAlex pre-flight probe | [#39](https://github.com/rgok001/Lineage/issues/39) [Q2] |
| 8. The two public roadmap commitments | Sources beyond arXiv is [#35](https://github.com/rgok001/Lineage/issues/35) [F7]; claim-level verification **shipped as Stage H** (section 4, now [PIPELINE.md](PIPELINE.md)), and the stamps it writes going stale on re-extraction is [#29](https://github.com/rgok001/Lineage/issues/29) [F1] |
| 9. ~~Topic-scoped traces~~ (done) | Section 3, which now also carries the field-versus-topic granularity note |
| 10(a). `--reground --limit` is rejected | [#20](https://github.com/rgok001/Lineage/issues/20) [B14] |
| 10(b). `workbench.py` prints success before it commits | [#21](https://github.com/rgok001/Lineage/issues/21) [B15] |
| 10(c). The map badge counts links drawn | Not a defect. Moved into section 6, where it is current state |
| 11. ~~Verdicts predate the re-extraction~~ (fixed in code) | [#49](https://github.com/rgok001/Lineage/issues/49) [B31], filed 2026-08-02, carrying the entry whole because `INCIDENTS.md` incident 14 cites its totals |
| 12. The parked `embedding` refresh | [#50](https://github.com/rgok001/Lineage/issues/50) [B32], filed 2026-08-02; sub-item (e) is [#49](https://github.com/rgok001/Lineage/issues/49) |
| 13. The home page lists every map | [#6](https://github.com/rgok001/Lineage/issues/6) [B5] |

The "Done since first draft" list that opened this section is progression rather
than open work, and moved to [DECISIONS.md](DECISIONS.md). The product
limitations paragraph moved to section 1, where it describes the system as built.

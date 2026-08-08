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
                     g/[id]/layout.tsx + tabs.tsx hold the second one, the four
                     places inside a map; it fetches nothing, on purpose
                     skeleton.tsx holds the loading shapes every boundary shares
                     (concepts)/ is a route group, not a URL segment: it exists
                     so / can have a loading.tsx that /about does not get
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

**The three states are also said in one vocabulary, decided once** (issue #129,
UX ruling implemented as given, 2026-08-08). #124 rewrote the verification claim
on `/g/[id]/report` because "extracted" names a step the reader has never been
told exists and cannot tell apart from a judgement the tool made; the same claim
was still made in the old words on six other reader-facing surfaces, so the
product stated its central promise two ways and a reader meeting both on one
journey had to work out whether they were the same check. They are. Two rules
now, recorded in `app/lib/stamp.ts` beside the words themselves: **"word for
word" always**, never "verbatim" and never "string-matched", because it says the
same thing without naming a technique; and **"the text this system pulled out of
the paper" always**, never "extracted text" and never "our own extraction",
because it names who did the pulling out. The three sentences are: verified,
"found word for word in the text this system pulled out of the paper"; inferred,
"the check ran against the text this system pulled out of the paper and could not
find it"; not re-checked, "not checked against the paper's text as it now
stands". They were applied to `STAMP_MEANING`, both per-row explainers on
`/g/[id]/evidence`, both stamp lines on `/g/[id]/p/[arxiv]`, the roadmap's
"Verified quotes throughout" item, and the export's preamble clause and two of
its three per-quote footnotes. No claim moved in any of them.
**Two deliberate exceptions.** `/about` keeps "string-matched against our own
extraction" in step 6 and the Verified tier, and keeps "verbatim" in step 3,
where it describes a passage: it is the page *about* the machinery, the reader
has been walked through extraction in step 2 before step 6
names it, and naming the technique there is the service being offered (#125 left
it on purpose and #129 confirms that on purpose). And the export preamble's
not-re-checked clause, which #128 protected, changed with the rest, on the
argument that the export is read furthest from any page that could explain the
word and so needs the plainest wording of the three surfaces rather than the most
protected.
**`STAMP_MEANING` has no readers**, which is how the divergence happened and is
recorded in its own comment: #129 was filed believing every stamp surface
rendered from it, and grepped on `c9d9deb` the readers are of `STAMP_LABEL` and
`STAMP_COLOR` only, with each page spelling its own sentence around a symbol and
its own extra clause. It is the wording those sentences are copied from, and a
change there is a change to make in each of them.
**A third rule finished it, on seven surfaces the first grep could not see**
(issue #135, UX ruling implemented as given, 2026-08-08). **"Verbatim" describes
a passage and never a check**: "verified verbatim against X" is the banned word
wearing an adverb, so none of the three lines #129 left standing was the
quotation case that would have been defensible. And **"against the source text"
had to go regardless of the copy question**, which is why this outranked a copy
sweep: "extracted" was ambiguous about who pulled the text out, while "source"
positively suggests the published paper, so each line stated a slightly stronger
claim than the product can support on the three surfaces where a sceptic goes to
check one. Nothing here is a rule 2 violation, and no claim moved on any of the
seven; it is drift in the direction rule 2 exists to prevent.
The seven: the **home page hero**, which was outside #129's grep and outside
#135's own filing and is the loudest statement of the promise in the product
(the owner found it on the deployed site) -- now "Every claim carries a quote
from the paper, checked word for word against the text this system pulled out of
it. Quotes the check could not find are marked, never hidden", the third
sentence being new and the first time the front page has said what happens to a
quote the check cannot find; the evidence page's ●/○/◌ key, whose *structure* is
what #127 protects and whose vocabulary changed with it, along with an "it" that
had drifted from the relationship to the quote; the dossier's verified caption,
which now carries the `· shown as verified` tail its two neighbours had; the app
export's verified per-quote stamp, matched to the document it sits in ("verified:
found word for word in the paper's own text") rather than to the pages, because a
document read away from every page needs one vocabulary inside itself above all;
the dossier's footer, a third phrasing of one promise four lines under captions
that say it the settled way, where "our own copy" could be read as a copy of the
PDF rather than of the text pulled out of it; **the CLI export's not-re-checked
mark** in `pipeline/export_related_work.py`, outside `app/` and so outside both
#129's grep and #130's list, in the other document that goes into somebody's
manuscript; and `/about`'s Verified tier, which said "string-matched against our
reading of the source" -- "reading" being the word every dossier line, thread
account and rationale on the site uses to mean *judgement, not checked*, spent on
the mechanical check, on the page whose job is to teach the difference. It now
says "our own extraction of the paper's text", the phrasing #129 already granted
that page.
**Left standing on purpose**: the evidence page's citing-sentence label
("supplied by Semantic Scholar, so we could not check it against our own copy of
the paper"), which is about the citing sentence rather than the quote and says
the true thing plainly.
**Reading the view gave the home page a hard dependency on migration 016, and
that dependency degrades rather than falling over** (issue #92): an app deployed
before the migration lands did not lose two numbers, it lost `/` entirely, since
Postgres raises `UndefinedTable` for a statement naming a relation that is not
there. `listGenealogies` now asks `to_regclass('public.map_report')` first, in
its own statement — a guard inside the query would be parsed by the thing it
guards against — and selects `NULL` for both counts when the answer is NULL. The
card prints "verified relationships not counted", in ink-soft and never in the
verified colour: `0 verified relationships` over a map holding 287 of them would
be a worse answer than the 500 it replaced, and a green one. Measured against a
real PostgreSQL with the views dropped: the query at `a30a006` raises
`UndefinedTable`, the query in the tree returns every map with both counts NULL,
and with the views present the two return identical counts on every map.
`RUNBOOK.md` still leads the migration entry with migration-before-deploy,
because `/g/[id]/report` has no such fallback and none would be honest.
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
Counted with comments and string literals removed, the numeric literals in
`016_map_report.sql` are exactly `{0, 0.25, 0.5, 0.75, 1}`: the three quantiles
that define the quartiles and the median, the `0` of every coalesced count and
`NULLIF` denominator, and the `1` of `members = 1` and `SELECT 1 FROM edges`.
Each defines or guards a statistic and none decides anything. A colour scale, a
grade, a badge or a composite score would be a threshold with the evidence
removed. This file and the design used to name `2` (quote slots per edge)
instead of the `0` and the `1`; that `2` left the executable text when the quote
slot count became `count(*)` over a `LATERAL` and the census was not recounted
(issue #94). The migration's own header now carries both this check and the
`MATERIALIZED` one as shell commands that run, both reading the file with its
comments stripped — a plain `grep MATERIALIZED` matches the header's promise not
to use it and is red on a correct file.

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
`run_cost_basis` carries which of those two states the cost figure is in, and it
is only as honest as the blob: the test is `jsonb_typeof(...) = 'number'`, so
whether a run has a recorded cost is decided entirely by whether the worker put a
number there. It did so unconditionally until issue #87, which is why that fix is
in the worker rather than in the view. **Rows written before it still hold a
literal `0.0` for a run that recorded nothing, and the view now truthfully calls
those recorded-at-zero.** Nothing in the blob distinguishes them from a genuine
zero, so nothing was rewritten; `RUNBOOK.md` carries the query that finds them
and the one-row repair.

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
  **`spend_usd` starts as JSON null and becomes a number only once some stage
  has actually printed a spend line** (issue #87). It used to be minted as
  `0.0`, which made the report view's `jsonb_typeof(...) = 'number'` test true
  from the first flush: a fully cached re-trace, which prints no spend line at
  all, was published as a run whose recorded cost was `US$0.00`. Once one stage
  has priced itself the figure is a measurement and a later zero is added to it
  as one. The worker's own completion line says "not recorded" in the null case
  and prints four decimals otherwise, so the log and the report agree.
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

**A second strip sits under it on every route inside a map** (issue #143):
The map · Threads · The evidence · What this map is made of. Same pattern one
step smaller, and it is where the sideways navigation now lives; the mechanism
and the reason it fetches nothing are in section 6 under the loading
boundaries.

**Routes.**
- `/` : the map list, with a link to `/trace` showing how many runs are in
  flight. Its closing line used to read "then curated by hand", unconditionally,
  on a page whose only curated map was the one this document had already
  retracted that claim about. It is now gated on `edit_count` across the listed
  maps and says the truthful thing when none has been curated (decision 18).
  **That closing line now says it in the reader's words** (issue #126): "any
  curatorial change is listed in the map's audit trail, with its actor where one
  was recorded" put two team words in one clause, and #120 had already replaced
  the first of them on the counter three lines above, so the page said "changes
  by hand" in one place and "curatorial change" in another about the same thing.
  It reads "Nobody has edited one by hand since. If anyone does, the change is
  listed in that map's audit trail, along with who made it where we know." The
  ticket left "audit trail" as the app's choice and it is **kept**: a researcher
  knows the phrase, and `/about` and the evidence page already use it, so the
  thing has one name in all three places.
  Each card counts **papers that define the term** (issue #123 names the
  population, because three other surfaces print a different number under the
  bare word "papers"; those four and the export's fifth are set out under
  `/g/[id]/report` below), threads
  or relationships, **verified relationships**
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
  **Three sentences here dropped the team's words** (issue #128). "A curator
  reviews each request before it runs" is "Someone reviews each request before it
  runs": `/about` explains what a curator is and this page is often reached
  first. "Your GitHub username is used only to attribute the request and to keep
  one person from queuing the whole corpus" put three team words in one clause,
  and the joke in "the whole corpus" only works for a reader who knows what one
  is; it now says the username records who asked and stops one person requesting
  every map at once. And the footer says "Reading a set of papers costs real
  money in model usage", because "corpus" is introduced on `/about` and appears
  nowhere else in the app.
- `/g/[id]` : the front door, an influence map (`InfluenceMap.tsx`, client).
  Two header claims are counted rather than assumed (decision 18): the badge
  reads "*X* of *Y* links quote-verified" instead of a flat "quote-verified",
  which on `embedding` sat above 201 verified of 305; and the footer states the
  map's actual `edit_count` instead of asserting it was curated by hand.
  **The badge counts the links *drawn on the map*, not all of the map's
  relationships**, and since issue #114 it says both numbers and where the other
  one is: "N links drawn here, all quote-verified · the full M are in the
  evidence" (see the report section below for how M is counted). It used to say
  "N of M links shown quote-verified" and leave the word "shown" to carry the
  whole difference. Its paper count says "N pivotal of M papers this map ranked"
  for the same reason (issue #123): M is the defining papers that carry an uptake
  score, which is not the map's paper count and is not what the home card or the
  evidence page counts.
  **The legend is derived from the link types this map actually drew** (issue
  #115). It was four hardcoded entries, migrates/extends/narrows/renames, against
  a taxonomy of six, while `InfluenceMap.tsx` holds a colour for all six: a
  `contests` or `merges` link among the pivotal papers drew in a colour the key
  never explained, which is the key failing exactly when the map says something
  unusual. Derived rather than hardcoded to six, so a map carries no dead entries
  for types it does not hold, and a type with no gloss still gets a row, named
  and unglossed, because a drawn colour with no key is the defect.
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
  **The closing footnote says what it means** (issue #126). "No curatorial
  changes have been made to it since" is `curationSentence` in `lib/genealogy.ts`
  and now reads "Nobody has edited this map by hand since. If anyone does, the
  change will be recorded, along with who made it"; its other branch lost the
  machine's "change(s)" and pluralises properly, including the verb, in both
  directions. "Scope is the corpus: broadening the source adds threads, each
  arriving with its evidence attached" was three team words and a claim
  compressed past one read, and now says it outright: this map covers only the
  papers it read, all of them from arXiv, and reading more from more places
  would add threads, each arriving with its own evidence. The count, and what
  counts as curation, are untouched.
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
  reader meets one rendering everywhere.
  **Its subtitle spells the three states out rather than naming them** (issue
  #127). It said "each quote is the paper's own definition, marked verified,
  inferred, or not re-checked", and those three words are defined on the evidence
  page, which a reader arriving from the front door has never seen. It now says
  what each of the three means in a clause each; nothing else on the page
  changed, because everything else on it is model-written content about
  machine-learning papers and rewriting that by hand would be inventing it.
  (`/g/[id]/river` redirects to the map; the path is kept working
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
  **The preamble pluralises and stops saying "string-verified"** (issue #128).
  It read "Scaffold generated by Lineage from 84 paper(s) across 5 thread(s)",
  which is the defect #120 removed from the home card and the audit trail, in the
  one output a reader takes away and pastes into their own draft. It now reads
  "Generated by Lineage from 84 papers across 5 threads", pluralised in both
  directions from the counts, checked at 1 and at many in both scopes. And "Every
  quotation was copied verbatim from the paper's own source text and
  string-verified against it" is "copied word for word from the paper's own text,
  and checked against that text" — the same claim, without the machine's name for
  it. The rest of the preamble is deliberately untouched, including "**This is a
  scaffold, not prose.** The citations, quotes and structure are real; the
  argument is yours to write."
  **And the count says which papers it means** (issue #133). #123 gave a
  population to the four on-site surfaces that print a number under the bare word
  "papers" and this was the fifth, in the one file the reader keeps: a researcher
  who quotes "Lineage read 84 papers" in a literature review has written a number
  whose population nothing states, read away from every page that would explain
  it. It now says "Generated by Lineage from the 84 papers in these 5 threads",
  and for one thread "covering the 17 papers in it". `arxivs` is built from the
  papers in the exported scope, so the population named is exactly what the
  reader is holding; no number changes and no claim is added. At one thread the
  line reads "in this thread" rather than "in these 1 threads", which is
  demonstrative agreement rather than a second claim.
  The CLI export (`export_related_work.py`) still writes the older sense-shaped
  document, and is kept because the pipeline is CLI-first. **Its copy was swept
  to match** (issue #130, UX ruling implemented as given, after it was reported
  out of #128's scope). "Skeleton generated by **Lineage** from N papers across M
  concept-states, with K traced relationships" is "Generated by Lineage from N
  papers across M meanings of the term, with K relationships between them":
  "concept-states" is the pipeline's word for what every reader-facing surface
  calls a meaning, and the first line of a document going into somebody's paper
  should say what it is rather than what it is not. The verification sentence is
  the one #128 shipped in the app export and #129 settled for the whole product.
  "Across this corpus" is "Across these papers". Every "(s)" is gone, in the
  document and on stdout, pluralised from the count in both directions. And both
  exports' curation note says "N changes by hand applied", which is what #120
  settled on for this same count on the home card, instead of "N workbench
  edit(s) applied": "workbench" is a word the reader meets only if they are the
  owner, and this line travels into somebody else's manuscript. The two
  implementations are twins by design, so they moved together.
  **The CLI note's list of stored operation names went with it** (issue #138,
  found closing #130 and outside its list). It read "3 changes by hand applied
  (delete-edge, merge, rename)", straight from `CURATORIAL_OPS`, in the sentence
  whose whole job is to tell somebody else's reader how much human judgement a
  map has had. "Edge" is not a word this product says to readers -- the report
  page, the evidence page, the dossier, the app export and this same document
  three lines above all say relationship -- and a reader who meets "delete-edge"
  in a footnote in a literature review can look nothing up to resolve it. The
  list is dropped rather than translated, on the argument that knowing some of
  the changes were renames does not change how the map is read, while the count
  and the actors carry the honesty claim already. This is also where the twins
  had diverged: `curationNote` in `lib/export.ts` never printed the ops, so one
  map exported two ways said two different things about the same edits. Verified
  by rendering both exports over the same two edits: the line is now
  character-identical in each.
  Two words beyond the ticket's list, in the "Unconnected senses" paragraph it
  did not quote: it said the senses "appear in the corpus but no citation link to
  the rest of the genealogy was traced", and house style bans "genealogy" from
  the interface outright. It now says "appear in these papers but no citation
  link to the rest of the map was traced". The last reader-facing "corpus"
  outside `/about` went with the same ticket, in `/roadmap`'s preview item ("so
  you can judge the papers before spending on them"); the item title "Bring your
  own corpus" stays, because #128 accepted it as a phrase a researcher knows.
  **The CLI export cites papers it has no BibTeX entry for.** Every member of a
  sense gets a `\cite{}` in the "This formulation appears in" list, including a
  paper with no author metadata, which is skipped in the `.bib` and reported only
  on stdout. So a `\cite{anon2015paper}` leaves in the document with nothing
  behind it, which is the exact failure `edge_cite`'s docstring names and refuses
  for edge endpoints (#79) and which the app export marks at the point of use
  ("citation incomplete: no author metadata for this paper"). Found while
  verifying #130, predates it, and is #136.
  **Both exports now escape all ten characters TeX reserves, in one pass, with
  every replacement brace-balanced** (issue #141, from CodeQL alert 1,
  js/incomplete-sanitization on `texEscape`). They escaped `\ & % $ # _` in a
  chain of replaces and let `{ } ~ ^` through raw. Titles and author names come
  from OpenAlex and arXiv, so that is external input landing in a `.bib` a
  researcher pastes into their own manuscript, and an unbalanced brace in a
  title ends the field early and turns whatever follows into BibTeX syntax
  (rule 4: what leaves here is real metadata or nothing). The chain was replaced
  by a single regex over the whole class with a lookup for the replacement, so
  no rule can rewrite another's output; and `{` and `}` became
  `\textbraceleft{}` / `\textbraceright{}` rather than `\{` / `\}`, because
  BibTeX finds the end of a field by counting braces and does not honour a
  backslash while counting, so the LaTeX-correct form still breaks the file.
  Measured through both real exporters on 12 adversarial titles (backslashes,
  lone and paired braces, `~`, `^`, `\end{document}\input{...}`, a title that is
  itself `\textbackslash{}`, and a field-closing `}, note = {pwned}` payload):
  12 of 12 entries parse under a real BibTeX parser, every title un-escapes back
  to its input character for character, no entry gains a sixth field, and the
  app and CLI emit identical bytes. The pre-fix escaper failed 10 of those 12,
  and an intermediate `\{` version lost 2 entries outright, which is why the
  brace form is the one it is. The cost is that the arXiv convention of writing
  `{BERT}` in a title to protect its capitalisation no longer has any effect;
  the field is already wrapped in a second pair of braces for that purpose.
- `/g/[id]/p/[arxiv]` : a paper's dossier. What it contributed (novelty claims,
  labelled **"in the tool's words, not the paper's"**; they read "extracted, not
  verbatim", from which a reader could not tell whether extracted meant taken
  from the paper, which is trustworthy, or produced by the tool, which is a
  judgement, and it means the second: issue #127), how it defines the term with the
  verified-or-inferred stamp, a note where we know our reading of that paper lost text (migration 013; shown only when something was found, since a clean scan is not a certificate), and its typed links in both directions ("what it
  drew from", "what drew from it") each carrying the edge rationale labelled as
  the tool's reading. A paper with no links says so without dialect (issue
  #120): it read "no typed links recorded for this paper among the corpus ...
  links only exist where one corpus paper cites another across meanings", and
  now says a link exists only where one paper in this map cites another that
  carries a different meaning of the term. The review's rewrite said "a
  different thread of meaning"; "thread" already names a stream on the front
  door, and lending it to a meaning would imply links only ever cross threads,
  which is false, so that one word is the deviation from the ticket.
  **Its footer says which parts are checked, in three machine terms fewer**
  (issue #127): "Verbatim quotes are string-matched against our own extraction of
  the source; the tool's readings are labelled as such and never wear the
  verified stamp" is now "Every quote on this page was checked word for word
  against the text this system pulled out of the paper. Anything labelled the
  tool's reading is the tool's judgement, and never carries the verified mark."
  Both claims are
  the same claim. It matters here more than elsewhere because a reader reaches
  this footer having just read a dozen model-written link rationales. #127's
  version said "our own copy of the paper's text"; #135 replaced that clause
  because it was a third phrasing of one promise, sitting four lines under stamp
  captions that say it the settled way.
- `/g/[id]/evidence` : the former genealogy page, now the evidence and
  workbench layer. Timeline of concept-state cards, typed relationship rows
  with evidence panels (both quotes, verification stamp, confidence), workbench
  edit controls (owner only), audit trail, danger zone (owner only). Meanings
  are grouped into citation-connected families (`computeFamilies()`, union-find
  over edges): a term whose senses do not cite each other (polysemy like
  "kernel") renders as separate families under a disclosure banner, with
  citation-isolated meanings pulled into an "Unconnected meanings" section. A
  single-family map renders flat and unchanged.
  **The page's banner and the door into it are scoped to the viewer** (issue
  #118). The banner said "Evidence & workbench" and the front door's card
  promised "the curation tools" to everyone, while every one of those tools is
  behind `canEdit = isOwner(viewer)`, where the viewer comes from the same
  `Promise.all` that fetches the map (issue #140; it was a second `await` on
  `getViewer()` after the map had already come back). A reader told there are tools
  and finds none concludes "broken" or "oversold", not "owner-only". The banner
  now reads "Evidence" and the door "The evidence → every typed relationship and
  the proof behind each" unless the viewer is the owner, in which case both say
  what they always did. `/g/[id]` calls `getViewer` for this and for nothing
  else; the tools stay gated where they were, inside the page and inside every
  action. **The underlying tension is unresolved and is the owner's**: product
  rule 3 says users can split, merge, rename and reclassify, and today only the
  owner can. The copy is now true either way, which is what stopped it waiting.
  **A relationship row keeps the stamp and the confidence apart** (issue #117).
  It read "● verified · 0.87": a mechanical result and the model's confidence in
  its own classification, sharing a line, a font and a separator dot, with the
  number unlabelled. Either half could be read as the other, and both readings
  are wrong -- the stamp is not probabilistic, and it says nothing about whether
  the link type is right. The stamp now stands alone in its state colour, and
  beneath it, smaller and in `--ink-faint`, "the tool's confidence in the link
  type: 0.87". How many digits that number deserves is #41 `[Q4]`, still open.
  The intro under the banner lost its dialect and its riddle with the same pass
  (issue #120): "the raw ranked papers ... the readable account is the map" is
  now "Every paper and every typed relationship, with the evidence behind each.
  For the readable account, go back to the map."
  Its header count reads "N papers grouped into meanings" rather than "N papers"
  (issue #123): it sums the membership of `genealogies.nodes`, which is a
  different population from the three other "papers" counts in the app. All four,
  and the export's fifth (issue #133), are set out under `/g/[id]/report` below.
  **Three more labels say what kind of thing the reader is looking at** (issue
  #127). The citing-sentence label has the hardest job on the page, because it
  must say "these are real words from a real paper, and we still cannot vouch for
  them the way we vouch for the quotes below", and it was written as "per
  Semantic Scholar, not string-verified" — the withholding of the claim, in the
  machine's name for the claim. It now says the later paper's own words, from the
  sentence where it cites the earlier one, supplied by Semantic Scholar, so we
  could not check it against our own copy of the paper. The novelty-claims label
  matches the dossier's. And the ranked-papers lede carried a real idea inside a
  subordinate clause three commas from its subject; it is three sentences now,
  and "even if lightly cited here" says what "here" meant, which is "within this
  map's papers".
- `/g/[id]/report` : what this map is made of (issue #30, `[F2]`). One screen,
  one column, no interactivity, every figure selected from migration 016's two
  views by `lib/report.ts` and computed nowhere else, so this page and
  `pipeline/map_report.py` cannot disagree about a figure they both print (which
  is no longer every figure: see the subset invariant below). Sections: how much
  was read, evidence (the three stamp states for definitions and for
  relationships), the same counts split by source, shape, when the papers were
  written with a per-year histogram, the run, and a closing list of the three
  things the page cannot tell you.
  **The By source table renders only when the rows carry more than one label**
  (issue #109). While there is one source, the six-column table restated the
  Evidence totals split by nothing a reader can see, under a lede explaining
  that it exists so a future source changes it visibly. It is one sentence in
  Evidence instead ("Every paper in this map came from the same place,
  <label>. When a second source is added, these figures will be split by
  source here"), with the label read out of the map's own rows rather than
  named. The view, `map_report_by_source` and the command keep the per-source
  grain regardless. **The known wrong trigger is #98**: an edge whose paper row
  is missing produces a bucket labelled `arxiv + no paper row`, which is an
  integrity artefact rather than a source, and it makes the table appear. That
  is where the label counting gets separated from the integrity buckets; the
  table is allowed to appear meanwhile, because a condition that swallowed the
  artefact would hide it instead.
  **Two Shape rows render only when their value is not zero** (issue #110):
  "meanings that could not be read", an integrity alarm that has never fired,
  and "relationships inside one meaning", which is zero by construction until
  F3 (#31) and explained itself in the words "queued work". This does not bend
  the absent-versus-zero rule, which governs a figure whose value is *missing*:
  `lib/report.ts` reads both as counts the view coalesces, so neither can arrive
  null, and what is skipped is a known zero rather than an absence. The
  instrument F3 will be read on is still this row, and the run that first makes
  it non-zero is the run that makes it appear. The derived sentence beside it
  lost its unreachable branch with the change: it is only ever rendered on a map
  that has at least one, so "no map in this system has one" could not be shown.
  **The years section leads with the papers-per-year chart, and the three
  quantile rows are cut** (issue #113). Lower quartile, median and upper quartile were a
  harder-to-read summary of the distribution the chart draws directly, in
  statistician's words. The median was offered as a sentence under the chart and
  was declined: `percentile_cont` interpolates, so a map can have a median of
  2019.5, and "half the defining papers are from 2019.5 or earlier" is a half
  year printed as a date on the page that exists to keep figures honest. Earliest
  and latest year stay, named as the chart's two ends, and **"papers with no
  year" stays below the chart**, because undated papers appear nowhere in it and
  a chart that silently omits them is the blank-reads-as-zero defect in picture
  form. All three quantiles still print in `pipeline/map_report.py`.
  **The plain-language recalibration reached the whole page** (issue #124, after
  41ebb00 applied it to the Shape section and stopped). Every "what moves this
  figure" note now names who does the moving in the reader's words ("the map
  being rebuilt", "someone editing the map", "the check being run again") instead
  of naming the classification, the grouping or the workbench. Four other things
  went with it. **"Reading" carried two meanings four inches apart** — the header
  calls the shape "this tool's reading", a judgement, and the first section
  called a paper's extracted text a reading too, on the page that turns on
  keeping those apart; the mechanical sense is now "read" everywhere ("How much
  was read", "papers read"). **The six sentences carrying the verification claim
  say who did the extracting**: "the text extracted from each paper" and
  "string-matched" are now "the text this system pulled out of each paper" and
  "matched word for word". The claim is unchanged: still mechanical, still word
  for word, still against this system's own copy and never against the published
  PDF. **"Corpus", "denominator" and "a map built from the command line" (three
  times) are gone**, the last replaced by "built directly by the team, rather
  than through a request on this site". **The sub-link said "the evidence and
  workbench" to every reader**, which is the promise #118 scoped on the
  front-door card and the evidence banner and missed here; it is now viewer-
  scoped like the other two.
  **The quote-reuse section is off the page entirely, and its point is two
  sentences at the foot of Evidence** (issue #132, UX ruling implemented as
  given). It was moved below the years (#108), had its lede cut to two sentences,
  and was retitled from "Quote reuse" to "The evidence behind the map" on the
  owner's own suggestion (#124); on the fourth reading the owner still said "this
  is still not obvious any of this means". Two of its three figures served
  nobody's task: "different papers on relationships" existed only to be read
  against the line above it, which is a self-check the team would run and not a
  question a researcher asks, and "different quotes the map stands on" meant
  nothing until it was divided by the relationship count, which the page never
  did. The comparison the copy taught also had no live case: on "embedding" the
  two figures are 125 and 125, on "attention" 82 and 79. What replaces it does
  the division in words, in the same position and shape as the by-source sentence
  #109 put there: "These 287 relationships rest on 82 different quoted passages,
  because each paper shows the same key quote wherever it appears. One passage is
  behind 43 of them, so the number of relationships is not a count of separate
  pieces of evidence." All three numbers come off the same view row the cut
  figures read, and the sentence renders only when all three are positive, so a
  map with nothing to say it about says nothing rather than printing a zero.
  All three figures still print in `pipeline/map_report.py`, which is the same
  page/command subset "quote slots" left under #108. Grammar at n=1 is #99's.
  **Shape's three pair rows are one row led by what it means** (issue #134, the
  owner's measure test applied to every figure on the page rather than only to
  the section he flagged: a measure earns its place by having a usable purpose,
  and what it measures must be apparent without a full account of how the system
  works). "Pairs of meanings that are linked" is cut from the page: nobody could
  name what a researcher or a sceptic would do differently knowing it, and its
  second sentence taught the counting rule rather than the finding. The other two
  had a use the page never stated, split over two rows, the second of which said
  "read beside the count above". They now read as one figure, "relationships
  between meanings linked in more than one way — 167 of 287 (58.2%), across 30
  pairs", with the count, its population, its share and the pair count on one
  row, and the explainer saying what to do with it: these are the relationships
  to read first when checking the tool's reading. **The copy deliberately does
  not say the tool contradicted itself.** The relationships on a pair come from
  different papers, and two papers can genuinely have done different things to
  the same idea, so the innocent reading is given first and in full ("the links
  do not always say the same thing: one paper may extend an idea while another
  narrows it"). Confirmed against migration 016's `pairs` CTE, which groups edges
  by an ordered (source_node, target_node) and counts distinct `edge_type`: a
  multi-type pair is two or more edges, from different paper pairs, carrying
  different types. It is a count and a share and carries no grade (decisions 24
  and 25). Both surviving labels were renamed in `pipeline/map_report.py` in the
  same commit, which widens its label column from 52 to 70 characters; the two
  cut labels are command-only, like "quote slots" since #108.
  Together the page went from 39 figure rows to 24, measured on the harness.
  **The page opens with one paragraph, not three**
  (issue #106, the UX review of #104): roughly 170 words of what the page is not
  stood between the reader and the first number. The lede now carries the story
  in three sentences (the two kinds of claim, and which of them is mechanical),
  keeps "no grade, no colour and no pass mark" as one clause, and the
  reference-point caveat moved down to sit beside `n=` above the first section,
  where it applies. Measured on the render harness, the header's prose went from
  3 paragraphs and 205 words to 1 and 108. **No threshold, no colour scale, no grade, no badge
  and no composite score**, because each of those is a threshold however it is
  spelled; the only colours on the page are the ink, line and card tokens plus
  the one link colour, which is checked rather than asserted. Beside every figure
  is the same figure for every other map, labelled "the other maps in this
  system" rather than a baseline, with the sample size taken from the number of
  rows the view returned rather than written into the page.
  **The page shows a reader's tier of the figures; `pipeline/map_report.py`
  shows all of them** (issues #107 to #113, from the UX review). Until
  2026-08-07 the invariant was equality, checked by a scratchpad harness:
  40 labels on the page, 40 in the command, same order, same absent-words.
  That was deliberately relaxed to **the page's labels are a subset of the
  command's, with identical wording wherever both print a figure**, because the
  two have different readers: a researcher meets the page, and the Operator runs
  the command with the read-only connection string and wants the whole account.
  The relaxation is recorded in both files' own comments so neither can be
  "fixed" back into equality by accident, and the harness now checks the subset
  plus an explicit list of what the tickets cut. Nothing is cut from the command.
  The first cut was **the count/share pairs merging onto one row** (issue #107):
  39 figure rows rendered at one identical visual weight, so "definitions
  verified, as a share" (the product's promise) looked exactly like "quote slots"
  (bookkeeping). Five pairs now print as `138 (100.0%)` under the count's label,
  and seven rows that carry the page's story are set one step of type larger than
  the rest. Weight only: no colour, no badge, no mark of quality, so decisions 24
  and 25 and the no-threshold rule are untouched. **A merged row carries two
  absent-words, not one**, because a count can be missing for a different reason
  than its share: on a map with no relationships "relationships verified" renders
  `0 (no relationships)`, a real zero beside an absent share.
  Every figure carries two lines: what it counts, and what would change it under
  a lead-in that asks the question.
  **The what-would-change-this note is its own line, led by "What would change
  this:"** (issue #137, UX filing implemented as given, 2026-08-08). It used to
  sit inside the explainer's paragraph, joined by a single space at one size in
  one colour, and 21 of the 25 rows opened that note with a subjectless,
  verbless fragment: the first figure on the page read "Papers whose text this
  map has read, whether or not a definition was found in them. The map being
  rebuilt over more papers." as one paragraph, where the middle sentence is not
  parseable at all. It was a careful answer to a question the page never asked
  aloud. The lead-in supplies the missing subject, so all 21 fragments ship
  unchanged, and "the same check as above" gains a visible antecedent because
  the row above now has a distinguishable note line. Styled as a label and not a
  heading: one line break, italic lead-in, `--ink-faint`, same size, never bold,
  because 25 bold labels would re-inflate the page #107 flattened.
  **The note slot was doing two jobs, and only one of them is that question.**
  Ten sentences across nine rows were reading caveats -- "the share reads absent
  rather than 0% on a map with no relationships", "a paper whose text could not
  be downloaded or read is not counted here at all" -- and they moved onto the
  end of the explainer, where they explain the figure. `papers that do not define
  the term` had a note that was *only* a caveat, so labelling the whole slot
  would have made that one row's label a lie; it now carries the plain note "The
  map being rebuilt", which is the truth about it. Verified by rendering the page
  before and after and comparing each row's two slots as a multiset of sentences:
  24 rendered rows, every sentence the sentence it was, one row gaining one.
  No figure was added or removed, no number changed, and nothing here grades,
  colours or thresholds anything. Two conditional rows, `meanings that could not
  be read` and `relationships inside one meaning`, keep a trailing caveat in the
  note; neither was on the filing's list and both were left rather than swept.
  **Five sentences a reader could not parse were rewritten, and the record's
  dialect is off the page** (issue #111, the Product Owner: "some of the
  language used to describe the measures feels convoluted and not very clear").
  The claims are identical and the words are not: the Coverage lede's "a floor
  under what the run set out to read" is now "a paper the run tried and failed
  to read is not counted anywhere on this page"; the Evidence lede's three
  states are three named sentences instead of one parenthetical chain; "no
  record of which bytes they were checked against" is "whose last check ran
  against an older copy of the paper's text". Rendered and grepped, the page
  now contains no "bytes", no "corpus", no "quote slots" and no "queued work",
  and "rows" only inside the By source table's description of its own rows,
  which #98 owns.
  **No sentence on the page states a count of the world that the page cannot
  recompute** (issue #89). Three did: "Both maps that exist today were built
  from the command line", "Today the classification never proposes one, so this
  reads zero on every map", and "Every paper this system reads today comes from
  arXiv". All three were false the moment they were rendered against six maps
  and nothing failed, and the second was the instrument F3 (#31) is meant to be
  read on. Each is now derived from the rows the page already holds: how many of
  the `n` maps have no run record, how many have a relationship inside one
  meaning, and which labels this map's own per-source rows carry, read out rather
  than named.
  **An absent figure prints words, never a zero and never a blank**, and the
  words distinguish "not recorded" (nothing in this system holds it) from an
  empty population ("no relationships", "no years recorded"). The cost figure is
  the sharp case: `genealogies.spend_usd` reads `0.0000` on every map and is
  written by nothing, so a `$0.00` there would be the exact defect this page
  exists to avoid; nothing in the path from the view to the page coalesces it.
  **`money()` prints cents unless cents would round a non-zero cost to nothing**,
  in which case it prints four decimals, and below that precision it says "less
  than US$0.0001" rather than a row of zeros (issue #87: a cached re-trace costing
  `0.004` rendered `US$0.00`, which reads as free). `money()` in
  `pipeline/map_report.py` is the same branches in the same order, and it rounds
  a half away from zero to match JavaScript's `toFixed`, which `format(f, '.2f')`
  does not: measured over 25 values, `US$0.125` printed `US$0.12` in the command
  and `US$0.13` on the page before that was fixed alongside.
  Pending the owner's answer to the report design's open question 1 — the roadmap
  says a stranger should see what a map cost, this file's copy rules say no cost
  talk aimed at visitors, and the two cannot both hold — the cost figure renders
  for the owner only and every other figure renders for everyone.
  **The front door's badge names both populations** (issue #114). It read
  "28 pivotal of 138 papers · 39 of 39 links shown quote-verified" while the home
  card said "320 verified relationships" and the evidence page said "320 typed
  relationships", with the word "shown" as the only bridge, so a careful reader
  concluded the map had lost 281 links. It now reads "N links drawn here, all
  quote-verified · the full M are in the evidence", and the M clause is omitted
  when the canvas already draws every link. `getInfluenceMap` counts M with
  `COUNT(*)` over the map's edges, which is exactly the population the evidence
  page lists: `getGenealogy` selects every edge of the map, and its LEFT JOINs
  cannot multiply a row because `definitions` is UNIQUE on (paper_id, concept,
  prompt_version). Issue #30's reasoning is kept rather than reversed: two counts
  on one page are dangerous *unlabelled*, and this labels them.
  **Four surfaces print a count of "papers" and all four count different sets**
  (issue #123). On the live "attention" map they read 88 on the home card, 84 on
  the front-door badge, 85 on the evidence header and 156 on this page, and a
  reader crossing that hop had nothing telling them the word meant four things.
  The four populations, each verified by executing that surface's own query
  against one constructed map (20 / 12 / 11 / 10, and each number moved only by
  its own input):
  - **every `definitions` row for the map**, whether or not the paper defines the
    term. This page's `papers_with_a_reading`, labelled "papers read".
  - **the rows with `defines_concept = true`**. The home card's `paper_count` and
    this page's `papers_defining`. Two implementations, same population, so both
    say "papers that define the term".
  - **the membership of `genealogies.nodes`**, summed over the stored grouping.
    The evidence page header, labelled "papers grouped into meanings". It is a
    snapshot Stage C wrote and curation edits, so it is neither a subset nor a
    superset of the defining papers.
  - **defining papers that also carry an uptake score**, which is the pool
    `getInfluenceMap` picks the canvas's dots from: a paper with no score cannot
    be sized or placed. The front-door badge, labelled "papers this map ranked".
  No query was found wrong and none was changed. The numbers are not forced
  equal, because they count different things; each names its population where it
  appears, which is the bar #114 set one number away on the same hop.
  **A fifth surface, found verifying that one on the live site** (issue #133):
  the export's preamble, which is the only one of the five the reader takes away
  and the only one read where no page can explain it. Its population is a fifth
  set again, **the papers in the threads being exported**, which `lib/export.ts`
  builds `arxivs` from and which is exactly what the downloaded document cites.
  It is named on the line: "from the 84 papers in these 5 threads", and for a
  single thread "covering the 17 papers in it".
  `/g/[id]` links to it from a full-width row beside the evidence and export
  rows and shows no report figures itself, because that header's badge counts
  only the links drawn on the canvas and is a narrower population. **That row's
  subtitle promises only what every reader receives** (issue #112): it read "what
  is verified, what it rests on, what the run cost", and the cost figure renders
  for the owner alone and says "not recorded" even for them on a map built from
  the command line. A door that promises what the room does not hold spends the
  trust the product exists to earn, so while the cost figure is owner-only no
  public copy advertises it.
- `/about` : the public methods page, written for a researcher deciding whether
  to rely on this. What a map is, how one is built, how papers are ranked (and
  why ranking on uptake alone hides the papers that moved a term), the six link
  types (rendered from the same `EDGE_MEANING` map the product uses, so it
  cannot drift), "What you can and cannot rely on" separating verified quotes
  from sourced-but-unverified text from machine judgment, "Limitations and
  scope", draft-then-judgment, and reproducibility.
  **Machinery is the subject here, so the test applied is narrower than
  elsewhere**: not "does a sentence mention a mechanism", but "does it name one
  the reader has not been introduced to, or need two reads" (issue #125). Ten
  failed it. "Keeping the top N rather than applying a similarity cutoff" is now
  "a fixed number of the closest are kept" and "a cut-off score is deliberately
  not used"; "grouping by citation topology would produce a graph-theoretic
  artifact" is "grouping by who cites whom would draw a picture of the citation
  network, not a picture of the idea"; "the centroid of every definition before
  it" is "the average"; "expanded one hop through the citation graph" is
  "widened by one step, to the papers those papers cite and the papers that cite
  them"; "anything below the match threshold" names the title check it is
  actually about; "raw pipeline output" is "exactly what the machine produced,
  unedited"; "calibrated judgment rather than measurement" is "the model's own
  estimate of how sure it is, not a measurement of anything". No claim is
  weakened and no guarantee widened by any of them.
  **"Corpus" is introduced once and then owned by the reader.** It was used
  eleven times and never explained, starting with the heading of step 1, and it
  carries the whole method. Step 1 is now "Choose the papers" and its first
  sentence reads "a list of candidate papers (the corpus)". This page is the one
  place in the app where keeping the word is right, because the researcher
  reading it will meet it again in their own field; everywhere else it is
  removed rather than glossed.
- `/roadmap` : built / working on next / under consideration / not planned,
  so a researcher can judge whether the gap between this and what they need is
  likely to close. "Not planned" is load-bearing: not a recommender, not a
  search engine, not automatically curated.
  **The buckets are hand-written arrays and the page says so** (issue #119),
  with a link to the GitHub issue list and the sentence that where the two
  disagree, the issues are right. It had drifted within a week: "Bring your own
  corpus" sat under Under consideration while [#37](https://github.com/rgok001/Lineage/issues/37)
  `[F9]` is labelled planned, and it has moved to Working on next; and
  "Claim-level verification" was listed as entirely ahead while Stage H ships it
  on thread accounts wherever it has run, so the entry now names the live part
  and the remaining part separately. **Deriving the buckets from issue labels
  was measured and does not work**: every open feature and quality-of-life issue
  carries `planned`, so labels cannot distinguish "working on next" from "under
  consideration", and a derivation would invent an ordering the tracker does not
  hold. The honest framing is the fix; the page remains prose the owner owns.
  **Two entries name an actor where they named three mechanisms** (issue #128).
  "Resolving open-access copies through DOIs, and biomedical full text, would
  open fields that do not preprint to arXiv" is "Finding free copies of papers by
  their DOI, and reading biomedical full text, would open up fields that do not
  post preprints to arXiv"; "the pipeline already separates finding papers from
  reading them, so this is more plumbing than invention" is "Finding papers and
  reading them are already separate steps inside the system, so this is more
  wiring than invention". "Bring your own corpus" is kept as a title, because it
  is a phrase a researcher recognises. "The pipeline drafts; a person decides" is
  the one place the word "pipeline" earns its keep on this page and is untouched.
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

**Every route is dynamic, so every route pays a round trip, and the reader is
told the click landed** (issue #140). Nothing under `/g/[id]` is prerendered:
each is `force-dynamic`, so a click costs a serverless invocation plus its
database queries before anything reaches the browser. Measured on the live site
from Sydney against the `iad1` functions, before any change (median of 9,
brotli, warm): `/g/13` 2.03 s to first byte, `/g/13/evidence` 3.06 s and 4.32 s
complete, `/g/13/p/1706.03762` 2.49 s, a thread 1.39–1.62 s, the report 0.78 s.
The `/g/13/river` redirect answers in 0.33 s and does no database work at all,
which is the network floor from that vantage point; the rest of each figure is
server work.

Two things were wrong and both are fixed. **There was no `loading.tsx` anywhere
in `app/`**, so the router held the previous page on screen, unchanged, for the
whole wait — the click was not acknowledged at all. There are now boundaries at
`/g/[id]` and at each of `evidence`, `report`, `river/[sid]` and `p/[arxiv]`,
and (since #144, below) at `/` and `/trace`, sharing the shapes in
`app/app/skeleton.tsx`. They render **shapes and never
content**: no counts, no titles, no quotes, not even plausible ones, because a
skeleton that guesses a number is a fabricated claim about a map for as long as
it is on screen (rule 4), and the only words on them are words about loading.
The pulse is one keyframe in `globals.css` and it stops under
`prefers-reduced-motion`.

**Both halves of the skeleton were then made legible** (issue #147, found by the
UX review of #140). The loading note — the only sentence on the screen and the
only element not `aria-hidden`, so the only thing a screen reader is given — was
`--ink-faint` at .68 rem, uppercase, .14 em tracked: **3.33 : 1 at 10.88 px**,
under WCAG AA's 4.5 : 1 and the least legible text in the product. It is now
`--ink-soft` at .8 rem in sentence case, **6.45 : 1**, with the words unchanged
and `role="status"` untouched. And under `prefers-reduced-motion` the rule used
to apply `opacity: .65`, which composited `--card` back towards `--paper` and
took the bars from 1.06 : 1 to **1.04 : 1** — a reader who switches animation off
because it makes them ill was shown a blank screen with one line of text on it.
The rule now raises them to `--card-2` instead, **1.14 : 1**, still and at the
top of the range rather than fading out of it. Contrast figures computed from the
tokens in `globals.css` rather than transcribed; the check is a render of every
boundary that asserts on the `role="status"` element's own style attribute, and
it was run against the pre-change source first and failed there on all four
counts.

**Confirmed after deploy in a real browser with `prefers-reduced-motion`
emulated**, reading computed styles off a skeleton that was on screen — the
served CSS being right is necessary and was not sufficient, since the old rule
was also "right" in the bundle and still produced a blank screen:

| | before | after |
|---|---|---|
| note colour / size | `rgb(90,106,114)` at 10.88 px, uppercase, 1.52 px tracked | `rgb(139,154,162)` at 12.8 px, `text-transform: none`, `letter-spacing: normal` |
| note contrast | 3.33 : 1 | **6.45 : 1** |
| bar under reduced motion | `--card` at `opacity: .65`, 1.04 : 1 | `rgb(24,33,38)` at `opacity: 1`, `animation-name: none`, **1.14 : 1** |

Sixteen bars on `/` and twenty-eight on `/trace` are present and still under
reduced motion, where before they were present and invisible.

**And four call sites each read the same `genealogies` row twice.** `getRiver`
selected `concept, streams`, and every caller then issued a second statement
against that same row for `prompt_version` — the key it needs to look up
anything else. The Neon HTTP driver makes every query a separate fetch, so that
bought a whole round trip for columns already on the wire. `getRiver` is
replaced by `getMapRow`, one SELECT returning concept, prompt version, river and
edit log, used by `getInfluenceMap`, `buildExport`, the thread page and the
paper dossier. Independent queries then went into `Promise.all`: the definitions
and the edge `COUNT(*)` in `getInfluenceMap`, the edges and the papers in
`getGenealogy`, the map and the session on the evidence page. `getInfluenceMap`
went from five statements in five rounds to four in three; `getGenealogy` from
three rounds to two; the paper dossier from six serial queries to three rounds.
Verified by differential harness rather than by inspection — old and new loaders
against one stubbed database returned identical JSON on the full map, the map
with no river, the missing row, a JSONB string where `user_edits` should be an
array, and an edge whose paper row is gone.

**After, same vantage point and same method** (seconds, TTFB then complete;
`/` is the control, it was not touched and it did not move):

| route | TTFB before → after | complete before → after |
|---|---|---|
| `/g/13` | 2.03 → 0.34 | 2.26 → 2.05 |
| `/g/13/evidence` | 3.06 → 0.36 | 4.32 → 3.34 |
| `/g/13/report` | 0.78 → 0.35 | 0.97 → 1.00 |
| `/g/13/river/s0` | 1.39 → 0.35 | 1.61 → 1.40 |
| `/g/13/river/s3` | 1.62 → 0.35 | 2.06 → 1.61 |
| `/g/13/p/1706.03762` | 2.49 → 0.34 | 2.71 → 2.02 |
| `/g/10` | 2.05 → 0.35 | 2.27 → 2.20 |
| `/g/10/evidence` | 3.18 → 0.36 | 4.32 → 3.37 |
| `/` (control) | 0.76 → 0.79 | 0.77 → 0.79 |

**Read those two columns differently, because they now measure different
things.** TTFB is no longer "the data is ready"; with a loading boundary the
server flushes the skeleton shell as soon as it has one, so every one of these
routes now returns its first byte at 0.33–0.36 s, which is the redirect's floor.
That is the number the reader feels, and it is why the page stops appearing
stuck. The complete column is the honest measure of when the whole answer
landed, and it is where the round-trip work shows: evidence −23%, the long
thread −22%, the paper dossier −26%, the map −9%. `/g/13/report` is the useful
control on the other side — its queries were not changed and its complete time
did not move, while its TTFB still fell by more than half from the skeleton
alone. The two levers are separable and this table separates them.

The skeletons cost roughly 1.4 kB brotli on the map and 2.5 kB on the evidence
page, since the shell ships alongside the content. The streamed content is still
server-rendered HTML and not client-only: the evidence page carries 2.29 MB of
non-script markup, and its rendered figures are unchanged across the deploy (85
papers grouped into meanings, 287 typed relationships, 286 verified, 1 inferred).

What is deliberately **not** here: caching and PPR. The report is computed on
read and never stored (decision 30), so any caching of it needs design before
code, and the ticket says so.

**`/` and `/trace` now have boundaries too, scoped by a route group** (issue
#144). After #140 those were the two longest unacknowledged clicks left in the
product, and they are the two tabs on every page: measured on the live site from
Sydney, clicking the global nav from `/g/13`, **1143 ms to `/` and 1347 ms to
`/trace`** with the old page whole and unchanged for the whole of it. The trade
recorded here previously — that a root `loading.tsx` would also wrap `/about`
and `/roadmap`, which navigate instantly — was not real: `/about` takes 591 ms,
because the root layout renders `<SignInButton />` and that makes every route in
the app dynamic. That cause is issue #145 and is design-pending; it removes the
wait rather than covering it, and nothing here anticipates it.

The scoping is `app/app/(concepts)/`, a route group holding the home page and
its `loading.tsx`. A route group changes no URL, so `/` still resolves to
`app/(concepts)/page` in the app-paths manifest. `/trace` needs no group — it
already has its own directory, so its boundary sits in it. Verified from the
build's own route tree rather than by reading the docs: `/(concepts)/page` binds
`(concepts)/loading.tsx`, `/trace/page` binds `trace/loading.tsx`, and
`about/page.js` and `roadmap/page.js` contain no loading module at all. One
boundary per route and none nested, so neither route can flash the other's note.

The shared shapes moved from `app/g/[id]/skeleton.tsx` to `app/app/skeleton.tsx`
in the same change: the home page reaching into a map's directory for them would
be the wrong dependency, and one file is what keeps every skeleton in the app on
one palette and one pulse. `Panel` gained `pad`, `radius` and `grow`, because the
cards on `/` and `/trace` are roomier than the ones inside a map and a skeleton
whose padding is off moves the page when the content lands. Neither new skeleton
draws the trace queue or the sign-in state, and neither claims a map count: those
are exactly what the page has gone to the database to find out, and they append
below what is already drawn, which shifts nothing.

**After, measured on the live site the way the ticket was measured** — headless
Chrome at 1440×900, real clicks on the global nav from `/g/13`, time from click
until anything at all changes on screen:

| clicked | nothing on screen, before | skeleton on screen, after | content arrives | CLS |
|---|---|---|---|---|
| **Concepts** (`/`) | 1143 ms | **7 ms** | 1392 ms | 0.0000 |
| **Map a new concept** (`/trace`) | 1347 ms | **15 ms** | 999 ms | 0.0001 |
| How it works (`/about`) — control, untouched | 591 ms | *no skeleton, by design* | 578 ms | 0.0000 |

`/about` is the control and it is the one that matters here: it did not move and
it draws no skeleton, which is the route group doing its job on a live click
rather than only in the build manifest. The nav links are above the fold, so the
router prefetches the new boundaries — that is why 1143 ms becomes 7 ms rather
than merely becoming a faster paint, and it is the same effect #140 bought on the
links a reader can see. The wait itself has not shortened and is not claimed to
have: content still arrives at 1392 ms and 999 ms. The `/trace` figure of 0.0001
is two shifts at 7.2 s and 8.2 s, long after arrival, from the panel that polls
every 3 s; nothing shifts at the skeleton-to-content swap on either route.

By `curl`, median of 9 warm brotli requests from the same vantage, comparable
with the table above this section: `/` first byte **0.79 → 0.31 s** while its
complete time did not move (0.79 → 0.74), which is the same separation of the two
levers #140 recorded — the click is answered, the data is not faster. `/trace`
answers at 0.33 s and completes at 0.54. The `/g/13/river` redirect, which does
no database work, is 0.31 s and is the network floor from here.

**Inside a map, the sideways links are now permanently in the viewport** (issue
#143). #140 and #144 bought a skeleton on every click, and #143 is the same
lever applied to the links themselves: Next prefetches a route's loading
boundary only while the link is on screen, so on `/g/13` the first thread card
answered a click in **5 ms** at y=871 while "The evidence →" at y=1135 took
**349 ms** and "What this map is made of →" at y=1185 took **325 ms**. The same
evidence link, same page, same session, answered in **14 ms** once it had been
scrolled into view. The two most important links on the map were the only two
that never got prefetched. A thread page carried no sideways link at all — its
only outbound was `‹ the map` — so moving between two threads was two waits and
a scroll hunt, and a reader on a thread had no way of knowing the evidence page
existed.

`app/app/g/[id]/layout.tsx` renders `tabs.tsx` above `{children}` on every route
under a map: **The map** (`/g/{id}`), **Threads** (`/g/{id}#threads`), **The
evidence**, **What this map is made of**. Four links, always above the fold,
always prefetched. On `/g/{id}/p/{arxiv}` no tab is marked current — a dossier
is a place, not a section, and lighting "The map" would be a small lie about
where the reader is.

**The layout awaits nothing, and that is the whole design rather than an
economy.** `loading.js` nests *inside* `layout.js`, so a boundary cannot cover
its own parent: any data read in this layout would block every navigation under
a map above the skeleton #140 bought, and would read as #140 regressing with no
visible cause. That is why "Threads" is an anchor to the map's thread list
rather than a menu of the five thread names, and why the strip does not carry
the map's name — both need the `genealogies` row. `await params` is routing,
not I/O, and is the only await in the file. The constraint arrives a second time
from the billing side: four extra prefetch requests per map page view are four
function invocations, and each must touch no database.

Verified from the build's own route tree rather than from the docs, the method
#144 established: every route under `/g/[id]` now carries
`layout: app/g/[id]/layout.tsx` at the `[id]` segment, with its leaf's own
`loading.tsx` at a segment *below* it — so `/g/13/evidence` binds
`evidence/loading.tsx` under the strip, and a tab click swaps the content inside
the map frame instead of re-skeletoning the page. The four existing skeletons
are unchanged and must not grow a strip of their own. The one edit to
`g/[id]/page.tsx` is `id="threads"` on the thread-list section.

Deliberately not done: no sticky positioning (a fixed bar on a 39-screen
evidence page is the wrong answer to a problem an index should solve), the
`‹ the map` breadcrumbs and the two bottom cards on the map page stay, and no
export control in the strip.

**Progress transport is polling, not SSE**, a deliberate deviation from the
original plan: progress lives in Postgres anyway, serverless cannot hold
streams open cheaply, and a 3 s poll of a tiny route gives the same live feel
while surviving reconnects and redeploys for free.

**Copy rules.** No internal jargon in public view (worker, polls, prompt
versions, databases), no cost talk aimed at visitors, "curator" language
throughout, raw failure output visible to the owner only, and **no em dashes
anywhere in user-facing content**. **A count of edits is stated in plain words
and pluralised properly** (issue #120): the home card and the evidence page's
audit trail both read "N curatorial change(s)", where "(s)" is the machine
talking and "curatorial" is a word the reader meets long before the about page
explains it. They now read "N change(s) by hand" / "N change(s) made by hand"
with the plural resolved. The counts are unchanged, and they are still counts of
`CURATORIAL_OPS`. The narrative sentences that use "curated" and "curatorial"
are left alone, because the "curator language throughout" rule above is the
owner's and #120 named the counters only. "Genealogy" and "trace" were internal words a
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

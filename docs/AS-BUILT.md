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
| LLM | Claude Sonnet (`claude-sonnet-5`) for extraction, classification and claim evidence; Claude Haiku (pinned snapshot `claude-haiku-4-5-20251001`) for magnitude scoring and thread generation | n/a | ~$6 per 150-paper trace, +~$3 claim checking (decision 17), both computed at Sonnet's standard $3/$15 and so ~$4 and ~$2 while its introductory rates run to 2026-08-31; +~$0.14 magnitude and threads, which the record published as ~$0.7 until #205 found Haiku calls being priced at Opus rates |

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
                     runs them in two passes, see PIPELINE.md for how many
                     steps that is — the count lives there and nowhere else)
  common.py          env loading, polite HTTP session, data_dir()
  check_extraction.py  audit of extracted-text fidelity (no model, no network)
  db/migrate.py      ordered SQL migrations, schema_migrations table
  db/migrations/     001..024
  recheck_stamp.py   re-checks stored stamps against the papers (read-only)
  record_pass.py     which pass of a build read which papers (#192)
  record_anchors.py  which of a map's papers a person named (#198)
  record_spend.py    what each step of a build spent (#47)
.claude/            settings.json (carries the LINEAGE_NO_DB guard; tracked),
                     launch.json, and memory/ (agents' lessons, boards and
                     verdicts; gitignored). The role prompts are NOT here
worker/run.py        the trace worker (queue consumer)
app/                 Next.js app (Vercel root directory is app/)
  app/               routes: /, /trace (request a map), /about, /roadmap, /terms,
                     /g/[id] (the influence map), /g/[id]/river/[sid] (a thread's
                     account), /g/[id]/p/[arxiv] (a paper's dossier),
                     /g/[id]/evidence (the old detailed view + workbench),
                     /api/traces, /api/viewer, /api/auth
                     layout.tsx + nav.tsx hold the one tab bar
                     signin-button.tsx is a client component; lib/auth-actions.ts
                     holds the two Server Actions it submits
                     g/[id]/layout.tsx + tabs.tsx hold the second one, the four
                     places inside a map; it fetches nothing, on purpose
                     current-tab-click.ts is the one behaviour both strips share
                     for a click on the tab you are already on
                     skeleton.tsx holds the loading shapes every boundary shares
                     (concepts)/ is a route group, not a URL segment: it exists
                     so / can have a loading.tsx that /about does not get
  lib/               db.ts, authz.ts, genealogy.ts, traces.ts, actions,
                     arxiv-id.ts (an arXiv id out of what a person typed, #198)
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

Nine tables and twelve views, migrations `001` through `025`, applied by
`python pipeline/db/migrate.py` (tracked in `schema_migrations`). The counts are
read off a database with every migration applied, not maintained by hand — they
said "six tables and two views" for several migrations after they stopped being
true:

    tables  definitions, edges, genealogies, map_anchor_papers,
            map_build_pass_papers, map_build_passes, map_build_stages, papers,
            trace_requests
    views   genealogies_current, map_invariant, map_invariant_findings,
            map_pass_build, map_pass_papers, map_report, map_report_anchors,
            map_report_by_source, map_report_by_type, map_report_passes,
            map_report_read_years, map_report_stages

Migrations `008`-`009` are data fixes (paths relative to `DATA_DIR`; correcting
future publication years OpenAlex mis-dated). `010`-`012` carry the
paper-centric turn and are described inline below. `016` adds no table and no
column at all: it is the two report views, described at the end of this section.

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

**genealogies** (001, 007, 012, 025): the map itself. `nodes` is JSONB
(concept-states with members and year ranges), `user_edits` is the append-only
curatorial audit trail (each entry `{op, detail, at}` plus at most one of `by`
and `by_asserted`; decision 18), `spend_usd` accumulates cost, `status` is one of
pending/running/complete/failed/aborted_spend_cap. **`status` stopped being
vestigial with issue #168**: `complete` is what Stage E writes and is now the
only value the app will read a map at, so it is the record of whether a map is
published. Everything else about the column is still loose and #48 still owns
tidying it. Migration 007 adds
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

**Migration 025 (`025_map_versions.sql`, issue #206) adds the version shape, and
nothing reads it yet.** Three columns — `version INT NOT NULL DEFAULT 1`,
`is_current BOOLEAN NOT NULL DEFAULT false`, `superseded_at TIMESTAMPTZ` — and
three rules the database now holds that were previously conventions:

- `genealogies_one_current_per_concept`, a unique index on `(concept) WHERE
  is_current`: at most one current map per concept, **per concept and not per
  (concept, prompt_version)**, so a newer prompt version's map supersedes the
  older rather than putting two cards for one term on the concepts list.
- `genealogies_current_is_published`, `CHECK (NOT is_current OR status =
  'complete')`: current implies published. It constrains currency by status and
  not the reverse, so a published map that is not current stays legal — that is
  every superseded version.
- `genealogies_concept_pv_version_key`, `UNIQUE (concept, prompt_version,
  version)`: a version number cannot be issued twice.

The backfill made the four published maps version 1 and current; everything else
in the table is `is_current = false`. `superseded_at` is the record written by
the swap that clears `is_current`, and is NULL everywhere today because no swap
has happened — it is never inferred from `is_current`, because a row that was
never current was never replaced either. **Nothing forbids `is_current = true`
beside a non-NULL `superseded_at`**; that fourth constraint is raised on #207,
beside the swap that would write the column.

**007's `UNIQUE (concept, prompt_version)` is still in place**, though the F4
design retires it. It cannot go until Stage C stops upserting on it: Postgres
resolves an `ON CONFLICT` target's arbiter index when it *plans* the statement,
so dropping the constraint makes `stage_c_cluster.py`'s insert raise
`InvalidColumnReference` on every build, including the first build of a concept
nobody has mapped. The drop is #207's, in the commit that rewrites Stage C.

**One behaviour did change, and it is the only one.** Re-clustering a *live* map
in place — `stage_c_cluster.py <concept>` with no `--embed-only`, which sets
`status = 'running'` on the existing row — is now refused by the CHECK, because
the row is current. That is the destructive overwrite F4 exists to remove,
refused a wave early and loudly, with the constraint named in the message. The
operator path is unchanged: delete the map first, which is what decision 12
already requires. `--embed-only` returns before the upsert (`stage_c_cluster.py`
line 320 against line 410) so the repair path after `stage_b --refresh` is not
affected, Stage C on a concept with no published map still works, and Stage E's
publish still works.

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

All 26 fields are offered, per decision 36, and `getArxivFields()` derives them
live from OpenAlex (`indexed_in:arxiv` grouped by `primary_topic.field.id`,
cached a day) rather than hard-coding a list. `requestTrace()` validates the
submitted id against that same list via `isKnownField()`. Until issue #175 it
did not: the check was the shape test `/^fields\/\d{1,4}$/`, so any of ten
thousand ids reached the row, and an id outside the twenty-six that exist was
approved and then failed at Stage A with no seeds. A value failing the old test
was rewritten to `fields/17` in silence, answering a request for one subject
with a map of another; it is now refused with a message instead. While OpenAlex
is unreachable both the picker and the allow-list fall back to the six
arXiv-heavy fields in `lib/openalex.ts`, so a choice made before an outage can
be refused during one.

The form states the coverage limit at the picker, in `/about`'s wording: arXiv
only, so fields publishing mainly through journals, conferences or books are
thin or missing. This is copy, not a constraint — nothing refuses a thin field,
and Stage A has no corpus floor, so a field arXiv barely covers yields a small
map carrying the same stamps as a large one. Measured 2026-08-08, arXiv as a
share of each field's articles ranges from 21.6% (mathematics) and 20.6%
(physics) to 0.13% (medicine) and 0.04% (arts and humanities); quality per
field is read on each map's report after it builds, not gated before.

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

**trace_requests** (005, 006, and migration 018, `018_trace_requeues.sql`): the
request inbox and the job queue in one table. Status flow: `requested -> approved -> running -> complete`, plus
`rejected` and `failed`, and `running -> approved` when a run is interrupted and
put back on the queue. `progress` JSONB is written live by the worker;
`updated_at` doubles as the worker heartbeat; `requeues` (018) counts how many
times a run has been restarted after dying without an error, and is read only by
the worker's sweep, never by the app; `genealogy_id` links the finished map. A
partial unique index allows only one open request per concept, enforced at the
database level because app-level checks can be raced by simultaneous submits.
`anchors` (migration 023, `023_anchor_papers.sql`, issue #198) is a `text[]` of
the arXiv ids the requester named, at most three. **NULL and the empty array are
different claims**: NULL means the request predates the field, the empty array
means the field was offered and nobody was named, and the app writes `'{}'`
deliberately for the second. The CHECK caps the array at three and refuses a NULL
or empty-string element; it does **not** test the shape of an id, which lives in
`app/lib/arxiv-id.ts` and `corpus_select.ANCHOR_ID_RE` and would be a third value
the moment one of them moved. It also does not catch an element of pure
whitespace, because a per-element predicate needs a subquery and a CHECK
constraint may not contain one (PostgreSQL: `cannot use subquery in check
constraint`, found by executing the migration against a real server rather than
by reading it). **The two ways of applying a migration disagree about a
statement that fails mid-file**, measured on PostgreSQL 16 on 2026-08-09:
`psql` prints the error to stderr, carries on and exits 0, leaving the table
created and the constraint absent, while `pipeline/db/migrate.py` hands the whole
file to one `conn.execute` inside the connection's transaction, which raises and
rolls the file back, so nothing is created and `schema_migrations` gains no row.
A bad migration therefore fails a deploy loudly and fools a harness or an
operator applying it by hand.

**map_anchor_papers and map_report_anchors** (023, `023_anchor_papers.sql`,
issue #198): which of a map's papers a person named at request time, and the
report figure that discloses them. Storage and read shape in one migration,
because there is one ticket; what survives from `020`'s design is the shape that
made it safe, a separate **view** rather than more columns on `map_report`, since
a missing column cannot be guarded by `to_regclass` and would 500 the report page
for the minutes between the Vercel deploy and Render's pre-deploy migration.

`map_anchor_papers` is one row per (map, arXiv id), keyed **on the id and not on
`papers.id`**, unlike `map_build_pass_papers` — an id that was named and could
not be fetched has no `papers` row, and that is exactly the case a requester must
be able to see, so a foreign key there would delete the evidence of the failure.
`named_by` and `named_by_asserted` are decision 18's split unchanged: a request
made through the site carries the first, because the app wrote that login from a
session and the worker only relays it; a corpus anchored from the command line
carries the second, which is all a script running for whoever holds the `.env`
can honestly claim. `named_rank` is the position in the order the ids were typed.
`pipeline/record_anchors.py` is the only writer and clears the map's whole record
before each build, so a map anchored once and rebuilt with nobody named comes
back saying nobody named a paper.

`map_report_anchors` carries `papers_named`, `papers_named_read`,
`papers_named_defining`, `papers_named_linked`, `named_by`, `named_by_asserted`
and `named_papers` (a JSONB list of `{arxiv_id, title, year, read, defines,
relationships}`, in the order named). **Every count is a real zero on every map
in this database and there is no absent case**, which is the one way this view
differs from `map_report_passes`: "no second pass ran" and "a second pass ran and
read nothing" are different facts with identical counts, while a map with no rows
here had no paper named by a person, and that is equally true of a map built
before the feature shipped and of one built after it with the field left empty.
So no `COALESCE` fabricates anything and both consumers state the zero in words.
`papers_named` and `papers_named_read` differ exactly when a named id could not
be fetched or produced no reading, and `named_by`/`named_by_asserted` are
selected by `pipeline/map_report.py` and deliberately **not** by
`app/lib/report.ts`: the sentence a reader is owed is about "the person who
requested it" and needs no login to be true.

**map_build_stages and map_report_stages** (024, `024_build_stage_spend.sql`,
issue #47): what each step of a build spent, how long it took and which pass it
ran in, plus the report figure that reads it. Storage and read shape in one
migration, for `023`'s reason, and the figure is a separate **view** rather than
more columns on `map_report`, for `023`'s and `019`'s reason.

**It is an instrument, and it exists so that the cost-reduction programme has a
"before".** Until now a build's cost existed as exactly one number — the worker's
regex over the stages' stdout, published as `map_report.run_cost_usd` — so
extraction costing a cent a paper on `embedding` and four cents on `attention`
could be observed and not located, and how much of a map's cost the shared
extraction cache avoids was unknowable (decision 27, ROADMAP open question 6).
**One optimisation shipped ahead of it**: #202's Stage H cache landed on the same
day, hours earlier, and its saving is therefore evidenced by that ticket's own
two-run measurement rather than by any map's record. Everything after it has a
per-stage before to be measured against, and the first map built with this
recording is where that reading starts.

`map_build_stages` is one row per (map, step): `stage_no` (the position the feed
showed), `stage` (the worker's own feed name, so the breakdown and the progress a
requester watched use one vocabulary), `build_pass` (1, 2, or NULL for a step
belonging to neither), `spend_usd`, `spend_lines`, `seconds`, `run_id` and
`recorded_at`. Keyed on the map and cleared per build, like
`map_build_pass_papers`, so a requeue or a re-trace re-states what it spent
rather than adding to it. `run_id` carries no foreign key on purpose: a deleted
request must not delete the record of what its build spent.

**`spend_usd` NULL and `spend_lines = 0` are the same fact and a CHECK makes them
inseparable: this step printed no cost line.** That is not a spend of zero. Most
steps of a build genuinely cost nothing (fetching, extraction, the audit,
grounding, the recorders) and a step that *stopped* printing its spend looks
identical from here; the two cannot be told apart and neither may be published as
`US$0.00`. What the record adds is that such a step is now a **named row with no
figure** instead of a silent absence inside a total, which is the half of #85's
complaint that was fixable. A stage that printed `$0.0000` — Stage C with every
label cached, Stage D with every pair cached, both deliberately — carries
`spend_lines >= 1` and a real zero.

**Nothing new is measured for it.** `Progress` in `worker/run.py` has parsed
every stage's spend line since the feed existed and resets its per-stage total on
`start_stage`; the whole change is keeping that number when the stage ends
instead of folding it into a running sum, so the per-step figures sum to the same
scrape the report already publishes. `pipeline/map_report.py` prints both and
marks a mismatch.

`map_report_stages` carries `stages_recorded`, `stages_with_a_cost`,
`stages_with_no_cost_line`, `stage_spend_usd`, `stage_wall_clock`,
`stages_pass_one`, `stages_pass_two`, `stages_outside_passes`,
`pass_one_spend_usd`, `pass_two_spend_usd`, `spend_outside_passes`,
`costliest_stage`, `costliest_stage_usd`, `costliest_stage_share`,
`stage_record_basis`, `stage_record_run_id` and `stages` (a JSONB list of
`{stage_no, stage, build_pass, spend_usd, spend_lines, seconds}`, in run order).
The pass is a **column rather than a filter** over one set of rows, `019`'s and
`020`'s discipline, so `stages_pass_one + stages_pass_two + stages_outside_passes
= stages_recorded` and the three spend subtotals sum to `stage_spend_usd` by
construction. `costliest_stage` is a `DISTINCT ON` with the tie broken by the
earlier step, and steps with no cost line are excluded from it rather than
treated as zero. Its share is a genuine share: the steps partition the total.
`stage_record_run_id` is selected by `pipeline/map_report.py` and deliberately
**not** by `app/lib/report.ts`, like `named_by` above — it is how an Operator
tells whether the breakdown and `run_cost_usd` describe the same run, and a
reader of a map is owed neither the id nor the queue behind it.

**Every spend figure stored before 2026-08-09 overstates what the build actually
cost, and none of them has been rewritten** (issue #205, incident 16). Until that
day `cost_usd` priced any model id it did not recognise at the table's most
expensive rates, and Stages F and G pass a dated snapshot id that was not in the
table: **their share of every stored figure is five times what those calls cost**.
The same fix corrected Sonnet 5 to its introductory rates, so the other paying
stages' share is overstated by half again for as long as those rates have been in
effect (the published page names their end, 2026-08-31, not their start). This
touches `genealogies.spend_usd` on every completed map, everything
`map_report.run_cost_usd` publishes from it, and `map_build_stages` — which has
no rows yet, since no build has run under it. **They are left as they are on
purpose**: each is a claim a particular build made about itself under the table it
had, and rewriting them would replace a recorded claim with a later
reconstruction, which is the one thing a record must not do. A figure from a
build after this date is priced correctly; the direction of the old error is
always overstatement, never the reverse.

**Every map built before #47 reads "no step-by-step record of this build", and
that is an absence and not a build that spent nothing.** The gate is an inner
`GROUP BY` plus a `LEFT JOIN` rather than a `CASE`, `020`'s device, so a map with
no rows produces no row in the CTE and there is no expression anywhere that could
coalesce it to a zero. There is no such thing as a build that ran no steps, so a
zero could only ever mean absence; `stage_record_basis` says which state a map is
in, never blank, in the shape `run_cost_basis` established.

Measured against a real PostgreSQL with `001`-`024` applied, one database per
scenario and 65 checks: a fixture two-pass build of 29 steps, a one-pass build, a
map with no record at all, a build every step of which printed nothing, a re-run
that re-states rather than accumulates, and five refusals (a cost with no line
behind it, a line with no cost, an unnamed step, two steps at one position, a
ledger that is not there) none of which wrote a row. A further 36 checks drove
`worker/run.py`'s own `StageRunner`, `Progress` and `run_job` with the
subprocesses replaced, and 27 rendered the compiled report page over the same
rows, including the deploy window with the view dropped.

**map_report_by_source and map_report** (016, `016_map_report.sql`): the map
report (issue #30, `[F2]`), the first two of the report's views; every later one
is described in its own entry above, and their number is not restated here
because it has moved five times. They store
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

**map_report_by_type** (017, `017_map_report_by_type.sql`): the mix of kinds of
link, one row per (map, kind), issue #162. Until it shipped, nothing on any
surface said how a map's relationships divide across the six kinds — `016`
touches `edge_type` exactly once, as `count(DISTINCT edge_type)` inside the
multi-linked-pair test — so a map whose 300 relationships were 290 `extends` and
10 everything else read as an excellent map on every figure the report published,
while a classification returning one label out of six is not classifying. It is
the figure a map built outside the field the taxonomy was written against fails
first, which is why it is a prerequisite of #164's calibration maps.

The view carries `edge_type`, `taxonomy_rank`, `edges` and `edges_share`. It
crosses every map with the six kinds, so **a kind no relationship was given is a
row reading zero rather than a row that is not there**, and it `UNION ALL`s a row
for any kind actually present that is not among the six, so **the rows always sum
to the map's relationship count**: a kind the `edges.edge_type` CHECK permits and
this view forgot cannot go missing. `taxonomy_rank` is `WITH ORDINALITY` over the
six, and NULL is what says the taxonomy does not contain that kind; both
consumers sort `NULLS LAST` and neither writes the six names down. `edges_share`
divides by the sum of this view's own rows for the map, taken as a window rather
than as a second count of `edges`, so the identity holds inside the view rather
than between two expressions; `NULLIF` makes the share absent, never 0%, on a map
with no relationships. Its numeric literals are `{0, 1}` — the `NULLIF`
denominator and `SELECT 1 FROM pg_roles` in the `GRANT` — and it carries `016`'s
two header checks over its own text.

Measured against a real PostgreSQL with `001`-`017` applied and four fixture
maps (a lopsided mix, one kind only, no edges, a single edge): the kinds sum to
`map_report.edges_total` on all four, every map appears on the view, a map with
no edges reports six zeros with an absent share, and after the CHECK constraint
was dropped and a `supersedes` edge inserted, that kind appeared as a seventh row
with a NULL rank and the sum still matched.

**map_report_read_years** (019, `019_map_report_read_years.sql`): what the map
**read**, by year, one row per map, issue #182 designing #33 (F5). Every year
figure `016` publishes is over the papers that *define* the term — its
`year_rows` CTE joins `definitions ... AND d.defines_concept = true` — so
`year_max = 2016` on the dark energy map conflates two causes needing opposite
fixes: selection never picked a recent paper, or selection picked it, Stage B
read it, and it did not define the term. The first is a defect in how papers are
chosen (what F5 fixes); the second is a finding about the literature, which F5
must be neither blamed nor credited for.

The view is `016`'s `year_rows` **minus** the `defines_concept = true`
predicate, with that predicate carried as a column instead, so both series come
out of one set of rows and `read_year_max >= year_max` and
`papers_defining_recent <= papers_read_recent` hold by construction; a map where
either fails has a join defect. It carries `read_year_min`, `read_year_max`,
`read_year_counts` (the histogram, in `year_counts`' shape so one renderer draws
both), `papers_read_with_no_year`, `recent_window_start`, `recent_window_end`,
`papers_read_recent` and `papers_defining_recent`. Its numeric literals are
`{1, 5}` — the `1` of `window_end - width + 1` and of `SELECT 1 FROM pg_roles`,
and the `5` of the recency window, which decides nothing about a paper and names
a population whose two ends both ship as columns, so the surfaces print "papers
from 2022 to 2026" rather than the word "recent". The window is read from
`current_date` when the view is read, so it moves with the calendar, which is
exactly why both ends are published rather than assumed.

**It is a fourth view rather than four more columns on `map_report`, and the
reason is the deploy window rather than the grain.** The grain is per map, the
same as `map_report`, so on grain alone these would have been columns. But
`CREATE OR REPLACE VIEW` can only append trailing columns to a definition given
in full, which would have put the live definition of `map_report` in two files
with the newer one silently winning; and a missing *column* cannot be guarded,
because `app/lib/report.ts` names every column of `map_report` in one statement,
so the whole report page would raise `UndefinedColumn` and 500 for the minutes
between the Vercel deploy and Render's pre-deploy migration. A missing
*relation* is guarded by the `to_regclass` fallback #92 earned, and the page
loses three figures instead of a page.

**map_invariant_findings and map_invariant** (021, `021_map_invariant.sql`): the
publish invariant, issue #168, covering the piece named in #149 and the publish
half of #2. Nothing in this system ever re-asked whether a map already published
still satisfies the rules of the stages that built it; these two views are the
question, and `pipeline/check_map.py`, Stage E's publish gate and (when #174
lands) the report page all read them, so none of them can hold a different
opinion about the same map.

Six clauses, each an existence test or an equality, **no threshold anywhere**:
(1) every entry of a concept-state's `definition_ids` names a definition Stage C
would admit today — it exists, it belongs to this map's `(concept,
prompt_version)`, `defines_concept` is true, the definition text is not empty and
the embedding is not NULL; (2) a concept-state's `members` and its
`definition_ids` describe the same papers; (3) every concept-state is readable
and uniquely named; (4) every relationship names two different concept-states of
this map; (5) every relationship's two papers are members of the concept-states
it names; (6) every paper the threads name is held by some concept-state of the
same map. `map_invariant_findings` is one row per violation, naming the
concept-state, the relationship or the thread and saying in words what is wrong
with it; `map_invariant` is one row per map, and its six counts are
`count(*) FILTER` over the findings, so the counts describing the findings is
true by construction. `satisfies_publish_invariant` is true only when all six
are zero. The numeric literals in the file are `{0, 1, 2, 3, 4, 5, 6}`: the six
clause numbers, the `0` of `= 0` and of every coalesced count, and the `1` of
`count(*) > 1` — which is the definition of a duplicate — and of `SELECT 1`.

**Clauses 2, 5 and 6 resolve a paper through `definition_ids ->
definitions.paper_id -> papers.id`, never by joining a member's `arxiv_id` to
`papers`.** That is the width the F7 note on #149 asked for: every member of a
stored node must resolve to one live paper row that still satisfies the rule of
the stage that put it there. When a map may draw papers from more than one
source, an arXiv id stops being an identity and that join would pair a member
with the wrong row; the member's arXiv id is used only to *name* what did not
resolve, in the finding's text. Clause 6 is measured against every paper the
`definition_ids` name, admissible or not, so a definition clause 1 already
reports is not reported a second time under another name.

**Nothing is stored — no verdict column, no `checked_at`, no provenance
column.** The recomputation is a `SELECT`, so a stored column could only be a
second ageing copy of something free, and the honest answer to "when was this
last checked" is "when you asked". **No constraint and no trigger** either: a
CHECK cannot reference another table, `edges.source_node` is TEXT into JSONB with
no foreign key available, a trigger would fire mid-rebuild where violation is
legitimate, and `CHECK (source_node <> target_node)` is refused because
`workbench.py`'s merge creates self-loops and deletes them in the same
transaction.

Measured against a real PostgreSQL with `001`-`021` applied and eleven fixture
maps: a well-formed map reports nothing at all on any clause (the falsifier), an
`n21`-shaped map — one concept-state whose only definition says
`defines_concept = false` with no text and no embedding — reports exactly one
clause-1 finding and one clause-2 finding and nothing else, and each of the six
clauses was driven red on the clean map one break at a time and back to green.
`definition_ids` holding a string, a fraction and a 26-digit number are three
clause-1 findings rather than an error out of the view: the id stays `numeric`
and is never cast to bigint, so bad JSON cannot make the instrument for finding
bad data raise.

**`papers_read_recent` is instrumentation and not evidence, and both surfaces
say so.** It counts papers in a window, so a selection rule that reserves seats
for recent work raises it *by construction* and it cannot report failure. The
evidence for F5 is `papers_defining_recent` and `read_year_max` against
`year_max`, because Stage B and the grounding check are independent judges that
can still answer no about exactly the papers a reservation admitted.

Measured against a real PostgreSQL with `001`-`019` applied and four fixture
maps (one that read newer work than it found defined, one that read nothing
recent, one that read nothing at all, one whose every paper is undated), 27
checks: every map has a row, `read_year_max >= year_max` and
`papers_defining_recent <= papers_read_recent` on all four, the histogram plus
the undated count equals `papers_with_a_reading` on all four, every year of the
defining series is present in the read series and never larger, the window is
the five calendar years ending in the current one, and a map with no dated paper
reports the histogram absent rather than as an empty object.

**map_report_passes** (020, `020_map_report_passes.sql`): which pass of the
build read a paper, one row per map, issue #193 instrumenting the two-stage build
designed on #184. `019` separated papers read from papers that define; a
two-stage map needs the further split, because pass two ADDS papers rather than
displacing them, so every total on the report rises when it runs and a map that
read fifteen more papers and learned nothing from any of them looks exactly like
one where the second pass moved the map.

`020` fixes the question the report asks and left where the answer LIVES to
#192, under one standing rule from the design: not a column on `papers`, which is
shared across every map ever traced. The seam is two views, **`map_pass_papers`**
(per map and paper: `definition_id`, `build_pass`, `pass_rank`) and
**`map_pass_build`** (per map: `passes`, `pass_two_outcome`, `pass_two_seats`,
`pass_two_candidates`, `pass_two_candidates_cleared`), shipped with the right
columns and `WHERE false`. A view is a read-shape holding nothing, so writing one
commits no storage and reserves no name in any table; that is why the seam is
views and not columns.

**Migration `022_build_passes.sql` (#192) is the other half, and it is now
applied.** Two additive tables — `map_build_passes` (per map: `passes`,
`pass_two_outcome`, `pass_two_seats`, `pass_two_candidates`,
`pass_two_candidates_cleared`, `recorded_at`, keyed on `genealogy_id`) and
`map_build_pass_papers` (`genealogy_id`, `paper_id`, `build_pass`, `pass_rank`,
primary key on the first two) — plus a redefinition of the two seam views over
them, and nothing else: not `020`, not `app/lib/report.ts`, not
`pipeline/map_report.py`, not the page. The primary key on
`(genealogy_id, paper_id)` is what keeps `020`'s sum identity true by
construction, since a paper counted in both passes would be one definition
counted twice.
**The pass is stored per PAPER and read back per DEFINITION**, and the view
resolves one to the other through the genealogy's own concept and prompt version.
The build knows which papers it read — the corpus files name arXiv ids — while
the report counts definitions rows (#123); a paper the build read that never
produced a definition therefore contributes no row to the seam, which is right,
because it is not one of the papers the report counts.
**It is `CREATE OR REPLACE VIEW` and not the `DROP VIEW` + `CREATE VIEW` `020`'s
header predicted.** `map_report_passes` selects from both seam views, so the DROP
fails on the dependency and `CASCADE` would take the report view with it and force
`022` to re-create it — putting `020`'s definition in two files with the newer
silently winning, which is the fault `020`'s own header refuses. `CREATE OR
REPLACE VIEW` may change a view's query however it likes provided the output
columns keep their names, types and order, which is exactly this change. The
types are therefore load-bearing and are spelled out in the tables.

The report view carries `passes_recorded`, `pass_two_outcome`, `pass_two_seats`,
`pass_two_candidates`, `pass_two_candidates_cleared`, `papers_read_pass_one`,
`papers_read_pass_two`, `papers_read_pass_unmarked`, `papers_defining_pass_two`,
`papers_linking_into_pass_one`, `pass_two_rank_bands` and
`pass_two_rank_band_width`. The pass is carried as a **column rather than as a
filter** over one set of rows, `019`'s discipline, so `papers_read_pass_one +
papers_read_pass_two + papers_read_pass_unmarked = papers_with_a_reading` and
`papers_defining_pass_two <= papers_read_pass_two` hold by construction; the third
count is "marked as neither the first nor the second pass", not "unmarked", so the
identity survives a pass number this view has never heard of. Every count is
gated on `map_pass_build` having a row by an inner `JOIN` rather than by a `CASE`,
which makes the absence structural: there is no expression anywhere that could
coalesce it to a zero. `papers_linking_into_pass_one` crosses to
`genealogies.nodes` and counts a meaning as found in pass one if it holds **at
least one** pass-one paper, not if it holds only pass-one papers — Stage C
re-clusters over the union corpus in pass two, so most meanings on a two-stage map
hold both and requiring purity would report almost nothing. Its numeric literals
are `{1, 2, 10}`: `1` and `2` name the two passes, and `10` is the width of the
selection-rank bands, published as `pass_two_rank_band_width` with each band
carrying its own first and last rank. It carries `016`'s two header checks over
its own text.

**Every map built before #192 reads "this map was built in one pass" and every
count is NULL**, which is a fact about the record and not a zero; so does a build
that deliberately ran one pass (`PASS_TWO_SEATS=0`), which writes no build row at
all rather than one saying `passes = 1`. A `COALESCE(..., 0)` anywhere would
report those maps as having run a second pass that read nothing. Once a build IS
recorded a zero is a real zero — a second pass that ran and found nothing — and
`pass_two_outcome` names which state produced it: the design's four (filled,
under-filled, none found, abandoned at the pre-flight gate) plus the fifth the
orchestration added, a second pass that failed and fell back to pass one, which
no count can be read off. It is never blank; it is reader-ready text arriving
through the seam,
the way `run_cost_basis` works on `016`, so this file does not enumerate a list a
fifth state would go missing from. `passes_recorded` prints its own absent words,
"nothing recorded how this map was built", rather than the conclusion drawn from
its absence.

`pass_two_rank_bands` is **#188's free half**: the defining rate over what the
second pass actually read, banded by ten of selection rank, which says whether the
seat count is larger than the map had papers worth reading. It costs nothing,
because it counts work the build already did. It **bounds the seat count from
above only** — past the point where the rate falls the seats are certainly
wasted, and nothing here can say whether a seat below that point earned its
place, which is the paid over-read #188 keeps for the first two-stage map — and it
measures whether a reserved paper *defines* the term, never whether it *moved* it.
It prints in `pipeline/map_report.py` and on no other surface, the same
page/command subset "quote slots" has sat in since #108, because it answers a
question for whoever sets the seat count and not for somebody reading a map.

**No recency score, no freshness grade and no "up to date" badge on any surface**,
and every ingredient of one is a count published here separately. A blended number
would be this tool's weighting read as a measurement, which is what decision 15
kept magnitude off the screen to avoid.

Measured against a real PostgreSQL with `001`-`020` applied and four fixture maps,
in two states: **as shipped**, with the seam empty, every map has a row, every
count is NULL and the outcome is the one-pass sentence on all four; and **as it
will be when #192 lands**, with the two seam views dropped and re-created over
fixture rows, which is exactly the change #192 makes. In that state the sum
identity and `papers_defining_pass_two <= papers_read_pass_two` both hold, the
linking count discriminates (two of four pass-two papers qualify, one is excluded
because its only relationship lands on a meaning holding nothing but pass-two
papers and one because it carries no relationship at all), a recorded build whose
second pass read nothing reports `0` beside an outcome naming why, a recorded
build with no outcome reads "not recorded" rather than the one-pass words, and a
pass number the view has never heard of lands in `papers_read_pass_unmarked` with
the sum still holding. 39 checks.

**Taken again on a real two-stage build** when `022` landed (#192), on a
throwaway PostgreSQL with `001`-`022` applied and the worker driven end to end
over a 9-paper fixture: the report row reads `passes_recorded 2`, the outcome
sentence, `seats 3`, `candidates 40`, `cleared 3`, `papers_read_pass_one 6`,
`papers_read_pass_two 3`, `papers_read_pass_unmarked 0`,
`papers_defining_pass_two 3`, `papers_linking_into_pass_one 2`, and one rank band
`{from 1, to 10, read 3, defining 3}`. Both identities hold on it. The same
figures were then read through the **compiled** `listMapReports` and rendered by
the **compiled** `/g/<id>/report` over that database, so the page's numbers are
the ones the shipped SQL selects.

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

**genealogies_current** (025, `025_map_versions.sql`, issue #206):
`SELECT * FROM genealogies WHERE is_current`. **It has no consumer yet** — #206
ships the shape alone so a defect in it is found on an unchanged system — and the
reads that will probe for it arrive with #208 and #209.

It is a view rather than a `WHERE` clause in four read functions because of the
deploy window (decision 31): Vercel deploys the app minutes before Render's
pre-deploy runs the migration, a missing *column* cannot be guarded, and a
missing *relation* is guarded by #92's `to_regclass` probe. The fallback is
correct rather than degraded — before `025` there is exactly one row per concept,
so an app that cannot find the view and reads `status = 'complete'` returns
precisely the same set, verified row for row on a fixture.

**The `SELECT *` is expanded at `CREATE` time and then frozen**, so a later
migration that adds a column to `genealogies` will not see it appear here: that
migration must `DROP VIEW genealogies_current` and recreate it, after its
`ALTER`. Verified by adding a column and reading the view's columns back. This is
the one view where `SELECT *` is deliberate, because it is a filter and not a
projection; the no-`SELECT *` rule above is about *consumers* of the report
views and is unchanged.

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

`worker/run.py`, ~580 lines, one process and one background thread (the
heartbeat, which also sweeps). Full walkthrough knowledge condensed:

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
  The RETURNING list carries `requested_by` and the papers the requester named
  (#198); the latter is selected as `to_jsonb(t) -> 'anchors'` rather than by
  name, because a rollback can leave this process one migration ahead of the
  schema and naming a column that is not there would make every queued build
  unclaimable with an `UndefinedColumn` on the poll. It costs one row's
  serialisation and yields NULL in exactly the two cases that mean the same thing
  to the build: no such column, and nobody named.
- **Execution.** Runs the pipeline stages as subprocesses (`python -u`,
  unbuffered) in order, passing `--corpus` to Stage B and, since #190, the
  same file to Stage C — the first stops a past trace's corpus being re-billed,
  the second stops it being clustered into this map. Subprocesses were
  chosen over imports so the pipeline stays CLI-first, a stage crash cannot
  kill the loop, and stdout is a parseable stream.
- **The first stage saves the map the build is about to replace** (issue #173).
  `snapshot_map.py --allow-missing --result-json` writes the genealogy row, its
  threads, its curatorial audit trail, its status, every edge and every definition
  the quotes come from, to `DATA_DIR/snapshots/<concept>_<pv>_<stamp>.json`. It is
  the first stage rather than the one before Stage C — which is where the
  destruction actually happens — because fetching and extraction rewrite the text
  on disk the live map's quotes were checked against, and because a snapshot that
  cannot be taken should cost the build nothing. Once per job: pass two re-clusters
  a map pass one has already overwritten. The worker reads the step's result file
  rather than its prose, prints the path and the counts into the progress feed, and
  **fails the job on either a non-zero exit or an unreadable result**, both of which
  happen while the map is untouched. **`data/genealogy_<concept>_<pv>.json` is
  therefore no longer the backup of record**; it is a deliverable, and it never held
  `streams`, `user_edits` or the definitions (incident 4 was recovered from it with
  the audit trail lost). `restore_snapshot.py` is the way back and since #173 it
  restores `status` too, without which a restored map stays invisible under #168's
  publish filter. Procedure in `docs/RUNBOOK.md`; retention is a documented sentence
  and not a mechanism, at under a megabyte per build.
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
- **The step ledger** (issue #47). The same parse, kept per step instead of
  folded into a running sum: when a stage ends, `StageRunner` writes its name,
  its pass, what it printed as its spend, how many cost lines it printed and how
  long it took to `DATA_DIR/stages_<slug>.json`, and a step near the end of the
  build (`record_spend.py`) puts that file into `map_build_stages`. No stage was
  taught to account for itself and no arithmetic was added, so the per-step
  figures sum to the same scrape `spend_usd` publishes. **`spend_usd` is null,
  never 0.0, for a step that printed no cost line**, which is the same rule one
  level down from the paragraph above and is enforced by a CHECK. The ledger is
  written after **every** step, including one that failed, so a build that dies
  mid-run still leaves what it had spent on disk; the database record is written
  only by a build that reached the recorder. The recorder is **second to last**,
  before the publish, because a step that exits nonzero fails the build and every
  other recording step does so while the map is still unpublished — the cost is
  that the record cannot contain the recorder or the publish after it, neither of
  which prints a cost line, so the money adds up where the wall clock is short by
  two steps. Both surfaces call it the time in the recorded steps for that reason.
- **Failure paths, all first-class, and split in two since #178.** The split is
  decided in one function, `classify_stage_exit(rc, shutting_down)`, which has
  no I/O so the branch can be exercised without a worker or a database.
  - *A defect fails.* A stage that exits nonzero while nobody asked the worker
    to stop: job marked `failed` with the message and the last 30 output lines
    (shown only to the owner in the UI). It is never retried automatically,
    because it has diagnostics attached and will fail the same way.
  - *An interruption requeues.* SIGTERM (every deploy sends one; decision 31
    makes every push a deploy) and Ctrl-C both raise into the same arm, which
    sets the row back to `approved` and exits inside Render's grace window.
    A flag set by the handler backs this up: the signal reaches the stage
    subprocess too, so if the child dies before the parent's exception lands,
    the stage's nonzero exit is still read as an interruption rather than a
    failure. Re-running is nearly free because every expensive stage caches.
  - *Sudden death requeues too, up to a cap.* A `running` row whose heartbeat
    is older than 10 minutes goes back to `approved` with
    `trace_requests.requeues` incremented and a progress message reading "run
    interrupted; restarting automatically (attempt N of 3)". At
    `MAX_AUTO_REQUEUES = 3` it fails, with an error saying it died repeatedly
    and that the worker's restart history is the place to look. The cap is what
    stops a crash-looping worker re-billing a job forever. The polite requeue
    above does not increment the counter: it needs a person to act and cannot
    loop on its own. Before this the sweep failed such a row outright, and a
    failed request has no way back into the queue (the app promotes only from
    `requested`), so the requester's only recovery was resubmitting by hand.
  - The sweep runs on every poll **and** from the heartbeat thread every ~30s,
    which matters because the main loop only polls when it is not running a
    job: a row abandoned by a dead instance used to sit visibly `running` with
    a frozen progress feed for as long as the surviving worker's build lasted.
    The heartbeat bumps its own row before sweeping, so it can never sweep the
    job it is beating for.
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
boundaries. Both strips share one answer to a click on the tab for the page you
are already on (`current-tab-click.ts`, issue #151): it scrolls to the top and
fetches nothing. The reasoning is with the other navigation costs, below.

**Only published maps are readable, and until issue #168 publication did not
exist as a state.** Nothing in the app filtered on `genealogies.status`:
`listGenealogies` selected every row and ordered by `updated_at`, `getGenealogy`
and `getMapRow` selected by id with no predicate, and no page added one. The row
is written by Stage C, roughly halfway through a build (`UPSERT_GENEALOGY` writes
`status = 'running'`), so **a half-built map — concept-states and no
relationships — was publicly listed and loadable on every build, for the whole
second half of it**, and had been for months. All three read functions in
`lib/genealogy.ts` now carry `status = 'complete'`, which is Stage E's own word
and a column that has existed since migration 001, so the refusal needed no
migration and cannot break during the minutes when the app is live against a
schema one migration behind (decision 31). It is an allow-list rather than
`status <> 'running'`: `pending`, `failed` and `aborted_spend_cap` are not maps
anybody should read either, and a status invented later is unpublished until
somebody decides otherwise.

**The refusal lives in the read functions and never in a page conditional**,
which is the control the two-stage build design (#184) names for this risk. The
design named two functions and there are three — `getMapRow` serves the map's
front door, the paper dossier, the thread page and the export — so guarding the
two named would have left the front door open. An unpublished map is therefore
indistinguishable from a map that does not exist on every surface those three
serve: `/` does not list it, `/g/<id>` redirects to the evidence view and that
404s, exactly as they already behave for an id nobody ever minted. There is no
exception for the owner, on the design's reasoning that "visible to them, not to
others" is a second visibility rule to keep in agreement with the first; a
requester watching their own build sees it in the live trace panel, which only
offers a link to the map once the run is complete.

**The fourth read path is `/g/<id>/report`, and it was closed by issue #194.**
It reads `map_report` through `listMapReports` in `lib/report.ts`, which carried
no predicate, so an unpublished map leaked there twice over: its own report
rendered, and it appeared with its half-built figures among "the other maps in
this system" on every *other* map's report, because one function answers both
questions the page asks. `listMapReports` now imports `PUBLISHED_STATUS` from
`lib/genealogy.ts` rather than respelling the word, and tests
`map_report.status`, which is `genealogies.status` selected straight through by
migration 016's view — the same column the other three read functions test, so
no migration was needed here either. The page needed no conditional for either
leak: it already 404s when the id is not in what the function returns, which is
how it has always handled an id nobody minted, and the reference-point rows are
the rest of that same array. The sample size the page prints ("N of the M maps
in this system") therefore now counts published maps, which is what it should
always have meant. `pipeline/map_report.py` is deliberately unchanged and still
reads every map with each map's status in its own header: it is the Operator's
instrument, seeing a mid-build map is most of its job, and it diverges the same
way `check_map.py` does. The two can still not disagree about a figure for a map
they both show.

Measured against a real PostgreSQL with 001 to 021 applied, holding one fixture
map per status, driving the compiled read functions and the compiled route: a
`complete` map is listed and returned by both single-map functions and its
report renders; `running`, `pending`, `failed` and `aborted_spend_cap` are absent
from every list and null from both single-map functions, and their reports throw
the same `NEXT_HTTP_ERROR_FALLBACK;404` as an id nobody ever minted, which was
the control. The `running` fixture is in-progress-shaped: Stage C's
concept-states, no relationships and no threads. On the same fixtures before the
change, both published maps' reports named all four unpublished maps as
reference points and printed the sample size as 6.

**Live on the deploy, 2026-08-09, commit `463728f`.** All four maps' reports
render, each one's comparison rows name exactly the other three, and all four
print "of the 4 maps in this system". **CLS is 0.00000 with zero layout-shift
entries and page height 6706 px on all four, unchanged**: the same measurement
was taken on the same four URLs immediately before the push and after the deploy
(headless Chrome 1280x900, cache off, `PerformanceObserver` on `layout-shift`
with `hadRecentInput` excluded, `networkidle0` then waiting for a string only the
assembled page emits, then 2.5 s of quiet). Probing ids 1 to 20 and 999, exactly
10, 13, 17 and 18 serve a report and every other id 404s — and all fifteen answer
HTTP 200, because this route's loading boundary flushes the shell before the page
runs, so the verdict is read from the digest in the RSC stream and never from the
status line (#159). **The refusal itself cannot be observed in production while
every map is `complete`**, which is the state today: the live reading says
nothing regressed, and the per-status behaviour is only ever provable against
fixtures, which is why it was taken there.

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
  **The form takes up to three papers a map should not miss** (issue #198), by
  arXiv id, optional, shown to a signed-in reader only because it is a field only
  they can submit. Its hint is attached to the control rather than to the page,
  unlike the arXiv-only caveat above it, and says the four things the design's
  first integrity condition requires: named papers are read and checked like any
  other, naming one does not make it matter, it earns a place on the map only
  through the papers it actually cites, and if it turns out not to define the
  term it is counted among the papers that do not. A successful submit echoes the
  count and the normalised ids back, because the field takes free text and folds
  duplicates. The queue rows deliberately do not show the named ids: the
  disclosure surface is the report, and `listTraceRequests` naming a new column
  would 500 `/trace` and `/api/traces` during the deploy window for a repeat of
  what the reader was already told at submit.
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
  **The timeline is ruled off at both ends of what the map read** (issue #44,
  `[Q7]`). The Product Owner opened the first physics map, `/g/17` (dark
  energy), on 2026-08-08, saw the dots stop at 2011 and asked whether the tool
  was claiming nothing had been added to the topic since. It was not, and it had
  no way of saying so: the right-hand end of a timeline reads as the end of the
  story unless the page says otherwise. Two dashed ink-faint rules now mark the
  oldest and the newest **defining** paper in the map, labelled "this map's
  reading starts · 1988" and "this map's reading stops · 2016", and a mono
  ink-faint caption under the canvas says what they mean: "Marked at both ends of
  the timeline: the oldest and the newest paper in this map that defines the
  term, 1988 and 2016. That is where this map's reading stops, not where the
  term's story does. Work outside those years may exist, and this map has not
  read it." The claim is about the map and never about the field. A map whose
  reading is one year wide gets one rule; a map whose years cannot be read gets
  neither rule nor sentence, because a horizon nobody can place is worse than no
  horizon. **The axis spans the reading, not the dots**: on `/g/17` the newest
  drawn paper is 2011 and the newest read is 2016, so the domain widens to 2016
  and the five empty years are the picture of the gap. This is a stopgap for the
  under-sampling of recent years (`[F5]`, issue #33), not a fix for it.
  The two years are `year_min`/`year_max` from `map_report`, the same expression
  the report page prints as "earliest year" and "latest year", so the two pages
  cannot disagree about one map; they ride on the statement that already counted
  the map's relationships, so `getInfluenceMap` is still four statements in three
  rounds. That statement `LEFT JOIN`s the view from a one-row anchor and is
  wrapped in a fallback rather than guarded by a `to_regclass` probe: the probe
  costs a round trip to ask about a name while the query resolves that name
  against a search path (issue #92), and the fallback asks the real question and
  answers with the count alone, logging the driver's message, if the view is not
  there. `readingWindowSentence` and `readingMarks` live in `lib/reading-window.ts`
  and not in `lib/genealogy.ts`, because `InfluenceMap` is a client component: a
  value import from `lib/genealogy` puts `lib/db.ts` in the browser bundle, where
  its module-level `throw` on a missing `DATABASE_URL` runs on load. Measured on
  the build that made that mistake: `/g/[id]` first load 154 kB with
  "DATABASE_URL is not set" in `.next/static/chunks/app/g/[id]/page-*.js`, 110 kB
  and no occurrences after the move.
  **Live on the deploy** (Chrome at 1440x1000, hard load, cache off): `/g/17`
  marks 1988 and 2016, `/g/13` 2012 and 2021, `/g/10` 2011 and 2023, each rule
  landing on the same x the axis prints that year at, to the pixel, and `/g/17`'s
  axis now labels up to 2016 where it stopped at 2010 before. **CLS is 0.0000
  with zero layout-shift entries on all three**, the same as the reading taken on
  the previous deploy: the caption is server-rendered inside the streamed
  content, so nothing arrives late to push anything down. The canvas still
  hydrates (the side panel answers a hover); the only failing request on the page
  is `/favicon.ico`, which is issue #153 and predates this.
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
  workbench layer. Two sections: the ranked paper spine ("Which papers shaped
  X"), then every typed relationship, **grouped by the earlier paper of each
  pair** (issue #146). Evidence panels carry both quotes, the verification stamp
  and the confidence; workbench edit controls, the audit trail and the danger
  zone are owner-only. (`computeFamilies()` in `lib/genealogy.ts` is unused by
  any page; the citation-connected families this entry described until #146 were
  not on the shipped page.)
  **Section 2 is a partition, anchored on the paper pair** (issue #146). Before
  it, one element on the whole 36 806 px page carried an `id`, so nothing on the
  map, on a thread page or in a link a reader was sent could point at the row
  they came to check.
  - `lib/anchors.ts` formats every anchor and is the only place that does:
    `p-1706.03762` for a paper's group, `r-1409.0473-1706.03762` for one
    relationship, with `/` slugged to `_` so old-style ids are one token and a
    second edge on the same pair suffixed `-2`. **The key is the paper pair and
    never `edges.id`**: `stage_d_edges.py` rebuilds a map with `DELETE FROM
    edges WHERE genealogy_id=…` then fresh INSERTs against a `BIGSERIAL`, while
    the `genealogies` row and therefore the URL survive, so a database-id
    fragment would silently point at a *different relationship in the same map*
    after a rebuild. An edge whose paper row is gone (#79) gets no anchor at all
    and the row says why; there is deliberately no fallback, because one
    fallback manufactures exactly that failure.
  - Each edge lands in exactly one group, keyed on its source, with a final
    group for edges whose source row is missing, so the count in the heading and
    the rows on the page are the same array. A group also exists for a paper
    that is only ever the later one; a wrapped line of links, "Where it appears
    as the later paper", is what stops it being a dead end, and it carries links
    only, never a second copy of the evidence.
  - **Each paper's own passage renders once at the group head, outside any
    `<details>`.** That is the point of the regrouping rather than a nicety:
    Firefox and Safari cannot find text inside a closed `<details>`, and every
    quote on this page lived in one, so find-in-page — the page's only
    navigation before this ticket — could not reach its most important words.
    The stamp there is `stampOf` over the definition's two digests and the
    paper's, the same resolver `/g/[id]/p/[arxiv]` and `/g/[id]/river/[sid]`
    use for the same string.
  - A jump index heads the section: one line of type counts, then every paper
    group as `year · title (n)` in a multi-column list. **The type counts are
    stated and are not jump links**, a deliberate deviation from the ticket:
    grouped by paper, a type is not contiguous anywhere on the page, so a "jump
    to extends" link would land on an arbitrary row and imply a block that does
    not exist.
  - **Both facing quote-cards stay inside every relationship** (product rule 1
    and the owner-blessed evidence panel), and nothing is paginated,
    virtualised or removed from the DOM. Only the summary changed: it no longer
    repeats the earlier paper, which the group head names three lines above.
  - `evidence/loading.tsx` was reshaped to the same silhouette (jump index,
    group head with a passage, collapsed rows), because the skeleton and the
    page having different shapes is what would bring back the CLS #140 measured
    at 0.000 here.
  - **Three pages link in**, which is the half that serves the sceptic's actual
    task: a thread page's paper and the map panel's selected paper both point at
    `…/evidence#p-<arxiv>`, and each typed link on a dossier points at
    `…/evidence#r-<pair>`. Every one of those strings is `lib/anchors.ts` over
    ids the page already holds, so none of them costs a query. Two deviations,
    both deliberate. The map panel links at paper level rather than per drawn
    edge, because that panel tallies a paper's links by type instead of listing
    them and turning the tally into a list is a change to the panel, not a link.
    And the thread page shows its link only for a paper that has a group to land
    on: section 2 groups relationships, so a paper in none has no place there,
    and two of six links on `/g/13/river/s0` missed before that was noticed.
    `in_evidence` is an `EXISTS` over the map's edges riding on the statement
    that page already ran, so it costs no round trip; it was executed against a
    throwaway PostgreSQL built from the project's migrations, including the two
    cases that could have been wrong — a paper that is only ever a target counts,
    and a paper whose only edge belongs to a different map does not.
  - Arrival is `app/app/hash-target.tsx` (issue #150), mounted **by this page**
    beside its groups. This is the longest streamed route in the product, so the
    browser applies the fragment seconds before any anchor exists and its own
    hash scroll cannot work; the component's mount is the event "the rows are
    here now". `scroll-margin-top` on both kinds of target is set here.
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
  views and migration 017's third by `lib/report.ts` and computed nowhere else,
  so this page and
  `pipeline/map_report.py` cannot disagree about a figure they both print (which
  is no longer every figure: see the subset invariant below).
  **Published maps only, as of issue #194**, and both the map named in the URL
  and the reference-point maps beside it come from the one filtered read: an
  unpublished map 404s here exactly as it does on the other three surfaces, and
  it is named on nobody else's report. The refusal and its reasoning are above
  in this section, under "only published maps are readable". Sections: how much
  was read, evidence (the three stamp states for definitions and for
  relationships), the same counts split by source, shape, when the papers were
  written with a per-year histogram, the run, and a closing list of the three
  things the page cannot tell you.
  **How much was read ends with the papers a person named** (issue #198),
  because the difference between a paper this system went and found and a paper
  somebody handed it belongs within one glance of the totals. Decision 16 keeps
  kinds of claim in separate tiers and has so far governed quotes; this extends
  the same discipline to corpus membership. Three figures — how many were named
  and how many of those were read, how many of the read ones define the term, how
  many carry a relationship — then a table naming every id, with `read`,
  `defines the term` and `relationships` per row and a link to the paper on
  arXiv. **A map nobody named a paper for says so in one sentence rather than
  drawing an empty block**, and that sentence is a measurement: zero here is a
  real zero on every map, unlike the pass figures beside it. The only absent case
  is `map_report_anchors` missing, which means the migration has not landed on
  this deployment yet, and the block then says the page could not count rather
  than claiming nobody was named. The actor is recorded and is **not** on this
  page: the sentence a reader is owed is about "the person who requested it", and
  a login would travel to every browser to support a sentence that does not use
  it. `pipeline/map_report.py` prints it, resolved with decision 18's precedence.
  **Shape ends with the mix of kinds of link** (issue #162), the figure that says
  whether the taxonomy described this literature at all. It is a small table
  rather than six more figures — the page's history is a fight against rendering
  everything at one weight, and six full rows each with an explainer, a note and
  a comparison line would have added a third of a screen to say one thing. Rows
  are the kinds in the view's order, columns are `kind`, `what it means`, `this
  map`, then one column per other map in the system, each cell a count and its
  share. The gloss column reads `EDGE_MEANING` in `lib/genealogy.ts`, which
  `/about` and the evidence page (the edge label and the reclassify dropdown)
  also read, so it gains no new home here. It is not the only home: the map at
  `/g/[id]` builds its legend from a shorter `GLOSS` of its own ("built on",
  "pushed back", "specialised"), which predates this and is untouched by it, so a
  reader moving between the map and the report meets two wordings of the same six
  kinds. A kind whose
  `taxonomy_rank` is NULL is labelled "not one of the six kinds this tool uses"
  from the view rather than inferred from a missing gloss. The paragraph above
  the table names the population and states the identity a reader can check
  ("Every one of this map's N typed relationships ... these add up to that
  total"), which is the falsifier for the whole figure. Nothing is graded, no
  mix is expected and no share is marked (decisions 24 and 25). Two states print
  words instead of the table: a map with no relationships says so, and a
  deployment whose schema is one migration behind says "not counted on this page
  at the moment, which is this page's reach and not a fact about the map".
  **That last state is the #92 fallback, applied where it had been declined.**
  `RUNBOOK.md` leads the 016 entry with migration-before-deploy precisely because
  this page had no fallback and none would have been honest for its core figures;
  017 is different, because the app tolerating its absence costs one figure rather
  than fabricating any, and CLAUDE.md requires the app to tolerate a schema one
  migration behind. `lib/report.ts` probes `to_regclass('map_report_by_type')`
  in its own statement, **unqualified**, which is the correction #92 earned: that
  probe schema-qualifies while its query does not, so any schema arrangement it
  does not name reads as absence. The probe's answer is a snapshot and the race
  is a known residue. `types: null` in `MapReport` means the read did not happen
  and is deliberately not an empty array, which would mean a map with no kinds of
  link; the view never says that, since it emits six rows for a map with no
  relationships.
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
  **The years chart draws two series, and three figures below it say what the
  map read** (issue #182, designing #33/F5, migration
  `019_map_report_read_years.sql`). Everything about years on this page counted
  the papers that *define* the term, so "the newest paper is 2016" could mean
  either that nothing recent was ever selected or that recent papers were read
  and none of them defined the term, which need opposite fixes. Now the papers
  read set each column's height and the papers that define the term are drawn
  over them from the same baseline, so **the exposed part of a column is exactly
  the papers read that year that did not define the term**; the number above a
  column is the papers read that year, and a key under the chart title names
  both series and says so. The three figures are `newest paper read` (never
  earlier than `latest year`, and the page says why), `papers read from the last
  five years` with the window printed beside the count as "written 2022 to 2026"
  rather than the word "recent", and `of those, papers that define the term`,
  printed as "N of M" rather than as a percentage. **The middle one is labelled
  as instrumentation in its own explainer**: it counts papers in a window, so
  changing how papers are chosen moves it by construction and it cannot report
  failure, and the copy says it "can say what this map read and it cannot say
  whether the reading was any good". No threshold, no colour and no pass mark,
  as everywhere else here. On a deployment one migration behind, `reading` is
  null: the chart falls back to the single series it drew before, the key does
  not render, the three figures are replaced by one sentence, and nothing 500s —
  the #92 fallback again, with an unqualified `to_regclass` probe.
  Verified by rendering the shipped page against three data states (both series,
  `reading` null, and a map with no years at all): the bars scale to the read
  peak with the gap drawn where the two series differ and no inner bar where a
  year has no defining paper, the key and the three rows appear and disappear
  with the state, and the comparison lines carry the other maps' figures.
  **Live on the deploy, all four maps, 2026-08-08** — this is the "before" half
  of #183's reading and was taken while /g/17 still is the before. `/g/13`
  (attention): 156 papers read, 88 define the term, newest defining 2021, newest
  read 2021, 0 papers written 2022 to 2026. `/g/10` (embedding): 187 read, 138
  define, 2023 and 2023, 6 in the window of which 5 define. `/g/17` (dark
  energy): 145 read, 100 define, 2016 and 2016, 0 in the window. `/g/18`
  (instrumental variable): 145 read, 96 define, 2025 and 2025, 32 in the window
  of which 23 define. **`newest paper read` equals `latest year` on every one of
  the four**, which satisfies the ticket's falsifier (it may never be earlier)
  and says something sharper than the falsifier asked for: no map has yet read a
  paper newer than the newest one it found defining the term, so /g/17's 2016
  ceiling is a result of what was selected and not of what the reading found.
  That is the discrimination this figure exists to make, and it is the reading
  F5 will be judged against. **CLS is 0.0000 with zero layout-shift entries on
  all four report pages** (Chrome 1440x1000, cache off, hard load), unchanged by
  the key and the three added rows: everything in the section is server-rendered
  in the streamed content, so nothing arrives late to push anything down.
  **A block at the foot of that section says what each pass of the build read**
  (issue #193, instrumenting #184, migration `020_map_report_passes.sql`). It sits
  there rather than in a section of its own because it answers the question the
  window figures above it raise: a map can read recent work because somebody
  reserved seats for it before the map existed, or because the finished map went
  looking, and those are different claims that belong within one glance of each
  other. Set like the "kinds of link" block in Shape — its own quiet label, its own
  paragraph, its own note — it renders in one of three states. On a deployment one
  migration behind it says how many passes this map was built in "is not counted
  on this page at the moment", the #92 fallback again with an unqualified
  `to_regclass` probe. **On every map that exists today it renders one sentence**:
  "This map was built in one pass: nothing in its record marks a paper as read in
  a second one", followed by how many of the maps in this system were built in
  more than one, counted from the rows rather than written down (#89) so it moves
  on its own the day a two-stage map lands. **No figure row is drawn at all in that
  state and no zero is printed for one**, because nothing records a paper's pass
  until #192 ships and a zero would report a second pass that never ran. On a
  two-stage map it draws five rows: `why the second pass ended`; `papers read in
  the second pass`, printed "N of M" with the seats beside it and labelled
  instrumentation in #182's own words, because changing how papers are chosen
  moves it by construction; `second-pass papers that define the term`, which Stage
  B can still answer no to; `second-pass papers linked to a first-pass meaning`,
  labelled the tool's reading in the same words the page uses for shape and
  explicitly not the claim that the idea moved recently; and `recent papers that
  cite this map`, with how many cleared both signals, so a second pass that read
  nothing can say whether there was nothing to read or no budget left. A sixth,
  `papers the record puts in neither pass`, renders only when it is not zero, the
  same treatment "meanings that could not be read" gets. The two labels that would
  have collided with #182's window rows were renamed rather than shortened, so no
  two rows in the section read alike.
  Verified by rendering the shipped page against five data states (one migration
  behind, the shipped one-pass state, a two-stage map, a one-pass map sitting
  beside two-stage ones, and exactly one two-stage map so the sentence's singular
  is rendered rather than reasoned about): 21 checks, including that the
  migration-behind state never claims the map was built in one pass and never
  reaches the view its probe said was absent.
  **Live on the deploy, all four maps, 2026-08-09.** Every one reads "This map
  was built in one pass: nothing in its record marks a paper as read in a second
  one. 0 of the 4 maps in this system were built in more than one pass", and no
  pass figure row is drawn on any of them, which is the whole of what this
  instrument can say until #192 records a pass. The Render pre-deploy had applied
  `020` before the first request reached the new page, so the migration-behind
  branch was not observed live and was taken against fabricated data instead —
  that state is only ever provable at build time, which is why it was rendered
  deliberately. **CLS is 0.00000 with zero layout-shift entries on all four report
  pages, unchanged**: the same measurement was taken on the same four URLs
  immediately before the push and after the deploy (headless Chrome 1280x900,
  `PerformanceObserver` on `layout-shift` with `hadRecentInput` excluded,
  `networkidle0` then waiting for a string only the assembled page emits, then
  2.5 s of quiet; waiting on `networkidle0` alone measures the streaming skeleton
  and says nothing). Page height went from 6407 px to 6706 px on every one of the
  four: the block is server-rendered inside the streamed content, so it lengthens
  the page without anything arriving late to push something down.
  **The run section opens its own total up, step by step** (issue #47, migration
  `024_build_stage_spend.sql`). It sits under "what the run cost" and inside the
  same `owner` gate that figure carries, and only below it: it is that number's
  breakdown, so a reader meeting it first would be reading parts of a whole they
  had not been shown. Three figures — `what the recorded steps spent`, `what the
  most expensive step cost` with its share and the step named beside it, and
  `steps that reported no cost line` printed "N of M" — then the table itself, one
  row per step in the order it ran, with the step's number, its name in the feed's
  own words, its pass, its cost and its time, and a footer subtotalling the first
  pass, the second pass and the steps in neither. **A step that printed no cost
  line reads "no cost line" in quiet italic and never US$0.00**, which is the same
  rule the page's money formatter carries one level up (#87): most steps of a
  build genuinely spend nothing and a step that stopped reporting looks identical,
  and neither is a measured zero. A step that did print `$0.0000` renders US$0.00,
  because that one is. A sentence under the table says the times cover the
  recorded steps and stop two short of the run, since the step that writes the
  record cannot time itself or the publish after it. **A map with no step record
  says so in one sentence and draws nothing**, with the count of maps that have
  one taken from the rows (#89); on a deployment one migration behind it says the
  spend per step "is not counted on this page at the moment", the #92 fallback
  again with an unqualified `to_regclass` probe. The per-pass subtotals and the
  request id are command-only, the subset invariant below.
  Verified by rendering the shipped page over a real PostgreSQL holding a fixture
  two-pass build, through the compiled `listMapReports` with the driver stubbed to
  reassemble its tagged template into text and `$n` and execute it, so the SQL
  tested is the SQL sent: 27 checks across four states — the recorded map seen by
  the owner, the same map seen by a signed-out reader (the whole block absent,
  with the rest of the page intact), a map with no record, and the view dropped
  under a live page. **No two-stage map exists yet**, so the first real reading of
  these figures will be #183's rebuild, and the fixture's own times are a stub's
  and not a measurement of anything.
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
- `/terms` : the terms of use (issue #160). Fixed prose, no data, prerendered
  (`○`) like its two neighbours. Six sections: what Lineage is, whose words the
  papers and quotes are, what signing in stores and enables, no warranty and the
  liability limitation, the code's license as a separate instrument, and that the
  terms can change. It carries a single `VERSION_DATE` constant, printed in the
  header and again in the changes section, because a terms page whose date
  disagrees with itself is worse than one with no date at all.
  **The two guarantees are restated here in the settled words, not new ones**,
  and drawn as the same left-bordered cards `/about`'s trust tiers use so a
  reader recognises them as one claim: the shape of a map is "the tool's reading"
  (product rule 3), and a verified quote "was found word for word in the text
  this system pulled out of the paper" (rule 2 and the wording law of #129/#135,
  recorded in `app/lib/stamp.ts`). A terms page is the last surface that may
  state the promise more strongly than the product supports; the page's own
  comment says so, and says the page moves if the wording law moves.
  **It sits in the tab strip rather than a footer**, which is what #160 asked
  for, because the site has no footer and the strip is where `/about` and
  `/roadmap` are linked from. It is last in `nav.tsx`'s `TABS`, which is the
  weight it should carry.
- `/api/traces` : read-only JSON: `{ now, rows }`. `now` is Postgres `now()`;
  the client computes its clock skew from it and measures elapsed time and
  heartbeat staleness against database time, never the viewer's clock.
- `/api/viewer` : read-only JSON: `{ login, owner }`, for the header's sign-in
  control alone (issue #145). It takes no input of any kind, so there is nothing
  to ask it about anyone else, and it answers only about the session its own
  caller presented. `owner` is a boolean and `OWNER_GITHUB_LOGIN` is never
  echoed: the client learns whether it is the curator, not who the curator is.
  `force-dynamic` and `Cache-Control: no-store, private`, because the response is
  one reader's identity and the worst failure available is serving it to another.
  It grants nothing; `requireOwner()` inside every mutating action is still the
  only lock.
- `/api/auth/*` : Auth.js GitHub OAuth.

**The `[id]` in a map URL is parsed once, before it can reach a query**
(`lib/map-id.ts`, issue #159, `[B33]`). Every route under `/g/[id]` used to
write `Number(id)` straight into its SQL and guard only the result with
`if (!g) notFound()`. That guards a map that is absent and nothing else:
`Number("abc")` is NaN, `Number("13.5")` is a float, `Number("1e999")` is
Infinity and `Number("9999999999999999999999")` is past what the driver can bind
to a bigint column, so each of those made the **query throw** and no null ever
existed for the guard to catch. There was no error boundary anywhere under
`app/`, so the reader got Next's global-error shell, unstyled, reading
"Application error: a server-side exception has occurred" with a digest;
`/g/abc/export`, a route handler with no boundary at all, answered a download
with a bare HTTP 500 and an empty body. Marvin found it on the live site on
2026-08-08 across `/g/[id]`, `/evidence`, `/river/[sid]`, `/p/[arxiv]` and
`/export`; `/report` survived only because it selects every map and matches in
memory, so nothing was bound to a column.

`parseMapId(raw)` returns a number or null: digits and nothing else, at least 1,
no larger than `Number.MAX_SAFE_INTEGER`. That is what `genealogies.id` can hold
(BIGSERIAL, so positive) intersected with what JavaScript can carry without
rounding — `Number("9007199254740993")` is 9007199254740992, a **different map**
than the URL names. Everything `Number()` used to accept quietly is refused:
sign, exponent, `0x`, `_`, surrounding space, each of which is a second URL for a
map that already has one. Pages call `notFound()` on null, the export handler
returns its own 404 with a body, and `/report` parses too, so one rule covers the
whole subtree rather than one route being polite for a reason nobody can find.

**Parsed rather than caught, deliberately.** A `try/catch` per route would fix
the same symptom, but it cannot tell a malformed id from Postgres being
unreachable, and it would report an outage as "no such map" — a silent 404 on a
map that exists is a worse defect than the one being fixed. It also would not
reach the export handler, which has no `notFound()` boundary to fall into. Held
by the harness below: with the data layer replaced by one that throws
`Error connecting to database: fetch failed`, all six routes on a valid id still
raise rather than 404.

**`app/error.tsx` is the app's only error boundary**, added with it. It sits at
the root of `app/` rather than under `g/[id]/`, so the front door and `/trace`
get it too; the build binds it to all eleven page routes and, as expected, to no
route handler (`grep error.tsx .next/server/app/**/page.js`). It says a page
could not be loaded, that the failure is ours and that nothing was lost, and
prints the digest as the reference to quote. **It never says the map is
missing** — that would be the tool lying about its own state on behalf of a map
that exists, which is exactly what parsing the id first is there to avoid. It
cannot catch a throw in the root layout; nothing there does I/O, and that would
need `global-error.tsx` carrying its own `<html>`.

Checked before the push, since the fix is a negative and the routes cannot be
run against the database from here. `parseMapId` on 32 constructed strings, the
ticket's seven crashers and its four controls among them, each printed beside
what `Number()` would have given: 32/32 as intended. Then the five page
components and the export handler were compiled and **called directly against a
data layer that refuses to answer** — every function records its call and returns
null, so "the query was never reached" is an assertion rather than an
inference. All seven malformed ids: `NEXT_HTTP_ERROR_FALLBACK;404` on the five
pages and HTTP 404 with a body on `/export`, with **zero** calls recorded on all
36 combinations. Controls: `999999` still reaches the database on every route and
still 404s on absence, and `/g/999999` still redirects to its evidence page
first.

**One control moved, and it is the redirect rather than the status.** `/g/-1`,
`/g/13e1` and `/g/0x10` used to be coerced to 130, 16 and -1, queried, found
absent and 404'd; they now 404 without a query, and on `/g/[id]` that means the
reader lands on the 404 instead of being redirected to `/g/-1/evidence` and
404ing there. Same page, one round trip fewer. `/g/999999`, the control the
ticket names, is untouched in both respects.

**The HTTP status cannot answer this question and did not before the fix
either.** Every route under a map has a `loading.tsx`, so the shell is flushed
with a 200 long before the page runs, and both the crash and the clean 404
arrived as `200`. The verdict is in the RSC stream: `NEXT_HTTP_ERROR_FALLBACK;404`
for a `notFound()`, `NEXT_REDIRECT;replace` for a redirect, and a bare numeric digest for
a throw. `/g/[id]/export` is the one route that carries its verdict in the status
line, because a route handler streams nothing. Anyone re-testing B33 by status
code alone will see 200s and conclude the site is fine.

**After, on the live deploy (2026-08-08), read that way.** All seven malformed
ids × five page routes: `404` in every one of the 35, against 35 numeric digests
before. `/g/abc` is 17,955 bytes carrying the site header and "This page could
not be found", with no digest anywhere in it. `/g/abc/export` is `HTTP/1.1 404`,
`text/plain`, body `No map with that id.`, against a 500 with `Content-Length: 0`
before. `/g/abc/river` still 307s to `/g/abc`, which now 404s instead of
crashing. Controls: `/g/999999` still redirects to its evidence page and 404s
there, `/g/999999/export` still answers `No map, or no threads generated for it
yet.`, and `/g/13` and its four sub-routes render at 76 KB, 6.08 MB, 137 KB,
106 KB and 176 KB with the export unchanged at 59,900 bytes. The boundary itself
was rendered through `react-dom/server` rather than triggered, since nothing on
the live site can be made to fail on demand: both branches (digest and no digest)
draw from the palette tokens only, and neither says the map is missing.

**Server Actions** (`lib/actions.ts`, `lib/trace-actions.ts`): renameNode,
mergeNode, deleteNode, reclassifyEdge, deleteEdge, deleteGenealogy,
requestTrace, approveTrace, rejectTrace. Every one authorises itself on its
first line (section 7). requestTrace normalises and whitelists the concept
(2..60 chars, letters/digits/spaces/hyphens; the string becomes a subprocess
argument and a filename), refuses already-traced concepts for everyone
(re-running Stage C would overwrite curated nodes), applies non-owner quotas
(1 open request, 3 per week), and inserts owner submissions directly as
`approved`. Since #198 it also parses the papers a requester named: at most
three arXiv ids, normalised to the one spelling the pipeline stores, and **a
malformed one refuses the whole submission with the id named** rather than being
dropped, because a silently discarded id is a requester believing their paper is
in a map that does not contain it. It is shape validation and not an existence
check, deliberately: `corpus_select.py` resolves every named id against OpenAlex
before the build spends anything and refuses the run by name, and an id can be
well-formed, resolve at request time and still be unfindable when the build runs,
so a check here would be a second answer to a question the later one has to
settle anyway. The insert names the `anchors` column even when nobody was named,
so "offered and declined" is stored as the empty array; a `42703` from the
minutes when Vercel is ahead of Render's migration is **caught rather than probed
for** and the two arms differ — nobody named, so nothing is lost and the request
queues in the old shape; papers named, so the request is refused with nothing
submitted, because queueing it would build a map missing the papers the requester
asked for and say nothing about it. deleteGenealogy requires the concept name typed back and verifies
it server-side, nulls `trace_requests.genealogy_id` (trace history outlives
the map), and lets edges cascade; papers and definitions survive, so deletion
re-opens the concept for cheap re-tracing.

**Every route that reads data is dynamic, so it pays a round trip, and the
reader is told the click landed** (issue #140; `/about` and `/roadmap` are the
exception since #145 and are prerendered, and `/terms` joined them on the same
terms in #160). Nothing under `/g/[id]` is prerendered:
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
the app dynamic. That cause is issue #145, fixed below; it removes the wait
rather than covering it, and nothing here anticipated it.

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

**After, measured on the live deploy**, headless Chrome at 1440×900 from Sydney,
real clicks on the strip, time from click until anything at all changes on
screen — all eighteen sideways navigations, every tab from every one of the five
sections:

| from | The map | Threads | The evidence | What this map is made of |
|---|---|---|---|---|
| the map (`/g/13`) | *current* | *anchor, same page* | **7 ms** (was 349) | **7 ms** (was 325) |
| the evidence | 12 ms | 11 ms | *current* | 13 ms |
| the report | 6 ms | 9 ms | 7 ms | *current* |
| a thread (`river/s0`) | 6 ms | 6 ms | **7 ms** (was no link at all) | **7 ms** (was no link at all) |
| a dossier (`p/1706.03762`) | 7 ms | 7 ms | 7 ms | 8 ms |

Six to thirteen milliseconds, against a falsification line of 100 ms. **And the
strip is the same DOM node before and after every one of those clicks** — the
run marks the `<nav>` with a `data-mark` the React tree knows nothing about and
re-reads it after the navigation, so a reused layout and a remounted one are
told apart by something other than how it looks. The content swaps inside the
map frame, the strip never re-skeletons, and the active tab is correct on
arrival in all eighteen.

**TTFB under a map did not move**, which is the check that says the layout never
started fetching (median of 9 warm brotli requests, same vantage and method as
the table above, so the columns are comparable): `/g/13` **0.33 s**,
`/g/13/evidence` 0.33, `/g/13/report` 0.32, `/g/13/river/s0` 0.32, `river/s3`
0.32, `/g/13/p/1706.03762` 0.32, `/g/10` 0.31, `/g/10/evidence` 0.32, against
0.34–0.36 recorded after #140 and a falsification line of 0.5 s. Complete times
are unmoved too (evidence 3.32 s against 3.34, the report 1.00 against 1.00),
and `/` is the untouched control at 0.32 / 0.75. **CLS is 0.0000 on a hard load
of all five routes**; the strip is server-rendered, so there is nothing to
shift, and `curl` confirms all four hrefs in the served HTML of all five, with
no tab marked current on the dossier.

**The prefetch cost is +2 route prefetches per map page view, not the +4 the
design budgeted.** Counted as `?_rsc=` resource entries: "Threads" points at
`/g/13`, the same route as "The map", so the two share one prefetch, and the
router does not prefetch the route it is already on. A thread page went from one
outbound prefetch to three, the evidence page from none in the viewport to two.

**One check from the design failed and was not fixed in #143: the `#threads`
anchor did not scroll.** It is fixed under #150, below; the diagnosis is kept
here because it is what the fix is built on. Clicking Threads from the evidence page or a thread page
landed on `/g/13#threads` with the right page and a scroll offset of 150 px — the
thread list is at 884 and stayed there. The cause is not the anchor: it is that `/g/13`
streams behind a `loading.tsx`, so at the moment the router applies the hash the
`#threads` element does not exist yet, and nothing re-scrolls when the content
arrives 4 s later. A **hard load** of `/g/13#threads` did not scroll either
(offset 0), which is what shows this belongs to the streaming boundary rather
than to the strip. Where the content is already present — clicking Threads while
on `/g/13` — it scrolled correctly and the list landed on screen. So #143 by
itself removed the *click* cost everywhere and the *scroll hunt* only for a
reader already on the map. Filed as issue #150 rather than improvised inside
#143, because any fix is client-side scroll restoration touching the same
anchors #146 is designing a scheme for, and because it is general: every in-page
anchor into a route with a `loading.tsx` has it.

**A hash anchor into a streamed route scrolls, and the mechanism is the mount**
(issue #150). `app/app/hash-target.tsx` is a client component of about twenty
lines with no props. On mount, and on `hashchange`, it reads `location.hash`,
decodes it, and looks the id up. Absent id: it does nothing. Found: it opens
every ancestor `<details>` and the element itself if it is one, then
`scrollIntoView({ behavior: "instant" })`.

The whole design is in **who mounts it**. A fragment is applied at a moment the
*document* defines — parse, load, or the router's navigation commit — while on a
streamed route the target's existence is defined by the *stream*. Those two
clocks are unrelated, which is why the browser's own hash scroll cannot be right
here and why a hard load failed identically to a soft one. This component is
mounted by **the page that renders the targets**, so its own mount *is* the
event "the targets now exist", with nothing inferred and nothing timed. That is
why there is no `MutationObserver`, no poll, no timeout and no retry count:
each of those infers an event that can be observed directly, and none works
without a deadline, which is a number nobody can measure on a page whose arrival
time is a network variable.

**It must never be mounted by a layout**, or by any wrapper above the streaming
boundary — anything already on screen while the reader waits fires early by
construction, which is the bug as filed. `g/[id]/layout.tsx` therefore stays free
of data *and* of page-specific behaviour, which is the same rule the layout
already carries for fetching, pointed one step further. If a future page renders
its targets inside a nested `<Suspense>`, the component goes inside that boundary
with them: a sibling of the content, never an ancestor of the wait.

It is mounted in exactly two places: `g/[id]/page.tsx`, beside the thread-list
section, which is #150, and — since #146 — `g/[id]/evidence/page.tsx`, beside the
paper groups, which is where it matters most and which withdrew its own
`open-target.tsx` in favour of this one. A page with no anchor targets does not
mount it, and no layout does. The evidence page's client bundle went from 177 B
to 454 B with the mount, which is the same fact from the other side.

**Verified from the deployed artefact, not from the source.** Counting the
component's `hashchange` listener across the client chunks each live route
actually loads: `app/g/[id]/page-*.js` one, `app/g/[id]/evidence/page-*.js` one,
and zero in `app/g/[id]/layout-*.js`, in the root `app/layout-*.js`, and in the
report and thread page chunks. When only the map mounted it, the same negative
was taken from the server route tree — `.next/server/app/g/[id]/page.js` named
`hash-target` and the layout, evidence and report entries named it zero times —
and **that method stopped working the moment #146 gave the component a second
importer**, because webpack then hoisted it into a shared server chunk that no
page entry names. The client chunk graph survives that and the server one does
not.

It had to be taken from an artefact either way: **a behavioural probe cannot
prove it.** Adding an element to `/g/13/report` and setting `location.hash`
scrolls the page whether or not this component is mounted, because a
same-document fragment change scrolls natively once the element exists —
measured, and it "passed" on all three routes including the two that do not
mount it. Only the chunk graph separates the two explanations.

`instant` is explicit rather than left to the default, so that a stylesheet later
setting `scroll-behavior: smooth` cannot turn an anchor into a glide down the
39-screen evidence page — nauseating, and against the `prefers-reduced-motion`
work in #147.

**Twenty assertions against the compiled component in a real DOM, all passing**,
before any deploy: `#threads` scrolls to `#threads` and passes
`{behavior:"instant"}`; no hash, a bare `#`, and `#nosuchthing` each scroll
nothing and throw nothing; a row nested two `<details>` deep is scrolled to with
both ancestors and itself opened; `#r-cs%2F0501001` resolves to the literal id
`r-cs/0501001`, which is the case an old-style arXiv id in an #146 anchor will
need; a malformed escape such as `#100%off` does not throw; a `hashchange` after
mount re-runs it; and the effect's cleanup removes the listener.

**After, measured on the live deploy**, headless Chrome 1440×900 from Sydney,
same vantage and method as #143's table above, so the columns mean the same
thing. The three rows the ticket filed:

| | scrollY, after #143 | scrollY, now | `#threads` |
|---|---|---|---|
| Threads, from `/g/13/river/s0` | 150 | **569** | 315 px down the viewport |
| Threads, from `/g/13/evidence` | 150 | **569** | 315 px down the viewport |
| **hard load** of `/g/13#threads` | 0 | **569** | 315 px down the viewport |

The thread list is at y=884 in all three, and 569 is the page's maximum scroll at
this viewport, so the section lands as far up the screen as the document allows.

**The scroll arrives with the content, which is the check that says the mechanism
is the mount and not luck.** Sampling a hard load at the ticket's own intervals:
no `#threads` and `scrollY` 0 at 500 ms, 1 s and 2 s; at 4 s the element is
present at 884 and `scrollY` is already 569. Sampled every 25 ms instead, the
element is first observed at **3728 ms** and `scrollY` first goes non-zero at
**3728 ms** — the same sample, a gap of 0 ms.

**It does nothing when it is not asked.** `/g/13` with no hash and
`/g/13#nosuchthing` both hold `scrollY` at a maximum of **0** over seven seconds
of polling, spanning the content's arrival, with no page error and nothing
logged to the console on either.

**Reduced motion sees no scrolling to reduce.** With `prefers-reduced-motion:
reduce` emulated, sampling `scrollY` every animation frame across a hash change
gives 241 frames holding exactly two distinct values, 0 for the 42 frames before
the hash was set and 569 after — **zero intermediate positions**, so there is no
glide to interrupt. The computed `scroll-behavior` on `<html>` is `auto`.

**The long case, which is what #146 needed this for.** A hard load of
`/g/13/evidence#r-1905.04899-2105.03404`, one of 287 anchors and 41,375 px down
an unscrolled page: it lands at `scrollY` 41,356 with the row 19 px below the top
of the viewport, the row itself open and every ancestor `<details>` open.

**Known behaviour, recorded rather than discovered later.** Resolution is on the
decoded id only, so an element whose id contains a literal `%` will not be found
where a browser's own fragment matching would also try the raw string. Nothing
in the product generates such an id. **Back to a URL with no hash restores the
reader's position** — left at 300 on `/g/13`, out to the evidence page, Back
returns to exactly 300, which is the journey EVE measured. **Back to an anchored
URL re-scrolls to the anchor** rather than restoring: the reader who lands at 569
via `#threads`, scrolls to 0 and leaves is returned to 569. Judged correct —
following an anchor link is the reader asking to be moved — and recorded so it is
a known behaviour rather than a surprise. **Without JavaScript** `/g/13#threads`
returns 200, the thread list is in the served markup, and the page does not
scroll: the anchor lands wherever the browser puts it and nothing breaks.
Degraded, not broken.

**The evidence page's anchors, measured on the deploy** (issue #146; headless
Chrome 1440×900, hard loads only, because the defect #150 diagnosed is invisible
when the content is instant and this route takes 3.3 s to arrive).

| | before | after |
|---|---|---|
| elements carrying an `id` | **1** | **367** (287 relationships, 79 papers, 1 pre-existing) |
| duplicate ids | 0 | 0 |
| in-page links, and dead ones | 0, 0 | 366, **0** |
| definition passages a find-in-page can reach | **0** | **78** distinct, one per paper group that has one |
| page height at 1440×900, rows closed | 36 806 px (41 screens) | **55 850 px (62 screens)** |
| the same height, on #151's re-run | 38 609 px | 57 620 px |
| non-script markup | 2.29 MB | 2.51 MB |
| relationships listed | 287 | 287 |
| verified / inferred | 286 / 1 | 286 / 1 |

**Arrival works, which is the check the anchors exist for.** A hard load of
`/g/13/evidence#r-<pair>` at the top, the middle and the foot of the page landed
with the row **in the viewport and open**, 19–20 px below the top (the
`scroll-margin-top` this page sets), at `scrollY` 3 008, 27 625 and 55 282, with
both quote-cards present. `#nosuchthing` scrolled nowhere: `scrollY` 0 at 0.2 s,
1 s, 2 s and 3 s, no `<details>` opened, no console error and no page error. With
all 287 rows opened by script, **287 of 287 carry exactly one "Earlier paper
says" and one "Later paper says"** — product rule 1, counted from the DOM rather
than argued.

The two height rows are the same finding taken minutes apart by two sessions
with different warm-ups; neither is wrong and both are kept, because a single
figure here would be a claim about precision this measurement does not have.

**The page got taller, not shorter, and that was the trade.** Grouping moved
each paper's passage out of its rows and onto the group head, where a browser's
find can reach it; 79 group heads and the index are +19 000 px. The design said
this in advance and said the answer to 39 screens is the index and the anchors
rather than the scrollbar. Before this, a reader's only instrument was
find-in-page and it could not see a single quote, because Firefox and Safari do
not search inside a closed `<details>`.

**Timings did not move.** `curl` medians of 5 warm brotli requests, one discarded,
same vantage as the tables above: `/g/13/evidence` 0.33 s to first byte and
**3.26 s** complete against 3.32 s recorded after #143, with `/g/13/report`
0.32 / 0.96 (recorded 1.00), `/g/13` 0.33 / 2.01 and `/about` 0.08 / 0.08 as
controls. The wire body is 527 kB brotli; the ticket's "226 kB compressed" is not
reproducible against the retired build and is not differenced here, but the same
captures compressed locally at one quality give 125 kB before and 153 kB after,
so the transfer grew by roughly a fifth.

**CLS is 0.0000 on a plain hard load and 0.2968 on an anchored one.** The first
is the number #140 measured and the one the skeleton reshape was at risk of
breaking. The second is the target row *opening* after paint, which moves
everything below it: it happens only when a reader followed an anchor, it is the
row they asked for, and it belongs to `hash-target.tsx`'s mechanism rather than
to this page's markup. The server never sees the fragment, so it cannot render
that row open, and the alternative — not opening it — is the failure the ticket
was filed about.

**What the served bytes cannot answer.** The row bodies are not inside their
`<details>` in the response: React emits `<template id="P:…"></template>`
placeholders and streams the content into hidden divs that its runtime moves into
place. So a grep over the HTML reports row quotes as being "outside a details"
when in the assembled DOM they are inside one, and the find-in-page property has
to be measured in a browser. Counted in the DOM it is 78 blockquotes outside any
`<details>`; counted in the bytes it reads 296.

**The index's links are big enough to hit** (issue #158). Measured on the live
page at 1440×900, 768×844 and 390×844, the 79 links were **17.0 px tall on a
21.2 px pitch at all three** — a standards failure at every width, not a mobile
one, since WCAG 2.2 AA 2.5.8 asks for 24 px targets or 24 px between the centres
of adjacent ones and neither held. The cost of a mis-click here is unusually
high: the neighbour is a different paper and following it moves the reader up to
50 000 px, with no way back but the browser's.

`display: block` with `padding: 3px 0` on the entry. The block is the
load-bearing half — vertical padding on an *inline* element paints a bigger box
but leaves the line box, and therefore the pitch, exactly where it was — and it
moves the truncation onto the `<a>`, because `text-overflow` acts on a block's
own inline content and the `<li>` no longer has any. px rather than rem, because
the standard's threshold is in CSS px. The unlinked entry (the group with no
paper row, which is listed and not linked) takes the same padding so one entry
does not break the rhythm of a column of 79.

**Checked before the push against constructed markup, in headless Chrome**, at
all three widths, because the block-versus-inline arithmetic is the whole of the
fix and getting it wrong costs a deploy. The control is that the harness
reproduces the live before-numbers exactly: **17.0 px on a 21.16 px pitch** at
1440, 768 and 390. After: **24.77 px on a 27.16 px pitch** at all three, the
unlinked entry at 24.77 too, column count unchanged, and 47 of 79 labels still
ellipsised — the truncation followed the block, which is the thing that could
quietly have been lost. No hover or focus background: the index is a list of
names, not a set of buttons.

**After, on the live deploy**, the same three widths: 79 links, **24.77 px tall
on a 27.16 px pitch at 1440, 768 and 390**, against 17.0 / 21.2 before — the
harness's prediction to the hundredth. Columns 3 / 2 / 1 as before, index block
836 / 1189 / 2286 px, and the page **55 850 → 56 371 px** at 1440, which is
+521 px for all four of these tickets together, under 1%.

**CLS is still 0.0000** on a plain hard load of `/g/13/evidence` and of `/g/13`,
sampled for four seconds past arrival. That is the check these four owed: the
group heads each grew by a mark's worth of line, the index by 6 px per entry,
and the standfirst by two sentences, all of it below the fold and none of it
moving anything a reader is looking at.

**The mark explainer is a definition list, and the instruction comes first**
(issue #157). It was four sentences of unbroken prose, one of them 44 words,
sitting between the reader and the only instrument this page has, with "Click a
row to see the evidence" last — after three symbol definitions nobody needs until
they have clicked something. Three symbols defined in a run-on with semicolons
also means a reader who scrolls back to check what `○` meant must re-read the
whole block to find it.

Same words, same vocabulary, same order, different shape: the instruction moved
to the top with its owner-facing suffix intact, the three clauses became a `<dl>`
with the glyph in a fixed column, and the scope sentence dropped the 20 words
explaining why its case happens (the row names the other paper, so the reader who
meets it can see why). #127 protects that paragraph's structure — three symbols,
one clause each, in order — and a definition list *is* that structure, made
individually findable; the clauses are byte-identical apart from dropping
"means", which the list form now says.

**Counted from the file's own text rather than a re-transcription**, reader
branch, glyphs counted as tokens: **117 → 98**. The `◌` definition stays although
this map never renders one (`●` appears 364 times, `○` once, `◌` not at all): a
reader can meet it on another map or after a re-check, and a page that defines
two of three marks is the #115 defect again. Nothing here is coloured, graded or
scored, and `inferred` / `not re-checked` stay the only emphasis in the block.
Two deviations from the ticket, both deliberate: it keeps "a **passage** marked
●" rather than the ticket's "a paper marked ●", because what the mark is about is
the passage and that precision is the whole of #135's work; and the ticket's
"76 words" does not reproduce — its own proposed wording counts 100 by the rule
above, so the shape is the win here and the length is a smaller one than claimed.

**After, read back off the live deploy**: 98 words, the same figure the file's
own text gave, with the lede reading "Each row is a typed relationship between
two papers. Click a row to see the evidence.", the three clauses in `● ○ ◌`
order, and the scope sentence last.

**The two verification marks are the same size, which is also the answer to the
design question #146 left open** (issue #156). Counted on the live page, every
mark element on `/g/13/evidence`: 78 group-head marks (one paper's own passage)
at **9.92 px**, 287 row marks (a pair) at **12.48 px**, all `--verified` green
but one `--inferred`. The group head's was the smallest text on the page and the
page's central claim, 0.96 px under the loading note #147 raised for being the
least legible text in the product; contrast was never the problem, green on paper
is 7.36 : 1.

The open question was whether the two scopes need visibly different forms. They
do not, and must not: the mark means the identical thing in both places — this
quote was found word for word in the text this system pulled out of that paper —
and what differs is the scope of the thing it is attached to, which the words
already carry twice ("this paper", singular, under the group head; "verified" at
the top of a row that names two). A second glyph vocabulary would say a second
kind of check ran, and would take the reader from three symbols to six on the
page where they can least afford to guess. So: `.62rem` → `.78rem` on the group
head's stamp and nothing else. No new form, no new colour, no second scale
(decisions 24 and 25), and the three strings are byte-identical. The uppercase
caption above it stays at `.62rem`, a label sitting under the claim.

**After, counted on the live deploy**: **78 group-head marks at 12.48 px** in
`rgb(92,179,137)` and **287 row marks at 12.48 px**, 286 of them the same green
and one `rgb(240,96,95)`. One size and two colours across all 365, which is what
"the same check, two scopes" should look like.

**The page now says, above the fold, that it has a way in** (issue #155). #146
built the index and nothing on the first screen named it: measured on the live
page at 1440×900, `nav[aria-label="Jump to a paper"]` starts at **y = 2152**, 2.4
screens down, behind the ranked paper list, on a page that is 62 screens tall and
got 52% taller in the change that added the index. The first screen was the h1,
the counts and a two-sentence standfirst that mentioned neither the index nor the
second way in — find-in-page, which #146 paid 19 000 px for and which nothing on
the page claimed.

The standfirst carries both now, in two added sentences, the second ending in an
in-page link to the index. The index's `id` is `the-index` and it is written in
`lib/anchors.ts` beside the content-derived ones, because the standfirst and the
`<nav>` are 200 lines apart and two literals that must agree is how a fragment
link stops resolving without anyone noticing. The `<nav>` takes the same
`scroll-margin-top` every other target on this page has, so it lands 1.2 rem
below the top of the window rather than flush against it, and `hash-target.tsx`
already handles the click through its `hashchange` listener.

**After, on the live deploy** at 1440×900: the link sits at **y = 312**, whole
and on the first screen; its `href` is `#the-index`; the id resolves, and the
element it resolves to is the index `<nav>` itself. Clicked, the page lands at
`scrollY` 2192 with the nav **19 px below the top of the window** — the
`scroll-margin-top` this page sets, 1.2 rem — and the hash reads `#the-index`.
The index's own top is at y = 2211, which is what the sentence exists to
shorten.

Deliberately not done, and both refusals are inherited: the index is not sticky
and has not moved above the ranked list. #143 refused a fixed bar on this page,
and section 1 is the page's own order.

**Clicking the tab you are already on no longer refetches that route** (issue
#151). It was one behaviour in two files — `nav.tsx` since it shipped, `tabs.tsx`
inheriting the pattern for #143 — and it had become the three longest waits in
the product, each of them returning exactly what was already on screen. Measured
on the live deploy before the fix, headless Chrome 1440×900 from Sydney: 2.8 s
clicking "The map" on `/g/13`, **3.7 s** clicking "The evidence" on
`/g/13/evidence`, 1.5 s clicking "What this map is made of" on `/g/13/report`.
Each threw the page away, and on the evidence page it also closed every
relationship the reader had opened.

`app/app/current-tab-click.ts` holds the one answer both strips now call, so a
third strip cannot inherit the old one. **The click scrolls to the top and
fetches nothing.** Doing literally nothing was the alternative, and in practice
this is that: neither strip is sticky, so the tab has to be on screen to be
clicked and the reader is already at the top. Going back to the top is the one
part of the old behaviour worth having, it costs no request, and it is already
the right behaviour if a strip is ever made sticky. **The scroll is instant and
never smooth**, which is a measurement rather than a taste: on the live site a
smooth scroll home from 20000 px down the evidence page takes **1494 ms** against
**4 ms** instant, and 1.5 s of glide is most of the wait this ticket exists to
remove. It is the same ruling `hash-target.tsx` already carries for #150 and
#147, so the two ways of arriving somewhere on a page behave alike. At the
distances reachable today the two are indistinguishable anyway, because the tab
has to be on screen to be clicked; `prefers-reduced-motion` therefore has nothing
left to switch on and the code does not consult it.

**Whether a click is going anywhere is decided from the href, never from which
tab is lit**, and that distinction is the whole of the risk here: they are
different questions. "Concepts" is lit on `/g/13` and goes to `/`; "Threads" is
lit on a thread page and goes to the map. Suppressing on the lit flag would have
broken both. A href carrying a hash is never suppressed, so "Threads" on
`/g/{id}` reaches the router untouched and still scrolls. **What scrolls it is
the router's own same-page hash handling, not `hashchange`**: measured on the
live deploy, that click fires `hashchange` **zero** times, and `hash-target.tsx`
does not remount either, so neither of #150's two paths runs. Anything that
suppressed this click, or converted the current tab to a non-link, would have
removed the only mechanism there is. A modifier or middle click is left to the browser,
which is a real request for a second copy. A click made while a query string is
present still navigates, because the bare href would clear state — nothing reads
`searchParams` today, and the location is read in the handler rather than through
`useSearchParams()`, which in the root layout's nav would opt every route out of
static rendering and undo #145.

**After, measured on the live deploy**, same vantage and method as the tables
above — real clicks, headless Chrome 1440×900, a `MutationObserver` watching for
the first DOM change:

| clicked while already on it | before | after |
|---|---|---|
| The map, on `/g/13` | 2.8 s | **no DOM change at all in 3 s** |
| The evidence, on `/g/13/evidence` | 3.7 s | **no DOM change at all in 3 s** |
| What this map is made of, on `/g/13/report` | 1.5 s | **no DOM change at all in 3 s** |
| How it works, on `/about` | — | **no DOM change at all in 3 s** |

Nothing is fetched: zero `?_rsc=` requests in the three seconds after each click,
once the page's own in-viewport prefetching has quiesced, and zero document
navigations. The `<body>` and both `<nav>` elements are the same DOM nodes
before and after, marked with a `data-mark` attribute React knows nothing about.
No skeleton paints. On the evidence page, **two relationships opened before the
click are still open after it** and the page's text is unchanged to the
character. Every one of the four ends at scroll 0. Re-run after #146 deployed,
which took that page from 38609 px and 92315 characters to 57620 and 125191: the
same checks pass on the bigger page, which is the point of measuring the reader's
open rows rather than the wait.

**The clicks that are meant to go somewhere still do**, all in 20–27 ms with the
first DOM change at 14–23 ms: the map to the evidence page, the evidence page to
the report, the report to the map, `/about` to `/roadmap`, and — the case the
href-not-lit-flag rule exists for — "Concepts" from `/g/13`, where the tab is lit
and the destination is `/`. Threads from `/g/13` lands with the URL at
`/g/13#threads`, the thread list 315 px down the viewport with its first card
whole, and the map not thrown away; the document is 1469 px against a 900 px
viewport, so 569 px is the whole scroll there is and the page took all of it.

**"Read the dossier →" is a link, and it was the last unacknowledged click in
the product** (issue #154). Measured on the live deploy before the fix, three
trials from the same panel: **279, 282, 288 ms** with the map unchanged on screen
and no `role="status"` anywhere, sampled at 50 ms and 150 ms after the click,
against 6–8 ms for the button directly beneath it. The two were written the same
way, `router.push` from `InfluenceMap.tsx`, so the difference is not the call: it
is that **no `<a href>` anywhere in the product pointed at `/g/{id}/p/…`** —
counted across all four map routes, 0 on `/g/13`, `/g/13/evidence`,
`/g/13/river/s3` and `/g/13/report` — so the router had never prefetched the one
route that button serves. This is #143's finding arriving in reverse: a route
nothing links to is a route nothing prefetches.

It is now a `<Link>` styled exactly as the button was, which also gives the
middle-click and the new tab a reader comparing two papers wants, and announces
itself to a screen reader as navigation rather than as a control. **Prefetch is
scoped to the pinned paper** rather than left on the default: the panel's
contents follow the pointer, so an in-viewport link whose `href` changes on every
hover would fetch a route per dot swept over, and none of those is reachable —
leaving a dot clears the hover and the panel falls back to the pinned paper, so
the only dossier the button can open is that one. The head start is therefore the
time between clicking a dot and crossing to the panel.

**After, measured on the live deploy**, same vantage and method as the tables
above — fresh page each trial, a real click at the centre of a dot to pin a
paper, then the link, with a `MutationObserver` for the first DOM change:

| the click | before | after |
|---|---|---|
| "Read the dossier →", **0.7 s after pinning** | 279, 282, 288 ms | **6.2, 5.1, 4.6 ms** |
| the same click, **fired immediately after pinning** | — | 297, 291, 259 ms |

Both rows are the answer, and the second is the boundary this fix has. The head
start is the walk from the dot to the panel, so a click that lands before the
prefetch returns still waits for it: 0.7 s of pause is enough and 0 ms is not.
A reader cannot produce the second row — the panel offers no button until a paper
is pinned, and the button is 250 px from the dot — but a harness can, so it is
recorded rather than left for someone to rediscover as a regression. All six
trials land on `/g/13/p/1706.03762` with the skeleton up.

**The box is pixel-identical to the button it replaced**: 36 × 230.81 px live,
and the same 36 × 230.81 for both when the old button and the new link are
rendered side by side, at the same 13.6 px, colour, background, radius and
padding. `line-height: normal` is explicit on the link because a button gets it
from the user agent and an anchor would have inherited the body's.

There is now exactly **one `<a href>` in the DOM pointing at `/g/13/p/…`**, and
still none in the served HTML: the panel is client-rendered, so a `curl`-based
link count reports zero here and that means "I could not see it", never "there is
none".

Not done here, and named because the ticket raises it: the thread page still
offers no way into a dossier. That is a change to what the thread page lists, not
a link, and belongs to the Architect.

**`/about` and `/roadmap` are now prerendered, and every other route on the site
stopped waiting for a session** (issue #145). This is the only one of the three
performance tickets that removes time rather than covering it. `layout.tsx`
rendered `<SignInButton />` as an async server component calling `getViewer()`,
and a dynamic API anywhere in the root layout opts **every route in the
application** out of static generation — including the two pages that are fixed
prose with no data in them. Nothing on the site was statically prefetchable, so
clicking "How it works" from `/g/13` left the old page whole on screen for
**547 ms** and "Roadmap" for **582 ms** (headless Chrome, 1440×900, the method
#144 established).

Three files, no schema, no migration, and no change to any authorisation check.
`signin-button.tsx` is a client component that fetches `/api/viewer` after paint;
the two Server Actions it used to declare inline moved to `lib/auth-actions.ts`,
because a client component cannot declare one. `layout.tsx` itself is unchanged —
the dynamism was never in the layout's own code, only in the component it
renders, which is why the file needed no edit and the build is the only thing
that can say whether the change worked.

**The slot renders nothing until it knows the answer.** Not a spinner, and above
all not "Sign in with GitHub" as a default, which would flash the wrong state at
the one reader who is signed in. On a failed request it stays empty for the same
reason: it never renders a state it has not been told, and the cost of that is
recorded below. Its `min-height` is `1.77rem`, measured rather than chosen — both
states of the control render 27.59 px tall at a 16 px root and the header row's
height is exactly the control's, so a shorter reservation moves the nav down when
the answer lands. 1.77rem is that height at the smallest root font worth
covering, since the button's 1 px borders do not scale with the root; it costs
the header 0.7 px of permanent height, which is not a shift. There is no
`min-width`: the signed-in width is a function of the login (141 px to 260 px
across 2 to 19 characters, measured), so no constant covers it, and the row is
`space-between` with the slot flush right, so its width moves nothing either way.

The mechanism did not change, only when the session is read. The actions are
still Auth.js Server Actions with its own CSRF handling, deliberately not
`next-auth/react`'s `signIn`/`signOut`, which is a different code path.
`startSignIn` takes no argument and hard-codes `"/"`: the old component had a
`redirectTo` prop defaulting to `"/"` that no call site ever set, and accepting
one from the client would be an open redirect introduced by a performance fix.
(`lib/trace-actions.ts` keeps its own server-side sign-in to `/trace`.)

**Verified from the build's own route table, which is the falsifiable test of the
whole ticket**: `○ /about`, `○ /roadmap` and `○ /_not-found` prerendered as
static content, every other route still `ƒ`. Before the change all fourteen were
`ƒ`. And the prerendered HTML is anonymous, which had to be asserted rather than
assumed once the page became shared: `.next/server/app/about.html` and
`roadmap.html` contain no login, no "Sign out", no "read-only", and no
"Sign in with GitHub" — the slot holds only the `<noscript>` link. The
occurrences of "curator" on `/about` are the page's own prose, which explains
the word.

**Authorisation is unmoved, and the build says so.** Comparing
`server-reference-manifest.json` across the change: twelve Server Action ids
before and twelve after, two removed and two added, and those two are the auth
pair that moved file. Every other id is byte-identical, including the six
reachable from the evidence page and the four from `/trace` — none changed id,
none was added, none was lost. `requireOwner()` is untouched and is still the
lock. The adversarial runtime test (`app/scripts/security-test.mjs`) was **not**
run: it reads `DATABASE_URL` out of `.env.local` and needs a server on
localhost, both of which an agent shell is refused, so it belongs to the Tester
on a machine that has them.

**After, measured on the deploy**, same method and same vantage (Sydney,
headless Chrome 1440×900, real clicks on the global nav from `/g/13`, median of
four; and `curl` medians of 9 warm brotli requests):

| clicked | content on screen, before | after | first byte, before | after | serving |
|---|---|---|---|---|---|
| How it works (`/about`) | 297 ms | **64 ms** | 0.316 s | **0.075 s** | PRERENDER, then HIT |
| Roadmap (`/roadmap`) | 275 ms | **70 ms** | 0.315 s | **0.075 s** | PRERENDER, then HIT |
| `/g/13` — control, untouched | — | — | 0.303 s | 0.300 s | MISS |
| `/g/13/river` — the floor, no database work | — | — | 0.320 s | 0.302 s | MISS |
| `/` — control, untouched | — | — | 0.309 s | 0.304 s | MISS |

Two things in that table are worth naming. **The first-byte figure went below
what this document has been calling the network floor**, and the floor was not
wrong, it was the floor for a *function*: 0.30 s is what it costs Sydney to reach
`iad1` and back. A prerendered page is served from the edge in Sydney and never
makes that trip, so 0.075 s is a different floor and the right one for these two
routes. `X-Vercel-Cache` reads PRERENDER on the first request and HIT after,
where it read `MISS` on every request before. And the three controls did not
move, which is what turns "it got faster after the deploy" into an attribution.

The ticket's own number was 591 ms and the first run of the day reproduced it at
547 ms; the 297 ms above is the warm median over four runs on the deploy
immediately before this one, and it is the honest "before" to compare against.
Both are the same finding and the cold figure is the one a first-time reader
actually pays.

**No flash and no shift, sampled every frame from before first paint** on hard
loads of `/about`, `/roadmap`, `/` and `/g/13` with cookies cleared: the slot
goes through exactly two states, empty and then the signed-out control, with no
intermediate and nothing wrong shown in between. The nav row sits at y=57.09 and
the header row at 28.31 px, identical before and after the answer lands, on all
four routes; CLS 0.0000 with zero layout-shift entries. The 0.7 px the
reservation adds shows up as the nav's y moving from 56 to 57 across the deploy,
which is a different page, not a moving one. And the action still works from a
prerendered page: clicking the button POSTs to `/about` with a `Next-Action`
header and the browser lands on GitHub's sign-in.

The signed-in states were verified by rendering the shipped component rather
than in a browser: signing in needs the owner's credentials, so the curator
badge, the sign-out control and the audit entry carrying `by` are the Tester's
to confirm live, along with the two-session cache check.

Costs, stated: one extra client request per page load, off the critical path,
replacing a server-side session read that was on it. And a reader with
JavaScript off loses the sign-in control, which used to be a server-rendered
form; the slot carries a `<noscript>` link to `/api/auth/signin`, Auth.js's own
page, which is one line and the honest answer.
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

`/api/viewer` (issue #145) is the one place the header learns who it is talking
to, and it grants nothing. It takes no input, so a caller cannot ask it about
anyone but themselves; it returns `owner` as a boolean and never echoes
`OWNER_GITHUB_LOGIN`, so the client learns whether it is the curator without
learning who the curator is. Its response is one reader's identity, so it is
`force-dynamic` with `Cache-Control: no-store, private` — the worst failure
available on that route is one reader's login being served to another from a
cache. Two-session confirmation of that, live, belongs to the Tester; the header
is set in the code and asserted in a harness over the route's own branches.

Adversarially verified at commit `3aceaf0`: 7 action ids harvested from the
build manifest, 35 unauthenticated mutation attempts, all rejected, database
unchanged. Rejections currently surface as HTTP 500 (fail-closed throw);
semantically they should be 403, accepted as open polish.

Money controls, layered: owner approval before any run; per-user request
quotas; `TRACE_SPEND_CAP_USD` aborts a stage mid-run; Stage B `--corpus`
scoping prevents cross-corpus billing; Stage D's classification cache (#172)
means an aborted or repeated run re-bills only what genuinely changed; and an
account-level cap at
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

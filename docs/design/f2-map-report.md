# Design: the map report

**Ticket: [#30](https://github.com/rgok001/Lineage/issues/30) `[F2]`.** Written
2026-08-07 against `master` @ `b26f306`.

**Status: proposed, awaiting the Product Owner.** Nothing here has been built.
The author held `LINEAGE_NO_DB=1` throughout and touched no database; every
count about the live system is quoted from `docs/AS-BUILT.md`, `docs/ROADMAP.md`
or a GitHub issue, and every claim about the schema was read from
`pipeline/db/migrations/`.

**This discharges open question 6 of `docs/design/f7-sources-beyond-arxiv.md`.**
That question asked whether the per-source grouping F7 depends on ships inside
#30 or as a follow-on. The Product Owner chose on 2026-08-07 to build F2 next
with the F7 design on the table, so the grouping is designed in here (section
2.5) and F7's gate is #30 itself, not a successor to it.

**Two tickets were filed from this design**, for figures #30 asks for that
nothing in the system records:
[#85](https://github.com/rgok001/Lineage/issues/85) (`genealogies.spend_usd` is
written by nothing) and
[#86](https://github.com/rgok001/Lineage/issues/86) (Stage D counts none of the
citation pairs it discards). **Neither is built inside F2.** Section 2.4 says what
the report prints in the meantime, and question 3 in section 9 asks the owner
whether #86 comes before F3.

---

## 1. The problem, restated

A map arrives today with no account of itself. A reader is shown 287 typed
relationships and 88 definitions and has no way to ask how much of that is
quote-verified, how much of the evidence the pipeline threw away, how lopsided
the shape came out, how old the sources are, or what the run cost. The owner
could answer those questions by reading the map, and did; on a platform where a
stranger generates a map nobody reads first, that answer has to come from the
map itself. What is wanted is **one row per map, computed from the map's own
rows at the moment it is read, with no ground truth involved and no threshold
anywhere** — so that a stranger can decide whether to trust one particular map
without having to trust us.

Two constraints from the ticket are load-bearing rather than stylistic, and this
design is shaped by them. **Nothing is stored**: a quality figure written to a
column survives the curatorial edit that invalidates it, and is then a lie with a
timestamp. **No thresholds**: with two maps there is no distribution to take a
quantile from, and this project has paid four times for a threshold moved because
a rate looked wrong (decisions 24, 25, 29).

---

## 2. The design

### 2.1 Two views, one of which is the base

Migration `016_map_report.sql` creates two views and nothing else. No table, no
column, no `MATERIALIZED`, no job.

**`map_report_by_source`** — one row per `(genealogy_id, unit, source)`, where
`unit` is `'definition'` or `'edge'`. Columns: `total`, `verified`, `inferred`,
`stale`. This is the base.

**`map_report`** — one row per genealogy, every figure the report publishes. Its
four verification counts per unit are `SUM`s over `map_report_by_source`, so
"the per-source figures add up to the map figure" is true by construction rather
than by test. Everything else is computed directly from `edges`, `definitions`,
`papers`, `genealogies.nodes` and `trace_requests`.

A view on a view is inlined by Postgres and both tables are in the low hundreds
of rows, so this costs nothing measurable. The reason to do it is not
performance: it is that a per-source total and a map total computed by two
separate expressions are two homes for one fact, and this record has already
paid for that pattern (`CLAUDE.md`, "one destination per kind of thing").

**Every share is a `NULLIF(denominator, 0)` division and renders as absent when
the denominator is zero.** A map with no edges reports its verified share as
"no edges", never as 0%. Zero percent is a claim about a population; there is no
population.

### 2.2 The stamp rule keeps three implementations, and the view takes over the SQL one

`stamp_state` / `edge_stamp_state` in `pipeline/common.py` and `stampOf` /
`edgeStampOf` in `app/lib/stamp.ts` are the same three lines in two languages. A
third expression exists in SQL, inside `listGenealogies`, and it exists only
because the home page needs the rule as an aggregate per map. Issue #60 is the
record of what a third copy costs: it disagreed with the other two on an
empty-string digest and counted such an edge **verified** on the front page.

**The view does not add a fourth copy. It replaces the third.**
`app/lib/genealogy.ts:listGenealogies` deletes its two stamp subqueries and
selects `edges_verified` and `edges_stale` from `map_report`. Net count of
implementations after F2: three, exactly as now, and the SQL one is in one place
that both the app and the CLI read.

The SQL form is **one `CASE` expression producing one label per row**, not three
independent predicates:

```sql
CASE
  WHEN COALESCE(e.source_text_digest, '') = ''
    OR COALESCE(sp.extracted_text_digest, '') = ''
    OR e.source_text_digest IS DISTINCT FROM sp.extracted_text_digest
    OR COALESCE(e.target_text_digest, '') = ''
    OR COALESCE(tp.extracted_text_digest, '') = ''
    OR e.target_text_digest IS DISTINCT FROM tp.extracted_text_digest
       THEN 'stale'
  WHEN e.verified THEN 'verified'
  ELSE 'inferred'
END
```

One expression means verified, inferred and stale are disjoint and sum to the
edge count **by construction**. Stage E's `stats` block was the boolean, the
boolean's complement and the stamp, and its three counts summed to more than the
edge count (issue #59); that arithmetic must not be reproduced here. The
definition-side expression is the same shape over `d.quote_text_digest` and
`p.extracted_text_digest`.

**Both joins to `papers` are `LEFT JOIN`.** `edges.source_paper_id` and
`target_paper_id` are nullable (`001_init.sql:61-62`) and may name a row that is
gone. Issues #60, #79 and #83 are three rounds of the same defect: an inner join
lets the join decide whether an edge exists, silently, and in the one direction
that is not available — an edge whose paper is missing is certainly not
verified, but it is also not nothing. A `LEFT JOIN` hands the `CASE` a NULL
digest, which is exactly what `stampOf` is handed for a paper with no digest, and
both call it stale. **The report must not inherit the assumptions of the five
remaining inner joins #83 lists in `pipeline/`**; it joins the way the four fixed
app-side queries join, and section 4's falsifier 2 is what proves it.

`definitions.paper_id` is `NOT NULL` with a cascading foreign key and cannot
dangle, so its `LEFT JOIN` is uniformity rather than behaviour — measured, the
result set is identical either way. It is written that way so that widening the
predicate later cannot silently reintroduce the join deciding the question, which
is the same note `getInfluenceMap` already carries.

### 2.3 Every number, and exactly where it comes from

A map is `(concept, prompt_version)`, unique since migration 007, so the join
from `genealogies` to `definitions` on that pair is provably single-valued.

**Coverage of the reading.**

| Figure | From |
|---|---|
| `papers_with_a_reading` | `count(*)` of `definitions` for the map's `(concept, prompt_version)`, both polarities |
| `papers_defining` | the same, `WHERE defines_concept = true` |
| `papers_not_defining` | the same, `WHERE defines_concept = false` |

`papers_defining` is the denominator of every definition figure below. The
negative verdicts are reported beside it rather than folded away: "this paper
does not define the concept" is a finding (migration 003), and a verified
fraction that quietly excluded them would read as a fraction of the corpus while
being a fraction of the definers. **What none of these is: the corpus.** A paper
selected in Stage A but never fetched, or fetched but never extracted, leaves no
`definitions` row at all, so this under-reports what the run set out to read.
The report says so on the page rather than in this document only.

**Evidence, per `map_report_by_source` and summed into `map_report`.**

| Figure | From |
|---|---|
| `definitions_verified` / `_inferred` / `_stale` | the definition-side `CASE` over `definitions.quote_verified`, `quote_text_digest` and `papers.extracted_text_digest` |
| `edges_total` | `count(*)` of `edges WHERE genealogy_id = g.id` |
| `edges_verified` / `_inferred` / `_stale` | the edge-side `CASE` in section 2.2 |

**Quote reuse.**

| Figure | From |
|---|---|
| `quote_slots` | `2 * edges_total` |
| `quote_slots_empty` | slots where the trimmed quote is `''` |
| `distinct_quote_strings` | `count(DISTINCT q)` over the union of non-empty `edges.source_quote` and `edges.target_quote` |
| `distinct_papers_on_edges` | `count(DISTINCT paper)` over the union of both endpoint ids |
| `most_repeated_quote_uses` | the largest per-quote occurrence count across both slots |

Empty strings are excluded from the distinct count deliberately: a quote holding
no text of the paper is not evidence (issue #57), and counting `''` as a
distinct quote string would manufacture distinctness out of an absence.

**These two numbers together are the honest form of this measurement, and one
alone is not.** An edge's quotes *are* the two papers' Stage B definition quotes
by design (decision 6), so a paper appearing on 43 edges contributes its one
quote 43 times. `distinct_quote_strings` far below `edges_total` is therefore
structural and not a defect — what the report is entitled to say is that an edge
does not carry evidence of its own. Publishing it beside
`distinct_papers_on_edges` is what makes it informative rather than alarming: the
two should be close, and if `distinct_quote_strings` is materially *lower* than
`distinct_papers_on_edges` then two different papers are carrying the same quote
string, which is a real finding this system currently cannot see. The reference
points already in the record: 287 `attention` edges rest on 79 distinct quote
strings, one appearing 43 times; 305 `embedding` edges on 107.

**Shape.** All of this reads `genealogies.nodes`, which is JSONB written by Stage
C and rewritten by the workbench.

| Figure | From |
|---|---|
| `nodes_total` | `jsonb_array_elements(g.nodes)`, counting entries that declare a `node_id` and an array `members` |
| `nodes_unreadable` | entries that do not |
| `nodes_with_one_member` | `jsonb_array_length(n->'members') = 1` |
| `nodes_with_no_edge_to_another_node` | nodes appearing on no edge whose two `node_id`s differ |
| `largest_node_id`, `largest_node_members` | the node with the most members, ties broken on `node_id` |
| `largest_node_edges` | edges with `source_node` or `target_node` equal to it |
| `node_pairs` | distinct `(source_node, target_node)` ordered pairs across the map's edges |
| `node_pairs_disagreeing` | of those, pairs carrying more than one distinct `edge_type` |
| `edges_on_disagreeing_pairs` | edges sitting on such a pair |
| `edges_within_one_node` | edges whose `source_node = target_node` |

**Malformed nodes are dropped and counted, never guessed at and never raised
on.** That is the posture `node_denotation` in `common.py` already takes, and the
counting is what stops it being silent: a map whose `nodes` blob is half
unreadable must say so on its own report rather than reporting a small,
confident `nodes_total`.

**The pair is ordered**, because an edge means "the later paper did X to the
earlier one's concept" and the reverse is a different claim. `node_pairs` and
`node_pairs_disagreeing` are published beside the share for the reason decision
24 exists: a rate says something is wrong and cannot say what, while the pair
counts distinguish "two enormous pairs carry everything" from "fifty small pairs
each disagree once". Those are different findings implying different actions.
`edges_on_disagreeing_pairs / edges_total` is the number `docs/ROADMAP.md`
measured at 62% and used to decline building a node-to-node view.

**Corpus age.** From `papers.year` over the map's defining papers.

| Figure | From |
|---|---|
| `year_min`, `year_p25`, `year_median`, `year_p75`, `year_max` | `percentile_cont` over non-NULL `p.year` |
| `year_counts` | `jsonb_object_agg(year, n)`, the distribution itself |
| `papers_with_no_year` | counted separately, excluded from the percentiles, never imputed |

`papers.year` is the **earliest credible date** — the minimum of the OpenAlex
year and the year encoded in the arXiv id (migration 009, after OpenAlex dated
"Attention Is All You Need" to 2025). The report says that where it prints the
figure, because a reader will otherwise read it as a publication date.

### 2.4 What is not recorded today, what the cell says, and which ticket fixes it

Three of the ticket's requested figures have no input in this database. Each
renders as an explicit **"not recorded"** — never a zero, never an estimate, and
never a blank that could be read as a zero — beside the ticket that would make it
recordable. **F2 builds none of that recording.**

**Run cost — not recorded, and the trap is specific.** `genealogies.spend_usd`
exists and **is written by nothing**: it reads `0.0000` on both live maps
(decision 26, and the closing comment on issue #53). The real figure is scraped
from stdout by the worker's regex and lands in `trace_requests.progress` as
`spend_usd`. So the view reads `progress->>'spend_usd'` from the chosen run and
**must never `COALESCE` it to `genealogies.spend_usd` or to 0.** A `$0.00`
printed under "what this map cost" is precisely the derived value stored and
allowed to age that this whole ticket is a reaction to, and it would be the
single most damaging line on the page. The view carries `run_cost_basis` beside
the figure, holding either "from the worker's record of the last completed run"
or "not recorded", and the page prints the caveats that are true of it: it is a
scrape of what the stages printed, it covers only the stages that print a spend
line, and it is one run's spend rather than the map's lifetime cost, so a repair
or a re-run adds nothing to it. Tickets:
[#47](https://github.com/rgok001/Lineage/issues/47) `[B29]` for per-stage spend;
and [#85](https://github.com/rgok001/Lineage/issues/85), filed from this design,
for the `genealogies.spend_usd` column that is written by nothing and reads
`0.0000` on every map.

**Wall clock — recorded for worker runs only, and neither existing map is one.**
`trace_requests.started_at` and `finished_at` are written by the worker.
`attention` and `embedding` were built from the CLI and have no `trace_requests`
row, so both cells read "not recorded" on the two maps that exist. The view
publishes `run_wall_clock` (`finished_at - started_at`, the run) and
`requester_wait` (`finished_at - created_at`, what a requester actually
experienced), because `docs/ROADMAP.md` open question 5 — whether "about fifteen
minutes" is a promise or a description — is answered by exactly this pair and by
nothing else in the system.

**Which run.** A genealogy may have several `trace_requests` rows over its life.
The rule is: the most recent row with `status = 'complete'` and
`genealogy_id = g.id`, ordered `finished_at DESC NULLS LAST, id DESC`. The view
also publishes `runs_recorded`, so a reader knows the figures describe one run
out of N rather than the map's whole history. With `runs_recorded = 0` every cost
and time cell reads "not recorded".

**Citation pairs discarded and why — not recorded anywhere, and this is the
gap that matters most.** `pipeline/stage_d_edges.py` discards candidate pairs in
five places and counts none of them: the cited paper is outside the corpus or is
the citing paper itself (`:142`), the two papers landed in the same concept-state
(`:144`), the classification call raised (`:220`), the model returned no parse
(`:230`), and the spend cap `break` leaves the remainder unattempted (`:261`).
Upstream of all five, a failed Semantic Scholar fetch is cached permanently as
"this paper has no references" (issue #14 `[B27]`), so pairs can vanish before
they are ever counted as candidates. None of this reaches Postgres, and the
candidate set exists only in S2 cache files under `DATA_DIR`, which a database
view cannot read.

So the cells read "not recorded", and the recording is
[#86](https://github.com/rgok001/Lineage/issues/86), filed from this design:
Stage D counts its discards by reason and persists the tally per run. Section 2.6
says why that ticket has to land before F3 rather than after.

### 2.5 The per-source dimension, built in rather than bolted on

`docs/design/f7-sources-beyond-arxiv.md` requires that the verified fractions of
definitions and of edges, and the discarded-pair counts, are grouped by
`papers.source` **from the start**, because a report that gains a dimension after
the fact reports two different things under one name and F7's whole
before-and-after comparison would then be against a differently-shaped number.

`papers.source` does not exist yet; F7's migration adds it. So the dimension
lives in the **shape** of `map_report_by_source` from day one, and its value is
**measured from the row rather than asserted**:

```sql
CASE WHEN p.id IS NULL           THEN 'no paper row'
     WHEN p.arxiv_id IS NOT NULL THEN 'arxiv'
     ELSE 'source not recorded' END
```

Today `papers.arxiv_id` is `UNIQUE NOT NULL`, so every row genuinely reports
`arxiv` and the report truthfully says "arXiv: 88 of 88". A literal `'arxiv'`
would have been an assertion that could not fail; this expression can. When F7's
migration drops the `NOT NULL`, a PMC paper falls into `source not recorded` —
**visibly** wrong rather than silently wrong — which is the failure mode to want.
**F7's migration replaces this expression with `p.source` in the same migration
that creates the column**, and section 4's falsifier 6 is the reading that says
it was not done.

An edge has two endpoints and may, after F7, span two sources, so grouping an
edge by a single source is not defined. The edge-side `source` key is the **pair
of endpoint labels, sorted and joined** — `arxiv`, and after F7 also `pmc` and
`arxiv + pmc`, with `no paper row` participating like any other label. Every edge
therefore lands in exactly one bucket and the buckets sum to `edges_total`. That
sum is falsifier 2, and it is the global sanity check that stops a per-endpoint
fallback from quietly swallowing a whole class of edge.

**Discard counts arrive as a third `unit` in the same view when they become
recordable.** No column is added for them now. This is the one place where "we
will add it later" genuinely costs nothing, because a view holds no data: the
extension is `DROP VIEW ... CASCADE; CREATE VIEW ...`, free, with no migration of
anything. That is why designing the grouping in is not scaffolding, and why the
discard columns not being there is not a gap F7 has to work around.

### 2.6 What F3 needs from this, and the part F2 cannot give it

`docs/ROADMAP.md` sequences F2 before F3 because F3 needs a before-and-after
measurement and F2 is the instrument. Two figures serve that, and the second one
does not exist:

**What F2 does give F3.** `edges_within_one_node` is **0 by construction today** —
`stage_d_edges.py:144` drops every same-cluster pair, so no edge can have
`source_node = target_node`. After F3 it must be non-zero, `edges_total` must
rise, `largest_node_edges` as a share must rise from its structural zero (issue
#31 measured 0 of 305 and 0 of 287 edges with both ends inside the largest node),
and `edges_on_disagreeing_pairs` may move in either direction. Those are four
lines of the same report read before and after, from the map's own rows, with no
new recording. That is a real instrument.

**What F2 cannot give F3.** The number F3 is *about* — 176 of 479 candidate pairs
discarded for being same-cluster, 36.7% of the evidence — is an input to Stage D
and is recorded nowhere (section 2.4). F2 cannot recover it, and after F3 ships
the discard disappears, so the chance to measure it from the running system
closes. **Recommendation: [#86](https://github.com/rgok001/Lineage/issues/86) is
sequenced before F3, not after.** Without it, F3's before-and-after is an
after-only, and the 36.7% stays a hand measurement taken once on 2026-08-01 that
nothing in the system can reproduce.

### 2.7 Where it renders

**A new page, `/g/[id]/report`.** The full report, one screen, one column, no
interactivity. Figures in IBM Plex Mono, the prose around each figure in
Spectral, "not recorded" cells in `--ink-soft` so absence reads as absence rather
than as a small number. Each figure carries two sentences: what it counts, and
what would move it. No verdicts, no letter grades, **no colour coding of any
number** — a red cell is a threshold wearing paint, and the ticket forbids
thresholds however they are spelled. Copy obeys product rule 3 throughout: the
page describes what this map is made of, never how good it is.

**The map page `/g/[id]` gets a link and no numbers.** Its header already carries
"*X* of *Y* links quote-verified" for the links it draws, which is a different
and narrower claim; adding report figures beside it would put two counts with
different populations in one header. The link sits in the footer beside the
existing curation line.

**The home page `/` gets no new numbers, and loses an implementation.** The card
already counts papers, relationships, verified relationships and not-re-checked.
`listGenealogies` stops computing the last two itself and selects them from
`map_report` (section 2.2). That is the strongest single argument for a view: two
surfaces that must agree now read one expression instead of two.

**Visibility.** The report route inherits the map page's authorisation, whatever
that becomes. Today every map is public, so this adds no exposure — except for
one figure. `docs/AS-BUILT.md` §6 records a standing copy rule of "no cost talk
aimed at visitors", while `docs/ROADMAP.md`'s end state says a stranger should be
able to see what the run cost. Both are owner-owned documents and they disagree;
question 1 in section 9 is that disagreement and nothing is built either way
until it is answered. The design's default, pending the answer, is that
`run_cost_usd` renders for the owner only and every other figure renders for
everyone.

The page uses the CSS variables in `app/app/globals.css`, which are the shipped
palette. Those are not the hex values `CLAUDE.md` lists under UI design tokens;
that divergence pre-dates this ticket, is not F2's to resolve, and F2 does not
deepen it by introducing a token of its own.

### 2.8 The CLI

`pipeline/map_report.py <concept> [--prompt-version <pv>] [--all] [--json]`,
modelled on `pipeline/recheck_stamp.py`: it **reads `LINEAGE_READ_URL` and never
`DATABASE_URL`, and issues nothing but `SELECT`.** It selects from the same two
views, prints the same figures in the same order under the same labels as the
page, and with `--all` prints every map's row so the reference points of section
2.10 can be read from a shell. `--json` writes the row to stdout and to no file:
a report written to disk is a stored quality figure with a different spelling.

Reading through the read-only role is deliberate and is what lets the Operator
run this against production and paste the result into a report, which is how the
numbers in this repository's records get taken.

### 2.9 Why this does not run offline against the genealogy JSON export

The ticket asks whether the report can also be computed from
`data/genealogy_<concept>_<pv>.json`. **It cannot, and it must not be made to.**

That file holds nodes, edges (with `stamp` already resolved), the two quotes per
edge and a small `stats` block. It does not hold `definitions`, so the definition
verified fraction is absent; it does not hold `papers.source`, so nothing groups;
it holds no cost, no wall clock and no discard counts. An offline reader could
compute roughly half the report — and would then publish half a report under the
same name as the whole one, from a second implementation of every measurement.
That is issue #60 with a larger surface: three copies of a three-line rule
already produced a wrong number on the front page, and this would be two copies
of thirty measurements.

There is a second reason, sharper than the first. The export is a **backup**, a
description of one moment (incident 4), and it already carries a `stats` block
that is a small stored quality figure. Growing that block into the report would
mean the file asserts a verified fraction that a later curatorial edit makes
false, with the file's own timestamp standing behind it. The ticket's "never
stored" rule forbids exactly that, and Stage E's `stats` block should not be
extended by this ticket for the same reason.

If offline reading is wanted later, the honest form is a dump of the two views
rather than a recomputation from a different input, and it belongs to F4
(versioned maps), which is where a report about a past state of a map has a
meaning.

### 2.10 The reference points, and the absence of thresholds

**No threshold appears anywhere in the view, the page or the CLI.** The only
numeric literals permitted in the migration are `0.5`, `0.25` and `0.75` (the
quantiles that define median and quartiles) and `2` (quote slots per edge).
Each of those defines a statistic; none decides anything.

Beside each figure the page prints the same figure for every other map, and the
sample size. **The sample size is `count(*)` over `map_report`, never a literal.**
Writing "n=2" into the page would be a derived value stored in source and allowed
to age the moment a third map exists — the same defect, one level up, and it
would happen on the very next trace.

The word beside the comparison is "the other maps in this system", not
"baseline", "expected" or "typical". Two maps are not a distribution. A threshold
gets set when there are enough maps to take a quantile from, against a stated
distribution, with the resulting rate named in the commit that sets it.

---

## 3. What it costs

**Money: nothing.** No LLM call, no API call, no new infrastructure. The view is
read on request.

**Time: about two to three days.** The migration and the two views, one day; the
CLI, half a day; the report page, one day; the `listGenealogies` change and the
record updates, half a day.

**Risk to existing data: none from the view itself.** `CREATE VIEW` writes no
row, takes no rewrite lock and is dropped with one statement. **No step in this
design spends money and no step rewrites live data.**

The one live-data-adjacent change is `listGenealogies` reading the view instead
of its own subqueries. That changes a rendered number only if the view disagrees
with the expression it replaces, which is falsifier 3.

**One operational detail that will otherwise be forgotten.** The `lineage_ro`
role holds `SELECT` on existing tables and will not automatically hold it on a
new view, so the CLI would fail with a permission error against production while
working perfectly for the owner. The migration issues the `GRANT` itself, guarded
by a `DO` block that checks `pg_roles`, so a local database with no `lineage_ro`
still migrates. `docs/RUNBOOK.md` gains the one-line note.

---

## 4. How it will be verified

Seven checks. Falsifier 1 is the one that decides whether this ships.

**1 — The stamp rule's fourth expression agrees with the other three.** Run the
48-row truth table from `docs/design/recheckable-stamp.md` §7 falsifier 5
(`verified ∈ {True, False, NULL}` × stamp digest ∈ `{NULL, "", d1, d2}` ×
current digest ∈ the same four) against the view's two `CASE` expressions, the
real `pipeline/common.py:stamp_state` and the real `app/lib/stamp.ts:stampOf`
compiled with the project's own `tsc`. **Proves it:** 0 disagreements of 48 for
both expressions. **Falsifies it:** any disagreement, and the view does not ship
until it is 0 — issue #60 is precisely a SQL copy that disagreed on one input and
put a wrong number on the front page.

**2 — Nothing is dropped by a join, and the buckets are disjoint.** On a scratch
map carrying, deliberately, one edge with a dangling `source_paper_id`, one with
`NULL` paper ids, one with an empty-string digest, one whose paper row has no
`extracted_text_digest`, and several ordinary edges: assert
`verified + inferred + stale = total` for both units in `map_report`, and
`SUM(total) OVER map_report_by_source = map_report.total` for both units.
**Proves it:** both equalities hold on the scratch map and on both live maps.
**Falsifies it:** any inequality, which means a join is deciding whether a row
exists — #60, #79 and #83 are three rounds of that, and #83 lists five more
copies in `pipeline/` this must not have inherited.

**3 — The report and the surfaces agree about the same map.** `edges_total`
equals the home card's relationship count; `edges_verified` and `edges_stale`
equal the card's other two counts; `nodes_with_no_edge_to_another_node` equals
the count of "Unconnected meanings" that `computeFamilies` produces on
`/g/<id>/evidence`. **Proves it:** equal on both live maps. **Falsifies it:** any
difference, which is the two-surfaces-disagreeing-about-one-map defect #79 was
raised about, arriving from a new direction.

**4 — Known values from the record.** `attention` (`/g/13`) reports 287 edges and
79 distinct quote strings with a maximum reuse of 43; `embedding` (`/g/10`)
reports 305 edges and 107 distinct quote strings. Those were measured
independently of this view and are quoted in `docs/ROADMAP.md` and
`docs/AS-BUILT.md`. **Proves it:** they match. **Falsifies it:** they do not, and
the report says which of the two is wrong rather than adjusting to agree.
**Read the verification counts against the current re-ground state, not against
the record's older numbers**: migration 015 left every pre-existing stamp stale
until a free re-ground is run, so `edges_verified = 0` and `edges_stale = 287` is
a *correct* reading if that re-ground has not happened, and the remedy is
`stage_b_extract.py --reground` then `stage_e_ground.py`. Settle which state the
database is in first, read-only, and record the answer.

**5 — Nothing is stored.** Delete one edge on a scratch map through the
workbench, then re-select the view. **Proves it:** the figures move immediately,
with no job, no refresh and no recomputation step in between. **Falsifies it:**
they do not, which means something cached — and a report that survives a
curatorial edit is the lie with a timestamp this ticket exists to prevent.
Alongside it: `grep` the migration for `MATERIALIZED` and for any `INSERT` or
`UPDATE` of a report value, expecting none.

**6 — No threshold, and the source expression is honest.** Read the migration's
numeric literals; the only ones present are `0.5`, `0.25`, `0.75` and `2`, each
defining a statistic. And, for F7's benefit: insert a scratch `papers` row with
`arxiv_id` NULL (possible only after F7's migration drops the `NOT NULL`) and
confirm it reports `source not recorded` rather than `arxiv`. **Falsifies it:**
it reports `arxiv`, which means the expression asserts a source instead of
measuring one, and every PMC paper would be counted as an arXiv paper on the one
report F7 is gated on.

**7 — The CLI writes nothing.** Capture the statements the CLI issues against a
scratch database. **Proves it:** every statement is a `SELECT` and `commit()` is
never called, the same check decision 24 required of `--compare-verdicts`.
**Falsifies it:** anything else, and the read-only role should reject it anyway —
if it does not, the role's grants are wrong and that is a finding of its own.

"Tested" is not on this list, and neither is a golden set. Every number above
comes from the map's own rows or from a record written before this design existed.

---

## 5. What was considered and rejected

- **A column on `genealogies` holding the report, refreshed by a job.** The
  ticket's central refusal. A stored quality figure survives the edit that
  invalidates it.
- **A materialised view.** The same object with a longer name: it stores, and it
  needs a refresher nobody would name.
- **One flat view with no per-source grain.** F7 would then bolt the dimension on
  and the two shapes would report different things under one name — the failure
  its design document names explicitly.
- **A per-source JSONB column inside the one-row view.** Hides the grain from SQL,
  so the "buckets sum to the total" check becomes application code instead of an
  assertion anybody can run.
- **Computing the report in TypeScript from rows the app already fetches.** Puts
  the arithmetic where only one of the two consumers can reach it, and would make
  the CLI a second implementation.
- **Recomputing the report from the genealogy JSON export for offline use.**
  Section 2.9: half the measurements, from a second implementation, under the same
  name.
- **Extending Stage E's `stats` block into the full report.** Stores it, in the
  backup, with a timestamp.
- **Counting curatorial edits in the view.** `CURATORIAL_OPS` is a closed list
  with one definition in TypeScript and one in Python; SQL would be a third, and
  `jsonb_array_length` standing there once already counted incident 12's restore
  as somebody's editorial work. The report links to the curation sentence the
  page already computes.
- **Any severity colour, grade, badge or composite "quality score".** Every one of
  them is a threshold, and a composite is several thresholds with the evidence
  removed.
- **Falling back to `genealogies.spend_usd` when the worker's figure is absent.**
  It reads `0.0000` on every map and always has; printing it would be the report's
  own founding sin.
- **Recording Stage D's discards inside F2.** Real work, a different stage, and
  its own ticket, [#86](https://github.com/rgok001/Lineage/issues/86), which
  section 2.6 sequences before F3.
- **An unordered node pair for the disagreement measure.** `A extends B` and
  `B extends A` are different claims; folding them makes agreement look like
  disagreement.

---

## 6. Migration and versioning

`016_map_report.sql`: two `CREATE VIEW`s and one guarded `GRANT`. No table, no
column, no data touched, no rewrite lock, no backfill. It is reversed by
`DROP VIEW map_report; DROP VIEW map_report_by_source;`.

**`docs/design/f7-sources-beyond-arxiv.md` names its own migration
`016_paper_source.sql`; it becomes `017`.** That document should be corrected when
F7 is built, along with its section 0, which can then say the grouping shipped.

One constraint worth stating because it will be met within a month:
`CREATE OR REPLACE VIEW` cannot change a column's type, drop a column or reorder
columns, so any later change beyond adding trailing columns is
`DROP VIEW ... CASCADE` followed by `CREATE VIEW`. Consequently **no consumer may
`SELECT *`** — the app and the CLI name every column they read, so a view
redefinition cannot silently change what a page renders.

---

## 7. Risks

1. **A threshold gets added to the view later, because that is where the numbers
   are.** The migration carries a comment naming the only permitted literals and
   why. The structural mitigation is better than the comment: the app and the CLI
   both read the view, so a threshold added there changes two surfaces at once and
   is visible in review rather than local to a page.
2. **The report is read as a verdict on the map.** Mitigated by copy, by the
   absence of colour and grades, and by every figure carrying the sentence that
   says what would move it. Product rule 3 is the standing constraint and the
   review of this page's copy is not optional.
3. **The first report published will look bad, correctly.** If the post-015
   re-ground has not been run, every stamp on both maps is stale and the report
   will say "0 verified, 287 not re-checked" about the showcase map. That is the
   honest state and the remedy is free, but it should be known before the page is
   deployed rather than discovered on it. Falsifier 4 settles which state the
   database is in.
4. **`trace_requests.progress` is a regex scrape of stdout.** The cost figure is
   only as good as the lines the stages print, and a stage that stops printing
   `spend $X` silently drops out of the total with no error. The mitigation is the
   `run_cost_basis` text and the caveats printed beside the figure; the fix is
   #47.
5. **The chosen run may not be the run that built what is on screen.** A map
   re-traced after curation has several `trace_requests` rows and the report shows
   the most recent complete one. `runs_recorded` is published so this is visible,
   but a reader may still take the figure as the map's whole cost. The page says
   otherwise in words.
6. **The source expression is not switched when F7 lands**, and every PMC paper
   reports `source not recorded`. Named as an obligation in section 2.5 with
   falsifier 6 as its detector, and it fails loudly rather than quietly.
7. **`nodes` is JSONB written by four things** — Stage C, the workbench, and both
   restore scripts. A shape change breaks the shape figures without breaking
   anything else. `nodes_unreadable` is the detector and it is on the page, not in
   a log.
8. **Performance on the home page**, which would now select the view once per
   listed map. Both tables are in the low hundreds of rows and this should be
   unmeasurable; if time-to-first-byte moves measurably at two maps, the view is
   wrong and should be read once for all maps in one query rather than per card.

---

## 8. What is explicitly not built, and not scaffolded for

- **No stored report.** No column, no cache, no materialised view, no report in
  the JSON export, no report in a snapshot.
- **No threshold, cut-off, grade, badge, colour scale or composite score**, and no
  constant that decides how anything renders.
- **No eval harness and no golden set.** "Is this map right" needs ground truth
  and stays on `CLAUDE.md`'s OUT list. Every number here comes from the map's own
  rows.
- **No new recording anywhere.** Stage D, Stage B, Stage E and the worker are
  untouched. The three missing figures stay missing, say so, and name their
  tickets.
- **No history of a map's report over time.** A report about a past state is F4.
- **No cross-map ranking, leaderboard or "best map" ordering.** The other maps are
  printed beside the figure as reference points, in a fixed order, with n stated.
- **No public JSON endpoint for the report.** F8 has not decided what a private
  map is, and an endpoint built before that decision is the thing that leaks when
  it is made.
- **No source picker, source filter or source badge.** The per-source grouping is
  a report grain, not a control.
- **No change to the workbench.** Zero curatorial operations have been performed
  in the product's life.

---

## 9. Open questions — Product Owner only

1. **Should a visitor see what a map cost and how long it took, or are those two
   figures for you only?** The roadmap says a stranger should be able to see them;
   the site's own copy rule says no cost talk aimed at visitors, and the two
   cannot both hold.
2. **The two maps that exist have no cost or time recorded, so their reports will
   print "not recorded" in those places — is publishing a report with honest
   blanks acceptable, or should the report wait until those two figures can be
   filled?** The design's recommendation is to publish, because a blank that names
   itself is the finding.
3. **Nothing in the system counts the citation links it threw away, and the change
   you have queued next (F3) is the change that alters exactly that number — do
   you want that counting built first, as its own small piece of work
   ([#86](https://github.com/rgok001/Lineage/issues/86))?** If not,
   F3's before-and-after becomes an after-only and the 36.7% figure stays a hand
   measurement nothing can reproduce.

---

*Architect, 2026-08-07.*

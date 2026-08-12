# Lineage — the pipeline

CLASS: derived
RECOMPUTED BY: the Developer, in the same commit as any change under
`pipeline/`, or to the stage sequence in `worker/run.py`.

**Why derived, argued rather than inherited from the file this came out of.**
Almost every line below names something that moves: a script, a flag, a
threshold, a function (`_parse_or_bisect`, `expand_own_macros`, `verdict_from`,
`quote_is_grounded`), a module constant, a migration number. A commit under
`pipeline/` can make any of it false without touching a word of it, and that is
the test for the class.

The case against was real and worth stating. Roughly a third of this file is
dated measurement — the four failed calibrations, the 2026-08-01 crosstab over
all 304 papers, the 40-paper verification of the gap detector — and a dated
claim about a moment is history, which cannot go stale and must never be edited
after the fact. Labelling that `derived` invites a Developer to recompute a
number that is a record of what happened. The case fails on what those
measurements are doing *here* rather than on what they are. The progression
record and the failures already live elsewhere and keep their numbers: the
choices those runs produced are decisions 21, 23, 24 and 25 in
[DECISIONS.md](DECISIONS.md), and the failures that prompted them are incidents
10, 11 and 14 in [INCIDENTS.md](INCIDENTS.md). What is left here is the
calibration the audit runs at *today* and the evidence for why it stands where
it stands — present tense, and invalidated by the next commit that moves a
threshold. [RUNBOOK.md](RUNBOOK.md) settled the same question the same way on
2026-08-02: a measured number is derived when a code change invalidates it, and
history when nothing a code change does can touch it.

Naming `worker/run.py` in the trigger is deliberate rather than tidy. It is the
one file outside `pipeline/` that can make this document wrong, because the
thirteen-step order below is the worker's and not the letters'.

Split out of `AS-BUILT.md` on 2026-08-02, where it was section 4 and 469 of that
file's 999 lines — 47% of it, against an average of 71 for the other six
sections. It keeps its original heading, so every "section 4" reference
elsewhere in the record still resolves here. Nothing was shortened in the move.

**Reading the section numbers cited below.** They are the as-built's original
numbering, which no split has changed. Sections 1 to 3 and 5 to 7 are
[AS-BUILT.md](AS-BUILT.md); section 8 is [RUNBOOK.md](RUNBOOK.md), section 9 is
[DECISIONS.md](DECISIONS.md), section 10 is [INCIDENTS.md](INCIDENTS.md), and
section 11 was removed in favour of
[GitHub Issues](https://github.com/rgok001/Lineage/issues).

---

## 4. The pipeline

Eight lettered stages, A to H, each a standalone CLI script reading root `.env`.
The pipeline is CLI-first by rule: the worker orchestrates these same commands
and adds nothing to them.

**The worker runs a build in TWO PASSES, thirty-one steps at most, and
publishes once at the very end** (issue #192, the design on #184). The passes are
what the letters cannot show: pass one selects a corpus the way it always did and
assembles a map from it, pass two asks that map which of its papers were the
turning points and reads the recent work citing them, and the map is published
only after both. Three things that began as optional auxiliaries are part of every
trace and appear in both passes: `check_extraction.py` audits the text the
grounding check is about to rest on (incident 11), `stage_b_extract.py --reground`
recomputes the definition stamps against the text actually on disk (decision 19),
and `enrich_authors.py` fills the author metadata the export cannot invent.

```
BEFORE    save the current map (snapshot_map.py --allow-missing)
PASS ONE  select corpus, fetch papers, extract text, audit extracted text,
          extract definitions (B), cluster concept-states (C), classify edges (D),
          re-check definition quotes, ground & assemble pass one (E --no-publish),
          record what pass one read, record the papers a person named
PASS TWO  ask the map what came next (pass_two_select), fetch the nominated
          papers, extract text, audit extracted text, estimate what reading them
          costs (B --dry-run)   ← the spend gate decides here
          read the nominated papers (B), join both passes' corpora (corpus_union),
          re-cluster over both passes (C), classify edges (D), re-check
          definition quotes, ground & assemble (E --no-publish),
          record what pass two read
FINISH    record how this build's second pass ended, fill author metadata,
          score magnitude (F), compose threads (G), check each claim (H),
          record what each step of this build spent (record_spend.py),
          ground & publish (E)
```

**Nothing is destroyed before the old map is saved** (issue #173). Decision 12
refuses a second map for a concept, so a trace against a term that already has
one is a rebuild, and Stage C's `UPSERT_GENEALOGY` is where the old one starts
disappearing: it overwrites `nodes`, sets `status` back to `running`, and
`CLEAR_STALE_EDGES` takes the relationships whose meaning moved. The build's first
act is therefore `snapshot_map.py --allow-missing --result-json`, which writes the
whole row and everything hanging off it to a timestamped file under
`DATA_DIR/snapshots/`. It runs ahead of corpus selection rather than beside Stage
C for two reasons: `fetch_papers.py` and `extract_text.py` rewrite the extracted
text on disk that the live map's verified quotes were checked against, so a step
before Stage C already erodes what a snapshot is worth; and a snapshot that cannot
be taken should cost the build nothing, which here means no arXiv politeness and
no money. Once per job, not once per pass — by the time pass two re-clusters, pass
one has already overwritten the map, and there is nothing left that this snapshot
does not hold. **A failure, or a success that leaves no readable record of itself,
fails the job while the map is still untouched.** The step's own path and counts
go into the requester's progress feed. `data/genealogy_<concept>_<pv>.json` is
therefore a deliverable again rather than incident 4's improvised backup;
`docs/RUNBOOK.md` holds the restore procedure.

**Publication is one act, at the end.** Every assembly before it runs
`--no-publish`, so `status` never reaches `complete` — which since #168 is the
same thing as saying no reader can see it — while the map is still being
re-clustered underneath. It is after Stage G rather than at the end of pass two
because clause 6 of the publish invariant reads the stored threads (#171's
residue): a gate that ran before Stage G would judge the previous build's threads
over this build's concept-states and refuse a re-trace after every paid step.
Grounding again costs nothing, so the last Stage E is a free re-check plus the
publish.

**Pass two is bounded and abandonable, and every way out of it is recorded.**
Its seat count is `PASS_TWO_SEATS` or `corpus_limit // 10`; `0` disables it and
that is the only way to ask this worker for a one-pass build. Before it buys
anything, `stage_b_extract.py --dry-run --estimate-json` prices it and the worker
compares that with what is left of the ONE per-trace spend cap — not a second cap
beside it, which would be a way to exceed the first. If it does not fit, pass
one's map is published and the estimate and the remaining cap are printed and
recorded, so an abandonment is auditable rather than a silent branch. The gate
sits after fetching and extraction because the estimate is a token count over the
text on disk: what is spent before it is patience, not money.
**A pass-two stage that fails degrades to pass one** rather than failing the
build: re-cluster over the pass-one corpus (which is what #190 makes nameable),
re-classify, re-assemble, publish. Measured on the harness below, that fallback's
Stage D reused 4 of 4 classifications and spent `$0.0000`. It is never silent —
the recorded outcome names the stage that failed and the report prints it.
**An interruption is not an outcome.** A deploy's SIGTERM mid-pass-two travels
past all of this and requeues the job (#178); the resumed build re-runs from the
start, and because every LLM stage caches and `record_pass.py --pass 1` clears the
map's pass record before re-stating it, it converges on the same map rather than
adding to a half-built one.

**Stage A part 1: corpus selection**
(`corpus_select.py <concept> --limit N --field fields/K --gloss "..." --json PATH`).
Metadata only; nothing is fetched or paid for before the corpus is chosen.
`--field` scopes to an OpenAlex field (default `fields/17` = Computer Science,
`all` disables) via `primary_topic.field.id`, replacing the old hardcoded CS
*concept* filter (concepts are deprecated). `--gloss` is an optional sense
clarification used as the relevance embedding query instead of the bare
concept, so a polysemous word ("kernel") retrieves the intended sense first;
the SEARCH still uses the bare concept for recall. Wide word, tight meaning.
Seeds come from OpenAlex relevance search (an OpenAlex "concept" mode exists
but the default is search: OpenAlex has no ML "attention" concept). Seeds are
filtered by an embedding relevance check (Voyage hosted API; the concept is
embedded as a "query", papers as "documents") with
**top-K retention, never an absolute cosine cutoff**: a 0.62 threshold once
deleted "Attention Is All You Need", which scores 0.567 (rank 21 of 400)
against the query "attention". The corpus then expands one hop through
citations, and expansion is **never relevance-filtered**: Bahdanau 2014, the
origin of attention, never says "attention" (it says "align") and scores lower
than the Adam optimizer paper against the query. Ancestors enter via
citations only. Stage A is recall; Stage B is the semantic gate. Output: a
ranked corpus JSON.

**Papers a person named** (`--anchor ARXIV_ID`, repeatable, at most 3; issue
#198, accepted on the consolidated ruling on #184). The requester of a map may
name up to three arXiv ids at request time, and they enter the corpus without
competing for a seat. **An anchor bypasses selection and nothing else**: Stage B
still asks it whether it defines the term, the grounding check still applies, and
Stage D still requires a real citation link before it will draw a relationship,
so a named paper that does not belong comes back as a paper that defines nothing
and connects to nothing, and both of those are already figures on the report.

Four properties are load-bearing and each is checked rather than assumed.
**Additive**: unlike the recency reservation, which takes R of the `--limit`
seats from the general ranking, and like pass two's seats, a named paper does not
displace a paper that earned its place, so the corpus is `--limit` plus at most
three. **Once, not twice**: a paper both named and selected on merit is marked in
place and consumes nothing. **First in read order**: position in the corpus file
is read order, so a spend cap truncates from the end, and a named paper a cap
dropped would be the silent failure this feature exists to prevent. **Refused
before the first write**: every named id is resolved against OpenAlex by arXiv's
own DOI (`10.48550/arXiv.<id>`, which resolves old-style ids too) ahead of the
seed search, and an id that does not resolve stops the run by name having fetched
nothing and spent nothing. It is a lookup and never a search, because a search
returns *a* paper for a mistyped id. The corpus JSON sets an `anchor` flag on
each, so provenance survives in the artefact; `record_anchors.py` reads that key
and nothing else in the pipeline reads it at all, which is what makes "an anchor
bypasses selection and nothing else" a property of the code rather than a promise.

**Recording who named them** (`record_anchors.py <concept> --corpus PATH
[--named-by LOGIN]`). Runs on every build, anchored or not, because it also
clears what a previous build of the same map recorded: a map anchored once and
rebuilt with the field left empty must come back saying nobody named a paper.
The actor is decision 18's split — `--named-by` for the authenticated login the
app took from a session and the worker relays, and `common.actor()` written to
`named_by_asserted` for a command-line run. The report figure is on
`/g/<id>/report` and in `pipeline/map_report.py`; `docs/AS-BUILT.md` §3 holds the
columns.

**The forward hop** (`expand_forward`, `--recent-since YEAR`, `--max-forward N`;
issue #180). The backward expansion asks what the seeds *cite*, so everything it
reaches is older than the seeds by construction, and the seeds themselves arrive
sorted by citation count. Nothing asked the other direction until 2026-08-08, and
that is where the recency gap was made rather than at the ranking: measured on the
dark-energy query behind /g/17 (`indexed_in:arxiv`, `primary_topic.field.id:fields/31`,
search `dark energy`), the 400th seed by citations has **883** citations, which
almost nothing published since 2022 clears. A recent paper was never in the pool
`score()` ranks. `expand_forward` batches the seed ids 50 at a time into
`cites:<id>|<id>|…` with `publication_year:>{since-1}`, counts for each returned
work how many of the seeds it cites (`seeds_cited`, the forward analogue of
`ref_freq`, counted against the whole seed set so batching cannot change a
number), and keeps those citing at least `FORWARD_MIN_SEEDS_CITED = 2` — the same
rule and the same number as the backward hop's `n >= 2`.
**It pages under two orderings, `FORWARD_SORTS`, and the second one is the
point.** One batch of 50 dark-energy seeds has 18,725 arXiv works citing it since
2021: 94 pages and ~270MB to read whole, which no trace can afford, so it is
truncated — and the first page by `cited_by_count:desc` is 129/200 from 2021 and
4/200 from 2024-25, so a citation-ordered truncation reproduces inside the window
the very age bias the window exists to remove. Paging the newest first as well
costs one extra request per batch and is the control.
Measured on the same query on 2026-08-08 (`--recent-since 2021 --max-seeds 150
--no-relevance-filter`, 150 seeds, 3 batches, 29s wall clock including the
backward hop): **876 distinct works fetched, 504 citing 2 or more seeds, and 504
of those 504 absent from the selected 150.** The selection held **0** papers from
2021 or later and its newest was 2016, against the hop's newest of 2026. Top of
the table by `seeds_cited`: *Robust preference for Dynamical Dark Energy in DESI
BAO and SN measurements* (2024, 23 seeds) at rank 3 and *Extended dark energy
analysis using DESI DR2 BAO measurements* (2025) at rank 11 — the literature the
map was missing. The design's stated failure condition, fewer than ~50 candidates
clearing two seeds, is checked in code and printed as a warning; 504 is not near
it.
**This hop introduces no cosine threshold and filters nothing on relevance**
(decisions 3 and 4 untouched), and the backward expansion is not modified by it.
As shipped in #180 it took no seat and only printed its table; #181 then gave it
seats to fill.

**The reserved partition** (`--recent-seats R`, default `--limit //
RECENT_SEATS_DIVISOR` = **15 of 150 since #192**, 30 of 150 before it; issue
#181). It was halved when the two-stage build landed, because pass two now reads
its own 15 papers out of the same recency window and keeping 30 here as well
would pay twice for overlapping populations; it is not retired, because a build
that abandons pass two at the spend gate would otherwise publish a map with no
recent work in it at all. Same total seats, better aimed, and the floor survives.
R of the seats are competed for
only within the recency window, and a candidate must pass **two signals that can
each veto**: it cites at least two of the seeds (it is attached to this lineage)
and it ranks well on the same embedding relevance check the seeds go through (it
is about this concept). Neither is derivable from the other, and each admits work
the other should reject — the forward hop returns papers citing the 1998
supernova results as boilerplate, and a citation-sorted recency window returns
kagome superconductors and twisted bilayer graphene. Candidates are the forward
hop's `seeds_cited >= 2` set **unioned with one page of the same search
restricted to the window and sorted by relevance** (`fetch_recent_by_search`),
which is the fallback for a young field or a concept whose founding work is
thinly cited; both sets are scored on both signals, because the search hits carry
`referenced_works` too. Seats go to the top R by relevance among candidates
clearing two seeds, falling through to relevance alone among the rest only when
that set cannot fill R. **The reservation is a floor, not a cap**: a recent paper
that wins an ordinary seat on the general ranking keeps it and does not consume a
reserved one.
Ranking inside the partition is relevance rounded to
`RECENT_TIEBREAK_PRECISION` places, then **citations per year** — the one honest
use of age normalisation in this file, and the reason it is rejected as a general
ranking term: inside a five-year window every candidate is roughly equally
un-cited, so a raw count measures which sub-area is fashionable rather than which
paper fits, while across the whole corpus it would re-order a pool that contains
almost no recent papers at all.
**`filled X of R reserved recent seats` prints unconditionally**, with both
candidate counts by tier and by source, a loud line when the reservation
under-fills and a louder one below half. A reservation that cannot say it went
unfilled is a fallback with no global check: four recent papers in a 150-paper
corpus would otherwise look like a fix on every figure downstream.
**The seats are interleaved through the corpus file, not appended**
(`interleave_reserved`). Position in that file is read order — `fetch_papers.py`
fetches in it and, since #185, Stage B reads in it — so appending would mean a
spend cap dropped exactly the seats the reservation bought. The file gains two
keys per paper, `seeds_cited` and `recent_seat`, so the rebuild's proof figure
can say which seats the reservation took; the addition is additive and every
existing reader names the keys it wants.
**Decisions 3 and 4 both hold.** The reservation is another top-K taken within a
partition and introduces no absolute similarity number anywhere;
`--min-relevance` is deliberately not applied to the partition, since that is the
one place this change could have put an absolute cosine floor. The backward
expansion stays unfiltered and unmodified: decision 4 protects ancestors, which
predate the term's vocabulary, and the reserved partition is the opposite
population, written after the name settled.
Measured on the dark-energy query 2026-08-08 (`--recent-since 2021
--recent-seats 30 --max-seeds 150 --limit 150`): **30 of 30 seats filled, all
from the two-signal tier, out of 629 candidates clearing two seeds and 41 more
from the search alone.** Against the same run with `--recent-seats 0`, the
reservation displaced exactly 30 papers, every one of them from 1996-2016, and
**the corpus year range moved from 1988-2016 to 1988-2026**: the 1988 Wetterich
cosmon paper decision 4 exists to protect is still in the corpus. That is the
selection-time reading of control 1; the map-level control is #183.

**Pass two's selection** (`pass_two_select.py <concept> --recent-since YEAR
--pass-two-seats R --json PATH`; issue #191, designing #184). A second
corpus-producing CLI, and the only one that reads a map. Stage A chooses papers
before the system knows anything about the concept; this one runs *after* a
pass-one map exists and asks that map what came next. **The worker calls it as
the first step of pass two** (#192); it stays a read-only instrument that writes
files and never a row, so it can also be run by hand against a live map at any
time without touching what a reader is being served.
**What nominates: every concept-state, equally, two nominators each** — the
member with the most edges touching it in either direction, and the newest member
by year, ties broken by year then arXiv id so two runs nominate the same papers.
Per state and not per map, and the reason is F5's own reason one level up:
nominating the map's globally top papers asks "what happened next" only where the
map is already dense, which reproduces the popularity bias this line of work
exists to remove. A strand of three papers gets the same two questions as a
strand of forty. **Not Stage F magnitude, deliberately**: F, G and H run once
after pass two (Stage H roughly doubles the cost of a map's first build,
decision 17; since #202 a rebuild of it is free, but a first build is not), so
nomination has to work from what exists at the end of Stage
D — and edge degree plus recency does, with no model call. One paper can be both
nominators and a one-paper state always is; it is then listed once.
**The population is `genealogies.nodes`, not the `definitions` table**, the same
correction #190 forced on Stage D: since Stage C can be scoped to a corpus, a
definition of the concept can exist outside the map, and nominating from the
table would aim pass two at papers the map does not contain.
**The fetch is #180's `expand_forward`, re-aimed** at the map's defining papers
instead of the search seeds — same batching, same `FORWARD_SORTS` control under
two orderings, same politeness. **The gate is two signals, both binding, neither
an absolute threshold**: cites at least `FORWARD_MIN_SEEDS_CITED` = 2 of the
map's papers, and survives to the top 3R by relevance among those
(`RELEVANCE_POOL_MULTIPLE`). Top-K, not a cosine floor — decision 3 holds and
`--min-relevance` deliberately does not exist on this CLI at all. Decision 4 is
untouched: `expand_one_hop` is not called here, and this population is the
opposite one, written after the term's name settled.
**The rank inside that set is nominators-cited first**, then relevance rounded to
`RECENT_TIEBREAK_PRECISION`, then citations per year, then arXiv id. Nominator
count leads because it is the new information pass two has and pass one did not;
relevance has already done gate-adjacent work at signal 2, and ranking on it
again would build a slightly better #181 rather than a two-stage method.
**`Filled X of R pass-two seats` prints unconditionally**, with the whole funnel
beside it (fetched, cite >= 2, eligible, after the top-3R, seated), the seats'
spread across nominating concept-states, a loud line under-filled and a louder
one below half. The spread is read as **coverage** — how many nominating states
have anyone seated behind them — and not as concentration: a paper cites several
states' nominators at once, so a per-state share above half is what a healthy
spread looks like, and #184's actual worry is small strands getting nothing.
**The degraded case is a finding and it prints.** Zero candidates means no recent
arXiv work cites two of this map's papers; the sentence names the citation graph
and stops, the run exits clean, and an empty `[]` corpus file is still written so
that "pass two nominates nothing" and "the run fell over" do not read the same to
#192.
**`--stats-json` writes the funnel as a file** (#192), on every exit including the
degraded ones, because the build records the citation-graph counts either side of
the gate on the map and the report prints them: a caller scraping them out of the
funnel line above would be deciding what a map claims on a column width. Its
`state` is the one code in this strand and it stays a code — `worker/run.py` turns
it into the sentence a reader meets, so the outcome has exactly one author and
nothing between there and the page translates anything.
**The output** is a corpus file in the shape `fetch_papers.py` reads and
`stage_b_extract.py --corpus` / `stage_c_cluster.py --corpus` (#190) scope by,
plus `pass: 2`, `nominators_cited`, `nominator_arxiv_ids` and `nominating_states`
per paper, so #192 can take the union of the two passes' files. A corpus file
with **no** `pass` key is a pass-one file; nothing writes `pass: 1`, because the
absence is what every file already written says. `in_corpus_refs` is null rather
than 0 for a pass-two paper: it was never in the pool `score()` ranks, and 0
would claim a measurement nobody took.
**Cost: no LLM call, with or without `--dry-run`** — OpenAlex metadata on the
polite pool plus one Voyage batch over the gate-passers. `--dry-run` selects and
prints exactly as a real run does and writes no file.
Measured 2026-08-09 against a fixture map rebuilt from /g/17's own published
papers (79 papers, its six threads as concept-states plus one state for the
papers the export places in none, 374 relationships taken from the real citation
links across states), `--field fields/31 --recent-since 2021 --pass-two-seats 15`:
**13 nominators across 7 states; 611 works fetched over 2 batches x 2 orderings;
383 cite two or more of the map's papers; top 45 by relevance; 15 of 15 seats
filled, and all 7 nominating states have a seated descendant.** The seats are the
DESI-era line the 2016 map is missing — *Extended dark energy analysis using DESI
DR2 BAO measurements* (2025, 6 nominators), *Dark Energy in the DESI Era* (2026,
6), *Dynamical dark energy in light of the DESI DR2 baryonic acoustic
oscillations* (2025, 5), *DESI 2024: reconstructing dark energy using crossing
statistics* (2024, 3). With `--no-relevance-filter` on the same map the citation
signal alone puts *Teleparallel gravity: from theory to cosmology* first, which
is the ritual-citation admission the second signal exists to veto. **Caveat on
that reading**: there is no `VOYAGE_API_KEY` on the machine that took it, so the
relevance half ran on a deterministic hashed bag-of-words stand-in rather than on
Voyage, exactly as #181's numbers were taken; the citation-signal figures are
exact and the ordering within the top-3R is not Voyage's.

**Acquisition** (`fetch_papers.py <corpus.json>`, `extract_text.py`).
LaTeX source preferred, PDF fallback, 1 request per 3 seconds against arXiv.
Gotcha: some arXiv "LaTeX" source is really a PDF inside an `\includepdf`
stub; the extractor detects and unwraps this. Citation and cross-reference
macros are normalised before parsing: pylatexenc knows `\cite` but not natbib,
biblatex or a paper's own `
ewcommand`, and an unknown macro is dropped in
silence, taking the citation with it and stranding the punctuation around it
(section 10, incident 10). Any macro whose name contains "cite", in any case,
is folded to one mark first, so the rule covers names nobody has listed. **The
paper's own macros are expanded before that** (`expand_own_macros`, incident
11): `\newcommand`, `\renewcommand`, `\providecommand`, `\def` and
`\DeclareMathOperator` are collected with a brace-balanced scanner, their uses
substituted with arguments, the definitions themselves stripped, and the pass
repeated up to four times so a macro defined in terms of another resolves while
a self-referential one cannot spin. Expansion runs *before* the citation rule,
so a paper's own `\mycite` wrapper expands to the real citation command and then
folds to a mark. Extraction uses pylatexenc for
LaTeX and pymupdf with de-hyphenation for PDF, computes `text_title_match`,
and warns loudly below the 0.5 guard.
**Since migration 015 it also names the file it produced.** The text is written
with `newline="\n"` so the artefact is the same bytes whichever platform
extracted it (no change on the Linux worker), and `papers.extracted_text_digest`
is taken from `out.read_bytes()` *after* the write rather than from the string in
memory, because the column describes the file and not the intention. The digest
and `papers.extractor_version` go out in the same `UPDATE` as
`extracted_text_path`, which is the only statement in the repository that writes
that path and must remain so: **path, digest and extractor version are written
together or not at all.** `EXTRACTOR_VERSION` is a 12-character digest of a
curated set of the extractor's own inputs (the citation and reference macro
lists, `UNKNOWN_CITE_RE`, the own-macro patterns, `MAX_EXPANSION_PASSES`, the
bisect and minimum-length bounds, and the parser mode strings), built exactly
like `check_version()` in `check_extraction.py` and for the same reasons: not the
file, which would fire on a docstring, and not the library release strings, which
would fire on `pip install -U` while nothing on disk moved.
**The skip path is the named recomputer for the digest.** A paper already
extracted with its file on this disk is still hashed, and when the result differs
from the stored digest the run says so loudly and corrects the column, which
makes the stamps taken against the old bytes go stale. It never touches a stamp's
own digest, which would claim more rather than less, and it never writes
`extractor_version`, because a skip knows the bytes and not who made them. Cost
is one full read of the text corpus per run: ~300 files, tens of megabytes,
seconds. `--dry-run` reports what would be extracted and which digests would be
written or corrected, and writes nothing at all.

**A parse failure now costs a paragraph, not a paper.** pylatexenc raises on
some real arXiv sources (17 of attention's 146, every one an IndexError), and
`diagnose_parse.py` confirmed on 1512.08756 that it raises on the untouched
source too: not our preprocessing, and not fixable by a flag, since its
tolerant mode is already the default. The old fallback dropped the WHOLE file
to a regex that leaves braces and dollars standing and loses every heading, so
one unreadable construct cost a paper its entire text. `_parse_or_bisect` now
splits at a paragraph break and retries each half, to a depth of 6, stripping
only the piece that actually defeats the parser. Measured on a document with a
single bad paragraph: 8% stripped where it used to be 100%. A healthy paper
still parses in one pass and pays nothing.

**Audit** (`check_extraction.py [--concept C] [--sample N] [--write]`). The
extracted text is what the grounding check rests on, and its fidelity went
unmeasured until 2026-07-31. This scans for the marks damage leaves behind:
macros the parser still drops, `$`/`{`/`}` residue from a parse that fell back
to the raw strip, short inline symbols that left no trace, sections lost to a
dropped `\input`, undecodable bytes, and the punctuation an eaten token strands.
No model, no network. Macro loss is reported twice, before and after expansion,
so the fix's worth is measured rather than argued. It is a lower bound and says
so: it finds damage that leaves a mark, and the worst damage leaves none.
**Three of its signals are reported and do not decide the verdict**: `stale`,
`gaps`, and the package half of the macro count. Each is true and useful to an
operator, and none of them means what the dossier note says, which is that the
passage a reader is looking at may be missing wording (decision 25).
`--write` stores the verdict on the paper (migration 013) together with a digest
of the calibration that produced it (migration 014), and `--only-unchecked`
treats a verdict written by a different calibration as unchecked, so a threshold
change re-measures itself.
`--clear-verdicts [--concept C] [--only IDS] [--dry-run]` does the opposite and
is the only mode that needs no corpus: it removes the stored verdict, signals
and checked-at from the papers in scope so the free `--only-unchecked --write`
pass measures them again at the worker's next start. For rows whose verdict was
frozen before `extract_text.py` learned to clear its own (decision 21), and for
a machine that holds the database but not the papers. `--dry-run` prints the
tally and the range of dates it would clear, and renders a `SELECT` rather than
the `UPDATE`.
`--compare-verdicts` is the instrument for the fifth calibration, added
2026-08-01 and described under "The fifth attempt" below. It stores nothing and
refuses `--write`, `--clear-verdicts` and `--dry-run`. The fifth calibration has
since shipped, so its proposal set is empty and the mode says so rather than
printing a crosstab of no movement; the sole-cause table stands on its own and is
what the sixth round will read.

**First real measurement (2026-07-31, "embedding", 187 papers, 182 LaTeX).**
The macro fix was worth more than the incident that prompted it suggested.
**22,039 uses of the papers' own macros, across 133 of 182 papers (73%), would
have been dropped in silence before it**; 378 uses across 12 papers (7%) still
escape, mostly delimited `\def` parameters the expander declines to guess at.
Separately, 1,411 of 11,763 short inline symbols (12%) leave no trace in the
extracted text. Against that, only 10 of 187 stored quotes (5.3%) carry a
visible damage tell, which is the number that matters to a reader and the
reason the product was not obviously broken: the loss is broad across the
corpus and thin in the passages Stage B chose to quote.

The first run also invalidated this file's own thresholds. At the guessed
values, 160 of 182 papers came back "damaged", driven almost entirely by
dropped *package* macros, which this same file argues cost a reader nothing.
A verdict that fires on 88% of a corpus is not a verdict, and it would have put
a warning on nearly every paper page. Package macros can no longer reach
"damaged", and the residue bars moved from 4/30 to 25/150.

The second run then failed the same way for a different reason: 73% "suspect",
driven by a gap detector that guessed at *words* which "never" take a following
comma. On real papers it flagged "the batch size.", "And," and "a fixed number
of dimensions." as damage. It now tests shape rather than vocabulary: a space
before punctuation, an empty group, a group missing its front, a run of spaces
that tidy_marks would have closed. Those same signatures found "vectors of
dimension .", "a neural ranking model ()." and "( 200 dimensions)" in real
stored quotes, so the strictness cost nothing that mattered.

The third run failed too, and worse: 100% flagged, with gap counts in the
hundreds per paper. The structural patterns were written with `\s`, which
matches a newline, so `\s{2,}` meant "any indented line" and a paper's own
layout became evidence against it. Anchored to `\w` and literal spaces, the
same patterns find every real case from the corpus and score zero on wrapped,
indented, list-bearing text. **Whitespace that spans a line break is layout;
only whitespace inside a line can be a hole where a token stood.**

The fourth run answered the question the first three were really asking. The
marks that kept firing were fed back through the current extractor, and it
removes every one of them: it closes a space before punctuation, collapses runs
of spaces, deletes an emptied bracket pair. **A file containing them was
therefore not written by the current extractor.** The corpus on the Render disk
is text an older pipeline produced and nothing has re-extracted, so the audit
was not crying wolf and the thresholds were not the problem: it was reporting,
in the only vocabulary it had, that the fixes have never reached these files.
That is now its own signal, kept out of the verdict, because the answer to it is
re-extraction and that is a decision about the corpus rather than a warning
about a paper.

The counts never changed through any of this; only what the tool is willing to
call damage did. **Thresholds guessed against a synthetic sample are a
hypothesis, and the first real corpus is the test.** Twice now the corpus has
said the hypothesis was wrong, and both times the tell was the same: a check
that fires on most of its input is measuring itself.

**The fifth attempt does not adjust anything, it measures first**
(`--compare-verdicts`, 2026-08-01). Four rounds of calibration went 88%, 73%,
100%, 76%, and every one of them read the corpus rate, disliked it and moved a
pattern or a number. A rate can only say the check is wrong. It cannot say which
signal is wrong, so each round had to guess and find out afterwards, and the
thing that made the loop possible was that a signal had no name: it was a
sentence written for a reader, with counts in it, and nothing could group by it.

Three changes, none of which alters a verdict:

- **Every signal now carries a machine key.** A signal is `(level, key, prose)`.
  The prose is unchanged and is still what `--write` stores; the key is what the
  comparison groups by. The prose is deliberately not the identifier: it carries
  counts and percentages, and parsing it back would make every wording change a
  silent behaviour change.
- **`verdict_from(signals, demoted, source_scan)`** is the tail of `scan_paper`
  lifted out, so today's verdict and a proposed one are one implementation given
  two inputs rather than two copies that drift. `source_scan` is a parameter and
  not a convenience: without it, demoting a paper's last signal would return
  `clean` for a paper whose archive was never read, which is decision 23's
  failure reappearing in a preview.
- **`PROPOSED_NOTE_SIGNALS: frozenset[str] = frozenset()`**, a module constant
  and not a flag. One hypothesis at a time, hardcoded and reviewable, rather
  than a config file or a `--what-if` taking arbitrary thresholds, neither of
  which leaves a record of what was proposed on the day the measurement was
  taken. It is empty because the hypothesis it carried shipped the same day as
  `NOTE_SIGNALS = frozenset({"gaps", "package_macros"})` (decision 25), and
  nothing is on trial behind it now. With nothing named,
  `--compare-verdicts` prints the identity matrix and says there is no
  proposal, rather than a diagonal that reads like a finding; to preview a
  demotion, name the signals here first.

`--compare-verdicts` prints two tables and writes nothing. The cross-tab is
today's verdict against the proposal's, per source format, with the count of
papers that would carry the dossier note under each. **The sole-cause table is
the one all four previous attempts lacked**: for each signal, how many papers it
fires on and on how many it is the only reason that paper is not clean. It also
prints the quote tells twice, as counted today and with a literal `...` folded
to `…`, so that effect is previewed rather than assumed.

Two causes of near-equal size sit behind the 76%, which is why the ticket that
does the measuring is separate from the ticket that changes the calibration:
fixing either alone lands around 63% and reads as failure. The measurement that
decides it has to be taken on the Render disk, which is the only machine holding
the corpus the 76% was measured on.

**And then it was taken, and the change is what it said** (2026-08-01, Render
shell, all 304 papers). The proposal was demoting `gaps` and `package_macros`
together, and all three criteria set before the run were met:

```
  all       304 papers          proposed →
      current ↓             clean    suspect    damaged    no text
      clean                    74          ·          ·          ·
      suspect                 105         98          ·          ·
      damaged                   ·          ·         15          ·
      no text                   ·          ·          ·         12
      would show the dossier note:  now 218 (72%)   proposed 113 (37%)
```

**72% to 37%, against 38% predicted offline. Nothing moved stricter: every
occupied cell is on or above the diagonal.** The largest remaining sole cause is
`symbols` at 16 of 304 (5.3%), well under the 15% bar that would have argued for
touching it, so the change is exactly the two demotions. **No threshold moved.**

The sole-cause table is also the live demonstration of why 1a's caption had to be
corrected. `gaps` was the only reason 33 papers carried a warning and
`package_macros` the only reason for 44, which sums to 77; the joint effect is
105. The 28-paper difference is co-occurrence, and an operator who added the two
columns would have concluded that demoting both buys 77 and that demoting one
buys half of that. It buys neither.

Shipped with it, and measured in the same run: a literal `...` is folded to `…`
before the shape tests, in the paper scan and in the quote tells alike. Gap tells
in stored quotes fall from 5 to 2 and quotes carrying any tell from 11 to 10.

**The verdict now records which calibration produced it** (migration 014,
decision 25). Nothing else in the change is visible to a reader: the two demoted
signals are still emitted, still stored in `extraction_signals` (as `note: ...`
rather than `suspect: ...`) and still printed by the audit, and
`app/app/g/[id]/p/[arxiv]/page.tsx` was not touched, because `quality !== "clean"`
was already the right condition once the tiers meant the right thing.

**What was verified about the gap detector while building this** (2026-08-01,
synthetic fixtures through the real extractor, plus 40 papers fetched fresh from
arXiv to a scratch directory and deleted afterwards; that scratch corpus is
today's extractor on today's papers and is therefore a **different population**
from the 32 papers of older text on the Render disk, so no rate from it is
comparable to the corpus rate):

- `GAP_STRONG`'s paren branch fires on faithful renderings of `\left(`, `\big(`,
  `\Big(`, a literal `$( x )$` and a thin space `$(\,x\,)$`. All four extract to
  `( x` and none of them lost anything.
- Its true positives are narrower than assumed. **A bare dropped macro consumes
  the space after its own name**, so `(\dmodel dimensions)` extracts to
  `(dimensions)` and `about (\dmodel 200 dimensions)` to `about (200 dimensions)`
  — no gap in either, which is the commonest shape of the loss. The branch only
  fires when the drop leaves the space standing, which needs math delimiters or
  empty braces: `($\dmodel$ 200 dimensions)` does extract to `( 200 dimensions)`.
- The second branch, two marks with nothing between them, has ordinary true
  positives: `x, $\dmodel$, y` extracts to `x,, y`.
- A literal `...` reaches that second branch, because `tidy_marks` closes the
  space in front of the dots first: `$x_1, ..., x_n$` extracts to `x_1,..., x_n`
  and `,.` matches. `\ldots` and `\dots` already render as `…` and score no hit,
  so folding the literal form to the same character is the shape of the fix, and
  it shipped in 1b.
  **Deleting the dots instead is not**: it turns `a,..., z` into `a,, z`, which
  the same branch then matches, so it manufactures the false positive it was
  removing. Confirmed through the real extractor: `x, $\dmodel$, y` extracts to
  `x,, y` and scores a hit, which is exactly the string the deletion would
  manufacture.

**And a finding about a different signal, not yet fixed.** `tidy_marks` is not
idempotent: rule 4 deletes an emptied bracket pair after rule 3 has already
closed the spaces before punctuation, so `word ( ) .` becomes `word .` in one
pass and `word.` only in a second. The `stale` signal's premise is that these
are marks today's extractor cannot make. It can. **Measured on the 40 freshly
fetched papers: 5 of 40 carry stale marks, 25 marks in total, and a second
`tidy_marks` pass removes every one of them.** `stale` stays out of the verdict
so no reader sees this, but it is the signal behind backlog item 4's count of
32 papers holding older text, and that count is therefore an upper bound.

**Stage B: definition extraction** (`stage_b_extract.py <concept> [--corpus JSON] [--dry-run]`).
For each paper with usable text, Claude answers: does this paper give the
concept a meaning of its own? If yes it must return the defining passage
verbatim, plus section and novelty claims (structured output via
`messages.parse()` and Pydantic). Negatives are cached (migration 003).
`--dry-run` estimates cost across models without an API call, using real
`count_tokens` when a key exists and a calibrated 2.6 chars/token heuristic
when not. A spend cap (`TRACE_SPEND_CAP_USD`) aborts cleanly mid-run.
`--refresh` re-extracts papers that already have a row, UPDATEing in place: `genealogies.nodes` holds definition_ids, so a delete-and-reinsert would mint new ids and orphan the curated node membership on every map built from that concept. It nulls the embedding, because the text it encodes has changed and stale is worse than absent: absent is visible to the re-embed step, stale is visible to nothing. Scope it with `--only <arxiv ids>`, which is what an audit hands you.
`--reground` is the free half of that repair: it re-checks the quotes already stored against the extracted text as it is now and rewrites the stamp alone, leaving the quote, the embedding and everything else untouched. It calls the same matcher Stage E calls, makes no model call and needs no API key, prints the verified count before and after, and reports separately the definitions it could not check because the paper's text is not on this disk. The worker runs it immediately before Stage E on every trace, so a definition's stamp is never older than the text it describes (decision 18).
Since migration 015 the stamp is `quote_verified` plus four columns — the matched span, the digest of the bytes the match read, and the extractor version of that text — so **a row is rewritten whenever anything about the stamp moved, not only when the verdict flipped**. A row whose match was never attempted, because the paper does not define the concept or the quote is empty, is written with all four NULL rather than with a real digest: a digest is the assertion "a check ran against these bytes", and writing one from the branch that skipped the check made the row resolve to `inferred`, whose published meaning is "could not be string-matched" (issue #62). NULL renders stale, which is what an unattempted check is, and it matches what the creation path in the same file already writes. The "has anything moved?" test is derived from the values about to be written rather than spelled out beside them (issue #64): written twice, the two drifted the moment the write learned about unattempted rows, and the result was a row in the correct state rewritten on every run forever while a row carrying a wrong digest was judged unchanged and so could never be repaired by the only thing that repairs it. The old behaviour skipped a row whose boolean did not move, which after 015 would leave a re-checked stamp with a NULL digest, still rendering stale after the very run that re-checked it. The printed narrative still names only the definitions whose verdict moved, because on the first run after 015 every checkable row is rewritten and one line each would drown the ones that matter; the count of rewritten stamps is printed separately. Every existing guard is untouched: the missing, empty and unreadable branches still leave the stamp exactly as it was and count loudly (those rows keep a NULL or old digest, so they render stale rather than lying), the `checked > 1 and grounded == 0` refusal stands, and the writes are still one transaction.
`--corpus` scopes extraction to one trace's papers; without it the query takes
every extracted paper in the shared papers table, which is correct for
single-concept research use and wrong for the worker (section 10, incident 3).
**It reads in corpus rank order** (`ORDER_BY_CORPUS_RANK`, issue #185). Until
2026-08-08 both selection queries ordered by `p.cited_by_count DESC NULLS LAST`,
which is the one order this stage must not use: the spend cap aborts cleanly and
the papers left unread are whichever the ORDER BY put last, so most-cited-first
means the papers dropped are the least-cited ones — since #181 exactly the
reserved recent seats. A capped trace would have selected the recency partition,
paid for it at Stage A and then not read it, and every recency figure on the
report would have said the fix did not work for a reason unconnected to
selection. `--corpus` already carries the arxiv ids in Stage A's own ranked
order, so `array_position` reads them in it; interleaving was the alternative and
was declined here because Stage A already ranked these papers and the interleave
belongs in the corpus file (`corpus_select.py` writes the reserved seats spread
through the rank, not appended). Without `--corpus` there is no rank to honour
and the order falls back to `p.id`, the insertion order, which is some earlier
trace's corpus rank: arbitrary across concepts, but carrying no citation bias.
Verified on a throwaway PostgreSQL against the real query strings, with the
pre-change query taken from git as the control: at a cap landing after 6 of 10
papers the old order read 0 of the 4 recent seats and the new order read 2 of
them, and the `--refresh` query and `--only` both keep rank order.
**`papers.cited_by_count` has no reader in this repository as of that change.**
It is written once, by `fetch_papers.py`'s UPSERT, from what OpenAlex said on the
day the paper entered the system, and is refreshed only if a later trace happens
to fetch the same paper again — a snapshot, timestamped by the `fetched_at`
written in the same statement, and never a current figure. Selection does not
read it (`corpus_select.py` takes citation counts live from OpenAlex on every
run), and this ORDER BY was its last reader. Anyone wanting an age-normalised
number for the report must fetch citations rather than read that column.

**What prices a stage's dollar figure, and why an unpriced model now stops a
run** (issue #205). One table serves the whole pipeline: `PRICING` in
`stage_b_extract.py`, USD per million tokens, keyed by model **family**, and
`cost_usd` beside it is what B, C, D, F, G and H all add up. Two rules about the
key, both of which cost real money before they existed.
**A dated snapshot resolves to its family.** Anthropic's ids are the family plus
`-YYYYMMDD`, and Stages F and G pin `claude-haiku-4-5-20251001` deliberately, so
that a rebuild months later scores and composes with the model the map was built
from. `pricing_key` strips a trailing eight-digit suffix and prices the family,
which is how the bill works, so pinning a new snapshot of a priced family needs
no table edit.
**An unknown model raises (`UnpricedModel`) and is never priced at a default.**
Until this ticket the lookup was `PRICING.get(model, PRICING[DEFAULT_MODEL])`, so
the dated snapshot fell through to the most expensive row in the table and
**every dollar Stages F and G printed was Haiku work billed at Opus rates: five
times what those calls cost** ($0.2125 printed against $0.0425 actual on a
25-batch Stage F shape; $2.00 against $0.40 on a Stage G shape). That figure is
what the worker scrapes into `genealogies.spend_usd`, into the per-stage record
(migration 024) and into the progress feed, and it is what
`TRACE_SPEND_CAP_USD` is checked against, so the cap was tripping early on a
bill nobody owed. Each paying stage now resolves its model **before** it builds
a client or opens a connection: in Stage F it must, because `cost_usd` is called
inside the batch's own `except`, where a pricing failure would be reported as a
batch of citations the model would not score. `--reground` and `--no-label`,
which buy nothing, are deliberately outside the check.
**One rate is a function of the date.** Sonnet 5 — Stage B's shipped model,
Stage C's labels, Stage D and Stage H — bills at introductory rates of $2/$10
per million through 2026-08-31 and at $3/$15 from 2026-09-01, so `rates_for`
takes the day of the call and `INTRODUCTORY` holds the changeover. A table
holding one of those two numbers is wrong on one side of that date by 50%, and
holding only the standard pair is what it was doing.
**Figures already stored were not rewritten**: what a build printed is what that
build claimed, and [AS-BUILT.md](AS-BUILT.md) section 3 says which stored figures
to distrust and by how much.

**Stage C: clustering** (`stage_c_cluster.py <concept> [--corpus JSON]`).
**`--corpus` scopes which papers the map may hold**, the same flag and the same
semantics as Stage B's, and the worker now passes the same file to both (issue
#190). Without it a map's membership is whatever is in `definitions` for this
concept and prompt version — table state rather than the papers the run
selected — so any definition row arriving by any route joins the map at the next
clustering. That is #169 seen from the other side: there table state silently
removes a member, here it silently adds one. It is also what makes #184's pass
two abandonable, because "re-cluster the pass-one corpus" has to name a set of
papers rather than a table. The scope is an **intersection, not an assertion**: a
file naming a paper with no definition row, or one whose row says it does not
define the concept, is the ordinary case (verified: a 10-id file over 8 papers,
one of them non-defining and two of them unknown, clustered the 7 that qualified
and did not error). Absent, the formatted query is byte-identical to the
pre-change one and so is the `nodes` blob it writes from the same input, both
checked against the file taken out of git. A file that leaves fewer than two
definitions exits without touching the map and says the scope in the message
rather than telling an operator to re-run the stage that costs money (verified at
one match, zero matches and an empty file).
**Stage D does not take `--corpus` and must not**, for the reason #190 gives: its
population is `genealogies.nodes`, which Stage C has just written, and a second
independent scope is a second thing to keep in agreement. It now takes that
population as `definitions ∩ nodes` rather than as every defining definition of
the concept — before scoping existed those were the same set, and afterwards the
difference was a `KeyError` on the first defining paper outside the map
(reproduced on a four-of-eight corpus). Papers excluded that way are counted on
the stage's own first line.
Embeds definitions via the Voyage hosted API (1024-dim, cached in
`definitions.embedding`), then agglomerative clustering with cosine distance
and no fixed k. `DEFAULT_THRESHOLD = 0.28`, recalibrated for Voyage vectors on
the 134-definition `embedding` corpus; clustering granularity is a curatable
draft either way. `--embed-only` fills missing vectors and stops before clustering: Stage C writes `nodes` wholesale on conflict, so a re-run costs a curated map its labels and merges. It is the second step of the repair path after `stage_b_extract.py --refresh`, and the reason that path does not simply re-run the pipeline.
The calibration it runs at, measured on that corpus: Voyage pairwise distances
sit at p5 0.205, p25 0.273, median 0.318, and the cluster count falls 41 at
0.25, 27 at 0.28, 20 at 0.30, 8 at 0.35. 0.28 is the loosest value that still
keeps the word, graph, recommender, knowledge-graph, latent-code and
kernel-mean senses on separate nodes: 0.30 merges graph-embedding with
recommender-embedding, and 0.35 collapses 124 of the 134 into one cluster. It
over-splits weak singletons on purpose: merge is a one-click curatorial act,
un-merge is not. Stage C output is a draft for curation, not a result. Claude
labels each cluster (pennies).
**A label is cached on its cluster's membership, so an unchanged cluster keeps
the words it was given** (issue #189). Until 2026-08-09 this stage bought a fresh
label for every cluster on every run, and two runs over an identical corpus could
word the same concept-state differently — which is not only a reproducibility
defect in its own right but reaches Stage D, whose classification prompt quotes
these labels: the same pair of papers could be handed a differently-worded
question on the second run and come back a different edge type. Measured on a
throwaway PostgreSQL with the pre-change files taken from git as the control, a
six-paper three-cluster fixture and a stub model whose wording moves between
calls: pre-change, two C-then-D cycles over an unchanged corpus produced three
different labels and **5 of 5 edge types different**; with the cache, the second
cycle bought **0 labels** and every label and every classification was identical.
The key is the cluster's member definition ids, sorted, plus a digest of the
definition text each id currently holds, plus concept, prompt version, model and
the labelling prompt's own bytes. The texts are in the key beyond what the ticket
asked because `stage_b_extract.py --refresh` rewrites a definition in place and
keeps its id (verified: rewriting one definition relabels exactly its own
cluster, 1 call of 3). The cluster's *position* is deliberately not in the key —
node ids are positional, so two runs can both produce `n3` and mean different
things by it. Files are content-addressed under `DATA_DIR/label_cache`, same
never-evict posture as `data/s2_cache`; a damaged or truncated one is a miss
rather than an error (verified: six files corrupted three ways, three clusters
relabelled, no crash), and buying fresh labels means deleting the directory.
Moving one definition between clusters by hand relabels exactly the two clusters
that moved and reuses the third.
Absolute distances are model-specific, which is why the number moved and the
method did not. The previous 0.16 was tuned for bge-large when embeddings ran
locally; against Voyage it sits at the 1st percentile of the pairwise
distribution and almost nothing merges (105 clusters, 87 of them singletons).
Decision 29 corrects decision 5, which still records the old number as a claim
about its own moment.
**Stage C no longer clears the map's edges unconditionally** (decision 20). Per
edge endpoint, it compares what each node id denoted before against what it
denotes now, and removes only the edges whose concept-states have changed
underneath them; the rest are left for Stage D to replace when its swap commits.
When nothing about the previous concept-states could be read, every edge clears
and it says *that* rather than reporting a clustering change it cannot support.
A re-run at the same threshold on an unchanged corpus **with cached embeddings**
reproduces the same clustering and so keeps every edge. Not with `--force`,
which re-embeds: vectors are stored at six decimal places, so a pair sitting on
the threshold can cross it and the clustering can move. The read, the node
upsert and the edge decision are one transaction.

**Stage D: edge classification** (`stage_d_edges.py <concept>`).
Pulls references and citation contexts from Semantic Scholar (public endpoint,
disk-cached in `data/s2_cache` — answers only, failed fetches are never written
(#217); the shared anonymous pool throttles hard on
repeat runs and the client backs off through 429s). Finds citations that cross
node boundaries, then Claude classifies each into the six-type taxonomy with a
confidence score. The LLM classifies only: edge quotes are the two papers'
Stage B definition quotes, never the S2 citation context, because S2's text
comes from its own PDF extraction and will not string-match our LaTeX-derived
text. Direction convention: cited = ancestor = source; citing = descendant =
target.
**Every successful classification is cached on disk** in
`DATA_DIR/edge_class_cache`, content-addressed, same never-evict posture as
`s2_cache` beside it (issue #172); to buy fresh classifications, delete the
directory. The key **names the semantic inputs** rather than leaning on a hash of
the assembled prompt to carry them: concept, prompt version, model, the two arXiv
ids, a digest of each paper's definition text, and a digest of the citation
contexts in the order the model reads them — plus the prompt hash, which stays
because `SYSTEM` and `USER` have changed once already (migration 010 added the
rationale) and a cache that survives a prompt change serves answers to a question
nobody asked. The prompt hash also carries the two concept-state labels, which is
why #189 had to land first. An aborted run now costs wall-clock and no dollars,
which is what makes #2's atomic rebuild affordable, and it is the measurement
#184's two-stage build rests on. Consequences worth knowing: a run whose
candidates are all cached **needs no `ANTHROPIC_API_KEY`** (the client is built
only when something has to be bought), and `--dry-run` reports how many
candidates would come back free. Only a parsed answer whose confidence sits
inside 0 to 1 is ever written — caching a failure or an unusable answer would
make it permanent and free — and a cache file that is unreadable, malformed,
outside the six-type taxonomy or carrying a confidence outside 0 to 1 is a miss
rather than an error, so no file on disk can put a value in `edges` that the
column's own CHECK would refuse. A *bought* answer outside those bounds gets the
same treatment at the model boundary (#216): it is counted as unclassifiable,
printed with the value that came back, and reaches neither the cache nor the
swap — before that guard, one such answer crashed the swap with a raw constraint
error after the whole run was paid, and its cached copy was refused as a miss on
every future run, re-buying that candidate forever. The call still resets the
consecutive-failure counter, because it answered; the answer is what is
unusable.
Measured on the same throwaway PostgreSQL harness as #189, extended to 8 papers
in 4 clusters with 6 cross-cluster links: **C, D, C, D over an unchanged corpus
classified 6 and then 0, $0.0270 then $0.0000, with the two edge sets identical**
row for row including confidence and rationale. Deleting the edges and re-running
Stage D restored the same 6 for $0.0000. Re-clustering after one definition was
moved to another cluster by hand re-bought the 4 pairs touching a cluster whose
membership changed and reused the 1 pair whose two clusters were untouched. Ten
cache files poisoned five ways (unknown edge type, confidence 4.0, a boolean
confidence, truncated JSON, wrong top-level type) produced 6 misses, no error,
and every edge still inside the taxonomy.
**The rebuild is atomic** (#2). Every candidate is classified into memory first,
and the DELETE of the old edges and the INSERT of the whole new set share one
short transaction at the very end — the slow, failure-prone half (S2 fetches,
LLM calls) runs on no database connection at all, which is also what closed the
idle-in-transaction kill that reconnecting used to dodge. The swap is guarded by
an accounting identity, not a proportion: it happens only when classified +
unclassifiable + failed equals the candidate count, i.e. the run consumed its
whole list, with the degenerate zero floor beside it (at least one candidate and
not one classified aborts, in Stage E's all-reads-failed posture). A spend-cap
hit is an abort rather than a break: nothing is swapped, the run exits non-zero,
and a `running` row — only a `running` row — is marked `aborted_spend_cap`, the
first thing ever to write that status; a by-hand run against a published map
leaves its status alone, since its edges were not touched. The
consecutive-failure guard now counts consecutive failures (reset on any answered
call) and aborts at ten regardless of how many candidates already classified —
the old guard required `written == 0`, so one success out of 305 immunised the
run. And the reference sweep carries floors that measure call success, not
corpus shape (#217 — the first cut counted references returned, so a corpus S2
genuinely holds no references for, #186's young-or-niche shape, could never
complete this stage and was blamed for an outage that never happened, with an
abort message prescribing deletion of cache entries that were honest data).
`fetch_references` now distinguishes an answer with references, an honest empty
(HTTP 200 with none, or a 404 — S2 does not hold every arXiv paper, and "no
citation data for this one" is an answer), and a transport failure (retries
exhausted, any non-404 error), and **failures are never cached**: only answers
reach `data/s2_cache`, so an outage cannot replay from disk, a re-run retries
exactly the failed papers and hits cache for the rest, and the old
delete-the-cache instruction is retired. Legacy `[]` entries written by the old
code stand — they cannot be told from honest empties, and invalidating every
honest entry to chase a suspicion would cost a full re-sweep per map; an
operator who suspects one deletes that file. The transport floor aborts when a
source with at least one paper got not one honest answer of any kind — every
fetch failed, the incident-12 shape the floor was built for; a partial-failure
run instead prints one summary count line and continues, reporting rather than
thresholding. The differential arm aborts when every honest answer for one
source is empty while another source returned references — an id scheme the
call rejects wholesale — dormant today with one source, live when F7's
`papers.source` column lands. A corpus whose every answer is an honest empty
warns and continues to the honest edge-less map it produced before #2's floor
existed, now with the reason stated. Under `--dry-run` the floors still
evaluate but print their finding as a would-abort line inside the `[dry-run]`
report and the run exits 0: the dry-run contract is "estimates cost without
calling the LLM", and its exit code never depends on corpus data. Every abort
leaves the previous edges exactly as the run found them, and costs no dollars
to retry: everything classified before it is in the #172 cache.

**Stage E: grounding and assembly** (`stage_e_ground.py <concept>`).
First sweeps out any edge naming a concept-state `genealogies.nodes` no longer
contains (decision 20), before the quote re-sync and before anything is judged,
so nothing is repaired, stamped or assembled for an edge that is about to go and
the reported verified count describes the map that will actually be published.
The count is printed, and a sweep that would remove *every* edge of a map that
has more than one refuses and exits non-zero instead, on the same reasoning as
the `--reground` guard and with the same lower bound (`total > 1` there is
`checked > 1`): no edge surviving is what an empty or swapped `nodes` blob looks
like, not what a re-clustered map looks like, while a one-edge map gives "all of
them" nothing to mean and refusing there would abort a trace at step 9 of 13,
after every paid step, over one removable edge.
Then re-derives each edge's quote pair from `definitions.verbatim_quote` before
judging anything. An edge's quotes ARE the two papers' definition quotes
(decision 6); Stage D copies them onto the edge when it classifies, and that copy
can go stale. Refreshing attention's definitions against re-extracted text did
exactly that: the definitions were all correct and individually verified, the
edges still held quotes taken from the text before the fix, and grounding them
against the new text failed 77 edges that had nothing wrong with them (287 of 287
verified fell to 210). A value defined as a copy of another value must never be
older than what it copies, so it is now re-copied every run. Empty definitions are
skipped rather than blanked, so a paper that no longer defines the concept fails
honestly instead of being emptied into a pass.
The mandatory grounding check: an edge is `verified` (rendered solid) iff both
quotes are found verbatim in the extracted source text. The comparison
(`grounded_span` in `common.py`, shared with Stage B, of which
`quote_is_grounded` is now the boolean-only form) folds away exactly two
things, both of them ours rather than the paper's: whitespace, which is an
artifact of line wrapping, and citation marks, which stand where the paper had a
citation. Nothing else is folded, so a paraphrase, a dropped word or an altered
figure still fails. A raw substring test was rejecting roughly a quarter of
good quotes on where a line happened to break, and a rejection renders as
"inferred", which tells a reader the tool cannot stand behind a passage it
copied correctly; otherwise it renders
dotted and is labelled inferred, never upgraded, never hidden. Writes the
genealogy JSON export to `data/genealogy_<concept>_<pv>.json` and marks the
genealogy complete. These exports **were** the de-facto backups (section 10,
incident 4) and stopped being so with #173: the worker now snapshots a map before
it rebuilds it, and a snapshot holds the threads, the curatorial audit trail and
the definitions an export does not. An export is a deliverable, and a partial one
as a backup. Re-run Stage E after curating.
**One matcher, and it now says where.** `grounded_span` returns the half-open
character offsets of the leftmost match, or None. The unit is **Unicode code
points, as Python indexes them, not UTF-16 code units, so JavaScript must not
slice with these directly** (issue #61): they disagree for any character outside
the BMP, nothing in `app/` reads the span columns yet, and anything that starts
to converts once at the boundary. `quote_is_grounded` is that
call with the answer thrown away. Two implementations of "is this quote in this
text" would eventually disagree and the disagreement would be invisible, because
the boolean and the span would be telling different stories about the same stamp.
The span names the smallest range of whole source characters covering the match,
so a match that begins or ends inside a character whose lowercase is several
characters covers that character rather than cutting it in half. `grounded_spans`
holds that arithmetic and yields every occurrence leftmost first; `grounded_span`
is its first result, and it is what anything verifying a stored span has to ask,
because the span's contract is this arithmetic and nothing stronger (issue #63).
**A quote that folds to nothing is not grounded** (issue #57). The fold removes
whitespace and citation marks, so `"<cit.>"`, `"   "` and `"<cit.><ref>"` all
fold to the empty string, and the empty string is a substring of everything: the
pre-015 boolean said True for those and 015 would have turned that into a stored
digest and span inviting a third party to trust them, with every one of the
re-checker's comparisons satisfied by the empty match. A verbatim quote carrying
no characters of the paper is not evidence (CLAUDE.md rule 1), so the matcher
answers None. This is the one input on which the matcher deliberately does not
reproduce the old boolean, and it claims less rather than more. It reaches Stage
B, Stage E and Stage H together, because all three call the one matcher.
Since migration 015 Stage E writes eight more columns per edge — span, text
digest and extractor version for each side — and three things change with them.
**"Could not check" stops being written as "inferred":** a NULL or unreadable
text path used to return a plain false, which is a failed verdict from a check
that never ran, and it now writes a false `verified` with a NULL digest, which
renders stale. A file that read fine yields its digest even when the quote fails,
so "we read these bytes and found nothing" renders inferred and only a genuine
absence of bytes renders stale; the four causes — no path recorded, unreadable,
a quote holding no text of the paper, and a real miss — are reported separately
per side, because an edge whose file read perfectly used to print "text could not
be read" and send an operator to look at a healthy disk (issue #58).
**A whole-run refusal:** if more than one edge is checked, at least one text file
was opened, and *every* opened file failed to read, the stage refuses and changes
nothing, on the same reasoning and the same degenerate boundary as the orphan
sweep above and Stage B's `--reground` guard — that is an unmounted or empty
`DATA_DIR`, not a map that failed, and the per-edge tolerance that makes one
missing file survivable is exactly what makes a total outage invisible (incident
12). It counts *reads*, not edges: a map whose papers have no
`extracted_text_path` at all has proved nothing about the disk, and counting
those as unreadable made a small map built from the ~12 papers with no text
unable to complete Stage E, blaming the mount (issue #58).
**Every write this stage makes is in one transaction** (issue #55). The
connection is autocommit and the refusal sits after the grounding loop, so the
orphan `DELETE` and the quote re-sync `UPDATE` had already committed when it
printed "Nothing was written and every stamp stands as it was". That was not only
a false sentence: the re-sync rewrites the edge quotes and deliberately touches
none of the stamp columns, so a refused run left a new quote beside the old span,
the old digest and the old `verified`, which the page then resolved to
**verified**. The refusal now rolls all of it back and the sentence is true.
**The export and the success report follow the commit** (issue #65). The
assembled JSON is written inside the transaction to a sibling `.tmp` path, so a
commit still cannot land without the export having been written successfully, and
only the atomic `os.replace` and the summary prose happen after the commit
returns. Putting the real file and the "Genealogy complete" line inside the
transaction meant a failing `COMMIT` destroyed
`data/genealogy_<concept>_<pv>.json` — the de-facto backup (incident 4) —
replacing it with a description of a map the database does not hold, and printed
a full success report for a run that wrote nothing. **A backup must never
describe a state the database did not reach.** A crash between commit and rename
leaves a committed map, the previous backup and a `.tmp` file, which is the one
residue worth having.
**That residue is now said out loud** (issue #67). The rename is wrapped, and a
failing `os.replace` reports that the run was committed, with the same counts the
success report gives, names the `.tmp` holding the new map and the previous
export that no longer describes the database, says the repair is a rename or a
free re-run, and exits non-zero. The traceback it replaces had no success line in
it, and a traceback with no success line reads as "nothing happened" — the same
wrong inference the whole reordering was about, arriving from the other side.
Every branch reachable after the commit now has a sentence, not just the happy
one. **That report goes to stderr** (issue #75), through the same `sys.exit(msg)`
every refusal in the stage uses. It went to stdout for one commit, which left a
scripted run that logs stdout and alerts on stderr with exit 1 and nothing on the
stream it watches; the traceback this replaced was at least on stderr. **And it
carries the same two conditionals the success report carries** (issue #76): the
matched-but-not-verified reconciliation line, and the "first run after migration
015, run `extract_text.py` (no `--force`) first" advisory. Both are facts about
the run rather than about the branch it ended on, so both reports take them from
one `_stamp_caveats`. The second one also changes the repair advice: where any
edge is stale, "or just re-run this stage, it writes the same result" stops being
offered flat, because before `extract_text.py` has run the same result is the
same stale stamps. **And it says what is on disk rather than what should be**
(issue #77): both file sentences were assertions, true only of the motivating
case. A `.tmp` swept between the write and the rename raises `FileNotFoundError`,
which is an `OSError`, and the report described a complete and correct file that
was not there; a first-ever export has no previous export to be untouched. Both
paths are now tested with `.exists()` and all four combinations have their own
sentences, including the repair, which offers the rename only when there is
something to rename.
**And it refuses to publish a map that violates the publish invariant** (issue
#171, the publish half of #2). Immediately before
`UPDATE genealogies SET status = 'complete'`, and inside the same transaction, it
reads `map_invariant` for this genealogy (migration 021) and exits non-zero on
any finding, naming every one of them and pointing at
`pipeline/check_map.py`. The stage used to mark a map complete with no check on
what it was completing: #2 is the future-tense case, where a truncated rebuild
gets ratified, and #149 the past-tense one, where a map today's rules would refuse
is marked complete and serves traffic for a month. **The query is inside the
transaction so it judges the map about to be published**, seeing the orphan
sweep's `DELETE` and the grounding loop's `UPDATE`s while they are still
uncommitted, and the refusal is upstream of the commit and of the export, so
"nothing was written and every stamp stands as it was" is true. It computes
nothing: the counts and the verdict come from the view, so an Operator checking a
map by hand and this gate cannot disagree about it. A missing view is a refusal
too, with the driver's own message and the name of the migration, rather than an
`UndefinedTable` traceback nine steps into a thirteen-step run.
**`--no-publish` assembles without publishing** (#192): the status is not touched
and the invariant is not asked, because publishing is what the invariant gates. A
two-stage build grounds and assembles three times — at the end of pass one, at the
end of pass two, and after Stage G — and must be public exactly once, at the end,
or readers would be shown pass one's map and then have it re-clustered underneath
them. The counts and the export are identical on both endings; only the first
sentence differs, `Genealogy complete` against `Genealogy assembled and NOT
published`, because that is the line an operator reads to decide whether anyone
can see it.
Two consequences, both in the runbook. A **re-ground of an unrepaired map now
refuses**, which leaves that map serving exactly what it was serving and makes
the repair a prerequisite (#170 is the worked example); a full **rebuild** is
unaffected, because Stage C rewrites `nodes` wholesale from the definitions it
admits today. And **clause 6 is read against the threads the map already has**:
on a re-trace the gate sees whatever `genealogies.streams` holds, so a paper that
has left the map's membership refuses the publish until `stage_g_threads.py` has
run again. **A worker build no longer meets that**, and the repair was the whole
reason the publish moved to the end (#192): Stage G runs immediately before the
publishing Stage E, so the threads the gate reads are this build's. Stage G was
also given the map as its population rather than the definitions table, so it
cannot compose a thread over a paper the map does not hold. What remains is a
Stage E run BY HAND after a re-cluster, which still refuses until Stage G is run;
that is the sequence in the runbook and the residue #171 recorded.
**And the assembled JSON gains `stamp` per edge** (the resolved three-state
value, computed against each paper's own stored digest, so the JSON and the page
agree by construction). `verified` stays on every edge, so
`restore_genealogy.py` and the existing exports keep working. In `stats`,
`verified_edges`, `inferred_edges` and `stale_edges` are counted off the resolved
stamp, are disjoint and sum to `edges`; `both_quotes_matched_this_run` is the
stored boolean under a name that says so. They were the boolean, its complement
and the stamp, which counted a stale edge twice and summed to more than the edge
count (issue #59). The stage's own summary counts the same way, because a summary
that folds stale into verified is the same overclaim as a page doing it.

**Auxiliaries.**
`corpus_union.py --json OUT IN...`: joins the two passes' corpus files into the
one file the union re-cluster is scoped by (#192). Order is pass one's then
whatever pass two adds, duplicates keeping their FIRST position, because
`stage_b_extract.py --corpus` reads in corpus-rank order (#185) and re-ordering
the union would re-order a re-run's extraction for nothing. It exists as a file
and a command rather than a set the worker holds in memory because since #190 a
map's membership IS the corpus file, and an Operator repairing a build has to be
able to reproduce it rather than reconstruct it with `jq`.
`record_pass.py <concept> [--pass N --corpus PATH | --build … | --show]`: writes
which pass read which papers and how the second pass ended, into
`map_build_pass_papers` and `map_build_passes` (migration 022), which is what
#193's report figures read through the `map_pass_papers` and `map_pass_build`
views. It records and does not decide: every number comes from a file the run
already produced or an argument the worker printed in the feed, and the papers
come from the same corpus file Stage B and Stage C were scoped by, so the record
and the map cannot disagree about the membership. **`--pass 1` clears the map's
whole pass record first**, so a requeued or re-run build re-states what it read
instead of adding to it — that is what makes #178's requeue converge. `--show`
reads it back through the same views the report reads.
`record_spend.py <concept> [--stages JSON | --show]`: writes what each step of
the build spent, how long it took and which pass it ran in, into
`map_build_stages` (migration 024), which is what #47's report figures read
through `map_report_stages`. **It records and does not measure**: every figure
comes from the ledger `worker/run.py` writes as it goes, which holds what
`Progress` already parsed out of each stage's own stdout for the feed. No stage
was taught to account for itself and no second accounting was added, so the
per-step figures sum to the same scrape `trace_requests.progress.spend_usd`
publishes and `pipeline/map_report.py` prints both with a mismatch marker. **A
step that printed no cost line is recorded with no cost, never with zero**: most
steps of a build spend nothing, a step that stopped reporting looks the same from
here, and neither may appear as US$0.00 (#85, #87). It clears the map's whole step
record before writing, for `record_pass.py`'s reason, in one transaction. It runs
second to last in the build, before the publish, so that a failure in it stops a
build that has not published yet; the price is that the record holds neither it
nor the publish, and both surfaces therefore call the total "time in the recorded
steps" rather than the run's time. `--show` reads it back through the view the
report reads.
`workbench.py`: CLI curation (merge, rename, split-out, delete, reclassify);
every edit appends to `user_edits`, carrying `by_asserted` (decision 18): this
script authenticates nobody, so the name is what the process says about itself,
`LINEAGE_ACTOR` if set and `user@host` otherwise. The append is done in the
database with `||`, not by reading the array and writing it back, so a
concurrent web edit is not erased. The actor is resolved before anything is
mutated, because resolving it afterwards meant a failure there rolled the
transaction back after the command had already printed its success line. The web
workbench (section 6) does the same operations via Server Actions and is the
only writer of `by`. **Merging drops any edge that becomes a self-loop**: once
two states are one state, a relationship between them is not a transition.
`enrich_authors.py`: fills author lists, arXiv first and OpenAlex only as
fallback, because a stored openalex_id can be wrong while the arxiv_id was
proven by the title-match guard. Missing authors are omitted from BibTeX, not
guessed. No longer optional: the worker runs it with `--concept` after Stage E,
because nothing upstream needs authors and the export needs them absolutely. A
corpus that skips it produces a document whose `\cite` keys do not resolve, which
is how the attention map's first export came out with 14 entries for 85 papers.
`export_related_work.py`: related-work skeleton (Markdown) + BibTeX from a
curated genealogy. Real structure, real citations, real verified quotes, no
invented prose. Its edge query `LEFT JOIN`s both papers (issue #79), so a
relationship whose paper row is missing appears in the document and is marked
"not re-checked" exactly as the app shows it, instead of being dropped here while
the site counts it. Where that leaves an endpoint with no arXiv id, `edge_cite`
writes a sentence saying so rather than a `\cite`: a citation key with no BibTeX
entry compiles to a bare `[?]` in somebody's paper, which is rule 4 broken in the
one output that leaves this system. The same function covers an endpoint outside
the map's concept-states, which has an id but no key, and where `keys[None]` was
a `KeyError` waiting for the join to change.
**Its copy is the same copy the app export writes** (issue #130): the first line
says "Generated by Lineage from N papers across M meanings of the term, with K
relationships between them" rather than naming concept-states and calling itself
a skeleton, the verification sentence is #129's for the whole product, "(s)" is
gone from the document and from stdout in favour of pluralising from the count,
and the curation line says "N changes by hand applied", which is what the home
card has said since #120 and, since #138, without the stored operation names it
used to print in brackets: "delete-edge" is the machine's word for what this
document calls a relationship three lines above, and its twin in
`app/lib/export.ts` had never printed the list at all. This document goes into somebody's paper, so the
machine's voice costs more here than on a page a reader can leave.
Its per-quote not-re-checked mark was outside that sweep, because it is outside
`app/` and so outside both #129's grep and #130's list; it said "not matched
against the paper's extracted text as it now stands" and now says "not matched
against the paper's text as it now stands", matching the sentence #129 settled
for the app export's preamble (issue #135). The inferred mark beside it keeps its
em dash: it was not among #135's seven surfaces and was left rather than swept.
**It cites papers it has no BibTeX entry for** (issue #136, found while verifying
#130 and older than it): every member of a sense gets a `\cite`, including one
whose author metadata is missing, and that paper is then skipped in the `.bib` and
reported only on stdout. Same bare `[?]` as above, arriving by the route
`edge_cite` does not cover.
**Its `tex_escape` covers the ten characters TeX reserves and is byte-for-byte
the twin of `texEscape` in `app/lib/export.ts`** (issue #141, from CodeQL alert
1). It escaped `\ & % $ # _` in a chain of replaces and let `{ } ~ ^` through
raw, so a title from OpenAlex or arXiv carrying an unbalanced brace broke the
`.bib` a researcher pastes into a manuscript. Now one pass over the whole class,
so no rule rewrites another's output, and every replacement is itself
brace-balanced (`\textbraceleft{}`, not `\{`) because BibTeX counts braces to
find the end of a field and does not honour a backslash while it counts.
Measured on 12 adversarial titles through both real exporters: 12 of 12 entries
parse, each title un-escapes back to its input character for character, and no
entry gains a field; the pre-fix escaper failed 10 of the 12 and the `\{` form
lost 2 entries outright. Braces are escaped rather than passed through, so the
arXiv `{BERT}` capitalisation trick no longer takes effect; the field is already
double-braced for that purpose.
`snapshot_map.py`: the whole of one map to a timestamped JSON, before anything
rewrites it. Stage E's export holds `nodes` and
`edges`; it does not hold `streams` (threads and their claims), `user_edits` (the
curatorial audit trail), or the definitions the edges quote, which a repair
overwrites in place. Incident 4 was recovered from that export with its audit
trail lost, which is the same gap. **Since #173 the worker runs this as the first
step of every build** (§4 above), which is what stopped the export doing a
backup's job. Two flags exist for that caller: `--allow-missing`, so that a first
build of a term reports "nothing to snapshot" and exits 0 rather than failing a
build that has nothing to save, and `--result-json PATH`, which writes
`{existed, path, genealogy_id, status, nodes, edges, definitions, user_edits,
threads, bytes}` for a caller that has to decide on a file rather than parse a
stage's prose. Without `--allow-missing` a missing map still exits 1, which is the
operator's path and is unchanged. A snapshot that cannot be written exits non-zero
naming the path, and one whose record cannot be written exits non-zero saying the
snapshot itself is safe and where. Restoring is deliberately not automated: the
file is plain JSON and a restore is a decision. It prints the curatorial edits
rather than counting them, and since decision 18 it prints each one's actor with
the basis for the name: this is the forensic tool for "who changed this map", so
the answer belongs where the owner is already looking. Entries written before
decision 18 print as `actor not recorded`, which is the whole truth about them.
`restore_snapshot.py`: puts a map back the way `snapshot_map.py` found it, by id
so nothing is orphaned: concept-states, threads, **the map's `status`**, every
edge, and each
definition's quote, verdict and magnitude scores. `status` came back into scope
with #173: Stage C sets it to `running` at the moment it overwrites a map and
since #168 the app serves only `complete`, so a restore that left it standing
would hand back a map nobody can open. Whatever the snapshot recorded is what
comes back, and the run prints it, adding that the map is invisible to a reader
where the restored value is not `complete`. `user_edits` is the one thing
not overwritten; the restore appends itself to it with `||` in the database,
because a restore is an event in a map's history rather than a way to un-happen
one, and because read-modify-write on that array loses a concurrent web edit. It cannot restore the
extracted text, so a map re-extracted since the snapshot comes back with verdicts
describing a document no longer on disk: run Stage E afterwards, which is free and
re-grounds every quote against the text that is actually there.
`restore_genealogy.py`: the inverse of Stage E's export; re-inserts a
genealogies row and its edges from a JSON export and records the restoration
in the audit trail. Written during incident 4 and kept as the recovery path.
`recheck_stamp.py`
(`recheck_stamp.py --concept NAME [--arxiv ID ...] [--edges] [--verbose]`): the
independent re-checker, and the point of migration 015. The stamp columns are
only worth having if something can consume them, and this is what proves a tick
is evidence rather than a claim. **It reads `LINEAGE_READ_URL` and never
`DATABASE_URL`, and issues no statement but `SELECT`**, so it structurally cannot
re-anchor a stamp, which is the failure incident 10 named as dishonest; it is
therefore the one tool in this feature an agent may run against production. Per
stamp it recomputes the file's digest and compares it to
`papers.extracted_text_digest` (disagreement means the file moved under us) and
to the stamp's own digest (disagreement means stale), asks the matcher every
place it grounds that quote in that file and looks for the stored span among them
(absent means the span names something else), and compares the stored span with
the leftmost of those (disagreement means the match is not where we said). Those
four comparisons arrive by three different paths — the database, the disk and the
matcher — so each of them can return false.
**Checks 3 and 4 ask the matcher, not a slice** (issue #63). The first version
tested `_fold(text[start:end]) == _fold(quote)`, which is a stricter contract than
`grounded_span` grants and than its own docstring claimed: a span is widened to
whole source characters, so the slice can fold longer, and folding is context
sensitive, so a slice can fold *differently* — `"ΑΣ".lower()` is `"ας"` while
`"Σ".lower()` is `"σ"`, and the final-sigma rule fires after any cased letter,
Latin included, so `x\Sigma` out of inline maths reaches it. Spans `grounded_span`
had itself produced therefore failed, and a span mismatch is the finding that
exits non-zero "which invalidates the stamps". `grounded_spans` now holds the
arithmetic and `grounded_span` is its first result, so there is still exactly one
matcher and the verifier holds it to its own contract rather than one it
re-derived. The matcher's own sigma artefact — a quote that is verbatim in the
paper and does not ground — is untouched by this and is issue #74. **The verdict is resolved against the bytes on disk, not against
`papers.extracted_text_digest`** (issue #56): resolving against the database's
value is the comparison the application already makes without a disk, and it made
the design's own falsifier 12 — corrupt one character, re-run — print the
disk/database disagreement as a note and then exit 0 under "Every stamp examined
re-checks out". Each stamp is counted exactly once, after all four of its checks,
so a stamp can no longer be reported verified in the same breath as having its
span declared wrong. **It reports both verdicts where they differ** (issue #66):
its own, against the bytes on disk, and the reader's, against
`papers.extracted_text_digest`. Resolving only against the disk answers a truer
question than the product asks and then reports it as though it were the site's,
so with a NULL paper digest — the state left by running live-data step 2 before
step 1 — it said "every stamp re-checks out" over a corpus every page renders
stale. A disagreement is a finding and fails the run, and the message names the
ordering mistake that usually causes it. **And a fifth check asks whether any of
the four ran** (issue #78): checks 3 and 4 are both guarded on a stored span and
both guarded on a quote, so a stamp resolving verified with NULL offsets, or with
no quote, was compared to its paper by nothing at all and was then counted as
verified. That is the tool reporting its own silence as evidence, in the one tool
whose single job is that a check can return false. It fires only where the stamp
resolves verified: a true boolean with no digest is the pre-015 stamp, which
resolves stale, is displayed stale and is what the whole migration window is made
of, and an unverified row with no span is the ordinary not-grounded state. No
writer produces the row it does fire on, because Stage B sets `quote_verified =
span is not None` and Stage E writes each edge's boolean and both spans in one
statement. It reports verified / inferred / stale / span-mismatch / unchecked /
unreadable / file-moved / page-differs, exits non-zero on any span mismatch, on
any stamp nothing compared, on any file the database describes wrongly, on any
stamp a reader is not shown the same way, and on the global check (more than one
stamp examined and not one file readable), and it does not re-anchor, repair or
write. Ever.

`map_report.py`
(`map_report.py <concept> [--prompt-version PV] [--version N] [--all] [--json]`):
what a map is
made of, from the map's own rows (issue #30, `[F2]`). Every figure is selected
from migration `016`'s two views, `map_report` and `map_report_by_source`, from
migration `017`'s `map_report_by_type`, and from migration
`019_map_report_read_years.sql`'s `map_report_read_years` (issue #182), and from
migration `020_map_report_passes.sql`'s `map_report_passes` (issue #193), and
computed here not at all, so this command and `/g/<id>/report` read one
expression and cannot disagree about the same map. **`019` and `020` are joined
into the report query rather than fetched as further statements**, because their
grain is the same one row per map, so the command still issues exactly three
`SELECT`s; the joins are `LEFT` and unguarded, so a map somehow absent from either
view prints "not recorded" for those figures rather than dropping off the report,
while a missing view stops the command loudly. The app guards the same views with
`to_regclass` instead, because it is live to strangers in the minutes between
the Vercel deploy and Render's pre-deploy migration.
**Which version of its concept a map is comes from migration `025`'s columns on
`genealogies`** (issue #209), joined the same way and for the same reason, and
from a fourth `SELECT` over every `genealogies` row for the per-version table.
They are stored facts rather than figures anything computes, so no eighth view
was added for them; `app/lib/report.ts` carries the argument. The join names a
subquery exposing four columns and not the table, because `genealogies` also
carries `concept`, `prompt_version` and `status`, which `COLUMNS` names bare, and
joining the table makes all three ambiguous. The command's own "Which version this
is" section prints the version, whether it is current, when it was replaced, the
hand edits on that version, and both the published count and the count including
builds that took a version number and never published — the second of which is
the Operator's half and has no equivalent on the page, along with the `status`
column on the table of every version. **The command's reference points are every
map in the database, published or not and current or superseded, and its opening
paragraph now says so**: `/g/<id>/report` compares against one map per term, so
the two surfaces print the same figures for a map they both show and can print a
different `n` beside them, which is the same deliberate divergence #194 recorded.
A concept can now name more than one map, so naming one reports every version of
it in version order unless `--version N` picks one; `--json` still emits exactly
one object for a named concept — the current version, with a note on stderr
saying which was chosen — because the flag decides the shape and the data never
does (#93).
The years block prints both series: everything from `earliest year` to `papers
with no year` is over the papers that define the term, and `oldest paper read`,
`newest paper read`, `papers read with no year`, the two `recent window` years
and the two window counts are over every paper read. The per-year bar shows both
at once, `#` for a paper that defines the term and `-` for one read that did not,
so the tail of the bar is the gap between the two populations.
`The two passes` is its own section (issue #193): which pass of the build read a
paper, and, under it, **#188's free half** — the defining rate over what the
second pass read, banded by ten of selection rank, with the band width stated and
each band carrying its own first and last rank. That ladder prints here and on no
other surface, because it answers a question for whoever sets the seat count and
not for somebody reading a map. The section also prints the two falsifiers rather
than leaving a reader to add up: the ranked papers against the papers the second
pass read, and `papers read = N in the first pass + N in the second + N in
neither`, each marked when it does not match. **The figures are drawn for a map
whose build recorded itself in passes and for no other** — migration `022` (#192)
points `020`'s two seam views at `map_build_pass_papers` and `map_build_passes`,
so a map built before that, or built in one pass on purpose, has no build record;
`passes the build recorded` prints its own words,
"nothing recorded how this map was built", rather than the conclusion drawn from
its own absence. **It reads `LINEAGE_READ_URL`
and never `DATABASE_URL`, and issues no statement but `SELECT`** — the second
tool in this pipeline built that way, and for `recheck_stamp.py`'s reason: its
value is that an Operator can run it against production and paste the answer into
a report, which is only safe if it structurally cannot write. It does not repair
and there is nothing to refresh, because a view holds no data.
It commits, and the docstring says so. `with psycopg.connect(...)` commits on the
way out of the block, which is what psycopg's context manager does; the commit
carries nothing because the transaction holds three `SELECT`s (two before #162
added the kinds of link), and it is left alone
rather than rewritten into a rollback, because the guarantee rests on the
read-only role and the statements issued rather than on the transaction's shape
(issue #93). `recheck_stamp.py` does the same.
`--all` prints every map, which is how the reference points beside each figure
are read from a shell. **`--json` goes to stdout and to no file**: a report
written to disk is a stored quality figure with a different spelling, and would
survive the curatorial edit that invalidates it. **Its shape follows the flag and
never the row count**: `--all --json` is a JSON array, of one element if the
database holds one map, and a named concept is a JSON object. It used to switch
on `len(chosen) > 1`, so `--all --json` returned an object against a database
with one map and an array against a database with six, and any script reading it
broke the day a second map was created (issue #93). Numbers arrive as strings in
the JSON rather than as floats, because they are exact values out of Postgres and
turning a count or a spend into a binary float on the way out would be this
command inventing a number.
It prints **every** figure, where the page prints a reader's tier of them, and
the page's labels are a subset of this command's with identical wording wherever
both print a figure (the UX review, issues #107 to #113; the equality this
sentence used to claim was deliberately relaxed then and this line had not
caught up). So a label rewritten on the page is rewritten here in the same
commit and in the same words: issue #124 moved "papers with a reading" to
"papers read", "distinct quote strings" to "different quotes the map stands on",
"distinct papers on relationships" to "different papers on relationships", and
"most reused quote, uses" to "times the most reused quote appears", and renamed
three sections. The subset widened again with issue #132, which cut the whole
"The evidence behind the map" section from the page and left all three of its
figures printing here: the page now says what they add up to in one sentence, and
the Operator keeps the counts. Issue #134 did the same to Shape's pair rows,
cutting "pairs of meanings that are linked" and "pairs carrying more than one
kind of link" from the page and renaming the two that survive to "relationships
between meanings linked in more than one way" and its share, here and on the page
together. That rename widens `LABEL_WIDTH` from 52 to 70, which is computed and
not written down. **Three section titles are read back by `render()`** to decide
whether to print the By source table, the Kinds of link table and the
papers-per-year histogram, so a
rename in `SECTIONS` that is not made there too loses a whole block in silence.
The Kinds of link block (issue #162) sits under Shape, where the page puts it,
and prints every kind the view returns in the view's own order with a `total`
line beneath, so the identity the page states in a sentence is arithmetic an
Operator can see: the total carries `<- DOES NOT MATCH typed relationships above`
when it does not. A map with no relationships prints one sentence instead of six
zero rows, and that branch is on the map's relationship count rather than on
whether the view returned rows, because the view returns six either way and
printing them put the absent words "no relationships" through a ten-column field
as `0no relationships` on the first run of it.
The absent words are the same on both surfaces as well — "not recorded" when
nothing in the system
holds the figure, and the name of the empty population ("no relationships", "no
years recorded") when the denominator is zero. Neither is ever a zero: `run_cost_usd`
in particular is NULL when no run recorded a spend, and `genealogies.spend_usd`,
which reads `0.0000` on every map and is written by nothing, is never consulted
by the view, by this command or by the page. There is no threshold, cut-off,
grade or colour in it, and the sample size beside the reference points is the
number of rows the view returned rather than a literal.
Unlike the page, it prints the cost figure unconditionally: it needs the
read-only role's connection string to run at all, so its reader is the Operator
and never a visitor.

`check_map.py`
(`check_map.py <concept> [--prompt-version PV] [--all] [--json]`): whether a map
still satisfies the rules of the stages that built it (issue #168, the missing
piece named in #149 and the publish half of #2). The six clauses are migration
`021_map_invariant.sql`'s two views and this command computes none of them, so it
and Stage E's publish gate cannot hold a different opinion about the same map.
**It reads `LINEAGE_READ_URL` and never `DATABASE_URL`, issues no statement but
`SELECT` and repairs nothing** — the third tool built that way, for the reason
`recheck_stamp.py` and `map_report.py` are: an Operator has to be able to point
it at production. It commits on the way out of the `with` block, carrying nothing,
for the reason given above.
**The exit status is the verdict**: 0 when every map asked about satisfies all
six clauses, 1 when any does not, taken from the view's own boolean rather than
from anything worked out here, so the answer cannot come from the value the tool
was supposed to be independent of. Every finding names the concept-state, the
relationship or the thread it is about and says in words what is wrong with it,
because its reader is whoever has to repair it; the six clause sentences come
from the view, so they are written down in the migration and nowhere else.
`--all --json` is **always** a JSON array — of one element against a database
holding one map, and `[]` against one holding none, which is the degenerate case
the shape promise is only as strong as (issue #93). There is no threshold, grade
or score in it and there must never be one: a map either satisfies every clause
or it names what it violates.

**Stage F: magnitude** (`stage_f_magnitude.py <concept> [--prompt-version PV]`).
Fills `definitions.attention` and `definitions.displacement` (migration 011),
which is what the influence map selects and sizes by. Attention is on-term
weighted uptake: not a raw citation count, which rewards famous-but-incidental
work, but each corpus-internal citation scored 0-2 by the model for whether the
citing sentence engages that paper's contribution to *this* term, weighted by
S2's citation intent. It reads the S2 cache Stage D populates, so it must run
after D. Displacement is the cosine distance of a paper's definition embedding
from the centroid of every earlier definition, marking turning points that
attention structurally misses (a paper that moves a term is cited by the field
it moved into, not by this corpus). The two were measured uncorrelated on
`/g/10` (Spearman +0.05), which is the point: they answer different questions
and neither substitutes for the other. Every paper gets an attention number
including zero, because the map selects on `attention IS NOT NULL` and a null
would drop a paper off the map rather than rank it last. Displacement is null
for the earliest paper, which has nothing to be displaced from.

**Stage G: threads** (`stage_g_threads.py <concept> [--prompt-version PV]
[--threads N]`). Fills `genealogies.streams` (migration 012) in two phases:
detect the threads and assign every paper to one, then compose each thread's
account. The target count scales with the corpus (`papers / 18`, clamped to
4..9) and is a guide rather than a range: a hardcoded "6-9" asked the model to
fill a quota and it returned 9 every time, which was right for embedding's 134
papers and too many for attention's 85. The prompt also refuses a thread for
work *about* the concept (surveys, interpretability) as opposed to development
*of* it. It reads the
corpus's content (definitions and novelty claims), not its citation topology,
which is why it is a stored artifact rather than something derived at render
time. **It generates no quotes.** An earlier version asked for a verbatim
fragment per paper and stored it, and the model returned paraphrase, which the
thread page then rendered under a verified stamp (section 10, incident 8).
Evidence is not regenerated: the app reads `definitions.verbatim_quote`, the
span Stage E actually matched.
**Its population is the MAP, not the definitions table** (#192), the same
correction #190 forced on Stage D and #191 made in nomination, and here it is
load-bearing rather than tidy: a definition of the concept can sit outside this
map — a re-trace with a smaller corpus leaves them, and so does the two-stage
build's fallback, where pass two reads papers and the map is then re-clustered
over pass one alone — and a thread naming one of those is exactly what clause 6
of the publish invariant refuses. Unscoped, the build would refuse its own
publish over threads this stage had just written. The papers dropped are counted
on the stage's own line, in Stage D's words.
**The blob it writes is shared with Stage H, and the write has a floor** (#3).
`genealogies.streams` also holds every paper's claims, so an unconditional
overwrite here used to destroy them along with the previous accounts whenever it
ran — a run where phase 1 succeeded and every phase-2 call failed stored threads
with every paper bare and took about a Stage H run's spend to restore. Two
protections now: the stage refuses to write when not one thread got an account
(the degenerate zero floor, in the posture of Stage E's all-reads-failed
refusal — a broken call, not a thin map; the stored threads and claims are left
untouched), and each paper's stored claims are carried into the new blob before
the write, with a line saying how many travelled and how many belonged to papers
no longer in any thread. Claims may be carried across a membership reshuffle
because a claim depends on the paper and on nothing else — the fact #202
measured and recorded at the claims cache — and every carried stamp is
re-grounded by Stage H the next time it runs *where the paper's text can be
read*; a carried stamp whose paper has no readable text meets no check in
either of Stage H's modes, which is why the stamp records what it was checked
against and the render path resolves it (#215) rather than trusting the carry. A thread whose account fails while
others succeed still keeps its papers bare until a re-run, as before: the floor
is at zero accounts, not a proportion nobody could defend.

**Stage H: claim-level evidence** (`stage_h_claims.py <concept> [--thread SID]`).
Asks each paper for 2-4 things it did for the term, each with the passage that
shows it, then checks every passage against our own extracted text with
`quote_is_grounded`. A claim whose passage fails keeps the claim and loses the
stamp, saying plainly that nothing was matched, rather than disappearing and
narrowing the account in silence. Written into the existing threads rather than
generated with them: thread membership is non-deterministic, so re-running
Stage G to improve prose reshuffles which papers sit where, and evidence should
be regenerable without disturbing a shape a curator has judged. It is the second
most expensive stage after extraction and roughly doubles what a map costs,
which buys the difference between an account a reader must trust paragraph by
paragraph and one they can audit sentence by sentence.
**Every parsed answer is cached on disk** in `DATA_DIR/claims_cache`,
content-addressed, same never-evict posture as `edge_class_cache` (#172) and
`label_cache` (#189) beside it (issue #202); to buy fresh claims, delete the
directory. The call depends on the paper and on nothing else — not on the map's
shape, not on thread membership, not on anything a rebuild changes — so before
this, every rebuild re-bought every claim at about $3.00 a map, and decision 38's
"restarts are cheap, since every LLM stage caches per paper" was false here.
Decision 39 records the correction and says plainly that Stages F and G still do
not cache. The key **names the semantic inputs**: concept, prompt version, model,
the arXiv id, a digest of the exact text sent (the post-`TEXT_BUDGET` slice, not
the whole file, because the tail the model never saw cannot have moved its
answer), plus the prompt hash, which stays for #172's reason. **The stamp is not
in the cache and cannot be**: a record holds only the claim text and the passage
as the model returned it, and `verified` is recomputed at load by grounding that
passage against the extracted text as it is on disk now (decision 30, issue #57 —
a stamp must never outlive the check that made it). One grounding path serves a
freshly bought answer and a cached one, so a cached claim is indistinguishable
from one bought a second earlier. Only a parsed answer is written; a file that is
unreadable, malformed, or not a list of `{text, quote}` strings is a miss rather
than an error, so nothing on disk can put a claim into `genealogies.streams` that
generation would not have produced. A run whose papers are all cached **needs no
`ANTHROPIC_API_KEY`** (the client is built only when something has to be bought),
and the stage prints its hit and miss counts and the dollars the hits avoided —
read back out of the records, which store the tokens the calls actually used, so
the saving is what was paid rather than a model of it.
Measured on a throwaway PostgreSQL with a stubbed model whose wording moves on
every call, 6 papers in 2 threads, one with no extracted text: **two runs over
unchanged input bought 5 then 0, `$0.1725` then `$0.0000`, claim for claim
identical in text, quote and stamp.** Rewriting one paper's text within
`TEXT_BUDGET` re-bought that paper and only that paper (4 of 5 from cache);
rewriting another paper's text beyond `TEXT_BUDGET` re-bought nothing, because the
model never saw that text, and its stamps were re-checked against the new file.
A record whose passage no longer appears in the paper loads with the claim's text
kept and its quote and stamp dropped, which is what generation would have done
with it, and so does a passage that folds to nothing (`<cit.>`). Ten cache files
poisoned five ways (not a list, missing `quote`, a non-string `text`, truncated
JSON, wrong top-level type) produced ten misses, no error, and every claim still
inside the shape the thread page renders. An unparsed response is not cached, so
the next run buys it again rather than serving a failure for free.
**Stage H inherits the empty-fold rule** (issue #57), because it calls the same
`quote_is_grounded` every other stage calls, and that is the point of there being
one matcher. A claim whose passage is only citation marks or whitespace used to
check out, since the empty string is a substring of everything; it now does not,
at generation and on `--recheck` alike. The direction is safe on this page
specifically: the thread page renders a claim's quote only under a resolved
verified or stale stamp, labelled as such, so such a claim loses its stamp and
its quote and keeps its text, which is exactly what the stage already does with
a passage that fails.
**Every claim stamp names the bytes its check ran against** (#215, decision 30's
rule extended to the third stamp population — this closes what was open question
2 in the 015 design). Both grounding paths — generation's `ground()` and
`--recheck` — read the text through `read_grounding_text` like every other
grounding stage and write `checked_against`, the digest of the exact bytes read,
beside every stamp, failed checks included. It is computed at the check and
never copied from `papers.extracted_text_digest`; the two are written by
different code at different moments, which is what lets the thread page's
`stampOf` comparison return false. The page resolves each claim against the
paper's current digest: equal digests render the stored verdict (verified, or
inferred for a check that ran and failed), and a differing or absent digest —
every claim stamped before #215, and every paper whose text this system cannot
read — renders stale, never verified. A paper with no readable text is skipped
by both modes exactly as before, its stored stamps untouched (a stamp is a
by-product of a check, and no check ran), and the run prints the skipped
papers' ids so an operator knows which claims will render stale. No migration:
`genealogies.streams` is JSONB, and blobs without digests are simply stale.
`--recheck` re-grounds the stored quotes without asking the model for new ones,
and costs nothing; re-extracting a corpus now leaves every claim stamp rendering
stale until a Stage H pass re-checks it, rather than silently asserting a check
that ran against a document no longer on disk. A claim that stops checking
out keeps its text and loses its stamp and its quote, which is what generation
would have done with it. Regenerating instead would cost $4-6 to rewrite prose
that was never the problem.

Stages F and G were one-off scripts hardcoded to the showcase map until 2026-07-29, which
meant no other map could have a front door. They are stages now, the worker runs
them after Stage E, and both were proven on a second concept (`attention`,
`/g/13`) before being committed.

---

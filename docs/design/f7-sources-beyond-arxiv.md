# Design: sources beyond arXiv

**Ticket: [#35](https://github.com/rgok001/Lineage/issues/35) `[F7]`.** Written
2026-08-06 against `master` @ `3bf51fd`.

**Status: proposed, awaiting the Product Owner.** Nothing here has been built.
The author held `LINEAGE_NO_DB=1` throughout and touched no database; every
count about the live system is quoted from `docs/AS-BUILT.md`, `docs/ROADMAP.md`
or issue #35, and every count about an upstream API was taken by live HTTP
against that API on 2026-08-06 and is shown with the request that produced it.

**BUILD IS GATED ON F2 ([#30](https://github.com/rgok001/Lineage/issues/30)),
WHICH HAS NOT SHIPPED.** `docs/ROADMAP.md` keeps "Non-arXiv sources before F2
ships" on the will-not-build list, and this document does not ask for that to be
relaxed. A source whose text extracts badly produces maps that fail grounding
rather than maps that are merely thinner, and until the map reports its own
verified fractions there is no instrument that can tell those two apart.

**What F2 must additionally provide before this may ship.** #30 as ticketed
reports one row per map: verified fraction of definitions and edges, distinct
quote strings against edge count, discarded citation pairs and why, corpus year
distribution, cost and wall clock. It carries **no source dimension**, correctly,
because today there is one source. F7 needs at minimum the **verified fraction
of definitions and of edges, grouped by `papers.source`**, and the discarded-pair
counts grouped the same way. That belongs inside #30, not here: a report that
gains a dimension after the fact reports two different things under one name, and
the before-and-after comparison this design rests on would then be comparing a
per-map number against a per-source one. Recommend amending #30 to add the
grouping while it is still being built. **No threshold on those fractions**, per
#30's own reasoning and decisions 24 and 25 — the numbers are published beside
the arXiv maps as the only reference points, labelled with their sample sizes,
and the decision to ship is the Product Owner's.

---

## 1. The problem, restated

Lineage reads arXiv and nothing else, so it maps machine learning and adjacent
preprint fields and is useless to a clinician, a chemist or an epidemiologist.
Every other limit in the product makes a map worse; this one decides whether a
map can exist at all. The Product Owner took non-arXiv sources off `CLAUDE.md`'s
OUT list on 2026-08-02 and filed them as F7, sequenced after the map report so
that the effect of a new source on extraction quality is measured rather than
assumed. What is wanted is a second source that can be read, quoted and verified
to the same standard as arXiv, and an honest answer to the question the ticket
asks: does this pipeline generalise beyond LaTeX?

---

## 2. The design

### 2.1 One source: PubMed Central full text, through Europe PMC

Integrate **PMC open-access full text, fetched as JATS XML from Europe PMC**, and
nothing else. The candidates were:

- **OpenAlex `locations` / Unpaywall / DOI-resolved publisher PDFs.** The
  metadata is already in hand — `corpus_select.py` selects `locations` in
  `WORK_FIELDS` and `arxiv_id_of()` already reads `loc.pdf_url` — so this is the
  cheapest plumbing. It is also the worst possible first answer to the ticket's
  actual question. Its text arrives as PDF from several hundred publisher hosts
  with no shared layout, no shared rate-limit policy and a long tail of scanned
  images. Issue #35 records that all 7 PDF-sourced papers in the current corpus
  are treated by the extraction audit as a separate and worse population. Ship
  this first and the measurement "did the pipeline generalise?" is confounded by
  PDF quality, which we already know is bad. **Rejected as first.**
- **ACL Anthology.** PDF only, and its ML content already overlaps arXiv heavily.
  Costs the same as PMC and opens no new discipline. **Rejected.**
- **PMC, as JATS XML.** One host, one documented API, a stable identifier, an
  entire discipline that arXiv does not serve, and — the reason it is first —
  **its text is structured rather than laid out.** JATS → text is a tree walk of
  the same kind as LaTeX → text, not the layout reconstruction that PDF forces.
  If the pipeline generalises beyond LaTeX, PMC is where that shows cleanly; if
  it does not generalise even here, we learn that for about two dollars instead
  of learning it confounded with hyphenation and column order. This is also the
  direction the public roadmap page already names. **Chosen.**

**Through Europe PMC rather than NCBI.** Verified live on 2026-08-06:
`GET https://www.ebi.ac.uk/europepmc/webservices/rest/PMC5334499/fullTextXML`
returns a JATS 1.4 document in one request, no tarball, no S3, no unpacking.
`GET https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:"..."&resultType=core&format=json`
returns `pmcid`, `isOpenAccess`, `inEPMC`, `hasPDF`, `license` and
`firstPublicationDate` for a DOI, which is the resolution step and the licence
check in the same call. NCBI's own OA Web Service returns `.tgz` packages and
**its legacy API is withdrawn on or after 2026-08-24** (stated on
`pmc.ncbi.nlm.nih.gov/tools/oa-service/`, read 2026-08-06). Do not build on
`oa.fcgi`; it has under three weeks to live. Boring tech here means one GET
returning one document.

**A negative finding that changes the resolution path.** OpenAlex cannot be asked
which of its works are in PMC. Measured 2026-08-06:
`filter=has_pmcid:true` returns `meta.count = 0`, while `filter=has_pmid:true`
returns `meta.count = 40,659,111` and populates `ids.pmid`. So the selector
filters on `has_pmid:true` plus the existing field clause, then resolves
PMID or DOI to a PMCID through the Europe PMC search endpoint. That is one extra
round trip per candidate, batched with `OR` in the query, and it costs time, not
money.

### 2.2 Paper identity

**The spec is wrong about where the arXiv id is load-bearing, and this matters.**
`CLAUDE.md` says the Stage B cache is "keyed by arXiv ID + prompt version". It is
not: `definitions` is `UNIQUE (paper_id, concept, prompt_version)` on the
`BIGSERIAL`, confirmed in migration 001 and in `docs/AS-BUILT.md` §3. **The Stage
B cache is already source-agnostic and needs no change at all**, and decision
27's commercial property rests on that key, not on arXiv. What is actually
coupled to the arXiv id is everything that *formats* it: the raw and text file
stems (`aid.replace('/', '_')`), the Semantic Scholar key
`f"{S2}/paper/arXiv:{arxiv_id}/references"`, the arXiv API `id_list` in
`enrich_authors.py`, the URL `https://arxiv.org/abs/${p.arxiv}` on the evidence
page, the route segment `app/app/g/[id]/p/[arxiv]`, the BibTeX
`eprint = {…}` / `archivePrefix = {arXiv}` pair in `app/lib/export.ts`, and the
`members: [{arxiv_id, year, title}]` shape stored inside `genealogies.nodes`.

The identity model is therefore **source-qualified, DOI-carrying, and additive**:

Migration `016_paper_source.sql`:

- `papers.source TEXT NOT NULL DEFAULT 'arxiv' CHECK (source IN ('arxiv', 'pmc'))`
- `papers.source_id TEXT` — the arXiv id or the PMCID.
- `papers.doi TEXT` — nullable, recorded from OpenAlex or Europe PMC, never
  minted.
- `papers.license TEXT` — nullable, from Europe PMC `license` for PMC rows, NULL
  for arXiv rows. Section 5 says why this is not decoration.
- `UNIQUE (source, source_id)`.
- `papers.arxiv_id` **keeps its `UNIQUE` and loses only its `NOT NULL`.** Postgres
  unique indexes do not collide on NULL, so PMC rows leave it NULL and every
  existing query, join and index is untouched.
- `source_format`'s check widens to `IN ('latex', 'pdf', 'jats')`.
- Backfill: `UPDATE papers SET source_id = arxiv_id`. This is an honest backfill
  and the contrast with migration 015 is deliberate — 015 refused to fill a stamp
  column because that would have turned unproven verdicts green. `source_id`
  copies a fact the row already asserts about itself, and no verdict changes.

**DOI is a resolution key and not the identity key.** arXiv preprints carry
`10.48550/arXiv.*` DOIs that our rows do not store, OpenAlex frequently hands
back the *published* version's DOI for a preprint, and some works have none.
Making DOI primary would collide a preprint with its journal version and would
make identity depend on the least reliable field OpenAlex serves us — the same
field that, per decision 28, has attributed `cond-mat/0308217` to a psychologist.

**One paper reference, two languages.** Add `paper_ref(source, source_id) ->
"arxiv:1706.03762" | "pmc:PMC5334499"` to `pipeline/common.py` and
`app/lib/paper.ts`, with the parse in each, and a legacy rule: a bare string with
no `:` prefix means arXiv. That single rule keeps every stored `arxiv_id` in
`genealogies.nodes`, every existing `/g/<id>/p/<arxiv>` link and every bookmark
alive with no redirect table. The route directory renames to `[ref]`.

**`genealogies.nodes` is JSONB holding live curated maps, so it is not rewritten.**
Stage C starts writing `members: [{arxiv_id, ref, year, title}]` — `ref` added,
`arxiv_id` retained for arXiv papers and absent for PMC ones. Every reader goes
through `refOf(member)`, which prefers `ref` and falls back to `arxiv_id`. Old
maps keep working because absence is the arXiv case.

**A work is fetched from at most one source, and arXiv wins.** `corpus_select.py`
today dedups the pool on the arXiv id (`pool[aid]`) and *drops* every work with
no arXiv id, which is the arXiv-only rule expressed as a filter. Change the pool
key to the OpenAlex work id — which the file already treats as identity in
`expand_one_hop` and `ref_freq` — and then choose one fetch route per work: arXiv
if `arxiv_id_of(work)` is not None, else PMC if a PMCID resolves and its licence
qualifies, else drop. This is the answer to the ticket's "may a map mix sources":
**a map may mix, a paper may not.** Without it the same article enters as a
preprint and as a journal version, Stage C puts its two definitions in different
clusters, and Stage D draws an edge from a paper to itself.

`--source` on `corpus_select.py` defaults to `arxiv` and takes `arxiv`, `pmc` or
`arxiv,pmc`. The default means no existing invocation changes behaviour.

### 2.3 Text extraction, and what it does to grounding

New `jats_to_text()` **inside `pipeline/extract_text.py`**, not in a new module,
for the reason in the next paragraph. It walks the JATS tree and emits:
`<article-title>`, `<abstract>`, and `<body>` `<sec>`/`<title>`/`<p>` in document
order; drops `<table-wrap>`, `<fig>`, `<ref-list>`, `<back>`; and — the load-bearing
detail — maps `<xref ref-type="bibr">` to `CITE_MARK` (`<cit.>`) and
`<xref ref-type="fig|table|sec|disp-formula">` to `REF_MARK` (`<ref>`). Those are
the two marks the LaTeX path already emits and the two that `_MATCH_MARK` in
`common.py` folds away before a quote is matched. **Emit the same marks and a PMC
quote grounds by exactly the rule an arXiv quote grounds by**, with no second
matcher and no per-source grounding logic. That is the whole compatibility claim
and it is checkable in section 4.

Math is where a JATS extractor silently loses. Prefer `<tex-math>` when the
article carries it and run it through the existing `latex_to_text`; otherwise take
the MathML element text. Dropping it reproduces incident 11 in a new dialect: a
quote reading "vectors of dimension ." grounds against nothing and leaves edges
inferred.

**`EXTRACTOR_VERSION` must split per format, and this is not cosmetic.**
`extract_text.py` computes one module-level digest over the LaTeX macro lists,
`UNKNOWN_CITE_RE`, the bisect constants and the parser modes, and writes it for
every paper. Add JATS inputs to that one digest and every LaTeX-side commit
reddens the PMC re-extraction queue and every JATS-side commit reddens the arXiv
one — a detector that fires on nearly all of its input has stopped measuring its
input, which this project has paid for four times (decisions 24, 25, 29). Leave
JATS out of it and a JATS extractor change queues nothing. So:
`extractor_version(fmt)` returns `"latex:<12 hex>"`, `"pdf:<12>"` or
`"jats:<12>"`, each a digest over the curated inputs that decide *that* format's
text plus the shared normalisation constants. The namespace prefix keeps
`WHERE extractor_version IS DISTINCT FROM <current for that format>` meaningful,
and it stays what decision 30 says it is — provenance and a re-extraction queue,
never an invalidator.

Splitting the digest changes the stored `extractor_version` of every existing
paper on its next real extraction. It does **not** touch a single stamp: the same
code over the same bytes produces the same file, so `extracted_text_digest` does
not move, and per decision 30 the stamp is anchored to the bytes and not to the
extractor. Section 4 states the reading that would falsify that.

**What PDF-free does not buy.** JATS is structured, but Europe PMC's OA subset is
not uniformly rich: some articles carry only `<abstract>` and no `<body>`.
**Those papers are dropped from the corpus, not fetched as PDF and not read from
their abstract.** Two reasons, and the second is the sharper one. Product rule 1
requires a verbatim quote from each paper, and a quote taken from a 200-word
abstract cannot support a claim about how the paper *develops* a concept. And
grounding a quote against an abstract we handed the model in the same call is a
check that agrees with itself: the pass rate would be near 100% and would carry
no information, while dragging the honest per-source figure upward. There is no
abstract fallback. A paper with no body text is not in the corpus.

### 2.4 The places that would fabricate, and the guard that goes in first

`app/lib/export.ts` emits, for every paper in a map:

```
  eprint        = {${arxiv}},
  archivePrefix = {arXiv},
```

Run a PMC map through that and it asserts an arXiv eprint id for a paper that has
none — fabricated citation metadata, product rule 4, in the one artefact a
researcher pastes into a bibliography. **The guard ships with migration 016,
before any PMC row can exist**: `export.ts` and `pipeline/export_related_work.py`
omit any paper whose `source <> 'arxiv'` from BibTeX and say so in a comment,
reusing the omission path that already exists for papers with unknown authors.
The proper `@article` entry with `doi`, `journal` and `year` replaces the
refusal later, in step 8 of section 6. Putting the refusal in first is the
same discipline as never destroying before replacing: the guard must precede the
data that would trip it, not follow it.

`pipeline/enrich_authors.py` is the second one. Decision 28 makes arXiv
authoritative for authors precisely *because* the fetcher proved the id by
downloading that paper and passing the title-match guard, and it warns that a
wrong key silently yields the wrong authors. There is no arXiv equivalent for a
PMC paper — but there is a better one: the JATS document we already downloaded
carries `<contrib-group>` with the article's own author list, proven by the same
title-match guard. **PMC authors come from the paper's own XML**, OpenAlex is not
consulted for them, and a paper whose XML carries no author list is omitted from
BibTeX rather than guessed. That is stronger than the arXiv path, not weaker.

### 2.5 Stage D, and the failure that would be invisible

`stage_d_edges.py` calls
`get_json(f"{S2}/paper/arXiv:{arxiv_id}/references", …)` and wraps it in
`except Exception: refs = []` with the comment "Semantic Scholar does not hold
every arXiv paper. A 404 means no citation data for this one, not a broken run."
That is correct per-item design and it is exactly what would hide a total
failure. Ask Semantic Scholar for `arXiv:PMC5334499` and it 404s for **every**
PMC paper; the code logs one warning per paper, returns an empty reference list,
and the map is assembled with every PMC paper carrying zero edges. Nothing errors.
Nothing reports. The map looks thin rather than broken.

Two changes, and the second is not optional:

1. `fetch_references` takes a paper ref and keys by source: `arXiv:<id>` for
   arXiv rows, `DOI:<doi>` for PMC rows carrying a DOI, `PMID:<pmid>` otherwise.
   The disk cache filename becomes the ref with `:` and `/` folded.
2. **A per-source global floor.** After the reference sweep, if any source
   contributed at least one paper and *zero* of that source's papers returned any
   reference, Stage D aborts non-zero and names the source. Per the standing
   rule, the assertion must not be immunisable: `refs_returned == 0` for a source
   with `papers >= 1`, not a ratio that one lucky hit can rescue. The same floor
   goes on `fetch_papers.py`: a run that attempted N papers from a source and
   fetched none of them aborts rather than reporting "N failed" and continuing to
   build an arXiv-only map that looks complete.

---

## 3. What it costs

**Money.** Acquisition is free: OpenAlex and Europe PMC take no key and charge
nothing, and no LLM call is made anywhere in sections 2.1 to 2.3. **Two steps
spend money and they are the only two**: the PMC-only trace in step 6 and the
mixed trace in step 8, each one Stage B/C/D/E/F/G/H run over ≤150 papers. AS-BUILT
records $1.47 to $1.92 per map, and `DEFAULT_MAX_CHARS = 40_000` caps a JATS
paper's input the same way it caps a LaTeX one, so **budget under $5 of LLM spend
for the whole verification plan**, against a `TRACE_SPEND_CAP_USD` default of 10
per trace. If a PMC trace approaches the cap, that is itself the finding — it
means JATS is producing far more text per paper than LaTeX — and the run aborts
cleanly as designed.

**Time.** Roughly the month the ticket estimates, and the shape matters more than
the total: migration and identity ~2 days; the Europe PMC client ~2 days; the
JATS extractor and its offline instrument ~4 days; corpus-selection changes ~3
days; export, route and evidence-page changes ~3 days; measurement and iteration
on the extractor ~1 week; slack for the decision point ~1 week.

**Risk to existing data.** Low and enumerable.

- Migration 016 is additive in Postgres terms. `DROP NOT NULL` and widening a
  `CHECK` are catalogue changes and take no table rewrite; adding four nullable
  columns with no `DEFAULT` on a table in the low hundreds takes no rewrite
  either. The one `UPDATE` is the `source_id` backfill, which touches every row.
- **The extractor-version split re-extracts the whole corpus once.** Free, no LLM,
  and it must be run with `extract_text.py --dry-run` first, which already reports
  exactly which digests would move. The expectation is: `extractor_version`
  changes for every paper, `extracted_text_digest` changes for none, no stamp
  moves. Section 4 says what it means if that is not what the dry run shows.
- `genealogies.nodes` is not rewritten and no curated map is touched.
- Live traffic: none of the above changes a rendered page until step 8.

**Licence.** The PMC OA subset has a non-commercial tier (CC BY-NC and
relatives). Decision 27 makes cached extractions the platform's, shared across
requesters, and contemplates a world where the platform sells the reading. This
design **restricts the first integration to the commercial-use tier — CC0, CC BY,
CC BY-SA, CC BY-ND — filtered on Europe PMC's `license` field at selection time**,
and records the licence on the row so the question can be re-asked without
re-fetching. Widening that is an owner decision, in section 7.

---

## 4. How it will be verified

Four checks, in the order they are cheap.

**Check 1 — the extractor's instrument, before any ticket work and before any
money.** Download 20 PMC OA articles as JATS to a scratch directory and run the
proposed `jats_to_text()` over them offline. For each, compare the extracted
text against Europe PMC's `abstractText` field from the *search* endpoint — a
different endpoint, a different serialisation, a reference the extractor did not
produce and cannot have shaped. **Proves it:** the search API's abstract
sentences appear, folded, inside the extracted text for ≥18 of 20. **Falsifies
it:** they do not, which means the tree walk is dropping content and the fix is
the extractor, before a single database column is added. This is the same move
that turned four fruitless threshold recalibrations into a sole-cause table:
build the instrument first, as its own step, and take the false-negative count
before writing the code.

**Check 2 — determinism of the extractor split.** `extract_text.py --dry-run`
after the per-format `EXTRACTOR_VERSION` change. **Proves it:** zero papers
report a changed `extracted_text_digest`. **Falsifies it:** any paper's digest
moves, which means extraction is not deterministic over unchanged input; stop,
because the split would then silently stale a stamp it has no business touching,
and the stamp architecture assumes what has just been disproved.

**Check 3 — the headline, and the reason F2 gates this.** One PMC-only trace on a
biomedical concept, then read F2's report with its per-source grouping.
**Proves it:** the PMC corpus's `quote_verified` fraction on definitions, and the
verified fraction on edges, sit alongside the arXiv figures for `attention` and
`embedding` without either of the two failure shapes below. **Falsifies it:**
either the PMC verified fraction is far below the arXiv ones, or — the one that
looks like success — it is far *above* them, which would mean the model is being
handed a document short enough to quote trivially and check 1's sample was not
representative. **No threshold is set here.** With one PMC map and two arXiv maps
there is no distribution to take a quantile from; the numbers are published with
n stated and the ship decision is the Product Owner's, which is #30's own rule.

**Check 4 — one paper may not arrive twice.** After the mixed trace, assert that
no `genealogies.nodes` member list contains two papers with the same
`papers.doi`, and that no edge has `source_paper_id = target_paper_id`.
**Proves it:** both counts are zero. **Falsifies it:** either is non-zero, which
means the one-source-per-work rule in 2.2 leaked and the map is asserting a
relationship between a paper and itself.

"Tested" is not on this list and neither is a golden set: `CLAUDE.md` keeps a
formal eval harness OUT and #30 is not one. Every number above comes from the
map's own rows or from an upstream API's own response.

---

## 5. What was considered and rejected

- **Publisher PDFs via Unpaywall / OpenAlex OA locations first.** Cheapest to
  wire, worst first answer: it confounds "does the pipeline generalise" with
  "is PDF extraction bad", and we already know the second.
- **DOI as the primary identity key.** Collides preprints with their published
  versions and rests identity on OpenAlex's least reliable field (decision 28).
- **Rewriting `papers.arxiv_id` into a generic `paper_id` text column.** Touches
  every query, every export, every stored map and every bookmark, to buy
  tidiness. Additive columns plus one `paper_ref` helper buy the same thing for
  nothing.
- **NCBI's PMC OA Web Service.** Returns tarballs and its legacy API is withdrawn
  on or after 2026-08-24.
- **A separate `pipeline/extract_jats.py` module with its own version digest.**
  Two namespaces in one `extractor_version` column silently breaks the
  re-extraction queue for whichever format lost the coin toss.
- **Falling back to the abstract when full text is absent.** Produces a grounding
  check that agrees with itself and inflates the very number this whole design
  exists to measure honestly.
- **Falling back to the PMC PDF when the XML is thin.** Reintroduces the weak
  path inside the experiment designed to avoid it. Drop the paper.
- **A per-source grounding threshold set in this design.** Four recalibrations on
  this project moved nothing; a threshold gets set against a stated distribution
  when one exists.
- **A "choose your sources" control in the trace request UI.** Scaffolding for a
  second and third source that are not being built.

---

## 6. Rollout order, and what is explicitly not built

0. **Gate.** F2 ships, with the per-source grouping of section 0 inside #30. Until
   then, nothing below starts.
1. Check 1 offline, on 20 downloaded articles. No repo change if it fails.
2. Migration 016, plus the BibTeX refusal for `source <> 'arxiv'` in both
   exporters. No behaviour change: every row reads `source = 'arxiv'` and no
   non-arXiv paper exists to be refused.
3. Per-format `EXTRACTOR_VERSION`, `--dry-run` (check 2), then one re-extract
   pass. Free.
4. `pipeline/sources/europepmc.py` and `jats_to_text()`. Offline, no DB, no LLM,
   tested against the step-1 fixtures.
5. `corpus_select.py`: pool keyed on the OpenAlex work id, `--source` defaulting
   to `arxiv`, licence filter, one route per work. `fetch_papers.py` and
   `stage_d_edges.py` gain their per-source global floors.
6. **One PMC-only trace on a biomedical concept. ~$2.** Read the report.
7. **Decision point, the Product Owner's.** If the PMC grounding rate is
   acceptable, continue. If not, stop: the source does not ship, and the JATS
   extractor is the remaining work. Nothing in steps 2 to 5 renders anything to a
   reader, so stopping here costs no rollback.
8. Evidence-page links, `[ref]` route, `@article` BibTeX with DOI, and one mixed
   trace (~$2) with check 4.

**Not built, and not scaffolded for:**

- Any second non-arXiv source. No Unpaywall, no DOI content negotiation, no ACL
  Anthology, no bioRxiv, no institutional repositories — not behind a flag, not
  as an unused adapter interface, not as a `sources/` registry with one entry.
  `pipeline/sources/europepmc.py` is one module, called by name.
- A PDF path for PMC, or any abstract-only fallback.
- A source picker, source filter or source badge in the trace-request UI. The
  evidence page must say where a paper came from, because a reader following a
  link needs the right host; that is a link, not a control.
- Any change to the workbench. `docs/ROADMAP.md`: zero curatorial operations have
  been performed in the product's life.
- Retrospective re-selection of existing corpora. `attention` and `embedding`
  stay arXiv-only; adding a source to a published map is a versioning question
  and belongs to F4.
- A per-source spend cap, per-source prompt or per-source clustering threshold.
  One pipeline, one prompt version, one threshold; if PMC needs its own, that is
  a finding to report, not a knob to add pre-emptively.

---

## 7. Risks

1. **The verified stamp's precondition weakens and nobody sees it.** The entire
   trust claim rests on having the paper's full text. Mitigated by the F2 gate,
   the per-source grouping, and by the BibTeX refusal landing before the data.
2. **Silent zero-edges for the whole new source** (section 2.5). The existing
   `except Exception: refs = []` would swallow a 100% failure as ordinary bad
   luck. This is the single most likely way the integration ships broken and
   looks merely disappointing. Mitigated by the per-source floors, which must not
   be ratio-based.
3. **The same paper entering twice**, as arXiv preprint and PMC article, producing
   split clusters and self-edges. Mitigated by one route per OpenAlex work, and
   measured by check 4.
4. **Europe PMC states no rate limit publicly.** Its developer pages give no
   requests-per-second figure and refer readers to a forum. Design as if it were
   arXiv's rule until told otherwise: a single throttled client, conservative
   default of 1 request per second in an env var, the existing `User-Agent` with
   `mailto`, and `get_bytes`' exponential backoff. **Confirm the stated fair-use
   position before the first run of more than a hundred requests**, and record the
   answer in `docs/RUNBOOK.md`. Do not assume the arXiv 3-second rule transfers,
   and do not assume its absence means unlimited.
5. **Licence tier.** CC BY-NC text cached and shared under decision 27's
   sell-the-reading model is a legal question, not a technical one. Mitigated by
   restricting to the commercial tier and recording `license`; see question 1.
6. **Fabricated citation metadata** (`archivePrefix = {arXiv}`, section 2.4).
   Mitigated by the refusal-first ordering.
7. **The NCBI legacy OA API withdrawal on or after 2026-08-24.** We do not use it.
   The risk is that somebody reaches for it during implementation because it is
   the first result for "PMC API". Named here so that does not happen.
8. **Field scoping.** `corpus_select.py --field` defaults to `fields/17` (Computer
   Science) and `app/lib/openalex.ts` populates its picker from
   `filter=indexed_in:arxiv&group_by=primary_topic.field.id` — the field list a
   requester can choose from is *derived from what arXiv holds*, with an
   arXiv-heavy hard-coded fallback. Adding PMC without touching that leaves the
   picker unable to offer the fields the new source exists to serve. It is a
   two-line change and it is easy to miss because nothing fails: the request
   succeeds, in the wrong field, and returns a thin map.

---

## 8. Open questions — Product Owner only

1. **Licence tier.** Commercial-use only (CC0, CC BY, CC BY-SA, CC BY-ND), as
   designed, or the whole OA subset including CC BY-NC? This changes corpus size
   materially and it interacts with decision 27's shared-extraction economics.
   The design takes the narrow reading by default.
2. **Does decision 27's carve-out extend to PMC?** It says "extractions from arXiv
   are shared; extractions from user-supplied papers are owned by the uploader",
   naming arXiv specifically. Is the rule "arXiv", or is it "any public source"?
   If the latter, the sentence should be amended when this ships, because it will
   otherwise be read literally by the next person.
3. **May a map mix sources, or must it declare one?** The design says a map may
   mix and a paper may not. If a map must declare one source, the UI copy, the
   trace request and F2's grouping all change, and the mixed trace in step 8 is
   deleted rather than run.
4. **Who reads the first biomedical map, and what does "it worked" mean?**
   `CLAUDE.md` says the product does not claim expertise in any field a map
   covers, and the Product Owner has disclaimed domain expertise. The grounding
   rate is mechanical and we can read it. The *shape* — whether the clusters and
   the edge directions are sensible — has until now been checked by an owner who
   could read the field, and on the first PMC map nobody on this team can. That
   is not an argument against shipping; it is an argument that the shape's own
   properties (F2) are the only acceptance criterion available, and the owner
   should say so out loud rather than discover it at review.
5. **What does a requester see when papers are dropped for want of full text?**
   The design drops them silently at selection. If the requester should be told
   "N papers were excluded because no full text was available", that is progress-
   feed work and belongs with F6 (#34), not here.
6. **Who amends #30 to add the per-source grouping**, and does that grouping ship
   with F2 or as a follow-on? The design assumes with F2. If it is a follow-on,
   F7's gate is that follow-on and not #30.
7. **Is a second source expected after this one?** The design deliberately builds
   no registry and no adapter interface. If the owner's intent is three sources
   within the quarter, say so now — that is the one answer that would change the
   shape of section 2.1 rather than its content.

---

*Architect, 2026-08-06.*

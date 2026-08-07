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

**The worker runs thirteen steps, not eight**, and the difference is not
decoration: three things that began as optional auxiliaries are now part of a
finished trace. `check_extraction.py` audits the text the grounding check is
about to rest on (incident 11), `stage_b_extract.py --reground` recomputes the
definition stamps against the text actually on disk (decision 19), and
`enrich_authors.py` fills the author metadata the export cannot invent. In
order: select corpus, fetch papers, extract text, audit extracted text,
extract definitions (B), cluster concept-states (C), classify edges (D),
re-check definition quotes, ground and assemble (E), fill author metadata,
score magnitude (F), compose threads (G), check each claim (H). Earlier drafts
of this section said "eight stages plus auxiliaries", which was true of the
letters and wrong about what a trace actually consists of.

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

**Stage C: clustering** (`stage_c_cluster.py <concept>`).
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
Absolute distances are model-specific, which is why the number moved and the
method did not. The previous 0.16 was tuned for bge-large when embeddings ran
locally; against Voyage it sits at the 1st percentile of the pairwise
distribution and almost nothing merges (105 clusters, 87 of them singletons).
Decision 29 corrects decision 5, which still records the old number as a claim
about its own moment.
**Stage C no longer clears the map's edges unconditionally** (decision 20). Per
edge endpoint, it compares what each node id denoted before against what it
denotes now, and removes only the edges whose concept-states have changed
underneath them; the rest are left for Stage D to replace on its first success.
When nothing about the previous concept-states could be read, every edge clears
and it says *that* rather than reporting a clustering change it cannot support.
A re-run at the same threshold on an unchanged corpus **with cached embeddings**
reproduces the same clustering and so keeps every edge. Not with `--force`,
which re-embeds: vectors are stored at six decimal places, so a pair sitting on
the threshold can cross it and the clustering can move. The read, the node
upsert and the edge decision are one transaction.

**Stage D: edge classification** (`stage_d_edges.py <concept>`).
Pulls references and citation contexts from Semantic Scholar (public endpoint,
disk-cached in `data/s2_cache`; the shared anonymous pool throttles hard on
repeat runs and the client backs off through 429s). Finds citations that cross
node boundaries, then Claude classifies each into the six-type taxonomy with a
confidence score. The LLM classifies only: edge quotes are the two papers'
Stage B definition quotes, never the S2 citation context, because S2's text
comes from its own PDF extraction and will not string-match our LaTeX-derived
text. Direction convention: cited = ancestor = source; citing = descendant =
target.

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
genealogy complete. **These exports are the de-facto backups** (section 10,
incident 4). Re-run Stage E after curating.
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
`snapshot_map.py`: the whole of one map to a timestamped JSON, before anything
rewrites it. Stage E's export is the documented backup and holds `nodes` and
`edges`; it does not hold `streams` (threads and their claims), `user_edits` (the
curatorial audit trail), or the definitions the edges quote, which a repair
overwrites in place. Incident 4 was recovered from that export with its audit
trail lost, which is the same gap. Restoring is deliberately not automated: the
file is plain JSON and a restore is a decision. It prints the curatorial edits
rather than counting them, and since decision 18 it prints each one's actor with
the basis for the name: this is the forensic tool for "who changed this map", so
the answer belongs where the owner is already looking. Entries written before
decision 18 print as `actor not recorded`, which is the whole truth about them.
`restore_snapshot.py`: puts a map back the way `snapshot_map.py` found it, by id
so nothing is orphaned: concept-states, threads, every edge, and each
definition's quote, verdict and magnitude scores. `user_edits` is the one thing
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
(`map_report.py <concept> [--prompt-version PV] [--all] [--json]`): what a map is
made of, from the map's own rows (issue #30, `[F2]`). Every figure is selected
from migration `016`'s two views, `map_report` and `map_report_by_source`, and
computed here not at all, so this command and `/g/<id>/report` read one
expression and cannot disagree about the same map. **It reads `LINEAGE_READ_URL`
and never `DATABASE_URL`, and issues no statement but `SELECT`** — the second
tool in this pipeline built that way, and for `recheck_stamp.py`'s reason: its
value is that an Operator can run it against production and paste the answer into
a report, which is only safe if it structurally cannot write. It does not repair
and there is nothing to refresh, because a view holds no data.
It commits, and the docstring says so. `with psycopg.connect(...)` commits on the
way out of the block, which is what psycopg's context manager does; the commit
carries nothing because the transaction holds two `SELECT`s, and it is left alone
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
the Operator keeps the counts. **Two section titles are read back by `render()`** to decide
whether to print the By source table and the papers-per-year histogram, so a
rename in `SECTIONS` that is not made there too loses a whole block in silence.
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
**Stage H inherits the empty-fold rule** (issue #57), because it calls the same
`quote_is_grounded` every other stage calls, and that is the point of there being
one matcher. A claim whose passage is only citation marks or whitespace used to
check out, since the empty string is a substring of everything; it now does not,
at generation and on `--recheck` alike. The direction is safe on this page
specifically: the thread page renders a claim's quote only when `verified` is
true, so such a claim loses its stamp and its quote and keeps its text, which is
exactly what the stage already does with a passage that fails. Claim-level stamps
are still not re-checkable from stored data — they are the third stamp population
and migration 015 does not cover them (open question 2 in the design).
`--recheck` re-grounds the stored quotes without asking the model for new ones,
and costs nothing. A stamp is computed once, at generation, against the text of
that moment: re-extracting a corpus leaves every stamp on the map asserting a
check that ran against a document no longer on disk. A claim that stops checking
out keeps its text and loses its stamp and its quote, which is what generation
would have done with it. Regenerating instead would cost $4-6 to rewrite prose
that was never the problem.

Stages F and G were one-off scripts hardcoded to the showcase map until 2026-07-29, which
meant no other map could have a front door. They are stages now, the worker runs
them after Stage E, and both were proven on a second concept (`attention`,
`/g/13`) before being committed.

---

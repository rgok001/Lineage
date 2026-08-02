# Backlog

Everything known and not yet done, in the order it is worth doing. Last
reviewed 2026-08-01, when item 1 closed: it was split into two tickets because as
it stood it named one of two causes and prescribed a fix that lands at 63%, then
both shipped. The measured before and after is in the closed list.

**This is the only list of open work.** `docs/FIX-LOG.md` was a second one,
written 2026-07-23 and referenced by nothing since; its nine open items were
checked against the code on 2026-08-01 and are now items 20 to 26 here, or in the
closed list, or recorded there as overtaken. The file is deleted, not archived —
`git show 2e70a4c:docs/FIX-LOG.md` is the copy, and the reason is in the closed
list.

The order is by what each item costs **if it fires**, not by effort. An item
that puts a wrong claim in front of a reader outranks one that merely wastes
money, because this product's whole proposition is that a tick means something.

**Numbers are not reused and the list is not renumbered.** A closed item leaves
its number behind, because the as-built and the commit log cite these numbers and
a renumber would silently repoint every one of them. So the open list starting at
2 means item 1 is done, not that it was lost.

Status words mean exactly one thing each. **Confirmed** was reproduced with an
input. **Reported** came from a review and has not been independently
reproduced. **Parked** is a decision to wait, not an oversight.

---

## P1 — do next

### 2. Stage D's rebuild is not atomic, and Stage E publishes whatever survives
**Reported (architecture review, W3).**

`stage_d_edges.py` runs `autocommit=True`, so the DELETE and each INSERT are
separate transactions, and the spend cap `break`s out of the loop. A cap hit at
edge 40 of 305 leaves 40 edges. Stage E then grounds those 40, sets
`status='complete'` with no check on the count, and overwrites
`data/genealogy_<concept>_<pv>.json` — the map backup — at a fixed path. The run
that truncated the map destroys the record of what the map was.

The global check is `failures == LIMIT and written == 0`, so one success out of
305 immunises the run.

Fix: classify into a list, then DELETE and INSERT in one transaction; treat the
spend cap as an abort rather than a break; replace the zero floor with a
proportional one; and stop Stage E marking `complete` or overwriting the export
when the edge count has collapsed against what the export holds.
Cost: $0, about a day.

### 3. Stage G discards Stage H's claims, and has no global check
**Reported (architecture review, W4).**

`stage_g_threads.py` catches any exception composing a thread and substitutes an
empty result, then writes the whole `streams` blob unconditionally. If phase 1
succeeds and every phase-2 call fails, it stores threads with every paper bare,
destroys the previous accounts, and destroys every claim Stage H wrote into the
same JSONB column. Restoring costs Stage G plus Stage H, roughly $3.70, because
Stage H's output lives inside the blob Stage G overwrote.

Fix: abort before the write if no thread got an account; carry forward existing
`claims` for any paper whose thread membership did not change.
Cost: $0 to build, protects about $4 per map. About a day.

---

## P2 — soon

### 19. Symbol loss is now the dominant reason a reader is warned, and its bar has never been measured
**Confirmed, measured 2026-08-01 on the Render corpus, after the demotion in
item 1 shipped.** Filed with the next free number rather than slotted in at 4:
these numbers are identifiers, not positions.

`symbols` is sole cause on **43 of 304 papers (14.1%)**, which is **38% of the
113 papers still carrying the dossier note**. Before the demotion it read 16.
Nothing about symbol loss changed; those papers were being co-caused by the two
noisier signals, and removing those is what exposed it.

**It was predicted by name.** The design that authorised the demotion set the bar
for "there is a third miscalibration here" at about 15% sole cause, and named
symbol loss as its prior, on the reasoning that corpus-wide symbol loss measured
12% while `SYMBOL_LOSS_SUSPECT` sits at 0.20 per paper. It came in at 14.1%:
under the line, so it did not trigger a sixth round, and close enough to it that
the margin is not evidence of anything.

**The honest weakness in how it was cleared.** That criterion was read off the
pre-demotion sole-cause table, and a signal's true sole-cause share only becomes
visible once the signals it co-occurs with are out of the way. So it was
evaluated on the one table that could not answer it. That is not a reason to
undo the demotion, which met the other two criteria on measured data and took
the note from 218 papers to 113. It is a reason to price this one rather than
assume it is fine.

**This is not yet a defect, and that distinction matters.** Unlike `gaps` and
`package_macros`, symbol loss plausibly *is* content loss: a symbol that left no
trace in the extracted text is a character the reader cannot see. The open
question is whether 20% per paper is the right bar, and that bar was guessed and
has never been measured against a distribution.

Fix: no code change until it is priced. Name `symbols` in
`PROPOSED_NOTE_SIGNALS` and run, on the Render shell:

```
python pipeline/check_extraction.py --compare-verdicts
```

That prices demoting it outright, which is what the instrument exists for. If
the crosstab says most of those 43 would go clean, the question becomes the
threshold rather than the signal, and the per-paper distribution of symbol loss
is what sets it, at a stated quantile with the resulting rate named in the
commit. Not a number that looks better, which is what all four failed
calibrations did.

**That distribution does not exist yet, and the threshold half of this item
cannot be finished until it does (Operator, 2026-08-01).**
`check_extraction.py` stores a signal record only when the rate crosses
`SYMBOL_LOSS_SUSPECT`, and the numeric rate is never a column — it survives only
as free text on the papers that already breached. The stored data is therefore
right-censored at exactly the value under review, so any quantile taken from it
is a quantile of the tail while looking like a quantile of the distribution.
Recording the per-paper rate unconditionally is a prerequisite of this item, not
a part of it. The `--compare-verdicts` half above is unaffected: it prices
demoting the signal outright, which needs no distribution.
Cost: $0. Minutes to measure, then a decision.

### 4. Some of the corpus on the worker's disk is stale, and some of it is absent
**Confirmed 2026-08-01, measured on the Render disk by the audit's first clean
run.**

The re-audit of all 304 papers reported two things nobody had counted before:

- **32 papers hold text produced by an older extractor** (an upper bound: see
  item 18, which found that the current extractor can leave the same mark) — 25 of 297 LaTeX
  papers (8%) and all 7 PDF papers (100%). The audit names them and says
  re-extracting applies the fixes. These are not damaged files; they are files
  the current pipeline would produce differently.
- **12 papers have no extracted text on that disk at all** (4%). They were
  correctly left unaudited rather than stamped, which is decision 23 working,
  but their dossiers now carry no note about their text because there is no text
  to have an opinion about.

Why this matters beneath the verdicts: a definition's quote is string-matched
against the file on disk, so for those 32 papers the grounding is being decided
against text the extractor no longer produces. Re-extracting could move a quote
either way, and nothing today distinguishes "this quote is genuinely absent"
from "this quote was copied out of a file we have since improved".

Why P2 rather than P1: the measured blast radius on what a reader sees is small.
Of 393 stored quotes, 11 carry any damage tell and **3** are flagged
`copied from text the extractor has since fixed`. So this is a real correctness
gap with a known and currently narrow effect, not a live misstatement on every
page.

Fix: re-extract the 32 with `extract_text.py --force --only <ids>` on the worker,
and fetch plus extract the 12. Both must run on the Render shell, which is the
only machine with the corpus. Since 2026-08-01 a re-extraction clears the paper's
verdict automatically (decision 21), so the audit re-measures them free at the
next boot with no manual clear.
Cost: $0 in model spend, an hour of pipeline time. Risk: it will move some
quotes from verified to inferred, or the reverse. That is the point.

### 5. The home page lists every map regardless of status
**Confirmed 2026-08-01.**

`listGenealogies()` has no status filter and `app/app/page.tsx` renders the list
unfiltered, ordered by `updated_at DESC`. A trace that is pending, running,
failed or aborted appears publicly alongside the finished maps, and a new one
sorts to the top. Nothing is in that state today, so this is latent — but the
next failed trace puts a broken map on the front page of a site that is being
shown to people. It is also why a scratch map could not be used for the reader
test.

Fix: filter the list to `complete`, or label the others honestly and sort them
below. Whichever, the front page should not present an unfinished map as a
finished one.
Cost: $0, under an hour.

### 21. A node's label can be narrower than the node, and the diagnosis on file was wrong
**Confirmed 2026-08-01, reconciled from the fix log (filed 2026-07-23).**

The 46-paper node covering word vectors, t-SNE projections and latent codes is
labelled "Learned image feature vector representation": the majority reading, not
the common thread. A wrong label is on the reader's primary view, which is why
this sits above the latent items below it.

The fix log blamed the labeller seeing a sample. It does not see a sample.
`stage_c_cluster.py:209` passes every member definition in the cluster and
`label_cluster_llm` joins all of them with no cap, and `git log -S member_defs`
returns one commit — the one that added Stage C — so it has never sampled. The
cause is the prompt: it asserts "They form one coherent sense" and asks for a
name, which invites the dominant reading. The centroid the old fix prescribed is
already computed at line 204 and used only to pick a representative member.

Fix: ask for the common thread rather than a name, and show the label as
provisional until curated.
Cost: $0 in extraction spend and a Stage C relabel; no Stage B re-run.

### 20. Stage B cannot tell a paper that defined the concept from one that merely used it
**Confirmed 2026-08-01, reconciled from the fix log (filed 2026-07-23).**

`stage_b_extract.py` asks one boolean, `defines_concept`, over "defines **or**
uses", and its system prompt says so in those words. That is deliberate recall
generosity at intake — Stage A defers the filter to here — but nothing downstream
can undo it: the `Extraction` schema carries no field separating a paper that
reshaped the sense from one that consumed it, so a node holds both. The
word-vector node carries Collobert and word2vec beside FAISS and the Transformer,
which merely consume embeddings.

Fix: a second field in the Stage B schema, reshapes versus applies, and either
split them in Stage C or mark the appliers on the node.
Cost: the prompt and schema change is minutes. The re-extraction is not. Any
schema change needs a `PROMPT_VERSION` bump, which invalidates the per-paper
cache across the whole corpus, so this lands *with* the parked `embedding`
refresh and is one more reason that pass is worth batching, not before it.

### 6. The paper dossier's verified stamp fails open
**Confirmed 2026-08-01 (architecture review, W10).**

`app/app/g/[id]/p/[arxiv]/page.tsx:154,159` render
`quote_verified === false ? inferred : verified`, so anything that is not
literally `false` renders as verified. Its two siblings on the thread page and
in the export both fail closed. The column is `NOT NULL DEFAULT false` so this
is latent, but the TypeScript type says `boolean | null` and the polarity is the
wrong way round in the one product where that matters most.
Cost: $0, minutes.

### 7. Stage F's global check only catches failure from the very first batch
**Reported (architecture review, W7).**

`if failed_batches == bi and bi >= 3` — two successful batches early and the
guard can never fire again however many of the rest fail. Each failed batch
contributes an empty list, padded to neutral silently, then persisted over the
real ranking. The influence map then picks its papers and rings its top band
from mostly-uniform numbers, and nothing looks broken.
Cost: $0, half a day.

### 8. Magnitude scores survive the definitions they describe
**Reported (architecture review, W9).**

`displacement` is a cosine distance from a centroid of definition vectors, and
`attention` is a scored pass. The documented repair path refreshes definitions
and re-embeds but never re-runs Stage F, so after the `embedding` refresh the
turning-point rings would still be computed from the definitions the money
replaced. Displacement is pure numpy over stored vectors and costs nothing to
recompute; the two halves are welded into one stage with no flag to run the free
one.

Fix: `--displacement-only`, and add it to the documented repair path.
Cost: $0, half a day.

### 9. The as-built states a clustering threshold the code does not use
**Confirmed 2026-08-01 (architecture review, W8).**

`stage_c_cluster.py:57` is `DEFAULT_THRESHOLD = 0.28`, with a full recalibration
comment measured on `embedding`'s definitions. Section 4 and decision 5 of the
as-built both still say `0.16` and attribute it to bge-large. The document that
outranks the spec, and that exists so a design does not re-make a paid-for
mistake, is wrong about a load-bearing calibrated constant, and agents read it
and repeat it.
Cost: $0, an hour.

### 25. `SEMANTIC_SCHOLAR_API_KEY` is required by the documentation and read by nothing
**Confirmed 2026-08-01, reconciled from the fix log (filed 2026-07-23).**

`CLAUDE.md:47` names it as one of the two keys the project needs and
`.env.example:19` carries the slot, but no code reads the variable. `common.py`
`session()` sets a User-Agent and nothing else and `get_json` sends no headers, so
Stage D's fetch phase still meets Semantic Scholar's shared anonymous pool and its
429 backoffs, which run past ten minutes. An operator who obtains a key, sets it
and sees no change has nothing to tell them it was never sent.

Filed here rather than as performance for the same reason as item 9: the
documents that outrank the code are wrong about the code, and agents read them.

**Measured 2026-08-01, and it points at removing the claim rather than wiring
the key.** The key is absent as well as unread: `.env` carries the line with an
empty value, so nobody has ever obtained one. The anonymous pool has cost
nothing observable. The local `data/s2_cache` holds 102 papers with a median of
48 references each and a maximum of 265, which is the cache doing exactly the job
`stage_d_edges.py:81` says it was built for. So the key is an optimisation for a
problem already solved, not a dependency.

**Recommendation: delete the claim.** Remove the `CLAUDE.md:47` requirement and
the `.env.example:19` slot. Wiring the header is the more expensive answer to a
smaller problem, and it carries a hazard the documentation change does not: see
item 27. If the header is ever added it must be attached per host inside
`get_json`, never on the shared `session()`, which is used for OpenAlex and arXiv
as well and would otherwise hand this project's Semantic Scholar credential to
two unrelated services on every request.
Cost: $0, minutes.

### 27. A failed Semantic Scholar fetch is cached permanently as "this paper has no references"
**Confirmed, and observed firing, 2026-08-01.**

`pipeline/stage_d_edges.py:93-101`. The `try` catches `Exception`, sets
`refs = []`, and the cache write at line 101 sits **outside** the handler, so it
runs whether the fetch succeeded or not. A 404 and a transport failure, a 429
exhaustion, an S2 outage or a rejected key are treated identically, and only the
404 deserves it. Line 87 then returns the cached file forever: nothing retries.

The comment above it justifies caching a 404, and that reasoning is right. It
just does not reach the other cases the `except` swallows.

**It has already fired.** `data/s2_cache/1502.02791.json` is `[]`. Queried
Semantic Scholar directly with no key: it holds references for that paper, at
least five, including *Domain-Adversarial Neural Networks* and *Deep Domain
Confusion*. So one paper contributes no citation contexts to Stage D, and every
edge touching it is displayed without the basis that decision 16 and the fix
log's highest-severity item existed to put there. 1 of 102 on this machine.

Fault five, failure that writes plausible data, applied to a cache: the run
reports success and the map is quietly thinner.

Fix: cache `[]` only on a definitive 404. Every other failure returns empty for
this run and writes nothing, so the next run retries. Remediating what is already
cached is deleting the affected files; the next Stage D run refetches them.

**Measured on the Render disk, 2026-08-01.** 205 papers cached, 3 empty, and
each of the three checked against Semantic Scholar with no key:

- `1412.7755` returns 404. S2 does not hold it, so caching empty is correct.
- `1706.02263` and `2005.04966` both return references. **Poisoned.**

So the bug has fired on the cache serving the live maps: 2 of 205, 1.0%, against
1 of 102 on the laptop. A steady low rate rather than one bad run. Those two
papers contribute no citation contexts, so every edge touching them renders
without the basis, and the runs that produced them reported success.

Remediation is deleting the two files. Do **not** re-run Stage D for it: the
fetch is free but the classification that follows is not, and there is no
standalone refetch. Deleting them now means the correction lands for nothing on
the next trace that covers those papers, at the cost of the maps staying two
papers thin until then, which for 2 of 205 is the proportionate trade.
Cost: $0, under an hour.

---

### 28. Nothing in this repository re-runs any of the checks that were used to prove it correct
**Confirmed 2026-08-02.**

Filed from a narrow finding and deliberately widened; the narrow version is
recorded first because it is what was asked for.

**The narrow finding.** Decision 18 asserted that the `Viewer` brand's boundary
"is kept as an executable probe rather than as this paragraph". There is no such
probe committed anywhere outside `node_modules`. It was written and run by a
tester and never checked in. The as-built has been corrected and now says what is
true, that five forgery variants were driven through the compiler and that
nothing re-runs them when `app/lib/authz.ts` changes. The record is honest; the
gap in the repository is real. This is incident 13's failure mode surviving inside
the entry written about incident 13.

**The wider finding.** `git ls-files` returns exactly one test-shaped tracked
file, `app/scripts/security-test.mjs`, and there is no test runner configured
anywhere: no pytest, no vitest, no jest, no `test` script in `app/package.json`.
Every check written on 2026-08-01 lived in a session scratchpad and is gone. That
includes the brand probe, the cross-language twin probes over 39 and then 61
malformed inputs, the database-guard probe, the reground probe with its 17
assertions, an exhaustive subtractive proof over 15,552 signal combinations, and
a 200,000-string check that a text fold never manufactures a match. Several were
the sole evidence for a decision entry. All of them would fail loudly if the
behaviour they pin were changed, and none of them will ever run again.

**Why this matters more under the platform decision than it did yesterday.**
Every quality property in the system currently holds because somebody looked. The
roadmap's whole shape is moving those properties into the pipeline so that a
stranger's map is trustworthy without the owner reading it. That is not
achievable while the repository has nowhere to put a check that must keep
passing.

**The unresolved part is ownership, not effort.** The tester writes probes and
does not commit code. The developer commits code and does not own the tester's
evidence. So a probe that must survive in the repository belongs to neither role
as they are written today, which is why fourteen of them were written and
discarded in a single day without anyone breaking a rule.

Fix: a place for checks to live and a command that runs them, then commit the
brand probe as the first inhabitant. The role prompts need a sentence saying
whose job it is; that is a change to `.claude/agents/`, and it is the Product
Owner's to make.
Cost: $0, half a day for the harness, minutes per probe thereafter.

## P3 — none of these is a live defect

Items 10 to 18 are also small. Items 22 to 26 are not all small: they are here
because none of them can put a wrong claim in front of a reader, which is the
only thing this list's order is about.

10. **`--reground` does not catch partial disk corruption.** The all-failed
   refusal fires when nothing grounds; 6 of 12 files truncated flips 6 stamps
   and exits 0. Safe direction, recoverable, no paid stage downstream reads the
   column. The as-built implies broader coverage than the guard gives.
11. **`--reground`'s refusal message should name the single-row escape.**
    `--reground --only <arxiv>` bypasses the guard by construction, which is the
    way out of a map that is honestly all-stale. The message does not say so.
12. **`--reground --dry-run` exits 1 on an all-failed run.** Correct in
    substance, surprising for a read-only mode that anyone scripts.
13. **Nothing fails if `CURATORIAL_OPS` drifts.** The list is exactly right in
    both languages today. A test asserting it equals the workbench subparser
    names plus the `actions.ts` literals would keep it that way.
14. **`--reground --limit` is rejected** on a rationale that applies equally to
    `--only` and `--corpus`, which are allowed.
15. **`workbench.py` prints success before it commits.** The actor is resolved
    before mutating, so the reported failure is fixed, but a database error in
    `record()` or at `commit()` still prints "Deleted n5 and 3 attached edge(s)."
    to an operator whose transaction rolls back.
16. **Zero-branch wording.** "No curatorial changes have been made to it since"
    asserts a negative where "None recorded" says the same thing without it.
17. **Brand documentation completeness.** Decision 18 names
    `as unknown as Viewer` as the cast escape; a single `as Viewer` and
    `Object.assign({}, real, {login})` also compile.
18. **`tidy_marks` is not idempotent, so `stale` fires on text the current
    extractor wrote.** Confirmed 2026-08-01 on 40 papers fetched fresh from
    arXiv. Rule 4 deletes an emptied bracket pair *after* rule 3 has closed the
    spaces before punctuation, so `word ( ) .` becomes `word .` in one pass and
    `word.` only in a second. The `stale` signal's premise is that these are
    marks the current extractor cannot make; it can. **5 of 40 freshly extracted
    papers carry them, 25 marks in total, and a second `tidy_marks` pass removes
    every one.** No reader sees it, because `stale` is reported and deliberately
    kept out of the verdict, which is why this sits here and not in P1. It does
    bear on item 4: that count of 32 papers holding older text comes from this
    signal, so it is an upper bound. Fix is a second pass or a rule reorder, then
    re-measure item 4.

22. **The timeline's start is a property of arXiv, not of the idea, and nothing
    says so where it shows.** A map begins in 2011 because arXiv's CS coverage
    does; the lineage runs back through Bengio (2003), Latent Semantic Analysis
    (1990) and distributed representations (1986), none of them on arXiv, and a
    reader will read the top of a timeline as the beginning. This is placement,
    not a missing disclosure: `/about` says "a term's pre-arXiv history is
    invisible" and as-built section 11 says it too. What does not exist anywhere
    is a marker at the horizon itself — grep for "horizon" across the tree
    returns nothing. Fix: say at the top of the timeline that the story starts
    here because the sources do.
23. **A definition quote can be a sentence fragment.** Quotes sometimes end
    mid-clause ("...such that the cosine similarity"), which reads as noise even
    when it is genuinely verbatim. The Stage B prompt requires
    character-for-character copying and forbids ellipses but never requires a
    whole sentence, and the only check on arrival is `quote_is_grounded`, a
    fold-and-substring test with no punctuation condition. It is not a false
    claim — a fragment wearing the verified tick really is verbatim — which is
    why it sits here. Fix: a prompt clause plus a terminal-punctuation check. It
    needs a `PROMPT_VERSION` bump to reach the cached extractions, so it batches
    with item 20.
24. **Stages B and D call the model one paper at a time.** About 143 extractions
    and about 305 classifications run sequentially, and most of a trace's
    wall-clock is network wait; a pool of 8 would cut Stage B from roughly ten
    minutes to one or two. Two things want care: `TRACE_SPEND_CAP_USD`, which
    aborts cleanly mid-loop today and would overshoot slightly, and the API rate
    limit. Not distribution — the bottleneck is waiting, not capacity, and rate
    limits are per account. This is as-built section 11 item 1, which covered
    Stage B only; that entry now points here.
26. **No claim carries its corroboration count.** The residual of an overtaken
    fix-log entry, see the closed list. 305 edge rows are roughly 85 distinct
    meaning-pairs at about 3.6 citations each, and the strongest claim in the
    `embedding` map — 37 citations carrying word vectors into image features —
    is stated nowhere as one claim with 37 supports. An enhancement rather than
    a defect, recorded so it is not rediscovered as one.

---

## Blocked on live data, not on effort

These need the Render worker or a person, and several are deliberately batched
behind the parked spend. Full list and rationale: as-built section 11 item 12.

- **Design checks 1 and 2.** A CLI edit must land `by_asserted` and no `by`; a
  web edit the reverse. Run on `/g/13`, which is uncurated. Checks 3, 4 and 5
  have been run and passed.
- **`--reground` on both maps.** `attention` first as the control, since it is
  the only map built entirely on correct text and a large fall there means the
  check is wrong rather than the map. Then `embedding`. Dry run, read, then wet.
- **Stage C's gate reached through a real re-cluster.** It has only ever been
  driven directly; `cluster()` needs sklearn and real vectors.
  (Done 2026-08-01, see the closed list.)
- **The Operator's connection is declared but has never been verified, so the
  role cannot start.** `LINEAGE_READ_URL` is set and names the `lineage_ro` role
  on the right database. What nobody has confirmed is that the grants landed:
  the setup SQL named a database that does not exist, so the `GRANT CONNECT`
  errored and every statement after it applied to whichever database the editor
  was connected to. The role may therefore hold nothing, or hold more than
  SELECT. Unblocking is one short session and no code: connect as `lineage_ro`,
  confirm the current database, user and privileges in one query, run a bounded
  SELECT, then attempt one harmless write and require it to be refused. If that
  write succeeds, the finding outranks whatever was being measured. Cost: $0.
- **Whether this record stays public is undecided.** Swept 2026-08-01: no
  credential has ever reached the remote — `.env` and `data/` have never been
  tracked on any ref, and the connection strings in `.env.example` are
  placeholders. What is public is the record itself: this backlog with every
  confirmed defect, the as-built including section 10, and `CLAUDE.md`. That has
  been true for the life of the repository. `.claude/memory/` was made private on
  the reasoning that incident detail should not be readable by anyone, which is
  either the right rule applied in one place or an inconsistency in two. Worth
  deciding deliberately rather than by default; it is the owner's call.

## Parked by decision

- **The $8.45 `embedding` refresh.** Held until there is a critical mass of
  changes worth validating against live data in one pass, rather than spent to
  verify one of them. Until then the map carries its honest partial figure,
  which is what the badge fraction was built for.

---

## Closed recently, so it is not rediscovered

- **The fix log is folded in and deleted (2026-08-01).** `docs/FIX-LOG.md` was
  written on 2026-07-23, tracked, public, and linked from nothing. It carried
  nine open items headed by "Edge evidence does not evidence the edge — severity:
  highest, this undermines the product's core claim", and that item had been
  fixed nine days earlier. All nine were checked against the code before it was
  removed: two had shipped (below), six are items 20 to 26 here, one was
  overtaken (below). Nothing in its "Fixed" table was unique — as-built incident
  7 records the same first cloud run in more detail, and the two lists of "seven
  deployment-only defects" do not name the same seven: the fix log omits the
  invalid `ANTHROPIC_API_KEY` and as-built omits the transaction held across the
  fetch. Eight distinct defects across two lists that each claim to hold seven is
  the argument for one list. Deleted rather than kept behind a status header,
  because a header is a weak control on a file nothing links to — anyone who
  reaches it arrives by search or by browsing, which is the reader least likely
  to read a header — and because a second standing record of open work is exactly
  what the numbering rule at the top of this file exists to prevent. Deletion is
  the recoverable direction: `git show 2e70a4c:docs/FIX-LOG.md`.

- **Edge evidence did not evidence the edge (fix log item 1; verified shipped
  2026-08-01).** The panel showed each paper's own definition quote, so neither
  quote mentioned the other paper and the pairing read as meaningless while both
  halves were accurate. Stage D was fetching the Semantic Scholar citation
  context, passing it to the classifier and discarding it, on the grounds that it
  cannot pass the verbatim string match. Shipped: migration
  `010_edge_basis.sql:25` adds `citation_context` (and `rationale` beside it),
  `stage_d_edges.py:242` stores what the classifier already saw, and
  `evidence/page.tsx:292` renders it in `BasisCard` under "Verbatim · where the
  later paper cites the earlier · per Semantic Scholar, not string-verified".
  `snapshot_map.py` and `restore_snapshot.py` carry the column, so it survives a
  restore. Two deviations from what was prescribed, both deliberate: the basis
  renders above both definition quotes rather than between them, headed "What the
  later paper did with the concept"; and the model's rationale is shown beside it
  marked "the tool's reading", which the item did not ask for. The honesty
  discipline it did ask for is there — neither may ever wear the verified stamp,
  and migration 010's own comment says so.

- **The export was built but not reachable (fix log item 7; verified shipped
  2026-08-01).** `app/app/g/[id]/page.tsx:100` links Markdown and `:101` BibTeX,
  served by `app/app/g/[id]/export/route.ts` with `?thread=` scoping. Note what
  did *not* happen: `pipeline/export_related_work.py` is still not wired into the
  app. What shipped is `app/lib/export.ts`, a parallel implementation mirroring
  what the reader sees, and the CLI export stays because the pipeline is
  CLI-first. That is a recorded decision, not drift — as-built line 816 and the
  header comment of `export.ts` both say it — so it is not filed as an item.

- **"The relationships section shows rows, not findings" was overtaken, not fixed
  (fix log item 6; established 2026-08-01).** The complaint was that a reader
  meets 305 rows. Since it was written the product grew a different front door:
  Stages F, G and H, the influence map with a through-line and turning-point
  rings, and threads read as accounts, while `/g/<id>/evidence` was retitled
  "Evidence & workbench" and now tells the reader in its own copy that "the
  readable account is the map". The row list is no longer anyone's first view, so
  the finding's premise is gone rather than its fix delivered — a distinction
  worth keeping, because the prescribed fix (group by meaning-pair, rank by
  corroboration) was never built and the part of it that still has value is item
  26.

- **The extraction verdict warned about three papers in four, on a corpus whose
  quotes are 97% clean (2026-08-01).** **Before: 218 of 304 papers (72%) carried
  the dossier note. After: 113 (37%).** Measured on the Render disk, the only
  machine holding the corpus, and measured *before* the change rather than after,
  which is what made this the fifth calibration and not the fifth guess.
  Two causes of near-equal size sat behind it, and the item as first written
  named only one and prescribed a fix that lands at 63%. `gaps` was the sole
  reason 33 papers were not clean and `package_macros` the sole reason for 44;
  the two together freed 105. That 28-paper difference is co-occurrence, and it
  is why 1a's caption on the sole-cause table had to be corrected before the
  table could be trusted: the columns do not add up.
  **1a shipped the instrument** (`--compare-verdicts`: a machine key on every
  signal, one `verdict_from`, the proposal as a module constant, a crosstab and
  the sole-cause table all four earlier rounds lacked). **1b shipped the change**:
  `gaps` and `package_macros` report as a note and stop deciding the verdict,
  a literal `...` folds to `…` before the shape tests (gap tells in stored quotes
  5 to 2), and migration 014 stores a digest of the calibration on every verdict
  so a future threshold change re-measures itself. **No threshold moved**, the
  largest remaining sole cause is `symbols` at 5.3%, nothing became stricter, and
  the reader-facing page was not touched. See as-built section 4 and decision 25.

- **Extraction verdicts described text that no longer existed (2026-08-01).**
  `extract_text.py` now clears the verdict, the signals and the checked-at in
  the same statement that records the new text path, so the free audit collects
  the row on the next boot; `check_extraction.py --clear-verdicts` does the same
  for the rows frozen before that line existed, from a machine that has the
  database and not the papers (decision 21). Two things came out of it that were
  not in the original finding. The frozen verdicts were written at 10:08:43 and
  the three commits that repaired this audit's calibration land between 10:19
  and 10:31, so they were computed by code the project had already replaced, and
  the live count of 160 `damaged` is the pre-repair run's own number. And every
  one of those repairs was lenient, so the re-audit should remove warnings
  rather than add them: 183 milder and 0 stricter over 227 papers, measured
  offline. **Both shipped and ran (2026-08-01).** The clear was run from the
  laptop, all 304 rows, backed up first; the re-audit was run on the Render
  shell, the only machine with the corpus. Measured: `damaged` fell from 250 to
  15 table-wide and from 160 to 11 on `/g/10`, `clean` rose from 3 to 74, and
  218 of 304 (72%) still carry some warning against the 76% predicted. Both
  halves of the prediction held, and the residual is item 1 rather than this
  having failed. See incident 14 for the state a test harness left on the
  database while this was being built.
- **The audit called a paper clean when it had not read that paper's source
  archive (2026-08-01).** Six signals need the archive and the whole block was
  skipped in silence when it was not on the machine, so 47 verdicts moved and 39
  became `clean` purely because a file was missing. An incomplete scan can now
  still report the damage it measured off the text, and can no longer report
  cleanliness it did not establish; `--write` skips it and names it (decision
  23). Refusing `--write` on a partial corpus was considered and rejected: the
  Render worker's own disk is partial, so no threshold separates it from a
  laptop.

- **The reader test passed (2026-08-01).** A reader with no context could tell
  the authenticated entry from the asserted one. Run against a standalone
  fixture rendering the real component, because a scratch map would have gone
  on the public home page (item 5). What was not captured is *how* they told
  them apart, so this is evidence the current wording works rather than a
  specification of why. That closes the last open check in the actor design.
- Definition stamps had no free recompute path — `--reground` shipped, wired in
  as stage 8 before Stage E (decision 19).
- Stage C deleted every edge before Stage D classified anything — gated on
  denotation, per endpoint, in one transaction (decision 20).
- The map page and home page claimed curation unconditionally — both now gated
  on a count of curatorial ops, and the badge states a real fraction.
- `user_edits` recorded who only sometimes, and rendered absence as "(cli)" —
  `by` / `by_asserted` / neither, absence never rendered as origin (decision 18).
- The as-built asserted a compiler guarantee that did not exist — `Viewer` is
  branded, and the boundary is pinned by a probe (incident 13).
- `workbench.py` and `restore_snapshot.py` rewrote the whole `user_edits` array
  and could erase a concurrent web edit — both append with `||` now.

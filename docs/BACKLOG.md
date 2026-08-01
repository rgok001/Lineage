# Backlog

Everything known and not yet done, in the order it is worth doing. Last
reviewed 2026-08-01, when item 1 closed: it was split into two tickets because as
it stood it named one of two causes and prescribed a fix that lands at 63%, then
both shipped. The measured before and after is in the closed list.

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

---

## P3 — small, and none of them is a live defect

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

## Parked by decision

- **The $8.45 `embedding` refresh.** Held until there is a critical mass of
  changes worth validating against live data in one pass, rather than spent to
  verify one of them. Until then the map carries its honest partial figure,
  which is what the badge fraction was built for.

---

## Closed recently, so it is not rediscovered

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

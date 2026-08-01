# Backlog

Everything known and not yet done, in the order it is worth doing. Last
reviewed 2026-08-01.

The order is by what each item costs **if it fires**, not by effort. An item
that puts a wrong claim in front of a reader outranks one that merely wastes
money, because this product's whole proposition is that a tick means something.

Status words mean exactly one thing each. **Confirmed** was reproduced with an
input. **Reported** came from a review and has not been independently
reproduced. **Parked** is a decision to wait, not an oversight.

---

## P1 — do next

### 1. Extraction verdicts describe text that no longer exists
**Confirmed, measured 2026-08-01. Live on the public site now.**

Every `extraction_checked_at` in `papers` carries the same timestamp,
`2026-07-31 10:08:43.957021+00`, and the audit that wrote them was reading the
pre-re-extraction corpus. `embedding`'s papers were re-extracted later that day.
160 of its 187 papers are stamped `damaged` on that basis, so the paper dossier
shows "our reading of this paper lost some of its text" on 86% of the map from a
measurement of text that is gone. A paper the re-extraction *fixed* looks
identical to one it did not.

Nothing corrects it: `check_extraction.py --only-unchecked` filters on the
timestamp being null and `extract_text.py` never clears it, so the automatic
re-audit skips these rows permanently.

Fix: one line beside the existing `UPDATE papers SET extracted_text_path...` to
null the verdict and the checked-at when the text is rewritten. The existing
`--only-unchecked --write` then re-audits them free on the next boot.
Cost: $0, about an hour. See section 11 item 11 of the as-built.

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

### 4. The home page lists every map regardless of status
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

### 5. The paper dossier's verified stamp fails open
**Confirmed 2026-08-01 (architecture review, W10).**

`app/app/g/[id]/p/[arxiv]/page.tsx:154,159` render
`quote_verified === false ? inferred : verified`, so anything that is not
literally `false` renders as verified. Its two siblings on the thread page and
in the export both fail closed. The column is `NOT NULL DEFAULT false` so this
is latent, but the TypeScript type says `boolean | null` and the polarity is the
wrong way round in the one product where that matters most.
Cost: $0, minutes.

### 6. Stage F's global check only catches failure from the very first batch
**Reported (architecture review, W7).**

`if failed_batches == bi and bi >= 3` — two successful batches early and the
guard can never fire again however many of the rest fail. Each failed batch
contributes an empty list, padded to neutral silently, then persisted over the
real ranking. The influence map then picks its papers and rings its top band
from mostly-uniform numbers, and nothing looks broken.
Cost: $0, half a day.

### 7. Magnitude scores survive the definitions they describe
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

### 8. The as-built states a clustering threshold the code does not use
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

9. **`--reground` does not catch partial disk corruption.** The all-failed
   refusal fires when nothing grounds; 6 of 12 files truncated flips 6 stamps
   and exits 0. Safe direction, recoverable, no paid stage downstream reads the
   column. The as-built implies broader coverage than the guard gives.
10. **`--reground`'s refusal message should name the single-row escape.**
    `--reground --only <arxiv>` bypasses the guard by construction, which is the
    way out of a map that is honestly all-stale. The message does not say so.
11. **`--reground --dry-run` exits 1 on an all-failed run.** Correct in
    substance, surprising for a read-only mode that anyone scripts.
12. **Nothing fails if `CURATORIAL_OPS` drifts.** The list is exactly right in
    both languages today. A test asserting it equals the workbench subparser
    names plus the `actions.ts` literals would keep it that way.
13. **`--reground --limit` is rejected** on a rationale that applies equally to
    `--only` and `--corpus`, which are allowed.
14. **`workbench.py` prints success before it commits.** The actor is resolved
    before mutating, so the reported failure is fixed, but a database error in
    `record()` or at `commit()` still prints "Deleted n5 and 3 attached edge(s)."
    to an operator whose transaction rolls back.
15. **Zero-branch wording.** "No curatorial changes have been made to it since"
    asserts a negative where "None recorded" says the same thing without it.
16. **Brand documentation completeness.** Decision 18 names
    `as unknown as Viewer` as the cast escape; a single `as Viewer` and
    `Object.assign({}, real, {login})` also compile.

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

## Parked by decision

- **The $8.45 `embedding` refresh.** Held until there is a critical mass of
  changes worth validating against live data in one pass, rather than spent to
  verify one of them. Until then the map carries its honest partial figure,
  which is what the badge fraction was built for.

---

## Closed recently, so it is not rediscovered

- **The reader test passed (2026-08-01).** A reader with no context could tell
  the authenticated entry from the asserted one. Run against a standalone
  fixture rendering the real component, because a scratch map would have gone
  on the public home page (item 4). What was not captured is *how* they told
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

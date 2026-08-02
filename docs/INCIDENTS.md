# Lineage — Incidents and lessons

CLASS: history
RECOMPUTED BY: nothing. Append-only.

Each entry is a dated claim about a moment, so it cannot go stale — only grow.
Never edit an entry after the fact; a correction is a new entry that names the
one it corrects.

Split out of `AS-BUILT.md` on 2026-08-02, where it was section 10 and the only
immortal part of a file that is otherwise derived from the code. It keeps its
original heading, so every "section 10, incident N" reference elsewhere in the
record still resolves here.

---

## 10. Incidents and lessons

Recorded because the system's shape is partly their consequence.

1. **OpenAlex metadata mismatches (build phase).** BERT and RoBERTa arXiv ids
   carried unrelated titles. Consequence: the `text_title_match` guard and the
   arXiv-first author enrichment rule.
2. **Negative results re-billed (build phase).** Stage B's cache only stored
   positives; re-runs re-paid for most of the corpus. Consequence: migration
   003, negatives as first-class cached findings. The caching claim is now
   tested behaviour, not an assumption.
3. **Cross-corpus billing (first live trace, 2026-07-18).** The 12-paper
   dropout trace scanned 40 papers because Stage B's query took every
   extracted paper in the shared table. Caught live by the end-to-end test;
   consequence: Stage B `--corpus`, passed by the worker. Side finding: some
   attention-corpus papers genuinely define dropout, and their definitions
   legitimately joined the dropout genealogy.
4. **Curated genealogy deleted (2026-07-19).** The new danger-zone delete was
   used on the curated attention map (id 2), likely while hunting an
   already-removed orphan row. Restored from the Stage E export as id 5 with
   curated labels intact; the original audit trail entries were lost.
   Consequences: `restore_genealogy.py`, the exports-are-backups rule, and
   this document's insistence on re-exporting after curation.
5. **Worker spend-parser crash (first live trace).** The regex `[0-9.]+`
   captured the trailing period of "spend $0.0093." and `float()` crashed;
   the job failed cleanly, was requeued, and completed for $0.10 thanks to
   caching. The failure handling design was validated by its first real
   failure.
6. **The five-hour false alarm.** A "5h ago" timestamp looked like a clock
   bug; investigation proved the session's background waits had genuinely
   spanned five hours and every clock was correct. The DB-time design (#10
   above) was kept anyway because it makes the heartbeat check robust against
   viewer clocks that really are wrong.
7. **The first cloud trace: seven deployment-only bugs (2026-07-21..23).**
   Nothing here could surface locally, where `DATA_DIR` sits inside the repo and
   RAM is plentiful. (a) Unbounded embedding batch: fastembed defaults to 256 and
   allocated ~2.4 GB of activations for a 130 MB model, OOM-killing the worker;
   capped to 8 (measured 2440 MB -> 342 MB). (b) Paths stored relative to the
   repo root broke when `DATA_DIR` became a separate mounted disk. (c) A shared
   DB with per-machine disks: papers flagged extracted elsewhere had no local
   text file. (d) Those same papers were silently dropped from the corpus until
   extraction learned to re-run on a missing file. (e) An invalid
   `ANTHROPIC_API_KEY` on the worker. (f) The 1024-dim model could not load in
   2 GB, and the fix was not a bigger box but removing local models entirely
   (decision 13). (g) A single arXiv 403 aborted a 150-paper fetch. **Lesson: a
   first real cloud run is a test in its own right; local success proves very
   little about a deployed environment.** Two wrong diagnoses along the way
   (instance size, then model file size) were corrected only by measuring.
8. **Generated paraphrase wearing the verified stamp (2026-07-28).** Migration
   012 specifies that each river paper's `quote` is a string-verified span, and
   the generation wrote a summary of the paper instead. All 102 were checked
   against the definition spans Stage E actually matched, and **none** was a
   passage from its paper; the thread page had been rendering them under a green
   "verified" check since the river shipped. Both the page and the export now
   read `definitions.verbatim_quote` with its real `quote_verified` verdict, the
   same source the dossier already used. **Lesson: a stamp must be derived from
   the check, never from the field's documented intent.** The contract said
   verified; nothing verified it. The generated prose was never the problem and
   stays, labelled as the tool's reading.
9. **An absolute threshold silenced the signal it was guarding (2026-07-29).**
   The influence map added "movers" by displacement but only from papers with
   `attention >= 1`. Displacement exists to catch papers the citation graph
   misses, so gating it behind a citation-derived score was self-defeating, and
   the number 1 is meaningless across corpora of different citation density. On
   the second map ever built (`attention`, 85 papers) exactly 20 papers cleared
   the bar and all 20 were already selected, so no mover was ever added and four
   of nine threads had no paper on the map while still being listed beneath it.
   Caught by the owner counting channels against the list. **Lesson: this is
   decision 3 again** — rank, never threshold. The rule was right and was not
   applied here, because the flaw is invisible on the corpus you tune against
   and only appears on the second one.
10. **The extractor ate the citations, and the papers looked illiterate
    (2026-07-29).** pylatexenc knows `\cite` and renders it `<cit.>`. It does not
    know natbib, biblatex, or a paper's own `\newcommand`, and an unknown macro
    is dropped in silence: the citation vanished and its punctuation stayed, so a
    stored quote read "a model should, detect the objects, and , segment them"
    and the paper wore the blame for our parser. Found by the owner reading a
    quote on a thread page. The fix is a rule, not a list: any macro whose name
    contains "cite" is folded to one mark before parsing, so names nobody has
    enumerated are covered too. **The knock-on was the interesting part.**
    Cleaning the text would have un-grounded every quote copied out of the dirty
    text, and re-grounding would have reported a collapse in verified counts as
    the result of a fix. 66 definition quotes and 367 edge-quote copies were
    re-anchored instead — exact match modulo whitespace and citation marks, never
    a guess — but re-anchoring makes the later check pass by construction, so the
    check was moved to where it belongs: `quote_is_grounded` now folds whitespace
    and citation marks itself. Verified edges went 233 to 286 of 305 on embedding
    and 211 to 287 of 287 on attention, most of which was never a quoting problem
    at all: it was where a line happened to break. **Lesson: when a check fails on
    things that are yours rather than the source's, it is the check that is
    wrong, and repairing the data to satisfy it hides that.**
11. **The recorded diagnosis was wrong, and the bug was incident 10 again
    (2026-07-31).** Open item 3 had said for days that *Attention Is All You
    Need* reads "vectors of dimension ." because `$d_{model}$` extracted to
    nothing. It does not: run against the extractor we actually ship,
    `$d_{model}$` extracts correctly to `d_model`. What extracts to nothing is
    `$\dmodel$`, because the paper writes `\newcommand{\dmodel}{d_{model}}` in its
    preamble and pylatexenc drops an unknown macro in silence along with its
    content. **That is incident 10 exactly, one class wider.** The fix has the
    shape the last one should have had: expand the definitions rather than
    enumerate the names.
    **Two lessons, and the second is the uncomfortable one.** A diagnosis written
    from a plausible reading is not a measurement: two minutes running both forms
    through the extractor would have shown maths mode works, and nobody spent
    them, because the explanation sounded right. And incident 10's own text names
    `\newcommand` as a thing pylatexenc does not know, while the fix that followed
    covered only "cite": **a lesson recorded at the width of the symptom will be
    applied at that width.** Ask of every fix what class the failure belongs to
    and whether the fix covers the class. Consequence: `expand_own_macros`, and
    `check_extraction.py`, which exists because none of this was visible from
    inside the system — every quote passed.
12. **An empty credit balance rebuilt the showcase map into nothing
    (2026-07-31).** Mid-repair of `embedding`, the Anthropic balance ran out.
    Every call returned `400 invalid_request_error: Your credit balance is too
    low`, and four stages in a row treated that as ordinary per-item failure,
    because each had been written to survive one bad item (decision 14). Stage B's
    refresh died. Stage D **deleted all 305 edges before classifying a single
    one**, classified none, and left the map with 27 concept-states and no edges.
    Stage E dutifully grounded zero edges. Stage F scored all 533 citations
    neutral and **persisted them**, overwriting the real uptake ranking with a
    uniform number that looks like data. Stage G crashed, which is the only one
    that behaved well, because it is the only one without a fallback.
    **Three lessons, and the third is the general one.** Destroy nothing until you
    can replace something: Stage D now defers its DELETE until the first
    successful classification. A per-item fallback needs a global sanity check:
    "one failure is neutral" is right, "every failure is neutral" is a broken call
    wearing a result's clothes, so Stage D and Stage F now abort when nothing at
    all has succeeded. And an error swallowed to its class name is not a log: 305
    lines reading `BadRequestError` said nothing, while one line of `str(exc)`
    would have named the cause immediately. All three now print the message.
    Recovery was from `snapshot_map.py`, taken minutes earlier, which is the only
    reason this is an incident rather than a loss.
13. **This document asserted a compiler-enforced invariant that the compiler did
    not enforce, and it propagated within hours (2026-08-01).** Decision 18
    shipped saying `recordEdit`'s actor parameter is a `Viewer` obtainable only
    from `getViewer()` or `requireOwner()`, so the compiler keeps unauthenticated
    text out of `by`. `Viewer` was a plain shape alias, and TypeScript compares
    object types by shape, so `recordEdit(1, "rename", {}, { login: "attacker" })`
    compiled clean under `--strict` with no cast, no `any` and no import from
    `authz.ts`. Caught by the tester with a `@ts-expect-error` control that
    reported the directive as *unused* — the cheapest possible probe and one
    nobody had run. By then an architecture review had read the claim out of this
    document and repeated it back verbatim, so the false invariant had a second
    source before it had a fix.
    **Closed** by the `unique symbol` brand on `Viewer` (`app/lib/authz.ts`,
    decision 18), which makes the sentence already written here true. What pins it
    is thin: the brand itself, plus the convention of re-driving the five forgery
    variants through the compiler. **No probe is checked in**, so nothing re-runs
    them when `authz.ts` changes.
    **Lesson.** A claim about what a type system enforces is a testable claim and
    `@ts-expect-error` tests it in one line; asserted without such a probe it has
    been hoped for, not checked. And this document is load-bearing enough to be
    quoted, so an over-claim in it does not stay in it — which runs both ways:
    `docs/FIX-LOG.md` sat public for nine days telling readers the product's core
    claim was undermined by a defect migration 010 had already fixed, referenced
    by nothing, so nothing prompted anyone to revise it (folded into the backlog,
    commit `d5625a6`). A document goes on asserting in the present tense until
    somebody edits it, in both directions.
14. **A test harness written to be offline wrote to production, because
    `common.py` loads `.env` at import (2026-08-01).** While building decision 21,
    a scratch script exercised `check_extraction.main()`'s argument guards over a
    set of `sys.argv` values. It was written to be safe by doing
    `os.environ.pop("DATABASE_URL")` first. **`load_dotenv` runs at `common.py`
    import time and does not override what is already set, so removing the
    variable is exactly what re-armed it.** Two of the eight cases were write
    paths and both ran against live Neon: `--clear-verdicts --concept embedding`
    cleared the verdict, signals and checked-at on 187 papers, and
    `--only-unchecked --write` then re-audited 199 against the laptop's partial
    `DATA_DIR` and stored 156 verdicts computed from text that is not the text on
    the Render disk; the remaining 43 were skipped as "no text on this machine".
    The mode writes three columns and no others, so no text file, quote,
    definition, edge or map was altered, and the loss is the per-paper record of
    what the 2026-07-31 batch said about `embedding` — whose totals survive in
    item 11 of section 11.
    **Three lessons.** Popping an environment variable does not isolate a script
    from the database, and nothing in this repo is offline by construction: the
    only reliable isolation is not calling `main()` at all. Every earlier harness
    here drove a *function* through a fake connection, which is why none of them
    could do this; reaching for `main()` to exercise argparse acquired every side
    effect `main()` has. And a dry run is not a safe default: the two destructive
    cases were in the list precisely to show they were refused, refusal was the
    only thing observable without a database, so the harness proved the guards by
    running the things the guards do not stop.
    **Closed (2026-08-01).** The control that replaces the instruction shipped as
    `LINEAGE_NO_DB` (decision 22). The database credential that reached an agent
    memory file as evidence has been **verified dead** by the owner — substituted
    into the live DSN it was auth-rejected while the real password connected — so
    no rotation is needed; the literal is redacted from memory and the lesson
    kept as `placeholders-inside-runnable-commands`. What remains is data, not
    exposure: the 199 stamped rows carry the same defect one machine over, and
    the repair is item 12(e) of section 11.

---


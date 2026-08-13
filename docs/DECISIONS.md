# Lineage — decision record

CLASS: history
RECOMPUTED BY: nothing. Append-only.

**This is the progression record.** It is what the owner reads to see how the
product got here, alongside [INCIDENTS.md](INCIDENTS.md): decisions are the
choices that were made, incidents are the things that went wrong, and between
them they are the history of the product. That is now this file's stated purpose
rather than a side effect of it living inside the as-built.

Each entry is a dated claim about a choice, so it cannot go stale — only grow.
Never edit an entry after the fact; a correction is a new entry that names the
one it corrects. **The numbers are cited by commit messages, by `INCIDENTS.md`,
by issue bodies and by agent memory: they are identifiers, not positions, and
they are never reused or renumbered.**

Split out of `AS-BUILT.md` on 2026-08-02, where it was section 9. It keeps its
original heading, so every "section 9, decision N" reference elsewhere in the
record still resolves here. Two cross-references inside it pointed at as-built
section 11, which was removed the same day; they were repointed to the issues
that section's items became (decision 21 → #49, decision 27 → #47). No claim in
any entry was altered.

---

## 9. Decision record

The why behind the load-bearing choices, in one place:

1. **Neon over local Docker Postgres.** Docker was not installed, Neon was
   already in use on another project, and Vercel-linked Neon removed a whole
   class of deploy friction. docker-compose.yml is kept as an optional local
   fallback only.
2. **Sonnet over Opus for extraction.** Head-to-head on 5 papers produced
   identical verdicts and the same quote spans at ~60% of the cost.
   `definitions.model` records provenance; switching models deliberately means
   bumping `PROMPT_VERSION`.
3. **Top-K seed retention, not a cosine threshold** (Stage A): thresholds
   deleted the field's most important paper.
4. **Never relevance-filter citation expansion** (Stage A): ancestors do not
   use their descendants' vocabulary.
5. **Clustering threshold 0.16, over-splitting on purpose** (Stage C):
   merge is cheap and auditable, un-merge is not.
6. **Edge quotes come from Stage B definitions, not S2 contexts** (Stage D):
   only text we extracted can pass our own grounding check.
7. **Postgres as the job queue** (`FOR UPDATE SKIP LOCKED`): one fewer
   system, atomic claims, and the request inbox and queue are the same table
   with the same audit trail.
8. **Worker runs stages as subprocesses**: CLI-first pipeline, crash
   isolation, stdout as the progress stream.
9. **Polling over SSE for progress**: identical UX on a 3 s poll, none of the
   serverless streaming fragility.
10. **Database time as the only clock**: `/api/traces` returns `now()`;
    clients compute skew. Viewer clocks are not trusted for elapsed time or
    heartbeat staleness.
11. **Server-side type-the-name confirmation for deletion**: a client-side
    confirm() decorates the button, not the endpoint.
12. **Already-traced concepts refused for everyone**: protects curated maps
    from silent Stage C overwrite; deletion is the deliberate re-open path.
13. **Embeddings via a hosted API, not local models** (2026-07-23). Running
    1024-dim embedding models in-process is what made the small worker
    unrunnable: onnxruntime spikes past 2 GB building its optimised copy at
    load, and the 1+ GB model download stalled on both Render and a laptop.
    Voyage removes the model from the process entirely (~250 MB footprint,
    nothing to download), which is what the `vector(1024)` schema was designed
    for. The lesson generalises: on small deployments, call an embedding API
    rather than hosting the model.
14. **Robustness at every external boundary.** Upstream sources fail
    individually and must not be fatal: arXiv 403s a minority of papers, the
    shared DB can disagree with a per-machine disk, a stage can go silent for
    minutes. Each is now skipped, guarded or heartbeat-covered rather than
    aborting a whole run.
15. **Two magnitude scores, and neither is ever displayed** (2026-07-26).
    Ranking on uptake alone hides the papers that moved a term, so
    displacement exists as its own axis rather than as a tiebreaker. Both then
    stay behind the interface: they select which papers appear and how large
    the dot is, and no number is shown. A number invites the reader to treat a
    model's weighting as a measurement, which is the failure this tool exists
    to avoid.
17. **Sonnet for claim evidence, measured not assumed** (2026-07-31). Stage H
    ran on Haiku because it was the cheap post-pipeline stage. On thread s0 of
    attention, same prompt and same papers, Haiku got 16 of 22 passages to check
    out and Sonnet got 22 of 22; one paper went from 0 of 4 to 4 of 4, meaning
    its entire account had rested on prose with nothing under it. ~3.7c a paper
    against ~1.2c, so roughly $2 more per map. The mirror of decision 2: there,
    a cheaper model gave identical verdicts and was the right call; here it does
    not, and the difference is only visible because every passage is checked.
    **A model that paraphrases when told to copy fails silently in any system
    that does not verify, and this one verifies.**
16. **Three tiers of trust, never blended** (migration 010, `/about`). A
    verified quote is string-matched against our own extraction. A citation
    context is verbatim but from Semantic Scholar's PDF extraction, so it is
    sourced and unverifiable here. A rationale is the model's reading. Each is
    labelled as what it is, everywhere it appears; only the first wears the
    verified stamp.
18. **An actor on every curatorial edit, and the basis for it** (2026-08-01,
    `docs/design/actor-on-edits.md`). In `genealogies.user_edits`, **`by` is
    authenticated** — a GitHub login the app obtained from a session, the web
    workbench being its only writer — and **`by_asserted` is not**: a name the
    running process asserts about itself (`LINEAGE_ACTOR`, else `user@host`),
    which is all a CLI script running for whoever holds the `.env` can honestly
    claim. An entry carries one, the other, or **neither, which is what every
    entry predating this change carries**. There is no backfill: that set is
    fixed at deploy time and must never grow, so an entry with neither key is by
    construction legacy rather than a new failure. **Absence is never rendered as
    a claim about origin** — the evidence page printed "(cli)" where `by` was
    missing, manufacturing a positive claim out of a silence, and now reads
    `actor not recorded`, as do the exports where they said "Curated by hand".
    `recordEdit`'s actor parameter is typed `Viewer`, and **`Viewer` is branded
    with a `unique symbol` only `lib/authz.ts` can name**, so it is nominal
    rather than structural: a hand-built object literal is a compile error at
    every call site, and `login`/`name`/`image` are `readonly`, so relabelling a
    real viewer in place is one too. Without the brand it was a plain shape alias
    and this entry asserted an invariant that was not enforced at all (incident
    13). **What no brand stops, stated so it is not re-claimed:** a value typed
    `any` is accepted in silence (`JSON.parse(body)`, or any helper with an
    unannotated return), `{ ...viewer, login: other }` works because `readonly`
    does not survive a spread, and `as unknown as Viewer` always works. None has
    a live path — all five call sites take the actor from `requireOwner()`, and
    `getViewer()` is the only function that produces a `Viewer`.
    The rejected alternative worth naming is a single `by` plus a `by_verified`
    boolean, which fails open the moment a reader ignores the flag; the split
    instead fails safe, a reader not updated for `by_asserted` seeing no `by` on
    a CLI entry and degrading to unattributed. Nothing here wears the verified
    stamp, which must keep meaning only "string-matched against extracted text"
    (decision 16).
    **Malformed entries degrade to unattributed rather than crashing.**
    `user_edits` is JSONB and really accepts `"by": 42`, a blank string, a
    missing `op`, or an element that is not an object; `editActor`/`edit_actor`
    and their `op` siblings agree on actor, basis and op for all of them in both
    languages. **The `at` sibling is the one deliberate divergence**: `editWhen`
    must parse in order to format for a locale, so an unparseable date reads
    "date not recorded" there while `edit_when` echoes it; any divergence beyond
    that one is a bug. `app/` has no `error.tsx`, so an exception in the audit
    trail is a 500 on `/g/<id>/evidence` and `/g/<id>/export`; `getGenealogy`
    therefore checks `Array.isArray` rather than `?? []`, since a JSONB string
    has a `.length` and no `.map`.
    **A stored name is folded before it is rendered, not only before it is
    stored.** React escapes where Markdown does not: an interior newline in
    `LINEAGE_ACTOR` broke out of the export's `> ` blockquote into body prose.
    Whitespace collapses, control characters go, the name caps at 64 characters,
    and `(`, `)` and `·` are removed. **The guarantee is narrow: a label cannot
    emit this product's own delimiters or break its own line.** It does not stop
    a label reading like a trust level — `rgok001 • signed in` with U+2022 goes
    straight through, as do `（ ）`, U+200B and U+202E — and chasing those is
    homoglyph enumeration, unwinnable and the shape of fault incidents 10 and 11
    are about, so it is deliberately not attempted. The defence that holds is
    structural: the true basis is printed last, in delimiters only the renderer
    can produce.
    `LINEAGE_ACTOR` unset degrades honestly: either of `getpass.getuser()` and
    `socket.gethostname()` failing yields `unknown@host` or `user@unknown` rather
    than the plausible junk `@host`, and both failing yields `unnamed process`.
    The return is never empty, because an entry with no actor key would join the
    legacy set this decision froze.
    **Both writers append with `||` in the database.** `workbench.py` and
    `restore_snapshot.py` used to read the whole array at process start and write
    it back, silently erasing a web edit that landed in between; this decision is
    what made that array load-bearing, so the latent race was closed with it.
    **A restore is not a curatorial change.** `CURATORIAL_OPS` — rename, merge,
    delete-node, delete-edge, reclassify — is defined once per language
    (`lib/genealogy.ts`, `pipeline/common.py`) and used by both exports and both
    pages; `restore`, written by the two recovery scripts, is excluded. `/g/10`
    carries exactly one entry, incident 12's restore, and announcing it as "1
    curatorial change ... recorded with who made it" was two false claims in one
    sentence. The list is closed rather than "everything except restore", so an
    op nobody adds is undercounted rather than overclaimed, and where entries
    name nobody the pages say "N with no actor recorded".
19. **Every verification stamp gets a free recompute** (2026-08-01).
    `definitions.quote_verified` was the last stamp in the system without one.
    Stage E re-grounds every edge on every run and Stage H's `--recheck`
    re-grounds every claim, both for nothing, while a definition's stamp could
    only be refreshed by paying Stage B for a fresh extraction, so in practice it
    never was. `embedding` is what that cost: its papers were re-extracted on
    2026-07-31 and its definitions were not, so its quotes were copied out of
    text no longer on disk while their stamps said the text had been searched.
    Stage E, which does recompute, put a number on it in passing: 286 verified
    edges down to 201. `stage_b_extract.py --reground` runs the same
    `quote_is_grounded` every other stage runs, rewrites `quote_verified` and
    nothing else, prints the count before and after, and the worker runs it
    immediately before Stage E on every trace. **A stamp that cannot be
    recomputed is a claim about the past written in the present tense.** It
    lowers `/g/10`'s definition verified count visibly, and that is the point:
    the count is wrong in the optimistic direction.
    A definition whose paper has no extracted text on this disk is **skipped,
    counted and printed, never flipped.** `quote_verified` is `NOT NULL DEFAULT
    false`, so there is no "unknown" to write: leaving it true perpetuates the
    stale claim the flag exists to kill, and writing false asserts a check that
    never ran and would mass-flip stamps on any worker whose disk is incomplete.
    Choosing between those two is a decision about the product, still open; the
    script's job is to make the number impossible to miss. An empty or
    whitespace-only text file — what an interrupted `extract_text.py` or a full
    `DATA_DIR` leaves behind — is missing text, not text the quote is absent
    from: a distinction of kind, not a threshold on file size.
    **And the run as a whole is refused if nothing at all grounded.** One
    definition failing is a finding; every definition failing is what a broken
    disk looks like, and this stage cannot tell the two apart, so it writes
    nothing and exits non-zero. The boundary is zero, deliberately, not a
    percentage: decision 3, incident 9 and the turning-point cutoff are three bad
    calibrations already, and a guessed fraction here would be the fourth. This
    is incident 12's rule (a per-item fallback needs a global sanity check)
    applied to a stage that publishes a verdict rather than spends money. Every
    verdict is decided before any is written and the writes go in one
    transaction, because the connection is autocommit and the stage used to
    commit the first rows before it had looked at the last.
    There is deliberately **no override flag**: Stage D and Stage F took the same
    all-failed abort with no escape, and if the loss is genuinely real the answer
    is to re-extract rather than to mass-flip stamps from here. The cost is that
    a map whose every quote is honestly stale cannot be corrected by this tool;
    that trade is taken in the direction that changes nothing.
20. **Stage D owns the edge lifecycle, and Stage C clears only what it has
    invalidated** (2026-08-01). `stage_c_cluster.py` used to run `DELETE FROM
    edges` unconditionally straight after the node upsert, on the reasoning that
    re-clustering invalidates the old edges and Stage D rebuilds them. **That is
    the reasoning Stage D itself held before incident 12**, and it made incident
    12's fix worthless: Stage D defers its own DELETE until the first successful
    classification, but the edges were already gone before Stage D was reached,
    so a Stage D that failed for any reason left a map with fresh concept-states
    and no relationships while its guard reported nothing had been touched.
    **Node ids are positional, and that is what makes this more than a tidy-up.**
    Stage C names clusters `n1..nk` by earliest member year, so an id names a
    slot rather than a concept-state and two runs can both produce `n3` and mean
    different things by it. "The old edges are stale" therefore has two meanings:
    an edge naming an id that is gone, which is merely dangling, and an edge
    naming an id that survived and now denotes different definitions, which is a
    **wrong displayed edge** between two concept-states nobody claimed were
    related. `/g/<id>/evidence` renders the second in full, with both quotes and
    a verified stamp if they ground; under product rule 1 that is worse than a
    missing edge.
    So the condition is the clustering itself, **per endpoint rather than per
    map**: an edge survives iff both ids still denote the definitions they
    denoted. Whole-map equality was the first attempt and over-cleared — a
    re-cluster that merely APPENDS a concept-state leaves every existing edge and
    id untouched, and comparing wholesale threw them all away. Labels, year
    ranges and `representative_arxiv_id` are not compared, because none changes
    what a node groups; renaming is the only curatorial act that leaves
    denotation intact. Clearing in the changed case is not incident 12 again:
    what is destroyed there is already invalid, and incident 12's rule is about
    not destroying something valid before its replacement exists.
    **The gate is one transaction**, covering the read of the old blob, the
    upsert and the DELETE, because the connection is autocommit and without it
    the new clustering commits the moment the upsert runs. That window is the
    gate's own creation, and it was reachable without hand-edited SQL:
    `restore_genealogy.py` validates no shape, so a truncated JSON gives a
    malformed `nodes` blob with a full edge set and a plain re-cluster walks into
    it.
    `node_denotation` in `common.py` is the single reader of `genealogies.nodes`
    for both stages, with one posture on malformed input: dropped, never guessed
    at, never raised on. **The posture is shared; the response is not, and the
    difference is deliberate rather than an inconsistency to tidy away.** In
    Stage C the unreadable blob is the *previous* one, already being replaced
    with Stage D to rebuild behind it, so clearing costs a rebuild; in Stage E it
    is the *current* one, about to be published, so deleting on its authority
    would destroy a map on the word of something unreadable — Stage E therefore
    refuses, deletes nothing and names the cause. The same asymmetry decides one
    node two ways, correctly: a node with a usable id and unreadable
    `definition_ids` exists, so Stage E vouches for it, while Stage C cannot say
    it still denotes what it denoted, so that edge clears. Stage E asks whether a
    concept-state is there; Stage C asks whether it still means the same. A node
    that does not say which definitions it holds denotes **unknown, and unknown
    is never equal to unknown** — each gets a fresh sentinel, because reading
    absence as the empty set would make two silent blobs compare equal and KEEP
    their edges, the one direction this must not fail in.
    The dangling case is settled in Stage E, which sweeps edges naming absent
    concept-states before grounding anything and refuses if more than one edge
    exists and every one would go — the twin of the `--reground` guard (decision
    19). Stage C reports the cause it actually has: a corrupt restore and an
    ordinary wholesale re-cluster used to print byte-identical lines, and the
    cost was an operator re-running Stage D, which spends, on a diagnosis nobody
    had made.
    **What this buys, driven directly against the code**: an appended cluster
    keeps all its edges where whole-map equality cleared them, a changed cluster
    clears only the edges touching it, and a forced raise inside the gate rolls
    back rather than committing new nodes over old edges. Reasoned, not measured:
    that a re-run at the same threshold reproduces the same clustering, since
    `cluster()` needs sklearn and real vectors and cannot run here. The sweep
    alone, as originally scoped, would have left the changed-clustering case
    showing misattributed edges; that is why Stage C still has a DELETE.
21. **A verdict about a file is cleared by whatever rewrites the file**
    (2026-08-01). `papers.extraction_verdict` was the last derived value with no
    path back to the thing it describes, and unlike a definition stamp (decision
    19) it had no recompute either: `extract_text.py` rewrote a paper's text and
    updated `extracted_text_path` and `text_title_match` while leaving the
    verdict, the signals and the checked-at where they were, and
    `check_extraction.py --only-unchecked` — the free pass the worker runs at
    every boot and every trace — selects on the checked-at being null. A stamped
    row was therefore unreachable forever, by construction, and the whole table
    was in that state; see [#49](https://github.com/rgok001/Lineage/issues/49)
    for what it cost a reader.
    `extract_text.py` now nulls all three in the same statement that records the
    new path. `extraction_signals` is `NOT NULL DEFAULT '[]'` (migration 013), so
    it empties rather than nulls; nulling it would abort the extraction.
    **Clearing a verdict and computing one are separate tools on purpose.**
    `check_extraction.py --clear-verdicts [--concept C] [--only IDS] [--dry-run]`
    removes the three columns and reads nothing else at all: no text, no quote,
    no definition. That looks like a weaker `--write` without `--only-unchecked`,
    which recomputes in place and leaves no gap, and where the corpus is present
    that IS the better instrument. The clear exists because the two are run from
    different machines: the corpus lives on the Render disk, the owner has the
    database and not the papers, and a `--write` from a partial `DATA_DIR` writes
    verdicts describing text that is not the text the map was built from.
    **The gap is real, it is not the safe direction, and the output says so.** On
    the dossier the note renders directly beneath "verified verbatim against the
    source text" and is the **only qualifier on that tick**, so clearing it does
    not leave the page saying less: it leaves the page saying *more*, with the
    verification stamp standing alone. Between the clear and the next audit the
    map makes a stronger claim than it did a moment before, which is the one
    direction this product may not drift in. Nothing re-audits on a timer — the
    Render worker runs the free pass at boot, and a background worker boots on a
    deploy, a manual restart or a crash — so the restart is part of the operation
    and not the next line of a runbook: `--clear-verdicts` ends by telling the
    operator to restart the worker now, and says what is standing unqualified
    until they do.
    **It takes a copy first.** The preview is a `GROUP BY`, so it says three
    papers were damaged and not which three, and the wet run would otherwise
    destroy the only per-paper record there is. Every row in scope is written to
    `DATA_DIR/snapshots/extraction_verdicts_<scope>_<stamp>.json` before the
    UPDATE, and on `--dry-run` too, since a rehearsal that skips the part that
    matters has not rehearsed. Restoring is deliberately not automated, for
    `snapshot_map.py`'s reason and one more: these values are stale by
    construction, so putting one back is a decision somebody makes deliberately.
    Commit `3b65766` is the rule ("destroy nothing until you can replace
    something") and incident 14 is what having no copy costs.
    Scoped, because `papers` is shared across every concept ever traced;
    `--concept` uses the same `EXISTS` on `definitions` that `extract_text.py
    --concept` uses, prompt version and all (it has none), so the tool that
    invalidates a verdict and the tool that clears it name the same papers.
    Unscoped it says it is about to touch every audited paper in the table, in
    the same words `extract_text.py --force` uses. `--dry-run` renders a
    different statement rather than branching inside one, so the preview cannot
    become the write by one edit.
22. **A Python process can be told it may not reach the database, and cannot
    untell itself** (2026-08-01). `LINEAGE_NO_DB`, set to anything non-blank,
    makes `common.env("DATABASE_URL")` refuse. Every connection **in the Python
    pipeline, the worker and the migrator** takes its DSN from that one function
    and none reads the variable directly, so one branch closes all twenty call
    sites; that was verified by enumerating them.
    **It does not cover the Node side, and the first draft of this entry said it
    covered everything.** `app/lib/db.ts:13 @ 5177253` passes `process.env.DATABASE_URL`
    straight to `neon()`, so `npm run dev` connects regardless of this flag.
    `app/scripts/check-db.mjs`, `check-auth-env.mjs` and `security-test.mjs` do
    not read the environment at all: each regexes `DATABASE_URL` out of
    `app/.env.local`, which exists on the development machine, and
    `security-test.mjs` fires mutation payloads at every Server Action id it
    harvests. So the true claim is "every Python entry point", and the reach of a
    guard is exactly the kind of sentence incident 13 is about.
    This exists because incident 14 proved that an instruction is not a control.
    Three properties are load-bearing, each drawn from how that actually failed.
    **It is immune to the pop.** The harness "sandboxed" itself with
    `os.environ.pop("DATABASE_URL")`, which is the move that let it through:
    `load_dotenv` does not override a variable that is already set, so removing
    it is precisely what allows `.env` to refill it. The guard records at import
    whether it was on and honours that afterwards, so it can be turned on and
    never off, and popping it does nothing.
    **It raises a `BaseException`.** The harness looped over eight cases,
    absorbing whatever each raised and continuing, which is how one mistake
    became two writes. `sys.exit` raises `SystemExit`; an `except Exception` eats
    everything else. `BaseException` is what an ordinary catch-and-continue
    cannot quietly swallow.
    **Any non-blank value counts, including `0` and `false`.** A guard that
    parses its own setting has a way to be wrong about it, and the safe reading
    of an ambiguous value is to refuse.
    Considered and rejected: making refusal the default and requiring an opt-out
    to run for real. It fails closed, which is this project's habit elsewhere,
    but it would put a new deploy-time failure mode into the worker — a missing
    variable in `render.yaml` and the worker cannot start — in order to prevent a
    development-time mistake, landing the cost on production to protect the
    workbench. Opt-in, named in every agent brief, is the trade taken.
    **The residue, stated so nobody has to rediscover it.** A harness nobody told
    about the flag is unguarded, which is the point of opt-in. Beyond that, three
    ways past it are known and none is closed:
    (a) The Node side above.
    (b) **`importlib.reload`, or any fresh import after the variable is popped.**
    "On, never off" holds for a module object, not for a process: the import-time
    reading lives in that object, so reloading `common` or importing it in a
    subinterpreter re-reads an environment that no longer has the flag. Popping
    cannot lift it; popping and then reloading can.
    (c) **A child process handed a deliberately minimal `env=`.** A parent that
    builds a clean environment for a subprocess, which is the careful-looking
    thing to do, does not pass a flag it was never told to pass; `load_dotenv`
    then refills `DATABASE_URL` from `.env` in the child. Copying `os.environ`
    and stripping secrets is safe here and handing over a minimal environment is
    not, and the two look equally careful, which is incident 14's whole shape one
    level down.
    None of these is fixed in code on purpose: each fix has a way to be wrong
    about it, and an accurate description of the residue is worth more today than
    a second guard whose reach would need its own paragraph.
23. **Report the damage you measured, never the cleanliness you did not
    establish** (2026-08-01). Six of `check_extraction.py`'s signals need the
    paper's source archive: the length ratio, the two macro counts and the symbol
    survival rate. `source_latex_for` returned a bare `None` when the archive was
    not on the machine, the whole block was skipped in silence, and the paper
    fell out of the bottom as `clean` with an empty signals array. `--write`
    stored that. **Measured by the tester: same 224 papers, same text files,
    archives removed and nothing else changed, and 47 verdicts move, 39 of them
    to `clean`.** The docstring above the function had promised the opposite
    since the day it was written, and it was true of the text file and false of
    the archive.
    This is worse than a wrong warning, and the asymmetry is the point. A wrong
    warning is visible: it is on the page, a reader can weigh it, somebody
    eventually checks it. A reassurance nobody computed is invisible by
    construction, and on the dossier it is not even a sentence, it is the absence
    of one.
    So the two failures are separated: `absent` (not on THIS machine, the answer
    exists elsewhere, incident 7c) and `unusable` (an archive holding only a PDF,
    or none with a main `.tex`, the same on every machine). Either way the scan
    is incomplete, and an incomplete scan **may still return `suspect` or
    `damaged`** — residue, undecodable bytes, gaps and missing headings are read
    off the text alone, so a finding there is true whatever else was skipped —
    but it **may not return `clean`**, because `clean` is the only verdict that
    asserts an absence. It gets a verdict of its own, joins `no text on this
    machine`, is counted and named in the output, and `--write` skips it. None of
    the three could be stored anyway: migration 013's CHECK allows only the three
    real verdicts, so the alternative to skipping was a constraint violation or a
    lie. **A PDF-sourced paper is not incomplete for this**: there is no LaTeX to
    measure against, so those six signals are inapplicable rather than
    uncomputed, and its verdict still comes from the signals that do apply.
    Inapplicable and uncomputed look identical in a code path and are opposites
    in what they license.
    **Considered and rejected: refusing `--write` when the corpus looks
    partial.** It is the obvious control and it cannot be written. The Render
    worker's own disk was visibly partial on the run that produced the frozen
    batch — 12 of its papers had no text on it — so any threshold low enough to
    catch a laptop holding half a corpus would have stopped the worker auditing
    anything at all, and a stage that refuses on the machine it was built for is
    worse than the defect. A fraction between those two cases is exactly the
    guessed calibration this project has shipped three of. What is guarded
    instead is the degenerate case: `--write` refuses when not one paper in scope
    could be scanned through, which is an unmounted or wrong `DATA_DIR` and
    nothing else. `refuse_if_nothing_scanned` is split out so it can be driven
    with a list of scans and no database.
    The remaining exposure is a machine holding *part* of the corpus writing
    verdicts about text the maps were not built from. Nothing in the data
    distinguishes that machine from the worker, so it is covered by operator
    controls rather than a heuristic: `LINEAGE_NO_DB` (decision 22), the runbook
    saying `--write` belongs on the worker, and `--clear-verdicts` being what a
    database-only machine runs instead.
24. **The instrument is built and read before the calibration is changed**
    (2026-08-01). The extraction verdict has been recalibrated four times and
    every round did the same thing: run the corpus, read the rate, move a
    pattern. That is the detector agreeing with itself, and it could keep
    happening because a rate is the only number the tool produced. It says the
    check is wrong. It cannot say **which signal** is wrong, nor what removing
    one would cost, so the next change was always a guess.
    `--compare-verdicts` is separated from the change it exists to inform and is
    deliberately the whole of its own ticket. It adds a machine key to every
    signal, lifts `verdict_from` out of `scan_paper` so a current and a proposed
    verdict cannot come from two copies of the arithmetic, and prints a cross-tab
    and a sole-cause table. It moves no threshold.
    **The proposal is a module constant, not a flag.** One hypothesis,
    `PROPOSED_NOTE_SIGNALS = frozenset({"gaps", "package_macros"})`, hardcoded in
    version control where it can be reviewed and argued with; it shipped as
    `NOTE_SIGNALS` the same day (decision 25), and the proposal constant is now
    empty and waiting for the sixth round. A config file rots and a `--what-if`
    taking arbitrary thresholds is unreviewable: neither leaves a record of what
    was proposed on the day the number was taken, which is precisely what is
    missing from the four rounds already spent. A key no signal emits raises at
    import, because a typo would demote nothing and print two identical columns
    that look like a finding.
    **A preview that can write is one edit away from being the write**, the rule
    `PREVIEW_VERDICTS` was already built on, so `--compare-verdicts` refuses
    `--write`, `--clear-verdicts` and `--dry-run` at the argparse block, ahead of
    the older guards so the message names the flag the operator typed. Verified
    by capture: the mode issues two `SELECT`s and calls `commit()` never; only
    `--json` writes anything, and it writes a local file.
    **Two sole-cause columns, not one.** "The only reason this paper is not
    clean" is the question worth asking; "the only reason it carries the note" is
    the same question asked of the page, and the two differ exactly on papers
    whose source archive is not on this disk, where removing the last signal
    leaves "we did not look" rather than "clean". Printing one as the other is
    how a signal gets blamed for a missing file.
    **The prose stays the prose.** `extraction_signals` still stores
    `"{level}: {sentence}"` and the dossier is untouched; only the in-process
    tuple grew a key, so the per-paper `--json` audit now holds three-element
    signal arrays instead of two.
25. **A signal can be true, worth reporting and deliberately outside the
    verdict; and a verdict is invalidated by the code that computes it as well
    as by the text it describes** (2026-08-01, migration 014). Two rules, shipped
    together because the second is what makes the first safe on a live corpus.
    **The first.** `stale` invented the position and `gaps` and `package_macros`
    joined it, after the measurement decision 24 exists to take and not before.
    The test is not how often a signal fires or how sure it is: it is whether the
    action the signal implies is a warning to a reader. Those three imply
    re-extract the corpus, open this paper on arXiv, and teach the extractor a
    package. The dossier note can say exactly one thing — that the passage in
    front of you may be missing wording the paper had — so a signal whose finding
    is not that sentence has no business deciding whether the sentence appears.
    `NOTE_SIGNALS` is the set and `NOTE_LEVELS` the pair of levels a verdict
    ignores; the thresholds still compute the level they always did and one list
    comprehension at the end of `scan_paper` demotes what the set names, so
    promoting a signal back is a change to a frozenset and nothing else.
    **Reported means reported**: the signals are still emitted, still stored (as
    `note: ...` rather than `suspect: ...`, the one visible difference) and still
    printed by the audit and the sole-cause table. 134 of 304 papers drop package
    macros and that number is worth an operator's attention; what changed is who
    it is addressed to.
    **What this cost, measured on the Render disk over all 304 papers before it
    shipped**: the dossier note falls from 218 papers (72%) to 113 (37%), 105
    papers move `suspect` to `clean`, and **nothing moves stricter** — every
    occupied cell of the crosstab is on or above the diagonal. Both demotions can
    only remove signals, so that direction is a property rather than a hope, and
    it was checked before the deploy rather than after.
    **The second.** `papers.extraction_check_version` holds a 12-character digest
    of the audit's thresholds, patterns, signal keys, note set and note levels,
    computed at import; `--write` stores it and `--only-unchecked` selects
    `extraction_checked_at IS NULL OR extraction_check_version IS DISTINCT FROM
    <this version>`. `IS DISTINCT FROM` and not `<>`, because the column is NULL
    on every row written before it existed and `NULL <> 'abc'` is NULL, which
    would exclude exactly the rows this was built for.
    **A digest rather than a hand-bumped integer, specifically because it cannot
    be forgotten.** The 292 verdicts written at 10:08:43 on 2026-07-31 were
    computed by a calibration three commits replaced between 10:19 and 10:31, and
    they sat frozen for weeks because `--only-unchecked` filtered on the
    timestamp alone. A version somebody has to remember to raise is a version
    somebody forgets, and that is not hypothetical here, it is the incident. It
    also beats the `--clear-verdicts` plus restart ritual it retires for this
    job, because a mismatch leaves the old verdict in place until the new one
    replaces it instead of opening decision 21's unqualified-tick gap;
    `--clear-verdicts` stays for the machine that holds the database and not the
    papers.
    **What the digest does not cover.** It hashes the calibration inputs, not the
    file, so a change to the arithmetic touching none of them will not move it.
    The mitigation is that the arithmetic's own data is in the hash:
    `NOTE_SIGNALS` and `NOTE_LEVELS` are inputs precisely because this decision's
    first half is a change of data, and a demotion the stored verdicts could not
    see would be the same defect again. Verified: the digest is byte-identical
    across five processes with different `PYTHONHASHSEED`s, moves for each of
    eighteen calibration inputs including a regex flag and the note set, and does
    not move when `0.20` is rewritten `0.2`.
    **The risk this creates, which is real and was accepted.** On the worker's
    first boot after the deploy every audited paper mismatches, and the startup
    `--only-unchecked --write` rewrites the verdict, the signals and the
    checked-at on up to 304 rows across both live maps in one pass with nobody
    watching. That is intended and it is still a live rewrite of reader-facing
    state, so the runbook requires a full `--clear-verdicts --dry-run` dump on
    the Render shell *before* deploying — it writes the per-paper JSON to
    `DATA_DIR/snapshots/` and touches the database not at all — and requires the
    re-audit to be lenient-only, which the crosstab above is where that was
    checked.

---

26. **The owner pays for a trace, until the product earns organic usage**
    (Product Owner, 2026-08-02). Requester billing is deferred, not rejected:
    "I would pay for the trace, until we have a generator and product which is
    feature rich enough to generate usage organically, then users will need to
    pay." So there is one payer and one Anthropic balance, and every map a
    stranger asks for is spent from it.
    That makes three existing items load-bearing rather than merely correct.
    **The spend cap must bound a run, not a stage** (backlog item 2 and the
    `--spend-cap` flag): today it covers Stage B and Stage D only, is read fresh
    per stage so it resets rather than accumulating, and F, G and H compute
    spend and check nothing. **`genealogies.spend_usd` must actually be written**
    (it is `0.0000` on both maps; the real figure sits in
    `trace_requests.progress`), because it is the instrument that says when the
    trigger condition has been met. **And the non-owner quota must be
    enforceable**, since count-then-insert with no constraint behind it is the
    only thing between a stranger and the balance.
    Measured inputs: a map costs $1.47 and $1.92, but per-paper extraction cost
    varied four-fold between those two runs for reasons nobody has measured, so
    budget $4 until it is explained. A hundred stranger-generated maps is $170
    to $400.
    **Nothing here precludes requester-pays and no part of it should.** Per-run
    spend attribution is the foundation either way, so answering "the owner"
    now costs nothing and answering "the requester" later costs no rework.
    Building payments before the trigger fires would be scaffolding for later,
    which this project does not do. The trigger is a judgement about organic
    usage; the data that informs it is per-map cost and request volume, neither
    of which is recorded today.

27. **A map belongs to whoever paid for it; the extractions underneath belong to
    the platform** (Product Owner, 2026-08-02). Two layers with different owners,
    and the split is the product's economics.
    **The map is the buyer's.** Private by default, theirs to curate, with an
    option to publish if they choose. That answers what "users can curate" means
    in product rule 3 under the platform reading: the payer curates their own
    map, and rule 3 stops being satisfied only when "users" means the owner.
    **The extraction layer is the platform's, and is shared.** `definitions` is
    keyed `UNIQUE (paper_id, concept, prompt_version)` with no genealogy
    reference, so a paper read once for a concept is never read again for that
    concept at that prompt version, whoever asks next. This is not a change; it
    is how the schema has always worked, and it is now a deliberate commercial
    property rather than an implementation detail: the platform pays to read a
    paper once and can sell the reading many times.
    **The saving is real and its size is unmeasured.** Only Stage B is cached.
    Clustering, edge classification, magnitude, threads and claims all run per
    map and are paid again every time. Per-stage cost is not recorded anywhere
    ([#47](https://github.com/rgok001/Lineage/issues/47)), so what fraction of a
    map's $1.47 to $1.92 the cache actually avoids is unknown. Record per-stage spend before pricing anything on
    this.
    **The carve-out, which is not optional.** Sharing an extraction is safe
    exactly when the paper is public anyway, which is true of arXiv and need not
    be true of an uploaded corpus. An unpublished manuscript read once and cached
    without an owner would surface in a stranger's map, attributed, by the same
    mechanism that delivers the saving. So: **extractions from arXiv are shared;
    extractions from user-supplied papers are owned by the uploader and never
    enter another user's map.** The cache key gains a nullable owner, and a null
    owner means public-source and shareable. Losing the saving on uploaded papers
    is the correct trade, and the copyright position on storing extracted text
    from papers a user supplies is a separate question this entry does not
    settle.

28. **Authors come from arXiv first; OpenAlex is fallback only.** BibTeX needs
    authors and product rule 4 forbids inventing them, so `enrich_authors.py`
    keys by `arxiv_id` — which the fetcher *proved* correct by downloading that
    paper's source and passing the title-match guard, so arXiv cannot return
    another paper's authors. OpenAlex ids have produced wrong metadata here
    repeatedly: it returned **one** author for Bahdanau instead of three, and
    attributed `cond-mat/0308217` to a psychologist rather than M.E.J. Newman.
    A wrong key silently yields the *wrong* authors, which is worse than none,
    so papers whose authors stay unknown are omitted from BibTeX, never guessed.

29. **The clustering threshold is 0.28, and this corrects decision 5**
    (2026-08-02, item `[B9]`, issue 12). Decision 5 recorded 0.16 and stays as
    written: it is a true claim about the day embeddings ran locally on
    bge-large. The move to the Voyage hosted API (decision 13) invalidated the
    number without touching the reasoning, because a cosine distance is only
    meaningful against the model that produced it. Recalibrated on the
    134-definition `embedding` corpus, 0.16 sits at the 1st percentile of
    Voyage's pairwise distances and merges almost nothing (105 clusters, 87 of
    them singletons); 0.28 is the loosest value that still holds the distinct
    senses apart. The measurements are in `docs/PIPELINE.md` section 4 under
    Stage C, which is where a number a code change can invalidate belongs.
    **The entry exists because the recalibration shipped without one.**
    `stage_c_cluster.py` has said 0.28 since commit `23c4512` on 2026-07-23;
    the record went on saying 0.16 for the ten days until this commit, and two
    documents agreeing with each other is exactly what let it. That gap is what
    `pipeline/check_record.py` now closes on commit (issue 54).

30. **A stamp names the bytes it was checked against, and a stamp that cannot be
    re-checked says so** (2026-08-02, item `[F1]`, issue 29, migration 015). Every
    verification stamp in this system was an assertion the pipeline made about a
    file on one worker's disk at one moment, and nothing stored beside it said
    which file, which bytes, or where in them the quote was found. A reader could
    not re-check a tick and neither could we without holding the corpus, which
    makes it a claim about evidence rather than evidence. Each stamp now carries
    the matched span, a `sha256` digest of the bytes the match ran against, and
    the extractor version of that text; `papers` carries the digest of the file
    as it is on disk now, written by the only code that writes the file. A stamp
    is displayable as verified only when the two digests are equal.
    **Three things make this a check that can fail rather than one that agrees
    with itself.** The two digests are never copied from one another — one is
    written by the code that just performed the match, the other by the code that
    just wrote the file. The stored span is explicitly not treated as a second
    confirmation of the boolean, because the same matcher put it there. And there
    is no threshold anywhere in it: every comparison is exact equality, and the
    two whole-run refusals use the degenerate boundary (*not one* file readable),
    which is a state rather than a calibration.
    **There is no honest backfill of a stamp column**, and the design says so
    twice on purpose. Filling `quote_text_digest` from the paper's current digest
    would turn every unproven stamp green in one statement, which is the silent
    re-anchoring incident 10 established as dishonest. Between the migration and
    the first re-ground every stamp renders stale, including all 287 verified
    edges on `attention`; that window is minutes and the fix is free, because
    re-checking was built to cost nothing (`--reground`, Stage E, Stage H
    `--recheck`).
    **The extractor version is provenance, not an invalidator.** Letting it make
    a stamp stale would redden the whole corpus on every extractor commit, and it
    would be wrong: if the bytes on disk have not changed, a stamp against them is
    still about that text. It is digested from a curated set of the extractor's
    own inputs rather than from the file, for the reason migration 014 curated
    its own: a detector that fires on nearly all of its input has stopped
    measuring its input. It is written only by the code that produced the file,
    never by the skip path that merely read one, which is what keeps
    `extractor_version IS DISTINCT FROM <current>` a usable re-extraction queue.
    The design is `docs/design/recheckable-stamp.md`; three of its render sites
    were found during implementation and are named there.
    **Two rules were added after review found the first implementation could
    still only agree with itself** (issues 55 to 63, Tester, same day). Stage E
    now makes every write inside one transaction, because the whole-run refusal
    sat after the loop on an autocommit connection: the quote re-sync had already
    committed when it said "nothing was written", leaving a new quote beside the
    old span and the old tick, which the page resolved to verified. And
    `recheck_stamp.py` now resolves against the bytes it has just read rather than
    against the database's digest of them — resolving against the database is the
    comparison the application already makes without a disk, and it is why the
    design's own falsifier 12 passed silently. A quote that folds to nothing
    ("`<cit.>`", whitespace) is no longer grounded at all: the empty string is a
    substring of everything, so that check could only ever agree with itself, and
    a quote carrying no characters of the paper is not evidence.
    **Three of those repairs then had to be repaired** (issues 64 to 66, same
    day), and the pattern in all three is a fix that moved a value without moving
    everything downstream of it. The re-ground's "has anything moved?" test was
    written beside the values it tests rather than derived from them, so it went
    on asking about the pre-fix expression. Stage E's new transaction swallowed
    the JSON export and the success report, which had been after the writes were
    durable, so a failing `COMMIT` destroyed the backup and announced a success:
    **a backup must never describe a state the database did not reach**, so the
    content is written to a temp path inside the transaction and renamed after it.
    And `recheck_stamp.py`, having been moved from the database's digest to the
    disk's, then answered only the disk's question, which is truer than the
    product's and is not the product's: it now reports both and treats a
    disagreement as a finding.

31. **Deployments are fully automatic, migrations included, and the owner chose
    it knowing what it retires** (2026-08-07, Product Owner, issue 102). Until
    now the app auto-deployed on push, the worker deployed from the blueprint,
    and database migrations were the one deliberately manual act: run from the
    owner's terminal, so that agent-written work could not reach the production
    database without a human between. The owner was offered semi-automatic — keep
    exactly that one manual command — with the trade-off stated in plain terms:
    full automation means the day an agent pushes flawed work, it changes the
    production database with no human in between. The owner chose full
    automation; the manual step was rare enough to be forgettable and forgotten,
    and a checkpoint that is a hassle is a checkpoint that gets skipped or
    batched, which is its own failure mode.
    What implements it: the worker's blueprint gains `autoDeploy: true` and
    `preDeployCommand: python pipeline/db/migrate.py`, so Render applies pending
    migrations before it swaps in the worker code that expects them. The worker's
    `DATABASE_URL` is already the direct endpoint migrations require. Agent
    sessions remain database-refused — `LINEAGE_NO_DB` is untouched; what changed
    is who carries a migration to production, not who may talk to the database
    from a shell.
    Two consequences are accepted rather than hidden. The Vercel app can go live
    minutes before the worker's pre-deploy applies a migration, so **migrations
    must be additive and the app must tolerate a schema one migration behind**
    (issue 92's fallback is the pattern, and migration 016's own deploy window is
    the precedent that survived it). And an auto-deploy restarts the worker,
    killing and requeuing any in-flight trace; acceptable at current volume,
    revisit when traces are frequent. The manual `migrate.py` path stays in the
    runbook as the emergency route.

32. **The dark palette is blessed; the law now records what ships**
    (2026-08-07, Product Owner, issue 116). The UX review found `CLAUDE.md`'s
    token section still carrying the light palette from the original approved
    mockup while the site has shipped a coherent dark system for weeks, and
    one of the six edge types (`merges`) had no colour in law at all. Asked
    which had moved — the system violating its law, or the law lagging a
    choice already made — the owner blessed the dark palette. `CLAUDE.md` now
    records the shipped values from `app/app/globals.css` verbatim, including
    all six edge colours and the two stamp colours. The light values survive
    only in this entry and in git history.

33. **Source-available under PolyForm Noncommercial 1.0.0** (2026-08-08,
    Product Owner, issue 142). The repository had no license, which legally
    means all rights reserved but reads as ambiguous to anyone deciding
    whether they may use the code. The owner chose the middle path between
    closed and open source: the repo stays public to read and free to use for
    any noncommercial purpose, and commercial rights — including hosting
    Lineage as a service — stay with the owner. Considered and rejected:
    MIT/Apache (would let a competitor host a clone of a product the owner
    may commercialise), AGPL (open source, but companies' blanket AGPL bans
    limit even legitimate noncommercial reading), and the Business Source
    License (its mandatory change date converts the code to open source
    automatically, a future decision the owner did not want made in advance).
    `LICENSE.md` carries the license text byte-for-byte from the PolyForm
    project's official repository (tag 1.0.0) plus the one line the license
    itself provides for: a `Required Notice:` naming the copyright holder.
    Relicensing later is possible because there are no outside contributors;
    that ease ends if a contribution is ever accepted without a contributor
    agreement.

34. **A BibTeX escape is chosen for BibTeX's brace counter, not for LaTeX**
    (2026-08-08, issue 141, from CodeQL alert 1). Completing the escape set for
    the export meant deciding what `{` and `}` become, and the obvious answer,
    `\{` and `\}`, is what every LaTeX reference gives. It is wrong here.
    BibTeX finds the end of a field by counting braces and does not look at
    backslashes while counting, so a title reading `Unbalanced { brace` escaped
    to `Unbalanced \{ brace` still swallows the rest of the entry. That was
    measured, not reasoned: the `\{` version lost 2 of 12 adversarial entries
    through a real BibTeX parser before `\textbraceleft{}` and
    `\textbraceright{}` replaced it. Those carry one brace of each kind, so the
    whole escape table is brace-balanced and no input can change the depth the
    exporter opened the field at. The same argument sets the shape of the
    function: one regex pass over the ten reserved characters with a lookup for
    the replacement, never a chain of replaces, because a chain rescans its own
    output and `\textbackslash{}` contains three characters the later rules
    would escape again.
    The accepted cost is that a title written `{BERT}` on arXiv to protect its
    capitalisation loses that protection. The field is already wrapped in a
    second pair of braces for exactly that purpose, so the inner pair buys
    nothing; and honouring an inner brace means honouring an unbalanced one,
    which is the defect. A researcher's `.bib` staying parseable outranks a
    capital letter.

35. **The type the law names is the type that ships: Georgia and the system
    stacks, no webfonts** (2026-08-08, issue 148, Product Owner). EVE's review
    of the speed work found `document.fonts` empty on every page: the Spectral
    and IBM Plex families named by decision 32's token line were never loaded,
    and every page the owner blessed on 2026-08-07 rendered in the fallbacks —
    Georgia and system-ui. The law and the running system disagreed, and the
    owner ruled the law had moved: the token now names Georgia (display/quotes),
    the system UI sans, and the system monospace. Webfonts were declined
    deliberately, not overlooked: three families even self-hosted and subset are
    ~150–250 kB of render-blocking fetch on the critical path issue 140 had just
    paid down, and a late font swap moves text under the reader's eye on the one
    page whose purpose is that a quotation can be checked. The reader loses
    nothing they ever had. If Spectral is ever wanted, the recorded honest
    version is display face only, self-hosted, subset, `font-display: swap` —
    never all three families. This corrects the type line of decision 32; the
    palette and everything else in decision 32 stand.

36. **All of arXiv, every field: the ML/CS restriction is lifted** (2026-08-08,
    issue 161, Product Owner: "we should not discriminate"). The F7 design
    (issue 35) measured what the scope law was holding shut: the trace form's
    field picker, `isKnownField()`, and `corpus_select.py --field` already
    carry any arXiv field end to end — the capability shipped, only the law
    forbade it. arXiv holds 3,208,161 works of which Computer Science is 24%;
    the largest audience expansion available cost a decision, not a build.
    Quality in new fields is read per map on the shipped report at the moment
    a map is judged — deliberately no pre-approval gate and no threshold,
    consistent with decisions 24 and 25 (n=2 baselines are a reference, not a
    bar). The architect's two calibration traces (economics, physics — issue
    164) remain worth running as measurement, but they gate nothing: the
    owner opened the door on principle, and the instrument exists to see what
    walks through it. Non-arXiv sources remain sequenced behind the field
    widening and F10 (issue 165) per the design on issue 35.

37. **Correction to decision 36** (2026-08-08, same day, issue 175). Decision 36
    says the field picker, `isKnownField()`, and `corpus_select.py --field`
    "carry any arXiv field end to end". The middle claim is false: the #175
    investigation grepped the call sites and `isKnownField()` is called from
    nowhere — the submit path validates shape only (`/^fields\/\d{1,4}$/`),
    so the picker was never the allow-list and crafted field ids pass through.
    The decision itself stands unchanged; only its supporting description of
    the mechanism was wrong. Real membership validation ships under issue 175.

38. **A run killed by infrastructure restarts itself; a run that failed on its
    own does not** (2026-08-08, issue 178, after incident 15). The owner's
    instruction was the specification: "can you fix it so if they fail they
    automatically requeue. It not reasonable to expect someone to observe and
    retry upon failure." Three parts, and the third is the one that decides what
    this is worth.
    **SIGTERM joins Ctrl-C.** Decision 31 made every push to master a worker
    deploy; a deploy stops the old worker with SIGTERM and waits before SIGKILL,
    and that window is now spent putting the job back on the queue. Nothing else
    was needed for the case that actually happened.
    **The sweep restarts rather than fails, up to three times.** A `running` row
    with a cold heartbeat is a death with nothing to say, and there is no
    diagnosis to lose by trying again. The cap exists because the alternative is
    a crash-looping worker restarting one job forever: restarts are cheap, since
    every LLM stage caches per paper, but cheap is not free and the spend cap in
    CLAUDE.md is per trace rather than per job-lifetime. Three, because two
    consecutive deploys landing on one build has already happened (incident 15,
    pushes four minutes apart) and a job that has died four times will not
    survive the fifth. The count lives in `trace_requests.requeues`, migration
    018, and the constant that reads it is `MAX_AUTO_REQUEUES` in `worker/run.py`.
    **A stage that exits nonzero still fails on the first try.** That is the
    boundary, and it is drawn in one function, `classify_stage_exit`. A stage
    failure has written diagnostics and will write them again; restarting it
    would re-bill for a deterministic result and bury the error under repeat
    attempts. The complaint being answered is about deaths that carry no
    information, not about failures that carry plenty. The two cases were
    indistinguishable before only because the worker never noticed the signal:
    catching SIGTERM is what makes "died silently" a small residue rather than
    the normal case, and the sweep's retry is the safety net under that residue.
    **The polite requeue does not spend the retry budget**, deliberately: it runs
    only when something deliberate stopped the worker, it always leaves a log
    line, and it cannot repeat without a person acting again. Charging deploys
    against the cap would mean four pushes during one long build permanently
    failing a job that nothing is wrong with, which is the complaint rather than
    a defence against it.

39. **Correction to decision 38's cost argument: three of the paying stages
    cached nothing, and now one of them does** (2026-08-09, issue #202).
    Decision 38 caps auto-requeues at three and defends the cap with "restarts
    are cheap, since every LLM stage caches per paper". The cap stands and the
    reasoning for three stands; that one clause was false when it was written.
    Stage B has cached per paper in `definitions` since the first pipeline,
    Stage C's labels since #189 and Stage D's classifications since #172 — but
    **Stages F, G and H cached nothing at all**, so a restart re-bought them in
    full. Stage H is the one that mattered: its call is a pure function of the
    concept, the paper, the prompt and the model, and at ~3.7c a paper it is
    about $3.00 of a $12.31 map, a quarter of the bill (the anatomy on #199).
    Incident 15's two builds died at stage 2 of 13, so neither had reached
    Stage H — but a deploy landing later in a build re-bought every claim on the
    map, three requeues allow that three times, and nothing anywhere said so.
    #202 gives Stage H the same content-addressed disk cache the other two have,
    keyed on the semantic inputs and holding no stamp, so a rebuild over
    unchanged papers buys none of it. Measured on a throwaway PostgreSQL over one
    fixture map, two runs of the stage over unchanged input: 5 calls and
    `$0.1725`, then **0 calls and `$0.0000`**, claim for claim identical.
    **Stages F and G still do not cache, and this entry says so rather than
    leaving the record sounding complete.** F was left alone on measurement, not
    oversight: it scores citations on Haiku in batches of twelve, so a map's few
    dozen calls are cents where Stage H is dollars, and its natural key is the
    batch, which every paper added to a corpus shifts — a cache that misses on
    exactly the rebuilds #192 performs, bought with a file that would have to be
    right about `genealogies.nodes` to be safe. G is one whole-map call whose
    answer *is* the thread membership, and freezing that across rebuilds is a
    product change rather than a saving. Both remain re-bought on every restart,
    and the honest reading of decision 38 after this ships is that restarts are
    cheap for B, C, D and H and merely cheap-ish for F and G.

40. **A costing function refuses an unknown model rather than pricing it at a
    guess** (2026-08-09, issue #205, after incident 16). `cost_usd` priced any id
    it did not recognise at `PRICING[DEFAULT_MODEL]` — the most expensive row in
    the table — and Stages F and G pass a dated snapshot that was not a key, so
    for months both printed five times what their calls cost. The fix is two
    rules, and the second is the one worth arguing about.
    **A dated snapshot is priced as its family.** `claude-haiku-4-5-20251001` is
    billed at `claude-haiku-4-5`'s rates, so `pricing_key` strips a trailing
    `-YYYYMMDD` and looks the family up. The alternative — a table row per
    snapshot — makes every model pin a two-file change and fails a build when
    somebody forgets the second one.
    **Anything still unknown raises.** A lookup with a default converts an
    unknown key into a confident wrong number, and this number is not a
    diagnostic: it is published as what a map cost, it is what
    `TRACE_SPEND_CAP_USD` decides on, and since #47 it is stored per stage. A
    default is also unbounded in the wrong direction — this one guessed high, and
    the same expression with a cheaper default would have let a run walk through
    its own cap. This is the zero-versus-absence rule (#87) applied to money: a
    figure that cannot be computed must announce itself, not resemble one that
    can. Every paying stage resolves its model before it builds a client, so the
    refusal lands before the first call rather than after it; `--reground` and
    `--no-label` stay outside it because they buy nothing.
    **A rate that moves on a date is held as both numbers and the date.** Sonnet
    5 is on introductory pricing to 2026-08-31, standard from 2026-09-01, and the
    table held only the standard pair — right in three weeks, wrong by 50% today.
    `rates_for(model, on)` takes the day of the call. This is the smallest thing
    that is not wrong on one side of a date, and it was found by reading
    Anthropic's published page rather than trusting the table, which is now what
    the table's comment tells the next person to do.
    **Stored figures were not corrected**, deliberately: each is what a build
    claimed under the table it ran with, and the as-built (section 3) records
    which ones are overstated and by how much.

41. **A constraint is dropped in the commit that removes what needs it, not one
    wave earlier** (2026-08-10, issue #206, against the F4 design on #32). The
    design ended migration `025` with `DROP CONSTRAINT
    genealogies_concept_pv_key`, in a ticket whose stated reason for existing is
    that it changes no behaviour. Those cannot both hold. `stage_c_cluster.py`
    upserts with `ON CONFLICT (concept, prompt_version)`, and Postgres resolves
    an `ON CONFLICT` target's arbiter index when it **plans** the statement, so
    with the constraint gone that INSERT raises `InvalidColumnReference` on every
    build — including the first build of a concept nobody has mapped, where a
    conflict cannot occur. Executed on a throwaway PostgreSQL against Stage C's
    own statement text, not reasoned about.
    **So `025` ships the whole shape and none of the drop**, which moves to #207,
    the commit that rewrites Stage C to insert. Nothing in `025` wants it: the
    partial index, the CHECK and `UNIQUE (concept, prompt_version, version)` are
    independent of it, and the last of those is the replacement key, applied and
    verified now so #207's drop is one line against something already in place.
    **The general rule this records**: when a migration removes a guarantee and
    the code that relies on it is in a different ticket, the guarantee outlives
    the ticket boundary, not the other way round. A schema change lands early and
    harmlessly; a schema change that removes something lands with its caller or
    it lands as an outage. 007's own header names three guarantees, and the third
    — thirteen scripts resolving a map by `(concept, prompt_version)` with a bare
    `fetchone()` — is not replaced by the partial index, which keys on `(concept)
    WHERE is_current` and answers a different question.
    **One behaviour did change and was accepted rather than designed around**:
    the CHECK refuses re-clustering a live map in place, because that sets
    `status = 'running'` on a current row. It is the destructive overwrite F4
    exists to remove, refused a wave early, loudly, with the constraint named;
    the operator path — delete first, then re-trace — is what decision 12 already
    required. Recorded in the as-built and the runbook rather than left to be
    discovered.

42. **A map's id names a version for ever; the concept gets a separate address**
    (2026-08-10, issue #208, the Architect's ruling on the F4 design, #32). The
    obvious alternative — `/g/17` means "the dark energy map, whatever version
    that is now" — is wrong for this product specifically. A reader who cites a
    map in a literature review is citing a set of claims, and if the id silently
    comes to name a different set, **their citation points at something they
    never read** and the tool whose whole value is that a claim can be checked
    has broken the check. The same reasoning already governs quotes, stamps and
    BibTeX keys here. So a superseded version renders in full at its own address
    — map, evidence, threads, dossier, report, export — with a line saying it was
    replaced and where the current one is; `/g/<id>/current` is the address that
    follows the concept, and the concepts list shows current versions only.
    **The four read functions therefore have three different rules and are
    deliberately not uniform**, which is the part a later reader is most likely
    to want to "fix": the list is current-only because "which concepts have been
    mapped" has one answer per concept, while `getGenealogy` and `getMapRow`
    serve any published version because an id is a version. Currency is layered
    on `status = 'complete'` (#168) and never replaces it, so a build in flight
    is invisible whether or not the currency filter was remembered.
    **And the guard differs with what is guarded.** The list's currency filter is
    probed for with `to_regclass`, because a silent fallback on a filter would
    put superseded versions back on the front page without saying so; the version
    facts a page prints are read behind a `try`, because a missing *column*
    cannot be probed (#182) and losing them costs a line rather than a rule. The
    fallback in both directions is exact rather than degraded: before migration
    025 there is one published row per concept, so the old query returns the same
    set as the view.

43. **A build writes a new version and resolves rows by asking which of two
    questions it means; a resume is named, never inferred** (2026-08-13, issues
    #207b and #214, implementing the Architect's design on #214). Three separate
    choices, recorded together because each is the reason the next one is
    survivable.
    **A rebuild INSERTs.** Stage C mints `version = max + 1` per concept and
    writes nothing a reader can see; Stage E's swap is what moves readers on.
    Migration 007's `UNIQUE (concept, prompt_version)` goes in migration 027, in
    this same commit, for decision 41's reason executed a second time: the old
    `ON CONFLICT` Stage C against a database with the constraint gone raises
    `InvalidColumnReference` on the first build of a concept nobody has mapped,
    measured on a throwaway Postgres before this commit was written.
    **Two predicates, not a rule per script.** The fifteen sites that resolved a
    map by `(concept, prompt_version)` each mean either "the row this build owns"
    (`status <> 'complete' ORDER BY version DESC LIMIT 1`) or "the live map"
    (`AND is_current`), and now say which. The alternative — passing a genealogy
    id through every CLI as a required argument — is honest and a week; the two
    predicates plus an optional `--genealogy-id` are a day and give the same
    determinism, because a build's own row always carries the highest version and
    every corpse is older.
    **Resume is explicit.** Stage C writes `{genealogy_id, version}` to
    `--result-json`; the worker binds `--genealogy-id` onto every step after pass
    one. There is deliberately no "reuse the newest running row" rule and no
    timestamp threshold, so no build can adopt the corpse of one that died three
    weeks ago, and an unreadable result file fails the build rather than letting
    each later stage resolve one for itself.
    **What this retires**: decision 12's "delete the map first, then re-trace" is
    no longer the rebuild path — a rebuild is now non-destructive, and rolling
    back is restoring a version's export, which comes back as a further version.
    Decision 41's accepted regression (a re-cluster of a live map dying on a
    CHECK) is retired with it: there is nothing to re-cluster in place.

44. **A version number is minted under a lock and never re-issued; superseding
    the live map, and buying for a row nobody named, are refused** (2026-08-13,
    issues #241 and #242, implementing the Architect's repair ruling posted on
    #241). Four commits, one rule, and the rule is about what an act destroys
    rather than about how confident a predicate is.
    **`status <> 'complete'` cannot mean "a build in flight".** Nothing in this
    system clears `running`: a build SIGKILLed, SIGTERMed at a deploy, or dying
    in its finish phase leaves that row for ever, and migration 027's own header
    calls it the normal residue of a failed build. So `build_row` finds a corpse
    as readily as a build, and the documented bare `stage_e_ground.py
    "<concept>"` published one over a curated live map — measured, exit 0, every
    curatorial edit gone from what readers see. A predicate no sweeper maintains
    may keep the acts that write nothing a reader sees, and may not keep the act
    that replaces what a reader is seeing. Stage E's publish and Stage H's buying
    now refuse a predicate-resolved row while the concept has a current map;
    `--genealogy-id` names a version and `--current` (Stage E) or `--recheck`
    (Stage H) names the live map. **The refusals nominate nothing**: they print
    the unpublished versions with status and age, and the commands with a
    placeholder id, because printing the newest candidate's id in a runnable
    command is the adoption they exist to prevent.
    **The version key moved to `(concept, version)`, with a hole stated rather
    than papered over.** 025's `UNIQUE (concept, prompt_version, version)` was
    claimed to make a lost race "a refusal rather than two rows both calling
    themselves version 2"; measured, at one prompt version the loser died on an
    unhandled `UniqueViolation` after Stage B's money, and at two prompt versions
    both rows were minted as version 2 with nothing raised. Migration 028 adds
    `UNIQUE (concept, version) WHERE version > 1`. It is partial because 025's
    backfill made every row that then existed version 1 and renumbering rows
    readers have addressed since #208 is the worse trade — so version 1 is
    unconstrained across prompt versions, the advisory lock in the mint covers
    it, and the index is the backstop for a writer that skipped the lock. The
    alternative, a total index, could not be created on the database we have.
    **A ledger, not a counter.** 028's append-only `genealogy_deletions` records
    the numbers deleted maps had, and the mint takes the greatest of the live rows
    and it, so a deleted version's number is never issued again over that
    version's export — the de-facto backup (incident 4). A `next_version` column
    would be a cache of history that re-issues silently when it drifts, and the
    row it would collide with is exactly the one that is gone.
    **What this retires**: #207b's claim that `build_row` is "deterministic
    without a lock, because a build's own row carries the highest version". It
    holds only until the next Stage C runs for that concept, so the worker now
    binds `--genealogy-id` from the clustering onwards rather than from the end of
    pass one, and the read-only instruments (`check_map.py`, `recheck_stamp.py`)
    answer about the live map instead of conjoining every version's verdict.


## Shipped since the first draft

Moved here from as-built section 11 on 2026-08-02. It is a progression record
rather than a list of open work, which is why it did not go to GitHub Issues
with the rest of that section, and why it sits below the numbered decisions
rather than among them. It is dated to the moment it was written and is not
maintained.

Done since first draft: Render worker deployed and verified live (2026-07-21);
Stage C genealogy upsert (migration 007, stable id); account Anthropic billing
cap (owner, confirmed set); topic picker + sense gloss (as-built section 11 item
9, now section 3); family grouping on the evidence page; the showcase
"embedding" map traced (`/g/10`; not curated, see as-built section 1); the
influence-map front door, thread accounts and paper dossiers; requests moved to
their own page; one tab bar and a public roadmap; export for writing
(`/g/[id]/export`, whole map or one thread) with the author backfill run over
the showcase corpus so its citations resolve; magnitude and threads promoted
from one-off scripts to stages F and G, which the worker now runs, giving a
second map (`attention`, `/g/13`) a real front door.

**Unresolved contradiction, flagged rather than decided (2026-08-02, Curator).**
This list says the account-level Anthropic billing cap is "confirmed set". The
as-built's security model says "an account-level cap at console.anthropic.com
(owner action, recommended, **not yet confirmed set**)". Both sentences were in
the same file. Only the owner can say which is true; neither was changed.

---

# Design: make the record's claims resolvable, and resolve them on commit

**Ticket: [#54](https://github.com/rgok001/Lineage/issues/54).** Written
2026-08-02 against `master` @ `5177253`.

**Status: approved by the Product Owner, 2026-08-02. Implemented the same day as
`pipeline/check_record.py` and `.githooks/pre-commit`.** Section 7's four
falsifying inputs were all run and all behaved as specified: the clean-tree run
found the two named assignment instances and nothing else, changing the code
constant blocked a real commit from Git Bash and from PowerShell, an
undocumented `pipeline/stage_i_nothing.py` blocked one naming the file, and
renaming the assignment form out of all four claims produced
`check_assignments resolved nothing; the instrument is broken, not the record`
rather than a clean report. Both instances are now fixed, which closes
[#12](https://github.com/rgok001/Lineage/issues/12) `[B9]`.

**What the implementation changed, and why (Developer, 2026-08-02).** Five
things did not survive contact with the code.

- **The record set is the eleven classed files and not "every file under
  `docs/`".** `docs/design/` is excluded, because a design document quotes the
  wrong value on purpose as its evidence: this file's own section 2 quotes
  `DEFAULT_THRESHOLD = 0.16` to prove it stale, and checking it would invert
  that. Neither design file declares a `CLASS:` and the destinations table has
  no row for `docs/design/`, which is an owner question. The exclusion restores
  the eleven-file floor section 5.2 measured.
- **`pipeline/check_record.py` excludes itself from the code it reads.** On its
  first run the comment explaining why `DEFAULT_THRESHOLD = 0.16` is stale
  satisfied the claim that it is stale, and the known drift instance went green.
  That is the project's fourth fault, a check that agrees with itself, arriving
  inside the check written to prevent it.
- **The colon form needs a quoted key on the record side.** Unquoted,
  `note: ...` in a sentence, `suspect: ...` and the runbook's
  `C:\Users\...\python.exe` all parse as assignments; measured, three of the
  four false positives on a clean tree.
- **The zero-resolution guard covers the four checks with measured floors**
  (classes, assignments, citations, coverage) and not `check_attestations`. A
  convention introduced by this change has no instances by construction, so
  guarding it would block every commit while asserting nothing.
- **Migration coverage has to read `001..014`.** Six of the fourteen numbers are
  named only by the range forms in `docs/AS-BUILT.md` section 2 and section 3, so
  a literal check reports six false positives on a clean tree, which section 7
  declares falsifying.

Two of section 2's counts were narrower in practice. `check_citations` reads 11
citations, not 31: the other 20 are in `.claude/memory/.snapshots/`, frozen
copies rather than record. `check_symbols` counts 56 tokens rather than 115 and
flags 2 rather than 9, because it takes a token as symbol-shaped only if it
carries an underscore or an internal capital, which drops the English words.
Both floors are still comfortably above zero.

Ten of the eleven citations are in `.claude/memory/dashboard.md` and nine of
those name role prompts outside this repository. They are `WARN` and become
`FAIL` under `--all`; the durable fix is the `manager.md` change section 9
proposes, which is the owner's to make.

## 1. The problem

The record declares, in every file's first two lines, who is responsible for
keeping it true, and nothing anywhere checks that they did. `RECOMPUTED BY: the
Developer` is an assignment. Ten instances of drift in one working session were
each found by a human or an agent sweeping for something else, and several only
because a role had been told to be suspicious of one named file. The layout is
sound; the layout was never the problem. What is missing is an instrument that
can go red without anyone remembering to look, and that goes red about the *code*
rather than about the documents' agreement with each other.

## 2. What I measured before designing, and why it changed the design

The ticket proposes some mechanisms. I prototyped four of them against the real
record — 11 classed files, ~2,900 lines, 500 distinct backticked tokens — before
choosing. Two of the results overturn the obvious design.

**A dangling-path check is unusable here. Measured: 8 hits, 8 false positives,
0 true positives.** Of the 52 path-shaped backticked tokens in the record, 8
resolve to nothing: `docs/ARCHITECTURE.md`, `docs/BACKLOG.md`, `docs/FIX-LOG.md`
(×2 each), `error.tsx`, and `pipeline/db/migrations/NNN_name.sql`. Every one is
correct prose. `CLAUDE.md:112` says "the deleted `docs/ARCHITECTURE.md`";
`docs/AS-BUILT.md:534` says those three files "were deleted";
`.claude/memory/board.md:19` says `docs/BACKLOG.md` "was folded into GitHub
Issues"; `docs/DECISIONS.md:135` asserts an *absence* — "`app/` has no
`error.tsx`" — which an existence check inverts into a defect; and the migrations
one is a filename template. The record's most valuable habit, naming what was
removed and why, is textually indistinguishable from the defect. A check that is
wrong eight times out of eight is ignored on its second run. **Do not build it.**

**An assignment-form check works, and found a live drift instance in under a
minute.** The record contains four claims of the shape `` `IDENT = literal` ``.
Two are wrong right now:

- `docs/PIPELINE.md:341` — "`DEFAULT_THRESHOLD = 0.16` was calibrated on
  bge-large". `pipeline/stage_c_cluster.py:57` has said `DEFAULT_THRESHOLD = 0.28`
  since the recalibration. This is the ticket's instance 1, still open as #10.
- `docs/PIPELINE.md:229` — "**`PROPOSED_NOTE_SIGNALS = frozenset({"gaps",
  "package_macros"})`**, a module constant". `pipeline/check_extraction.py:258`
  has `PROPOSED_NOTE_SIGNALS: frozenset[str] = frozenset()`, emptied when that
  hypothesis shipped. **This is an eleventh instance, not on the ticket**, in a
  `derived` file that was split and recomputed earlier the same day. A reader
  acting on that sentence would run `--compare-verdicts` expecting a demotion
  preview and get the identity matrix.

A third apparent mismatch, `LINEAGE_NO_DB = 1` in `CLAUDE.md:103`, is real and
correct — it is declared in `.claude/settings.json` as JSON, which my prototype
regex did not read. That is a specification detail below, not a finding.

**A code-to-docs coverage check has a 0% false-positive rate today and would have
caught instance 10.** All 19 scripts under `pipeline/` and all 14 migration
numbers are named somewhere in `README.md` or `docs/`. When stages F, G and H
landed with no documented invocation, this check would have been the only thing
in the repository that knew.

**A symbol-existence check is marginal.** 115 distinct symbol-shaped backticked
tokens, 9 unresolved (7.8%), and all 9 are legitimate: env vars set outside the
repo (`LINEAGE_READ_URL`, `PYTHONHASHSEED`), a Postgres role (`lineage_ro`), two
git SHAs, agent-prompt vocabulary (`novel`, `refinement`), a git subcommand, and
one historical name. Zero true positives today. It earns its place only as a
rename detector, and only at warning level.

**Line citations are already rare and already broken.** 31 `file:NNN` citations
exist. Thirty are in `.claude/memory/dashboard.md` and its snapshots; one is a
code cite in `docs/DECISIONS.md:339`. `dashboard.md:46` cites `AS-BUILT.md:1849`
into a file that is 559 lines long. By contrast, all 44 "section N" citations and
all 29 markdown link targets still resolve, across three restructures in two days.

## 3. The design

One script, one hook, one convention. No new directory, no new class, no CI.

### 3.1 `pipeline/check_record.py`

It sits beside `pipeline/check_extraction.py` because it is the same kind of
object — an instrument that reads artefacts and reports — and because `pipeline/`
already holds non-stage tools (`diagnose_parse.py`, `snapshot_map.py`,
`workbench.py`). No new row in the destinations table is needed for a script.

Pure standard library. It opens no database, imports nothing under `pipeline/`
that does, and honours `LINEAGE_NO_DB=1` by never needing it.

```
load_record()      -> list[RecordFile]   # every CLASS:-bearing file, header parsed
load_code()        -> dict[str, str]     # pipeline/ worker/ app/ (minus node_modules,
                                         # .next, __pycache__), render.yaml,
                                         # docker-compose.yml, .claude/settings.json
check_classes(record)              -> CheckResult
check_assignments(record, code)    -> CheckResult
check_citations(record)            -> CheckResult
check_coverage(record, code)       -> CheckResult
check_attestations(record)         -> CheckResult
check_symbols(record, code)        -> CheckResult   # warn-only
main()                             -> int
```

`CheckResult` carries `resolved: int` — how many claims of that kind the check
actually found and resolved — and `findings: list[Finding]`, each with a level of
`FAIL` or `WARN`, a path, a line and a message naming both sides.

**`check_classes`** — every file under `docs/` and every `.md` at the record roots
declares `CLASS:` in line 2 and `RECOMPUTED BY:` in line 3, and `CLASS:` is one of
`law | derived | history | ticket | inbox`. This is the grep in `CLAUDE.md:156`
turned from a listing into a check, and it is what tells every other check which
class a claim lives in.

**`check_assignments`** — for each `` `IDENT = literal` `` in a `derived` or `law`
file, find `IDENT` in the code and compare the literal. Three assignment forms,
because the record legitimately quotes all three: `IDENT = literal` (Python, TS),
`"IDENT": literal` (JSON, YAML) and `IDENT=literal` (env, shell). Normalise
whitespace, surrounding quotes and one trailing full stop; do not normalise
numbers (`0.20` and `0.2` are the same value and different claims, and the
extraction digest already treats them as different — keep that consistent).
Mismatch or not-found is `FAIL`. In `history` files this check does not run: a
dated entry recording that the threshold *was* 0.16 is correct forever.

This is the migration-014 idea at claim granularity rather than file granularity,
and section 5.1 argues why that distinction is the whole design.

**`check_citations`** — any `path:NNN` in the record must name an existing file,
`NNN` must be within its length, **and it must carry a commit-ish**: `AS-BUILT.md:1849
@ 9e37e64`. Without one it is `FAIL`. With one the check does not verify the line
(that would need a `git show` per citation and is not worth the cost); it only
requires that the citation be falsifiable by hand. Section 4.1 argues this.

**`check_coverage`** — every `pipeline/*.py`, every `pipeline/db/migrations/*.sql`
number, and every `stage_[a-h]_*` token in `worker/run.py` must be named by at
least one `derived` document. Unnamed is `FAIL`. This is the only check that runs
code → docs, and it is the one that catches the code growing something no
document noticed.

**`check_attestations`** — any `(attested: <who>, <YYYY-MM-DD>)` marker parses and
carries a date; missing or unparseable is `FAIL`. The check prints each
attestation's age and **never fails on age**. Section 4.3 explains why there is
no number here.

**`main`** — prints, per check, `<name>: <resolved> claims, <n> findings`, then
the findings. Exit 1 if any `FAIL`. **Exit 1 also if any check resolved zero
claims**, with the message "check_assignments resolved nothing; the instrument is
broken, not the record". Flags: `--all` (raise the untracked memory tier from
`WARN` to `FAIL`, for the Manager and the Tester), `--counts` (print resolution
counts and exit 0, for the dashboard).

The zero-resolution guard is the most important line in this design and section
5.2 explains what it is defending against.

### 3.2 `.githooks/pre-commit`

Three lines: `exec python pipeline/check_record.py`. Enabled once per clone with
`git config core.hooksPath .githooks`, added to `README.md`'s setup section — a
`derived` file whose recomputation this change is itself an instance of.

The hook checks the working tree and fails only on **tracked** record files:
`CLAUDE.md`, `README.md`, `docs/*.md`. `.claude/memory/` is gitignored, so a
commit can never contain it and blocking a commit for a dashboard defect is how
you teach a team `--no-verify`. The memory tier is checked at `WARN` in the hook
and at `FAIL` under `--all`.

### 3.3 The attested form

One new sentence-level convention and one new row of prose in `CLAUDE.md`'s
record section, for facts about the world outside the repository that no code can
settle. Written inline: `an account-level cap at console.anthropic.com (attested:
owner, 2026-08-02)`.

## 4. The three questions, decided

### 4.1 Cross-file citation should be constrained to identifiers that are assigned once, never reused, and not derived from position

That is the definition of a stable identifier, and it is already this project's
rule for issue ids — `CLAUDE.md:17` says the item numbers "are never reused"
precisely so commits can cite them years later. Line numbers fail all three
clauses: they are pure position, reassigned by every edit above them. Section
numbers pass, because this record has already promoted them from positions to
ids: `docs/AS-BUILT.md` sections 8, 9, 10 and 11 survived being split into other
files as pointer stubs that kept their numbers, and `docs/INCIDENTS.md:10` says
so explicitly. That was the right instinct and it should become the stated rule:
**a section number is an id. A split keeps the number; a number is never reused.**

So: item numbers, decision numbers, incident numbers, section numbers, migration
numbers and relative markdown links are the permitted forms of cross-reference.
Line numbers are permitted only pinned to a commit-ish, which makes them
permanently true instead of true for one edit. The measured cost of the rule is
one dangling citation to fix (`dashboard.md:46`) and one to pin
(`DECISIONS.md:339`).

### 4.2 The one-fact-one-file rule should be enforced by resolving each copy against the artefact, not by comparing the copies to each other

Detecting "two files state the same fact differently" in prose requires knowing
which sentences are about the same fact. Any n-gram or similarity approach needs
a threshold, and there is nothing here to measure one against; this project has
shipped four bad calibrations of a threshold that *did* have a corpus behind it
(`docs/DECISIONS.md`, decisions 24 and 25). A semantic comparator means an LLM
call per commit, which is cost, latency and non-determinism in a pre-commit hook.
Reject both.

And a document-to-document comparator is the project's own named fault — a check
that agrees with itself, one level up. Two files can be perfectly consistent with
each other and both wrong about the code, which is precisely instances 1, 3, 4 and
10. A comparator that goes green on those is worse than nothing.

The measured alternative already works. `PROPOSED_NOTE_SIGNALS` is asserted in
both `docs/PIPELINE.md:229` and `docs/DECISIONS.md:451`; comparing each
independently to `pipeline/check_extraction.py` catches the duplicate *and* says
which copy is wrong, because there is a ground truth. **Contradiction becomes a
special case of staleness the moment both copies are resolved against the thing
they were derived from.** That is free — it is `check_assignments` — and it needs
no threshold.

### 4.3 Instance 7 is not a contradiction the rule could have prevented, because neither file could be recomputed

`docs/AS-BUILT.md:496` says the Anthropic account cap is "recommended, not yet
confirmed set"; `docs/DECISIONS.md:623` says "confirmed set". The Curator found
it and could not resolve it, and the reason is structural rather than careless:
**the fact is about a setting in a vendor console, and there is nothing in this
repository that can settle it.** `RECOMPUTED BY: the Developer, in the same commit
as any behaviour change` can never fire for it, because there is no commit. The
same shape produced instance 3 — the count of secrets the Render dashboard holds.

The fourteen-row destinations table has no home for this. The cheap fix is not a
fifth class and not a new file; it is a form. An attested claim lives in exactly
one `derived` file, names who looked and when, and the checker requires the date
and prints the age. It is then honest in the only way it can be: it says "nobody
has looked since 2026-08-02" rather than asserting a state of the world it cannot
see.

**There is deliberately no staleness threshold on attestations.** A number here
would be guessed — there is no corpus of attested facts to measure decay against,
because the convention does not exist yet. Printing the age with the claim gives
a reader the information without the instrument pretending to a judgement it has
not earned. If, after a few months, the ages cluster somewhere that suggests a
cutoff, that is a measurement and a separate ticket.

### 4.4 It runs as a pre-commit hook

**Because the commit is the unit of record-keeping this project already
declares.** The Developer's prompt says "Update the project's record in the same
commit"; `CLAUDE.md:24` says to reference the issue in the commit. Every one of
the eleven drift instances entered the repository through a commit. The hook adds
no rule — it enforces the one that is already written, at the exact moment it
applies, and git remembers when nobody does.

Against the alternatives:

- **A script a human invokes** is the failure being fixed. "We will remember to
  run it" is the same class of promise as `RECOMPUTED BY:`.
- **A worker stage** has the wrong trigger and the wrong blast radius. A commit
  can sit for weeks without a trace and a trace can run for weeks without a
  commit, so it would report drift late or not at all. Worse, the worker runs on
  Render against a deployed tree: it cannot fail a commit, only a user's paid
  trace. Failing a trace because a document is stale is a bad trade and the
  operator would disable it within a week.
- **A role's standing instruction** is what exists now, in seven prompts, and it
  is the thing that failed eleven times. It also depends on dispatch, and the
  owner commits from a terminal outside Claude Code — `CLAUDE.md:103` says real
  runs happen there.
- **Something in `.claude/`** — a Claude Code hook — fires only for Claude
  sessions, for the same reason. It is a reasonable *second* net later; it is not
  the primary one.

The hook is bypassable with `--no-verify`. That is correct and matches the
project's own principle at `CLAUDE.md:103`: reaching production takes an act, not
an omission. A bypass is visible in a reflog and nameable in a review; forgetting
is not.

## 5. Checking this design against the project's five faults

### 5.1 A derived value stored and then allowed to age — avoided by deliberate rejection

The obvious reading of migration 014 is "put a digest in the file header": `DERIVED
FROM: pipeline/ @ <tree-hash>`. I rejected it and the reason matters, because it
is the ticket's own leading suggestion.

Migration 014 works because the digest hashes eighteen named calibration inputs —
a small closed set that moves only when the verdict's meaning moves — and because
**nothing can write the stamp except the code that computes the verdict**. The
stamp is a by-product of the recomputation and can never be an independent act.

A document stamp has neither property. A tree hash of `pipeline/` fires on every
commit to a busy directory whether or not any claim in the document changed: a
detector that fires on nearly all of its input has stopped measuring its input,
which is the fault this project has already paid for four times. And re-stamping
is an independent act by an agent under time pressure, so the cheap way out is to
re-stamp without re-reading — after which the file carries a green tick that is
now load-bearing and false. That is strictly worse than no stamp.

The design stores nothing derived. A claim written as `` `DEFAULT_THRESHOLD =
0.28` `` **is already its own stamp**: it names the artefact and the value, it can
be resolved against the code by anyone at any time, and nobody has to remember to
refresh it because refreshing it and correcting it are the same act.

### 5.2 A check that agrees with itself — two independent directions, plus a zero-resolution guard

`check_assignments`, `check_citations` and `check_classes` resolve documents
against the filesystem and the code. `check_coverage` resolves the code against
the documents. Neither direction's reference is copied from what it checks.

But the sharper version of this fault is an instrument that passes because it
checked nothing. If a restructure changes how constants are written and no line
matches the assignment form any more, every check returns green while resolving
zero claims — a per-item pass rate of 100% over an empty set, which is exactly
"every failure is neutral" wearing a result's clothes. Hence: **any check that
resolves zero claims fails the run.** Today's floors are 33 coverage artefacts, 4
assignment claims, 31 citations, 11 classed files.

Note that the guard is `> 0`, not a stored count. A stored count would itself be a
derived value allowed to age, and would go wrong the first time a script is
legitimately deleted. Zero is the only threshold-free signal that the instrument
is broken rather than the record.

### 5.3 A threshold guessed rather than measured — there is no threshold in this design

Every check is exact equality or existence. The attestation check deliberately
declines to have one (4.3). The two checks that would have needed one — path
existence over prose and contradiction detection — were measured and rejected
(sections 2 and 4.2), at a measured 8-of-8 false-positive rate and an unmeasurable
threshold respectively.

### 5.4 Destroying before replacing — no destructive step

The change adds one file and one hook. It rewrites nothing and touches no data.
The two corrections it will force (`docs/PIPELINE.md:229` and `:341`) are edits to
wrong sentences.

### 5.5 A per-item fallback with no global sanity check — this is 5.2, and it is why the guard is not optional

## 6. What it costs

**Money: nothing.** No API call, no CI minutes, no service.

**Build time:** one script of roughly 250 lines and a three-line hook. One
Developer session with the design in hand.

**Per-commit time: negligible.** The prototype reads all 64 relevant code files
(504 KB) in 6 ms warm; the whole check should land well under 200 ms cold. If it
ever exceeds a second on this repo, that is a defect in the check.

**Maintenance:** the checks are structural, not calibrated, so a restructure does
not invalidate them — that was the ticket's explicit constraint and it is met by
having nothing to recalibrate. The residual cost is nine `WARN`s from
`check_symbols` on legitimate non-code tokens, which is why that check is
warn-only and reports a count rather than a list by default.

**Deliberately no suppression file.** Any suppression is written on the line it
suppresses, as `<!-- record-check: <reason> -->`, so it is visible next to the
claim and dies when the claim does. An allowlist in a separate file is where drift
would hide, which is the failure this ticket exists to fix. Measured: the
`FAIL`-level checks need **zero** suppressions today. That is a consequence of
having rejected the path check rather than tried to tame it.

**Risk to existing data: none.** No database access, no writes outside the repo.

**The honest limitation:** the hook reads the working tree, not the index. A
partially-staged commit can pass on unstaged text or fail on it. Reading staged
content via `git show :path` is correct and more complex; the working tree is what
the Developer will edit anyway, and I would rather ship the simple version and let
the Tester tell us whether the edge case is real.

## 7. How it will be verified, and what would falsify it

**The input that proves it works, available today.** Run
`python pipeline/check_record.py` on `master` @ `5177253` unmodified. It must
report exactly two `FAIL`s from `check_assignments`, naming `docs/PIPELINE.md:341`
(`DEFAULT_THRESHOLD`, doc 0.16, code 0.28) and `docs/PIPELINE.md:229`
(`PROPOSED_NOTE_SIGNALS`, doc `frozenset({"gaps", "package_macros"})`, code
`frozenset()`), plus one `FAIL` from `check_citations` for `dashboard.md:46` under
`--all`. **It must report zero findings for `LINEAGE_NO_DB` in `CLAUDE.md:103`**,
which is the specific false positive my prototype produced and the JSON assignment
form exists to remove. Anything else on a clean tree is a false positive and must
be fixed before the hook is installed.

**The input that proves it can go red about the code.** Edit
`pipeline/stage_c_cluster.py:57` to `DEFAULT_THRESHOLD = 0.31` and commit. The
hook must block. Restore it. This is the test that distinguishes a working
instrument from a green tick, and it should be repeated by the Tester on a
schedule, not once — a check that has never been observed failing is a check
nobody has evidence about.

**The input that proves the coverage direction works.** Add
`pipeline/stage_i_nothing.py` and commit with no documentation change. The hook
must block, naming the file. Delete it.

**The input that proves the guard works.** Rename the assignment form in all four
places so no claim matches, and run. It must exit 1 saying `check_assignments`
resolved nothing, not exit 0 with a clean report.

**What falsifies the design.** Any of these, and the mechanism should be reduced
or withdrawn rather than tuned:

- The hook produces a false positive on a clean tree in its first month. A check
  that cries wolf once will be bypassed, and bypassing is a habit.
- The `FAIL`-level checks require more than two in-line suppressions in the first
  month. That would mean the forms I chose are not actually how this record writes,
  and the honest response is to drop the failing check, not to grow an allowlist.
- Six months on, `check_assignments` still resolves only four claims. The check's
  value scales with how many claims are written in resolvable form; if the record
  does not drift toward that form, it is catching one class of one file and should
  be retired to a warning.
- Anyone is found running `--no-verify` on a record failure. That is the
  measurement that says the check is annoying rather than useful, and it is worth
  looking for in the reflog.

**Where the numbers go.** `--counts` output belongs in the Manager's dashboard
under measure 6, Hygiene: claims resolved per check, and record-check failures
outstanding. That is computed from disk, which is what that prompt requires, and it
gives the untracked memory tier an enforcement point the hook cannot reach.

## 8. What I considered and rejected

- **A `DERIVED FROM: <tree-hash>` header stamp per file** — fires on every commit
  to a busy directory, and can be refreshed without being re-read (5.1).
- **A dangling-path check over prose** — measured 8 false positives, 8 hits (§2).
- **Restricting the path check to markdown links only** — 29 targets, 0 dangling,
  0 false positives, but it would have caught none of the eleven instances,
  because every one of them was written in backticks.
- **A duplicate-sentence or similarity contradiction detector** — needs a
  threshold with nothing to measure it against (4.2).
- **An LLM pass over the record on commit** — cost, latency and non-determinism in
  a hook, and a check whose failures cannot be reproduced is not a check.
- **A fifth `attested` class** — a whole class and a table row for a form that one
  inline marker carries (4.3). The record was reorganised twice today; adding a
  class is the expensive answer.
- **A GitHub Actions workflow** — `CLAUDE.md` says no CI this project will not
  run, and a check that reports after the push is a check that reports after the
  drift is public. That was instance 2's whole shape.
- **A `tools/` directory** — a new directory needs a destinations row; `pipeline/`
  already holds tools and already holds the sibling this is modelled on.
- **Making `check_symbols` fail rather than warn** — 7.8% false positives and no
  true positives today. It is a rename detector on probation.

## 9. Role prompts: what needs changing, proposed as diffs, not made

These are the owner's files. I have not edited them.

**`~/.claude/agents/developer.md`, House rules** — the one change that matters.
After "Update the project's record in the same commit", add: *"Run
`python pipeline/check_record.py` before committing and state its counts in your
report. If it blocks, fix the record; never `--no-verify` a record failure. If you
believe a finding is wrong, say so and leave the commit unmade."* The existing
lesson `recompute-by-grepping-the-claim` already covers grepping a claim
repo-wide, and this is its enforcement.

**`~/.claude/agents/tester.md`, Six classes to test by name** — add a standing
item under class 3 (a stamp that does not follow its check): *"Prove the record
check can go red. Change a documented constant in the code, confirm the commit
blocks, restore it. Report the commit-ish you did it at."* Nobody else in the team
is positioned to test the instrument itself, and an instrument never observed
failing is a green tick.

**`~/.claude/agents/manager.md`, measure 6 (Hygiene)** — add record-check
failures outstanding and claims resolved per check, from `--counts`. And a second,
smaller change: the dashboard is the only file in the record that cites line
numbers, and `dashboard.md:46` is instance 9. Add to "Where it goes": *"Cite item,
decision, incident and section numbers, never line numbers; a line number without a
commit-ish is false by the next edit."*

**`~/.claude/agents/curator.md`** — one addition under "Age the board": *"A
present-tense fact that no code in the repository can settle is an attested claim.
It gets one home, a name and a date. Do not document a contradiction in place;
either resolve it against an artefact or convert the surviving copy to an
attestation and delete the other."* That is the instruction that would have let the
Curator close instance 7 instead of recording it.

**`~/.claude/agents/architect.md`, `operator.md`, `security.md`** — no change.

## 10. Open questions

1. **Does the owner want the hook to block, or only to warn, for the first two
   weeks?** A warn-only period would measure the false-positive rate on live
   commits before anyone can be annoyed by it, at the cost of two weeks of the
   thing not working. I recommend blocking from day one, because the measured
   false-positive count on a clean tree is zero and a warning nobody must act on is
   the mechanism this ticket rejects. But it is the owner's tolerance to spend.
2. **Is the Anthropic account cap actually set?** The design cannot answer this and
   neither can the repository. Someone must look at console.anthropic.com, and then
   `docs/AS-BUILT.md:496` becomes an attestation and `docs/DECISIONS.md:623` stays
   as the dated claim it always was. This blocks nothing, but it is the live
   instance and it wants an act rather than a mechanism.
3. **Should `docs/PIPELINE.md:229` be corrected or deleted?** The paragraph
   describes a shipped change in the present tense inside a `derived` file. If the
   answer is that this narration belongs in `docs/DECISIONS.md`, that is a Curator
   question about where change-narration lives, and it may be a small pattern
   rather than one paragraph.

— Deep Thought, Architect

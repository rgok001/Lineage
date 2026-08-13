# Lineage — operations runbook

CLASS: derived
RECOMPUTED BY: the Developer, in the same commit as any change to an
environment variable, a CLI flag, a deploy step or an operational procedure.
This file describes how the system is operated *today*, so the code moving
underneath it is exactly what makes it wrong. It is derived rather than law
because nothing here was decided — every line was observed, and the measured
numbers in it (8.7 seconds for 227 papers, the 900-second `startup_task` kill,
the expected verdict split) are readings that a change to the code invalidates.
The reasons behind these procedures are decisions and live in
[DECISIONS.md](DECISIONS.md); what the stages and the extraction audit actually
*are* lives in [PIPELINE.md](PIPELINE.md); the procedures themselves live here.

Split out of `AS-BUILT.md` on 2026-08-02, where it was section 8. It keeps its
original heading, so every "section 8" reference elsewhere in the record still
resolves here.

---

## 8. Operations runbook

**Environment variables.**

| Variable | Where | Value/notes |
|---|---|---|
| `DATABASE_URL` | root `.env`, worker/Render | Neon **direct** endpoint (no `-pooler`): pipeline and worker hold real connections |
| `DATABASE_URL` | `app/.env.local`, Vercel | Neon **pooled** endpoint (`-pooler` host): serverless wants per-query fetches |
| `ANTHROPIC_API_KEY` | root `.env`, Render | pays for stages B, C labels, D |
| `VOYAGE_API_KEY` | root `.env`, Render | embeddings for Stage A relevance and Stage C clustering. **Required**; the pipeline fails fast without it |
| `VOYAGE_MODEL` | optional | defaults to `voyage-3` (1024-dim, matches the column) |
| `LLM_MODEL` | root `.env` | `claude-sonnet-5` (see decision record). **Must be a model `PRICING` in `pipeline/stage_b_extract.py` holds rates for**, or a dated snapshot of one: since #205 a stage that cannot price itself refuses to run rather than publishing a guessed figure. Add the model to that table, from Anthropic's published pricing, before setting it here |
| `PROMPT_VERSION` | root `.env` | `v2`; part of the Stage B cache key |
| `TRACE_SPEND_CAP_USD` | root `.env` | 15. **One cap per trace, covering both passes** (#192): the worker prices pass two against what is left of it and abandons the pass rather than exceeding it |
| `PASS_TWO_SEATS` | optional, root `.env`/Render | how many papers the second pass may add; default `corpus_limit // 10` = 15 of 150 (#192). **`0` disables the second pass**, and such a build writes no build record, so its report says the map was built in one pass. A value that is not a whole number is ignored with a line in the log, never read as 0 |
| `DATA_DIR` | root `.env`, Render (`/data`) | absolute paths honoured |
| `OPENALEX_MAILTO` | root `.env`, Render | polite-pool contact |
| `LINEAGE_NO_DB` | set per shell, never committed | any non-blank value and every Python entry point refuses to hand out `DATABASE_URL` (decision 22). Set it in any shell running pipeline code to inspect it rather than to operate on real data. Does not reach the Node side |
| `LINEAGE_READ_URL` | set per shell, never committed | the read-only `lineage_ro` role, SELECT and nothing else. Read by `recheck_stamp.py`, `map_report.py` and `check_map.py`, and by nothing else. Deliberately not named `DATABASE_URL` so no existing code path can route through it by accident |
| `AUTH_SECRET`, `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET`, `OWNER_GITHUB_LOGIN` | `app/.env.local`, Vercel | Auth.js reads exactly these names |

**Local development.** App: `cd app && npm run dev` (port 3000). Worker:
`python worker/run.py --once` for one job, no flag to poll forever. Pipeline:
run stages directly per README. Python is not on PATH on the dev machine;
invoke `C:\Users\GGPC\AppData\Local\Programs\Python\Python312\python.exe`.

**Migrations.** Add `pipeline/db/migrations/NNN_name.sql`, run
`python pipeline/db/migrate.py`. Applied set is recorded in
`schema_migrations`. Migrations run against the direct endpoint.

**Deploying the app.** Push to `master`; Vercel auto-deploys (root directory
is `app/`) to https://lineage-green.vercel.app — recorded here 2026-08-07
because until then the address existed only in browser bookmarks. Env var
changes in Vercel do not reach an existing build: redeploy after changing them.

**Deploying the worker, and migrations with it.** Automatic since decision 31
(2026-08-07, issue #102): a push to `master` deploys the worker
(`autoDeploy: true` in `render.yaml`), and Render's pre-deploy step runs
`python pipeline/db/migrate.py` before the new worker code starts, so pending
migrations apply themselves in order with the code that expects them. If the
pre-deploy fails, Render aborts the deploy and the old worker keeps running: a
broken migration stops the release rather than half-applying it — read the
deploy log, fix, push again. Because Vercel is usually live minutes before the
worker's pre-deploy finishes, **migrations must be additive and the app must
tolerate a schema one migration behind** (the #92 fallback is the pattern).

The manual path remains the emergency route: `python pipeline/db/migrate.py`
from the owner's terminal applies whatever is pending, and is safe beside the
automatic one because both consult `schema_migrations`.

First-time worker creation is unchanged: Render dashboard -> New -> Blueprint ->
this repo; Render reads `render.yaml` and prompts for every secret it marks
`sync: false`; the table above says what each one is for. A count was written
here instead, and it was still saying three after `VOYAGE_API_KEY` became the
fourth. Success looks like "Worker up. Polling every 10s for approved trace
requests" in the logs. An auto-deploy restarts the worker; an in-flight trace is
killed and requeued, which is accepted at current trace volume (decision 31).

**What a deploy does to a run in flight, and what it no longer does** (decision
38, issue #178). Render stops the old worker with SIGTERM and allows a grace
window before SIGKILL. The worker catches SIGTERM, puts its job back to
`approved` and exits, so the new instance picks the same job up and the pipeline
resumes from its caches. In the log that reads `[job N] interrupted (received
signal 15) — requeueing as 'approved'`. Until 2026-08-08 it caught only SIGINT,
so every deploy left its build marked `running` and the sweep failed it ten
minutes later; the failure was terminal, because a failed request cannot be
re-approved. Two consequences worth holding:

- **An app-only push still restarts the worker.** `autoDeploy: true` has no path
  filter, so a push touching only `app/` or `docs/` redeploys the worker and
  kills whatever it is building. Blast radius does not follow the changed paths.
- **If the row still goes stale** (SIGKILL beat the update, or the process died
  without a signal), the sweep now requeues it rather than failing it, up to
  three times, counting in `trace_requests.requeues`. The log line is `[sweep]
  job N: heartbeat went stale; requeued automatically (attempt 1 of 3)`. At the
  cap it fails with an error saying it died repeatedly, and that error is a
  statement about the worker's restart history, not about the pipeline: read the
  Render events for that window before resubmitting. A failed row cannot be
  re-approved from the UI (the Approve button lifts a row only from
  `requested`), so put it back by hand once the cause is fixed:
  `UPDATE trace_requests SET status = 'approved', requeues = 0, error = NULL,
  started_at = NULL, finished_at = NULL WHERE id = N;`. The partial unique index
  on open concepts means this fails if the same concept has since been
  resubmitted, which is the right answer: one of the two rows is redundant.
- **A stage that exits nonzero is not retried at all**, then or ever. That is
  deliberate: it has diagnostics attached and will fail the same way. Only
  silence is retried. **The one exception is a stage of pass two** (#192), which
  costs the build its second pass and not its map: the build falls back to
  re-clustering over the pass-one corpus, publishes that, and records an outcome
  naming the stage that failed. Look for `pass two FAILED` in the log and for
  "The second pass failed while '…'" on the map's report.

**Watching a two-stage build** (#192). The feed narrates the passes: `pass one
complete: N paper(s) read, M meaning(s), K relationship(s). Not yet published.`,
then `pass two: X recent paper(s) cite this map, Y cite two or more of it, Z
cleared both signals. Reading the top R.`, then the finish. A build runs the
sequence in `docs/PIPELINE.md` §4, which is where the step count lives (it has
moved three times and a second copy of it here was wrong within a week), and the
feed's total is corrected downward the moment a pass is skipped, with the reason
on the same flush. Its first line is either `saved the current map
before rebuilding it: … -> <path>` or `no existing map for this term to save: this
is its first build.` — see the backup paragraph below. **The map is invisible for
the whole of it**:
`status` stays `running` until the last stage, and since #168 the read path
refuses anything that is not `complete`.

Three things to check on a build that came out one-pass, in this order, all of
them from the map's own report or from `python pipeline/record_pass.py <concept>
--show`:

- `The second pass was not run: … estimated at US$X and US$Y of the US$Z spend
  cap was left.` The gate did its job. Either raise `TRACE_SPEND_CAP_USD`, or
  lower `PASS_TWO_SEATS`, and re-trace; nothing is wrong.
- `The second pass found nobody to read: no arXiv paper from YEAR or later cites
  two or more of this map's papers.` A fact about the citation graph. For a
  mature term it is worth knowing; for a young one it is expected. It is never
  reported as the field going quiet.
- `The second pass failed while '…' was running.` A defect. The stage's own
  output is in the worker log for that build; the map is pass one's and is
  correct.

**Recording a pass by hand.** If a build's record is wrong or missing —
`papers the record puts in neither pass` above zero on
`pipeline/map_report.py` is the symptom — it is re-stated with the same corpus
files the build used:

```sh
python pipeline/record_pass.py "<concept>" --pass 1 --corpus data/corpus_<slug>.json
python pipeline/record_pass.py "<concept>" --pass 2 --corpus data/corpus_<slug>_pass2.json
python pipeline/record_pass.py "<concept>" --build --passes 2 --outcome "…" \
    --seats 15 --candidates 611 --cleared 45
python pipeline/record_pass.py "<concept>" --show
```

`--pass 1` clears the map's whole pass record first, so this is a re-statement
and not an addition. `--outcome` is printed verbatim on the report: it must be a
sentence, not a code. A map that should read "built in one pass" has its record
removed rather than set to `passes = 1`:
`DELETE FROM map_build_passes WHERE genealogy_id = N;`.

**Reading what a build spent, step by step** (issue #47). `python
pipeline/record_spend.py "<concept>" --show` prints the whole breakdown from the
map's own record: every step with its cost, its pass and its time, the per-pass
subtotals and the most expensive step. The map's report prints the same figures,
and `pipeline/map_report.py` prints them beside "what the run cost" with a
mismatch marker — **if it says `DOES NOT MATCH`, read the request id above it
first**: the run figure describes the last *completed* run and the steps describe
the last build that reached the recorder, so a build that recorded its steps and
then failed at the publish leaves the two describing different runs. That is the
common cause and it is not a defect in either figure.

The record is written by the worker near the end of every build, from a ledger it
writes to `DATA_DIR/stages_<slug>.json` as it goes. To re-state it by hand — a
build interrupted after the recorder, a record that is wrong — point the command
at that file, which the worker leaves on disk even for a build that died:

```sh
python pipeline/record_spend.py "<concept>" --stages data/stages_<slug>.json
```

It clears the map's whole step record first, so this is a re-statement and not an
addition. A map that should read "no step-by-step record of this build" has its
rows removed rather than zeroed: `DELETE FROM map_build_stages WHERE
genealogy_id = N;`. **Never insert a row with a cost of zero for a step that
printed no cost line** — the two are different facts, the report says so in
words, and a CHECK on the table refuses the pair anyway. A map built by hand from
the command line has no ledger and therefore no record, which is correct: nothing
watched what its steps printed.

**Naming papers a map should not miss** (issue #198). Through the site: the
request form on `/trace` takes up to three arXiv ids. From the command line, the
same thing is two flags:

```sh
python pipeline/corpus_select.py "dark energy" --field fields/31 \
    --limit 150 --json data/corpus_dark_energy.json \
    --anchor 2404.03002 --anchor 2404.03000
# … the rest of the build …
python pipeline/record_anchors.py "dark energy" \
    --corpus data/corpus_dark_energy.json          # then check it:
python pipeline/record_anchors.py "dark energy" --show
```

Three things to know before using it. **An id that OpenAlex cannot resolve stops
the selection by name**, before anything is fetched or spent, so a typo costs a
retype and never a silent omission; re-run with the id corrected. **The named
papers are additive**, so a 150-paper corpus with three named papers holds 153
and nobody lost a seat. And **`record_anchors.py` clears the map's whole record
before writing**, so it is a re-statement and not an addition: to make a map read
"nobody named a paper", re-run it against a corpus file in which no entry has its
`anchor` flag set, or `DELETE FROM map_anchor_papers WHERE genealogy_id = N;`.
Run from the
command line, the record carries `named_by_asserted` (from `LINEAGE_ACTOR`, else
`user@host`) rather than an authenticated login, and the report says which.

Being named buys a paper a reading and nothing else. If it turns out not to
define the term it is counted among the papers that do not, and if nothing in the
map cites it, it carries no relationship. Both show on `/g/<id>/report` under
`papers a person named`, which is the point rather than a defect.

**Backup and restore.** **The backup of record is the snapshot the worker takes
before every build** (issue #173), at `DATA_DIR/snapshots/<concept>_<pv>_<stamp>.json`
— on Render that is `/data/snapshots/`. It holds the genealogy row, its
concept-states, its threads, its curatorial audit trail, its `status`, every edge
with its quotes and stamp columns, and every definition the quotes come from.
Stage E's JSON exports under `data/` are deliverables and hold only `nodes` and
`edges`; they are not the backup and have not been since #173. Papers, texts and
definitions are not covered by an export at all; they live in Postgres and
`DATA_DIR` and are cheap to regenerate except for LLM spend, which the caches
mostly protect.

**Retention is a sentence rather than a mechanism, deliberately: nothing prunes
these and nothing should.** One JSON per build of one concept, and a build takes
about fifty minutes, so the arrival rate is a handful a week at most. Size scales
with the map: the attention export (156 papers, 287 verified edges) is 235 KB and
a snapshot holds that plus the definitions and threads, so budget under a megabyte
each. If the worker's disk ever becomes the constraint, delete the oldest by hand
after checking that the map they describe is still live; do not automate it, and
never delete the newest snapshot of a map that is currently being rebuilt.

**Restoring a map a re-trace destroyed.** This is the recovery path when a build
dies after Stage C — the map is then invisible, because Stage C set `status =
'running'` and the site serves only `complete`. It needs `DATABASE_URL`, so it is
run from a terminal with database access and never from an agent shell.

```sh
# 1. find the snapshot. The newest one for the concept is the build that broke it.
ls -t /data/snapshots/ | head

# 2. read it back before writing anything: the counts now vs the counts in the file.
python pipeline/restore_snapshot.py /data/snapshots/<file>.json --dry-run

# 3. restore.
python pipeline/restore_snapshot.py /data/snapshots/<file>.json --confirm

# 4. re-ground, free, because the restore cannot restore the extracted text.
python pipeline/stage_e_ground.py "<concept>"

# 5. confirm the map satisfies the rules that built it.
python pipeline/check_map.py "<concept>"
```

Four things about it that are not obvious from the commands. It restores **into
an existing row** by id; if the row itself is gone, `restore_genealogy.py` from an
export is the only path and it recreates a row with a new id. It restores the
snapshot's `status`, so a map that was `complete` comes back visible on the site
and a map that was already mid-build comes back mid-build, and the run prints
which. It does **not** overwrite `user_edits`: the audit trail is append-only, and
the restore appends itself to it, so the map's history says it was restored rather
than pretending nothing happened. And step 4 is not optional if the papers were
re-extracted since the snapshot — the verdicts coming back describe text that may
no longer be on disk, and Stage E is what makes the verified count true again,
even if it comes back lower.

Verified end to end on fixtures rather than on a live map (#173): snapshot a
curated map, destroy it with Stage C's own `UPSERT_GENEALOGY` plus Stage D's edge
delete plus a definition refresh, restore, and the concept-states, threads,
status, all edge columns and all definition columns come back identical, with one
`restore` entry appended to the audit trail.

If Stage E ends with "Publishing the export then FAILED" (on **stderr**, like
every other refusal the stage makes), the database has the new map and the file
does not: the run committed, and only the rename of
`genealogy_<concept>_<pv>.json.tmp` over `genealogy_<concept>_<pv>.json` did not
happen (a locked path, a read-only mount, a full disk). Do not read the export as
the current map until it is repaired, and repair it by renaming the `.tmp` over
it or by re-running Stage E, which is free and writes the same result. **If the
report names stale stamps, prefer the rename**: a re-run before `extract_text.py`
has run after migration 015 writes the same stale stamps again, and the report
says so where that applies. The report checks both paths before it describes
them, so read it rather than assuming: where it says the `.tmp` is gone there is
nothing to rename and the re-run is the whole repair, and where it says there is
no previous export, no file on disk describes that map at all. Stage E exits non-zero there, so a scripted run stops
rather than continuing on a backup that is one run behind.

**Applying migration 015 (the re-checkable stamp).** Two steps touch live rows
after the migration itself, they must be done **in this order**, and the alarming
part is stated in advance so nobody reacts to it as a fault.

The migration adds columns with no `DEFAULT` and no `NOT NULL`, so it rewrites no
row and takes no table rewrite lock. Record
`SELECT count(*) FROM definitions WHERE quote_verified` and the per-map verified
edge counts before it and re-read them after: **any change at all falsifies it.**

**Between the migration and step 2, every stamp in the database renders stale**,
including all 287 verified edges on `attention`. That is correct and it is the
feature working: those stamps genuinely are not re-checkable. The window is
minutes and the fix is free. What must **not** happen is filling
`quote_text_digest` from the paper's current digest as a "backfill" — that turns
every unproven stamp green in one statement, which is the silent re-anchoring
incident 10 forbids. **There is no honest backfill of a stamp column. The only
way a stamp becomes re-checkable is by being re-checked.**

Immediately after the migration and before anything else, on the Render shell:

```
python pipeline/recheck_stamp.py --concept "attention" --edges
```

Expect **every** stamp reported stale, reason "no digest recorded". A single
stamp reporting verified means something wrote a digest it could not know.

**The order of the two steps below is load-bearing, and running them backwards is
now detected rather than assumed against.** A re-ground before the papers
backfill writes stamps that agree with the files on disk while
`papers.extracted_text_digest` is still NULL, so every page renders them stale
and `recheck_stamp.py` would once have reported them verified and exited 0. It
now names that disagreement and exits non-zero (issue #66). If you see it, run
step 1 and re-run step 2; nothing is damaged, but nothing is published either.

1. **Live-data step 1, the papers backfill.** `papers.extracted_text_digest` must
   be populated for the ~300 papers already extracted. This is `extract_text.py`
   with **no** `--force`: every paper is skipped as already extracted, and the
   skip path hashes the file and writes that one column. `--dry-run` first.

   ```
   python pipeline/extract_text.py --dry-run
   python pipeline/extract_text.py
   ```

   Honest and safe, because a digest computed now is a statement about the file
   now and claims nothing about any past match. It writes **only**
   `extracted_text_digest`; it must not touch `extracted_text_path`, the
   extraction verdict, or any stamp. Expect the number of papers with a non-NULL
   digest to equal the number whose text file exists on that disk, and the ~12
   papers with no text to stay NULL. A digest on a paper with no file falsifies
   it. `papers.extractor_version` stays NULL for every one of them, which is
   correct: a skip did not produce those files, and that NULL is what makes them
   selectable as the re-extraction queue later.

2. **Live-data step 2, the re-ground.** Per map, and **take the snapshot first**
   (the worker takes one before a build since #173; a hand-run repair is not a
   build, so this one is yours to take):

   ```
   python pipeline/snapshot_map.py "attention"
   python pipeline/stage_b_extract.py "attention" --reground --dry-run
   python pipeline/stage_b_extract.py "attention" --reground
   python pipeline/stage_e_ground.py "attention"
   ```

   Nothing here is new behaviour — it is the same free re-check the worker
   performs on every trace — but it is the first time it has been run
   deliberately across the corpus, and it is the step that visibly moves counts
   on the published maps. Expect the verified count to return to its
   pre-migration value **minus exactly** the definitions whose text is missing or
   whose quote no longer matches, each named by arXiv id in the output. Any stamp
   moving from stale to verified for a paper whose file could not be read, or a
   count that recovers to *more* than it was, falsifies it.

3. **Re-check, and then try to break it.** Re-run `recheck_stamp.py` and expect
   zero span mismatches and zero unchecked, with the stale set exactly equal to
   the set of papers with no text on that disk. An "unchecked" count above zero
   means a stamp resolves verified with no span or no quote to compare it by, so
   nothing here or on the site ever checked it (issue #78); it cannot come from
   this pipeline's writers, and the repair is a re-ground of that map. Any span mismatch is the matcher and the stored
   offsets disagreeing and invalidates the feature rather than describing the
   corpus. Then change one character in one paper's extracted text file and
   re-run it: that paper's stamps must flip to stale and the tool must report the
   disk/database disagreement. Restore the file. **This is the falsifying input
   for the whole feature** — if a stamp survives a change to the text it claims
   to have been checked against, none of this works.

`recheck_stamp.py` needs `LINEAGE_READ_URL` and issues only `SELECT`, so it is
safe to run at any point above, including from an agent's shell.

**Applying migration 016 (the map report). The migration must land BEFORE the
app renders against it: the home page and `/g/<id>/report` both read
`map_report`, and until it exists there is no report to read.** Since decision
31 the worker's pre-deploy applies it on the next push; until that push has
deployed, or to close the window sooner, run it manually as below.

That ordering used to be the whole of it. Since issue #92 the home page also
degrades rather than falling over: `listGenealogies` asks `to_regclass` whether
the view is there and, if it is not, selects NULL for the two counts, so `/`
renders with "verified relationships not counted" on every card instead of
returning a 500 in full. The degraded state is a safety net and not a supported
one — `/g/<id>/report` still needs the view and has nothing to show without it —
so the ordering above is still the instruction. Deploy first and the front page
tells every visitor that nothing is counted.

Two `CREATE VIEW`s and one guarded
`GRANT`. No table, no column, no data touched, no backfill, no rewrite lock, and
nothing to schedule afterwards: a view holds no data and is computed on read.

```
python pipeline/db/migrate.py
```

It is reversed by `DROP VIEW map_report; DROP VIEW map_report_by_source;` and
there is nothing to restore, because nothing was stored.

**The `GRANT` is in the migration and has to be.** `lineage_ro` holds `SELECT` on
the tables that existed when it was created and does **not** automatically hold it
on a new view, so without this `map_report.py` fails with a permission error
against production while working perfectly for the owner, who connects as the
writable role and would never see it. The statement is wrapped in a `DO` block
that checks `pg_roles` first, so a local database with no such role still
migrates. Confirm it after the migration, from a shell holding
`LINEAGE_READ_URL`:

```
python pipeline/map_report.py --all
```

A permission error there means the role existed under another name when the guard
ran; the repair is one `GRANT SELECT ON map_report_by_source, map_report TO
<role>;` as the owner, and it is worth correcting the migration too.

**Expect the first report to look bad, and expect it to be right.** The report is
the first surface that states a map's verification counts in full, and migration
015 left every stamp made before it not re-checkable. **If the post-015 re-ground
has not been run, `attention` correctly reports 0 relationships verified and 287
not re-checked**, and `embedding` the same shape. That is not a fault in the
report and it is not a regression in the map: those stamps genuinely are not
re-checkable, which is what 015 says. The remedy is free and is the two live-data
steps of the 015 procedure above, **in that order** — `extract_text.py` with no
`--force` first, then per map `snapshot_map.py`, `stage_b_extract.py --reground`
and `stage_e_ground.py`. Settle which state the database is in **before**
deploying the page rather than discovering it on the page:

```
python pipeline/map_report.py "attention"
python pipeline/recheck_stamp.py --concept "attention" --edges
```

Read the report's "relationships not re-checked" against `recheck_stamp.py`'s
`stale` count; if they agree and both are the whole map, the re-ground has not
run. Record the numbers before and after, because the re-ground is the step that
visibly moves counts on a published map.

Two figures on the report will read "not recorded" on both live maps whatever you
do, and that is also correct: `attention` and `embedding` were built from the
command line and have no run record at all, so run cost and wall clock have
nothing behind them. **`genealogies.spend_usd` reads `0.0000` on every map and is
written by nothing** (issue #85); it is not a fallback and nothing in the view,
the page or the command reads it.

**Applying migrations 025 and 026 (the version shape, and the swap that uses
it).** Nothing to do for either: 025 is additive and backfills itself, 026 adds
one CHECK that every row already satisfies because nothing had ever written
`superseded_at`, and they apply in the ordinary Render pre-deploy with no page
changing. What an operator should know before the next build, though, including
one read-only check to run once after 026 deploys.

**It refuses to apply if two published maps share a concept.** The backfill makes
every `status = 'complete'` row current and the partial index allows one current
row per concept, so a duplicate fails the index and rolls the whole migration
back — `migrate.py` applies every pending file in one transaction. The message is
`could not create unique index "genealogies_one_current_per_concept"` naming the
concept. That is deliberate: two published maps for one term is a state somebody
has to decide about, and a migration that picked a winner would decide it
unwatched. Resolve it by deleting or un-publishing one, then re-run the migration.

**Re-clustering a live map in place is now refused.** `stage_c_cluster.py
"<concept>"` sets `status = 'running'` on the row it finds, and a *current* row
cannot leave `complete` — the CHECK `genealogies_current_is_published` refuses
it, naming itself. That is the destructive overwrite F4 exists to remove,
arriving with the shape rather than with the swap. The path is unchanged from
what decision 12 already requires: **delete the map first, then re-trace.**
Unaffected: `--embed-only` (it returns before the upsert, so the repair after
`stage_b_extract.py --refresh` still works), Stage C on a concept with no
published map, Stage E's publish, the workbench, the threads job and the claims
job. One thing `--embed-only` deliberately cannot see, and the refresh now says
out loud (#169): a paper the refresh flipped from defining to not-defining. The
demoted row keeps its id, so any map citing it still holds the paper, but its
embedding stays NULL — `--embed-only`'s SELECT carries `defines_concept = true` —
and the map now fails the publish invariant. `--refresh` prints a DEMOTION line
naming each such map and node and an end-of-run banner; when a refresh prints
one, run `check_map.py "<concept>"` and repair (#170 is the procedure) before
re-grounding. `restore_snapshot.py` restores the snapshot's own `status`, so restoring a
mid-build snapshot **onto a current row** hits the same refusal; restore onto the
`running` row the recovery path is written for, which is not current.

**Publishing a map now makes it the current one** (#207a, issue #226). Stage E's
publish is two statements inside the transaction it already ran in: it demotes
every *other* current version of the concept — `is_current = false`,
`superseded_at = now()` — and then promotes the map it is publishing to
`complete` and current, clearing `superseded_at` on it. A build that finishes
therefore appears on the concepts list, in every report's comparison set, and at
`/g/<id>/current`, with no step for an operator. Re-publishing the same map
changes nothing: the demotion excludes the row being published.

**Publishing a version that was superseded rolls the site back to it** (#229).
Running Stage E with `PROMPT_VERSION` naming an older, already-demoted map
demotes the live one and makes the older map current again, clearing the
timestamp that said it had been replaced — one command, no by-hand SQL, and the
concepts list follows. Before #229 the promote left `superseded_at` in place and
that run died on `genealogies_current_not_superseded` at the very end, after the
whole grounding run had been paid for.

**One check, once, after this deploy.** Between migration 025 and #207a nothing
wrote `is_current` at all, so any map that completed in that window is `complete`
with `is_current = false` and is invisible to those three readers. Nothing
promotes it on its own — the swap only ever touches the row being published and
the incumbent it replaces:

```sh
psql "$LINEAGE_READ_URL" -c "SELECT id, concept, superseded_at FROM genealogies
                              WHERE status = 'complete' AND NOT is_current"
```

A row with `superseded_at` set is a superseded version and is correct as it
stands. A row with it NULL published in the window; promote it by hand from a
terminal with write access:

```sh
psql "$DATABASE_URL" -c "UPDATE genealogies SET is_current = true
                          WHERE id = <id> AND status = 'complete'"
```

The partial index refuses the promotion if the concept already has a current map,
which is the right answer: that is two published maps for one concept and it is
the case above.

**Rebuilds still crash at Stage C, and this warning comes off with #207b**
(#214). #207a moved publication and nothing else, so a re-trace of a published
map still dies at "cluster concept-states" on `genealogies_current_is_published`
— after corpus selection, fetching, extraction and Stage B have run and been paid
for. The refusal and the path around it are the section above: delete the map
first, then re-trace, which is what decision 12 already requires. #207b is the
commit that inserts a new version row instead of overwriting the live one, and it
is the one that makes a rebuild survivable.

**After the #215 deploy: re-ground the claims, once per live map.** There is no
migration to apply — `genealogies.streams` is JSONB and #215 added no column —
but there is a live-data step, and until it runs the thread pages under-claim.
A claim stamp now carries `checked_against`, the digest of the exact bytes its
check read, and resolves through the same three-state rule as every other stamp;
every claim stored before this deploy has no such digest, so `/g/13/river/*` and
every sibling thread page renders its claims as not checked against the paper's
text as it now stands, rather than as the paper's own words. That is the safe
direction and it is the feature working: those stamps genuinely are not
re-checkable, and filling the field from `papers.extracted_text_digest` would be
the silent re-anchoring incident 10 forbids. As with migration 015, the only way
a stamp becomes re-checkable is by being re-checked. The live maps are
`attention` and `embedding` (AS-BUILT section 1), so from a terminal holding
`DATABASE_URL` and the worker's `DATA_DIR` — the Render shell, because both the
extracted text and the #202 claims cache live on that disk:

```
python pipeline/stage_h_claims.py "attention"
python pipeline/stage_h_claims.py "embedding"
```

This costs ~$0: the cache hands back the same claims that were bought when the
map was built, and only the grounding runs again. The stage says so before it
buys anything, in a line printed ahead of the first paper — `N of M paper(s)
already have claims and will cost nothing; K to buy` — and on both maps `K`
should read 0. If it does not, something the cache key is made of has moved
since those claims were bought: the paper's extracted text, `PROMPT_VERSION`,
the stage's own prompt, or `--model`, which defaults to a literal in the stage
and not to `LLM_MODEL`. `--recheck` re-grounds the passages already stored and
writes the same `checked_against` for nothing, and is the answer whenever you do
not want to buy. Success is the per-paper lines reading `v/n claims carry a
checked quote`, a closing `spend $0.0000`, and a summary whose only skips are the
papers named as having no text to check — their claims stay stale, correctly, and
the run prints their arXiv ids. Then open a thread page: the claims that carried
it before show the green "✓ the paper's own words" again.

**Reading a cost cell.** The figure is scraped by the worker from the `spend $X`
lines the stages print, kept in `trace_requests.progress`, and published only
when that key holds a JSON number. There are three things a cost cell can say and
each means something different:

| The cell says | What it means |
|---|---|
| `not recorded` | no completed run, or a completed run in which no stage ever printed a spend line. A fully cached re-trace is exactly that run |
| `US$0.0040` | a real sub-cent cost. Four decimals appear only where two would round a non-zero amount to `US$0.00`; it is not a display fault (issue #87) |
| `US$0.00` | the run recorded a spend of zero |

So a `US$0.00` cell now has **two** true causes and the old entry named neither.
Either every stage that printed a spend line printed zero, or — and this is the
one to check first until the old rows age out — **the run finished before the
fix for issue #87 landed**. Until then the worker minted `spend_usd: 0.0` into
the progress blob at the moment a job was claimed and only ever overwrote it on a
spend line, so a pre-fix run that printed none is stored as a recorded zero and
is indistinguishable from a real one. Nothing in the blob separates them, so
nothing was rewritten: **no data was invented to clean this up.** Count the
affected rows read-only before believing any zero:

```sql
SELECT id, concept, finished_at, progress ->> 'spend_usd' AS spend
FROM trace_requests
WHERE status = 'complete'
  AND jsonb_typeof(progress -> 'spend_usd') = 'number'
  AND (progress ->> 'spend_usd')::numeric = 0
ORDER BY finished_at;
```

Any row there with `finished_at` before the #87 deploy is a "not recorded"
wearing a zero. If you can confirm from that run's own log that no stage printed
a spend line, the honest repair is one owner statement per row, setting that key
to JSON null rather than deleting the blob:

```sql
UPDATE trace_requests SET progress = jsonb_set(progress, '{spend_usd}', 'null')
WHERE id = <the id you checked>;
```

A cost cell showing `US$0.00` on a map whose run is known to have called the
model, with no pre-fix row behind it, is still what the old entry described:
something has started coalescing the figure, and that is a defect.

**Asking a map whether it still satisfies the rules that built it** (migration
021, issue #168). Two `CREATE VIEW`s and one guarded `GRANT`, in the shape
migration 016 established: no table, no column, no data touched, nothing to
schedule, and reversed by
`DROP VIEW map_invariant; DROP VIEW map_invariant_findings;`. Apply it with
`python pipeline/db/migrate.py` and confirm the `GRANT` from a shell holding
`LINEAGE_READ_URL`:

```
python pipeline/check_map.py --all
```

It reads `LINEAGE_READ_URL` and never `DATABASE_URL`, issues only `SELECT` and
repairs nothing, so it is safe to point at production. **Its exit status is its
verdict**: 0 when every map asked about satisfies all six clauses, 1 when any
does not, which is what makes it usable inside a procedure. Every finding names
the concept-state, the relationship or the thread it is about; there is no score
and no threshold, so there is nothing to calibrate and nothing to argue with
except the finding itself.

**A map that fails is not repaired by re-running anything.** The six clauses are
about disagreements between what a map stores and what today's stages would
build, and every one of them needs a decision: #170 is the worked example, where
one concept-state of the showcase map cites a definition that says its paper does
not define the term. Take `snapshot_map.py` before any repair.

**Stage E refuses to publish a map that fails** (issue #171). The refusal happens
inside the stage's one transaction, immediately before
`UPDATE genealogies SET status = 'complete'`, so nothing is written, the map is
left exactly as it was, and the export is not overwritten. It prints the same
findings this command prints. Three consequences worth knowing before you meet
them:

- **A re-ground of an unrepaired map now refuses.** That leaves a published map
  serving exactly what it was serving, and it means the repair has to come first.
  A full rebuild is not affected: Stage C rewrites `nodes` wholesale from the
  definitions it admits today, so the state clause 1 is about does not survive
  one.
- **Clause 6 is read against the threads the map already has**, so a Stage E run
  BY HAND after a re-cluster sees the *previous* threads over the new
  concept-states, and a paper that has left the map's membership refuses the
  publish. The repair is to run `stage_g_threads.py` and then Stage E again.
  **A worker build no longer meets this** (#192): it composes threads immediately
  before the one publishing Stage E, and Stage G's population is now the map
  rather than the definitions table, so it cannot put a paper in a thread that
  the map does not hold.
- **A database without migration 021 refuses too**, naming the migration and the
  driver's own message. That is the right way round — a gate that cannot read the
  invariant has not passed it — and Render's pre-deploy applies the migrations
  before the worker starts, so it should only ever be seen locally.

**Changing the audit's calibration.** Since migration 014 this needs no clear
and no ritual: every verdict stores a digest of the calibration that produced it,
and `--only-unchecked` treats a mismatch as unaudited, so the worker's free pass
at its next start re-measures every paper the change affects. Deploy and restart
is the whole operation.

Two things are required around it, both because that pass rewrites reader-facing
state on up to 304 rows across both live maps with nobody watching.

1. **Take the dump first, before deploying**, on the Render shell:

```
python pipeline/check_extraction.py --clear-verdicts --dry-run
```

   Unscoped and read-only. It writes every stored verdict, its signals and its
   check version to `DATA_DIR/snapshots/extraction_verdicts_all_<stamp>.json` and
   touches the database not at all. This is the only per-paper record of what the
   verdicts were, and incident 14 is what having no copy costs.

2. **Satisfy yourself the re-audit is lenient-only, before the deploy rather
   than after.** `--compare-verdicts` on the Render shell is where that is
   checked: name the change in `PROPOSED_NOTE_SIGNALS` and read the crosstab.
   Rows are today's verdict and columns are the proposal's, both in
   `VERDICT_ORDER`, so **a stricter move lands above and to the right of the
   diagonal** — `clean → suspect`, `clean → damaged`, `suspect → damaged`. Any
   cell there is a calibration to stage rather than deploy, because the pass
   runs unattended and there is no approval step in it. Below and to the left is
   the milder region and is where the intended change appears: the 2026-08-01
   run put 105 papers at row `suspect`, column `clean`, which is the whole point
   of it.
   **Read the `no source` and `unusable` columns too, and they are not milder.**
   A paper moving there has not lost its warning; `--write` cannot store an
   unstorable verdict, so the row keeps its old, stricter verdict *and* its old
   check version, which means it is selected and skipped again on every
   subsequent boot and the stale warning stands indefinitely. That is decision
   23 working as designed and it is still a reader seeing a note this
   calibration would not give. Zero papers on the 2026-08-01 run, because every
   audited paper scanned through.

3. **Write down what the boot should produce, before it produces it.** A number
   arrived at afterwards is not a check. For the 2026-08-01 demotion of `gaps`
   and `package_macros`, taken from the crosstab of the compare run that
   authorised it:

   ```
   Wrote 292 verdicts        12 skipped, all "no text on this machine"
   clean 179    suspect 98    damaged 15
   dossier note: 218 papers before, 113 after
   ```

   `damaged` must not exceed 15 and no paper may be `damaged` that was `suspect`,
   which is what the dump from step 1 is for. The expected split is the
   crosstab's proposed column and nothing else: the 12 unauditable papers belong
   in neither `clean` nor `suspect`, and counting them into the split is how an
   earlier draft of this procedure arrived at 191 and 86 and would have made a
   correct deploy look twelve papers wrong.

**Refreshing the extraction verdicts.** When a verdict describes text that has
been replaced, the free audit has to be told to look again. `--clear-verdicts`
runs from anywhere with a `DATABASE_URL` and needs no corpus; the measuring
happens on the worker. Since 014 this is no longer the tool for a calibration
change, and the reason is the gap it leaves: a clear NULLs the verdict, a version
mismatch does not.

```
python pipeline/check_extraction.py --clear-verdicts --concept "embedding" --dry-run
python pipeline/check_extraction.py --clear-verdicts --concept "embedding"
```

Then restart the worker from the Render dashboard (Manual Deploy -> Restart
service) and watch its log for `[startup] audit extracted text` and a
`Wrote N verdicts` line. **Restart it straight away, and treat that as part of
the operation.** Until it boots, those papers show no note about their text at
all, which leaves the verified stamp on each of them standing with nothing next
to it: the page claims more than it did before the clear, not less (decision 21).
The clear takes a per-paper copy of what it removes into
`DATA_DIR/snapshots/`, on `--dry-run` as well, so the record survives the
operation whatever happens next.

Do one map at a time, and repeat without `--concept` for the rest of the table
once the first has been seen to work. The reason is blast radius and rehearsal,
not runtime: the audit was measured at **8.7 seconds for 227 papers**, mean
0.038s and worst case 0.32s, against `startup_task`'s 900-second kill, so there
is no time pressure here at all. `--only <arxiv id>` clears a single paper,
which is the smallest end-to-end rehearsal of the whole loop.

On a machine that has the corpus, `python pipeline/check_extraction.py --write`
without `--only-unchecked` does the same job in one step and leaves no gap. Do
not run it anywhere else: a partial `DATA_DIR` produces verdicts about text the
maps were not built from (incident 14). The scan will now decline to call a
paper `clean` when it could not read that paper's source archive (decision 23),
so a run off the worker writes fewer verdicts and names what it skipped, but it
still writes some, and they are still about the wrong text.

**Measuring what a calibration change would do, before making it.** The Render
disk is the only machine holding the corpus the current rate was measured on, so
this runs on the Render shell:

```
python pipeline/check_extraction.py --compare-verdicts --json /data/verdict_compare.json
```

It stores nothing, changes no threshold, and refuses `--write`,
`--clear-verdicts`, `--dry-run`, `--only-unchecked` and `--sample` (decision 24).
**Read the crosstab first, then the sole-cause table, and read them for
different things.** The crosstab is the joint effect of the proposal on trial:
how many papers would still show the dossier note if every signal it names were
demoted together. The sole-cause columns are per signal and say which one to
suspect. **They do not add up.** A paper carrying two of the named signals is
sole-caused by neither and appears in neither row, so the rows understate the
proposal by however much the signals co-occur. Measured on the Render disk over
all 304 papers, which is the run that decided the fifth calibration: `gaps` alone
freed 33 papers, `package_macros` alone 44, both together 105. Reading 33 and 44
as 77 is the arithmetic that makes "fix one cause" look reasonable, and it is the
reason this work was split into 1a and 1b.

A signal that already reports as a note reads zero in both sole-cause columns,
because it is out of the verdict and demoting it again frees nobody. That is the
answer and not a gap in the table, and the row is marked `(note)` to say so.
With no proposal named the mode prints no crosstab at all and says why, rather
than showing a table of no movement that reads like a proposal measured and found
to cost nothing.

**Observing a trace.** The queue and progress panel on `/trace` is the primary
view.
Direct SQL: `SELECT id, concept, status, progress, updated_at FROM
trace_requests ORDER BY id DESC`. A `running` row whose `updated_at` is
minutes old means the worker died; the sweeper will mark it failed within 10
minutes.

---

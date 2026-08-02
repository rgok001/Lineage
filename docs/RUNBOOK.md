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
[DECISIONS.md](DECISIONS.md); the procedures themselves live here.

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
| `LLM_MODEL` | root `.env` | `claude-sonnet-5` (see decision record) |
| `PROMPT_VERSION` | root `.env` | `v2`; part of the Stage B cache key |
| `TRACE_SPEND_CAP_USD` | root `.env` | 15 |
| `DATA_DIR` | root `.env`, Render (`/data`) | absolute paths honoured |
| `OPENALEX_MAILTO` | root `.env`, Render | polite-pool contact |
| `LINEAGE_NO_DB` | set per shell, never committed | any non-blank value and every Python entry point refuses to hand out `DATABASE_URL` (decision 22). Set it in any shell running pipeline code to inspect it rather than to operate on real data. Does not reach the Node side |
| `AUTH_SECRET`, `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET`, `OWNER_GITHUB_LOGIN` | `app/.env.local`, Vercel | Auth.js reads exactly these names |

**Local development.** App: `cd app && npm run dev` (port 3000). Worker:
`python worker/run.py --once` for one job, no flag to poll forever. Pipeline:
run stages directly per README. Python is not on PATH on the dev machine;
invoke `C:\Users\GGPC\AppData\Local\Programs\Python\Python312\python.exe`.

**Migrations.** Add `pipeline/db/migrations/NNN_name.sql`, run
`python pipeline/db/migrate.py`. Applied set is recorded in
`schema_migrations`. Migrations run against the direct endpoint.

**Deploying the app.** Push to `master`; Vercel auto-deploys (root directory
is `app/`). Env var changes in Vercel do not reach an existing build: redeploy
after changing them.

**Deploying the worker.** Render dashboard -> New -> Blueprint -> this repo;
Render reads `render.yaml` and prompts for the three secrets. Success looks
like "Worker up. Polling every 10s for approved trace requests" in the logs.

**Backup and restore.** Stage E's JSON exports under `data/` are the map
backups; re-export after curating. Restore with
`python pipeline/restore_genealogy.py data/genealogy_<concept>_<pv>.json`
(refuses if the genealogy already exists). Papers, texts, and definitions are
not covered by exports; they live in Postgres and `DATA_DIR` and are cheap to
regenerate except for LLM spend, which the caches mostly protect.

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

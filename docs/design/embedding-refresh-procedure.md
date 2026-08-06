# Procedure: finish the parked `embedding` refresh

**Ticket: [#50](https://github.com/rgok001/Lineage/issues/50) `[B32]`.** Written
2026-08-03 against `master` @ `8ec81f6`. No new ticket was created; this is the
design half of #50.

**Status: proposed, awaiting the Product Owner.** Nothing here has been run. The
author held `LINEAGE_NO_DB=1` throughout and touched no database, so every count
in this document is either quoted from `docs/AS-BUILT.md` or derived from it by
arithmetic that is shown. **The pre-flight steps in section 2 are what turn those
predictions into readings; if a pre-flight reading disagrees with a prediction
here, the reading is right and this document is wrong.**

Every command below is pasted into the **Render worker shell**, from the repo
root, which is where that shell opens. `DATA_DIR` is `/data`, `PROMPT_VERSION`
is `v2` and `LLM_MODEL` is `claude-sonnet-5` (`docs/RUNBOOK.md`, section 8).

---

## 1. The problem, restated

`/g/10` — the `embedding` showcase map — sits half-repaired. Its papers were
re-extracted with the fixed extractor on 2026-07-31; incident 12 killed the run
before its definitions were re-extracted from that new text. The definitions
therefore quote a document that is no longer on disk. Since this morning's
re-ground the map says so honestly rather than falsely: 187 definitions at 115
verified, and grounding reports 201 of 305 edges verified. The repair is to
re-pay Stage B for definitions taken from the text as it now is, put the
downstream stages back over the top, and return the map's verified counts. The
owner wants the commands, in order, with the point at which to stop.

**One deviation from the ticket, stated up front.** #50 prices this at $8.45,
which is the cost of re-extracting all 187 definitions. This procedure spends
about a tenth of that, because since the ticket was written migration 015 and
this morning's re-ground have made it possible to *name* which definitions are
broken instead of buying all of them. Section 7 prices the rest of the $8.45,
says what it would buy, and says why it is not bought here.

---

## 2. Pre-flight: five readings, no writes

Each of these is a SELECT or a shell echo. None of them costs anything and none
of them changes a row. Do all five before anything else, and **write the numbers
down** — sections 5 and 6 compare against them.

**2.1 — The shell must be able to reach the database, and must be the worker's.**

```
echo "LINEAGE_NO_DB=[${LINEAGE_NO_DB}]"; echo "DATA_DIR=[${DATA_DIR}]"; echo "PROMPT_VERSION=[${PROMPT_VERSION}]"; echo "CAP=[${TRACE_SPEND_CAP_USD}]"
```

Expect `LINEAGE_NO_DB=[]` (empty), `DATA_DIR=[/data]`, `PROMPT_VERSION=[v2]`,
`CAP=[15]`.

**ABORT if `LINEAGE_NO_DB` is non-empty** — you are in an agent's shell, not the
worker's, and every command below will refuse. **ABORT if `DATA_DIR` is not
`/data`** — you are on a machine that does not hold the corpus, and incident 14
is what running these commands there costs.

**2.2 — Was `embedding` extracted with a sense gloss?**

```
python - <<'PY'
import sys; sys.path.insert(0, "pipeline")
import psycopg; from common import env
with psycopg.connect(env("DATABASE_URL")) as c:
    for r in c.execute("SELECT id, status, gloss, field_id FROM trace_requests WHERE concept = 'embedding' ORDER BY id"):
        print(r)
PY
```

Expect either no rows at all (the map predates the trace UI; `attention` was the
first map built end to end by the worker) or rows whose `gloss` is NULL.

**ABORT if any row carries a non-NULL gloss.** The gloss is injected into Stage
B's question (`SENSE`, `stage_b_extract.py`), so refreshing without it asks a
different question of the model than the one that produced the rows being
replaced, and a paper can legitimately flip `defines_concept` for that reason
alone. If a gloss exists, every `stage_b_extract.py` command in section 4 needs
`--gloss "<that exact text>"` appended, and this document should be corrected.

**2.3 — The refresh set, and the number that decides the spend.**

```
python - <<'PY'
import sys; sys.path.insert(0, "pipeline")
import psycopg; from common import env
Q = """
SELECT p.arxiv_id, d.quote_verified, d.quote_text_digest IS NULL AS no_digest,
       p.extracted_text_path IS NOT NULL AS has_path
FROM definitions d JOIN papers p ON p.id = d.paper_id
WHERE d.concept = 'embedding' AND d.prompt_version = 'v2'
  AND d.defines_concept = true AND d.quote_verified = false
ORDER BY p.arxiv_id
"""
with psycopg.connect(env("DATABASE_URL")) as c:
    rows = c.execute(Q).fetchall()
    tot = c.execute("SELECT count(*), count(*) FILTER (WHERE defines_concept), count(*) FILTER (WHERE quote_verified) FROM definitions WHERE concept='embedding' AND prompt_version='v2'").fetchone()
print("definitions / defining / verified:", tot)
print("refresh set:", len(rows))
for r in rows: print("   ", r)
open("/data/snapshots/refresh_set_20260803.txt", "w").write(" ".join(r[0] for r in rows))
print("\nids written to /data/snapshots/refresh_set_20260803.txt")
PY
```

Expect `definitions / defining / verified: (187, 134, 115)` and a refresh set of
**19**, that being 134 − 115. The selector is `defines_concept = true AND
quote_verified = false`: a paper that says it does not define the concept has no
quote to have fallen, and its negative verdict is a cached finding worth keeping
(incident 2), not an absence of one.

That selector is worth one sentence of justification, because it is the whole
design. It is not a stored assertion about staleness — there is no such column,
`definitions` has no timestamp, and `quote_extractor_version` was overwritten
with the paper's current version by this morning's re-ground. It is the verdict
of the matcher, run against the bytes on disk this morning, on a path the
definition row did not travel. It cannot agree with itself.

**ABORT if the refresh set is 0** — then nothing is broken, this whole operation
is unnecessary, and the map's 201 is the map. **ABORT if the refresh set is
above ~40**: the arithmetic above says 19, a much larger number means either the
re-ground did not commit or something re-extracted text since, and buying
definitions is the wrong response to either. **Note any row where `has_path` is
false**: Stage B will skip it with `⚠ text missing`, correctly, and it can never
be repaired by spending.

**2.4 — Has #49's worker restart already happened?**

Today's password rotation changed the Render environment variables, and a
service whose env vars change is redeployed, which restarts the worker, which
runs `startup_task("audit extracted text", ... --only-unchecked --write)`.

```
python - <<'PY'
import sys; sys.path.insert(0, "pipeline")
import psycopg; from common import env
with psycopg.connect(env("DATABASE_URL")) as c:
    print(c.execute("""SELECT extraction_verdict, count(*), min(extraction_checked_at), max(extraction_checked_at)
                       FROM papers WHERE extraction_checked_at IS NOT NULL
                       GROUP BY 1 ORDER BY 1""").fetchall())
    print("unaudited:", c.execute("SELECT count(*) FROM papers WHERE extraction_checked_at IS NULL").fetchone())
PY
```

If `max(extraction_checked_at)` is 2026-08-03, the restart has happened and the
audit ran: **#49 is discharged**, and the Render log will carry the matching
`[startup] audit extracted text` / `Wrote N verdicts` block as the evidence to
paste into that issue. If it is 2026-08-01 or earlier, the restart has not
happened; do it from the Render dashboard (Manual Deploy → Restart service) and
read the boot log, per `docs/RUNBOOK.md`.

One consequence to record rather than fix: `docs/RUNBOOK.md` requires
`check_extraction.py --clear-verdicts --dry-run` to be taken *before* a pass that
rewrites verdicts, and a restart triggered by a password rotation took nobody's
permission. If that pass has already run, the per-paper record of the pre-restart
verdicts is gone. That is a small loss — those verdicts are the ones incident 14
wrote from a partial `DATA_DIR`, which is exactly why #49 exists — but it is a
loss, and it is not this procedure's to recover.

**2.5 — What the map holds right now, in one line.**

```
python - <<'PY'
import sys; sys.path.insert(0, "pipeline")
import psycopg; from common import env
with psycopg.connect(env("DATABASE_URL")) as c:
    g = c.execute("SELECT id, jsonb_array_length(nodes), status FROM genealogies WHERE concept='embedding' AND prompt_version='v2'").fetchone()
    print("genealogy:", g)
    print("edges / verified:", c.execute("SELECT count(*), count(*) FILTER (WHERE verified) FROM edges WHERE genealogy_id=%s", (g[0],)).fetchone())
PY
```

Expect `(10, 27, 'complete')` and `(305, 201)`. **These two numbers are the
falsifiers for everything below.** Nothing in this procedure may leave the map
with fewer than 305 edges or fewer than 201 verified.

---

## 3. Backups, before anything destructive

Two artefacts, because `snapshot_map.py` and the Stage E export do not cover the
same ground and each has cost this project a map once.

```
python pipeline/snapshot_map.py "embedding"
cp /data/genealogy_embedding_v2.json /data/snapshots/genealogy_embedding_v2_pre_refresh_20260803.json
```

The first writes `genealogies` (nodes, streams, user_edits), every edge with its
eight stamp columns, and every definition with its quote, verdict and both
magnitude scores, to `/data/snapshots/embedding_v2_<stamp>.json`. That is the
only copy of the definitions the refresh is about to overwrite in place.

The second exists because `stage_e_ground.py` writes its export to a **fixed
path**, so the Stage E run in section 4.4 overwrites the map's de-facto backup
(incident 4) with a description of the map as it is after the repair. Issue #2
names this: the run that truncates a map destroys the record of what the map was.
One `cp` removes that.

Confirm the snapshot reports `305 edges (201 verified)` and `187 definitions`
before continuing. **ABORT if it reports fewer** — snapshot a map you have
already broken and you have backed up the breakage.

The undo, throughout, is
`python pipeline/restore_snapshot.py /data/snapshots/embedding_v2_<stamp>.json --confirm`
followed by `python pipeline/stage_e_ground.py "embedding"`. Restoring is
deliberately a decision and not an automation; the file is plain JSON.

---

## 4. The refresh

**Set the spend cap down first, and understand what it does and does not do.**

```
export TRACE_SPEND_CAP_USD=2
```

`TRACE_SPEND_CAP_USD` is 15 on Render, which is above the whole $8.45 and
therefore constrains nothing in this operation: Stage B's pre-flight
`est > cap` refusal never fires and its in-loop `spend > cap` break never fires.
Lowering it to 2 for this shell session turns the estimate itself into the guard
— a refresh that has somehow selected 187 papers instead of 19 is refused before
one token is bought. **It is a per-process cap, not a per-operation one**: every
command below gets its own $2 of headroom, so four stages under a $2 cap can
still spend $8 between them. The cap protects each step against selecting the
wrong set; it does not protect the operation against being run four times.

### 4.1 — Estimate (no spend)

```
python pipeline/stage_b_extract.py "embedding" --refresh --dry-run \
  --only $(cat /data/snapshots/refresh_set_20260803.txt)
```

Success looks like a table of models with `claude-sonnet-5` marked
`<- selected` and `ok` against the cap, over ~19 papers, at roughly **$0.85**.
The token count is exact, not heuristic, because the worker has
`ANTHROPIC_API_KEY` and the estimator calls `count_tokens`.

**ABORT if the paper count is not the refresh set count** from step 2.3 — the
`--only` list did not reach the query, and a `--refresh` with no `--only` prints
`Refreshing EVERY paper for this concept` and would buy all 187. **ABORT if the
total is over $2** for any reason; it is over the cap and Stage B will refuse
anyway, but knowing why before it refuses is the point of a dry run.

### 4.2 — Buy the definitions (**this step spends money**)

```
python pipeline/stage_b_extract.py "embedding" --refresh \
  --only $(cat /data/snapshots/refresh_set_20260803.txt) 2>&1 | tee /data/snapshots/stage_b_refresh_20260803.log
```

This is the only step in the procedure that spends real Anthropic credit and the
only one that rewrites live rows irreversibly-except-by-restore. It UPDATEs each
definition in place: the row's **id is preserved**, which is the whole reason
`--refresh` exists rather than a `PROMPT_VERSION` bump —
`genealogies.nodes[].definition_ids` names those ids, and minting new ones would
orphan every node on the map. It also NULLs `embedding`, deliberately: the
definition text it encoded has changed, and absent is visible to the re-embed
step while stale is visible to nothing.

Success looks like `[i/19] <arxiv>: <title>` then
`✓ definition captured, ✓ verified` for most, and a final
`Done: N definitions (M with unverified quotes), K papers dropped as not
defining the concept. Total spend: $0.8x of $2 cap.`

**ABORT (Ctrl-C) on the second consecutive `⚠ QUOTE NOT FOUND IN TEXT`.** Every
paper here was chosen because its old quote does not ground; a *new* quote that
also does not ground means the model and the extractor disagree about the
document for a reason a refresh cannot fix, and buying seventeen more of them
proves nothing. Extractions already made are cached, so stopping is free.

**ABORT if the run dies with an Anthropic error.** It will, loudly and with the
message rather than the class name — Stage B `--refresh` has no per-item
`try/except` around `client.messages.parse`, so the first API failure kills the
whole run. That is incident 12's Stage G property and it is the correct
behaviour: the stage with no fallback is the one that behaved. Fix the cause and
re-run; the papers already done are cached and will not re-bill.

**Read `K papers dropped as not defining the concept` before continuing.** A
paper that flips from defining to not-defining leaves the clustering, changes
`nodes`, and turns section 4.5's cheap re-cluster into an expensive one. Nonzero
is not an abort, but it is a prediction that section 4.5's gate will clear edges,
and it should be noted in the #50 comment.

### 4.3 — Put the vectors back (free, no model)

```
python pipeline/stage_c_cluster.py "embedding" --embed-only
```

Fills the embeddings the refresh NULLed, from the Voyage API, and **stops before
clustering**. Stage C writes `genealogies.nodes` wholesale on conflict, so
clustering here would rewrite the map before Stage E has been given a chance to
publish an honest one. Success is `embedding N definition(s) via Voyage…` for N
equal to the refresh set, then `Nodes untouched; re-run Stage E to re-ground.`

**ABORT if N is materially larger than the refresh set** — something else nulled
embeddings, and a re-embed is not the diagnosis for that.

Voyage is a separate key and a separate bill from Anthropic; ~19 short documents
is a rounding error, not a line item.

### 4.4 — Re-check every stamp, then ground and publish (both free)

```
python pipeline/stage_b_extract.py "embedding" --reground
python pipeline/stage_e_ground.py "embedding" 2>&1 | tee /data/snapshots/stage_e_20260803.log
```

`--reground` here is a **positive control as much as a repair**. The refreshed
rows were stamped by the creation path minutes ago and the other 168 were
re-ground this morning, so the expected result is
`verified before: 134 / verified after: 134` and **`stamps rewritten: 0`**.

**Anything rewritten is a finding, not a success**: it means the text under a
definition moved between this morning and now, and nothing in this procedure
moves text. Stop and find out what did. The `checked > 1 and grounded == 0`
refusal is in this path and will refuse the whole run rather than mass-flip
stamps if the disk is truncated.

Stage E then re-syncs each edge's quote copy from its definition (an edge quote
is defined as a copy, so it must never be older than what it copies), sweeps
orphans, re-grounds every edge and writes the export. Success is
`re-synced N edge quote pair(s)`, `305 edge(s), every one of them between
concept-states this map has`, then
`Genealogy complete: 27 concept-states, 305 edges (V solid/verified, I
dotted/inferred, S stale).`

**ABORT if V < 201.** The map ended worse than it started and the money made it
worse; restore from the snapshot and re-run Stage E. **Treat V == 201 as a
failure to investigate, not a success**: the refresh bought nothing, and
accepting that quietly is how a repair becomes a ritual. **ABORT if the edge
count is not 305** — nothing in this procedure removes an edge, so a smaller
number means the orphan sweep found something and the nodes and edges disagree.

Everything Stage E writes is one transaction and the export is renamed into place
only after the commit returns, so a refusal here really does leave every stamp as
it was.

**This is the publishable state.** Take a second snapshot before going on:

```
python pipeline/snapshot_map.py "embedding"
```

### 4.5 — The re-cluster, which is what discharges #50(d)

```
python pipeline/stage_c_cluster.py "embedding" 2>&1 | tee /data/snapshots/stage_c_regate_20260803.log
```

Decision 20's gate has only ever been driven directly, because `cluster()` needs
sklearn and real vectors. This reaches it the way a trace does. `/g/10` is
uncurated — its single `user_edits` entry is incident 12's restore, and a restore
is not curation — so a wholesale rewrite of `nodes` is recoverable here in a way
it would not be on a curated map. It costs one Sonnet labelling call per cluster,
about $0.02 for 27, and it will re-generate every node label; the snapshot from
4.4 is the undo if the new labels are worse.

The evidence for (d) is **which of the gate's three branches printed**, and it
must be read, not merely captured:

- `every concept-state these N edge(s) name still holds the same definitions, so
  all N were kept` — the gate working, and the cheap outcome. **No Stage D is
  needed. Skip to 4.6.**
- `X of 305 edge(s) named a concept-state that no longer holds the same
  definitions, and were removed` — also the gate working. Those X edges were
  *wrong*, not merely at risk: node ids are positional, so a kept one would be
  drawn between two concept-states nobody claimed were related. Stage D must run
  (section 4.5a).
- `the map's previous concept-states could not be read / were not recorded at all
  / did not say which definitions they held` — **this is not the gate reporting a
  clustering change and it is not evidence for (d).** It is a finding about
  `genealogies.nodes`. Stop, restore from the 4.4 snapshot, and read the prior
  `nodes` blob before anything else.

Paste the branch, the cluster count and the before/after edge counts into #50 as
the discharge of (d), naming which branch fired. A pasted log that does not say
which of the three it is has not discharged anything.

**ABORT if the cluster count is not 27 ± a few.** The threshold is unchanged at
0.28 and only ~19 definitions moved; a jump to 41 or a collapse to 8 means the
vectors are wrong, not the concept.

### 4.5a — Stage D, **only if the gate cleared edges** (this step spends money)

```
export TRACE_SPEND_CAP_USD=3
python pipeline/stage_d_edges.py "embedding" --dry-run
python pipeline/stage_d_edges.py "embedding" 2>&1 | tee /data/snapshots/stage_d_20260803.log
python pipeline/stage_e_ground.py "embedding"
```

The dry run prints `N cross-node citation link(s) found` and classifies nothing.
**That N is the denominator for the real run** and it is computed by an
independent path — the on-disk Semantic Scholar cache and the new node
assignment — so it is a real check and not the stage agreeing with itself. Expect
N near 305. Reference fetching sleeps 1.1s per citing paper even when cached, so
budget ~3 minutes of apparent silence.

Then, on the real run, at ~$1.65 for ~305 edges on Sonnet:

- **ABORT (Ctrl-C) on the second consecutive `classification failed` line.** This
  is the one place in the whole procedure where incident 12 can still happen.
  Stage D now defers its `DELETE` until the first successful classification, so a
  run that classifies *nothing* leaves the map untouched — but its global guard
  is `failures == CONSECUTIVE_FAILURE_LIMIT and written == 0`, and once a single
  edge has succeeded the DELETE has already run and that guard can never fire
  again. One success out of 305 immunises the run (issue #2, P1). **The operator
  is the guard here. Nothing else is.**
- **Post-condition: `Done: W edges classified` where W == N minus the number of
  `classification failed` lines.** Anything less and edges were lost silently.
- **ABORT if W < 250.** Not a calibrated threshold and not offered as one: it is
  a blunt floor well below any legitimate outcome, chosen so that the collapse
  incident 12 produced (0 of 305) and anything resembling it stops the operation
  before Stage E marks the map `complete`. If W lands between 250 and N, do not
  publish — restore from the 4.4 snapshot and diagnose.

### 4.6 — Stage F, because the scores are derived from what the money replaced

```
export TRACE_SPEND_CAP_USD=1
python pipeline/stage_f_magnitude.py "embedding"
```

`definitions.displacement` is a cosine distance from the centroid of earlier
definition vectors, and those vectors just changed for every paper — moving one
definition moves the centroid for all of them. Leaving it is precisely a derived
value stored and allowed to age: the influence map's turning-point rings would be
computed from definitions that no longer exist. Issue #11 `[B8]` asks for a
`--displacement-only` flag so this could be free; it does not exist, so the
attention pass re-runs with it at roughly $0.10 on Haiku (~45 batches of 12).

Success is `N papers | with attention: N | with displacement: N-1` — the earliest
paper has nothing to be displaced from — followed by the top-papers table.

**Read that table, do not just let it scroll.** Stage F's global check is
`failed_batches == bi and bi >= 3`, which can only fire if failure starts at the
very first batch (issue #10 `[B7]`); two good batches early and it is disarmed
for the rest of the run, and every failed batch pads silently to neutral. **ABORT
and restore if the attention column is uniform or near-uniform** — that is
incident 12's Stage F, and it looks exactly like data.

### 4.7 — Re-ground the claims (free, no model)

```
python pipeline/stage_h_claims.py "embedding" --recheck
```

The 476 claims on the thread pages carry quotes checked against the old text.
`--recheck` re-grounds them against the text on disk and moves only the stamp,
keeping the passage either way. It calls no model and needs no key. Stage G is
**not** re-run: composing threads costs money and nothing about the threads'
composition is wrong, only the stamps under their claims.

---

## 5. What the map should look like afterwards

| | Before | After | Falsified by |
|---|---|---|---|
| definitions | 187 | 187 | any other number; nothing here creates or deletes a row |
| defining | 134 | 134, or 134 − K | K is the "dropped as not defining" count from 4.2; unexplained movement |
| verified definitions | 115 | 134 − K | anything below 115 |
| edges | 305 | 305, or N from 4.5a | anything below 250 |
| verified edges | 201 | **≥ 201, target ≈ 286** | anything below 201; exactly 201 means nothing was bought |
| stale edges | small | ≤ the ~12 papers with no text on that disk (issue #5) | a stale count in the dozens means a digest went missing |

286 is the target because it is what this map held on 2026-07-31, when its
definitions and its text last agreed — before the re-extraction and before
incident 12. The current text is better than that text, so 286 is a floor to aim
at rather than a ceiling; it is not a pass mark, and the pass mark is the
directional one in the table.

Re-run the 2.5 reading afterwards and compare it against what Stage E printed. If
the two disagree, believe neither and stop: Stage E's summary counts at the
resolved stamp and the SQL counts the boolean, and they were made disjoint for a
reason (issue #59).

---

## 6. What is mechanically guarded, and what is you

Incident 12 had four failure modes. Three of them cannot recur here.

**Guarded by the code, nothing for the operator to watch:**

- **Stage D destroying before replacing.** The `DELETE` waits for the first
  successful classification. A run that classifies nothing leaves the map exactly
  as it found it.
- **Stage C destroying before replacing.** Its unconditional `DELETE` is gone.
  Edges clear per endpoint, and only where a node id no longer denotes the same
  definitions — where keeping the edge would draw a claim nobody made.
- **Every-item-failed read as bad luck, in the free stages.** Stage B
  `--reground` refuses on `checked > 1 and grounded == 0`; Stage E refuses when
  every attempted read failed and refuses the orphan sweep when every edge is an
  orphan. All boundaries are zero rather than a guessed fraction.
- **Stage B `--refresh` under an outage.** No per-item fallback at all: the first
  API error raises and the run dies. That is the property incident 12 praised in
  Stage G.
- **Errors reduced to a class name.** Stage B, D and F all print `str(exc)` now.
  305 lines of `BadRequestError` cannot happen again.
- **A backup describing a state the database never reached.** Stage E's export is
  written to a `.tmp` sibling inside the transaction and renamed only after the
  commit returns.

**Not guarded. These are yours:**

- **Stage D once one edge has succeeded** (issue #2, P1). The edges are already
  deleted and the global guard is disarmed. Section 4.5a's Ctrl-C rule is the
  only thing between an outage and a truncated map. This is the single most
  dangerous minute of the procedure.
- **Stage F after its first batches succeed** (issue #10, P2). Failed batches pad
  to neutral and persist over the real ranking. Read the table.
- **The spend cap.** At the Render value of 15 it constrains nothing here, and it
  is per process, so lowering it protects each step's *selection* and not the
  operation's total. There is no mechanism that stops this procedure being run
  twice; only you.
- **Balance exhaustion mid-run.** It now fails loudly at whichever stage is
  running rather than silently rebuilding the map into nothing — but the stage it
  stops in decides how much re-running that costs, and only Stage B's cache makes
  the re-run free.

---

## 7. Money

Per-paper Stage B unit, from the $8.45 estimate for 187 papers on
`claude-sonnet-5` ($3/M in, $15/M out): ~13.3k input tokens and 350 output tokens
per paper, so ~$7.47 of input plus ~$0.98 of output, ~$0.045 per paper. The 4.1
dry run reprints this exactly and that number, not this one, is the one to act
on.

| Step | Model | Expected |
|---|---|---|
| 4.2 refresh, ~19 papers | Sonnet | **~$0.85** |
| 4.3 re-embed | Voyage | negligible, separate bill |
| 4.4 `--reground` + Stage E | none | $0.00 |
| 4.5 re-cluster labels, 27 clusters | Sonnet | ~$0.02 |
| 4.5a Stage D, **only if edges cleared** | Sonnet | ~$1.65 |
| 4.6 Stage F | Haiku | ~$0.10 |
| 4.7 Stage H `--recheck` | none | $0.00 |
| **Total, cheap path** | | **~$0.97** |
| **Total, with Stage D** | | **~$2.62** |

**What the other ~$5.8 of the $8.45 would have bought, and why it is not bought
here.** Refreshing the 168 definitions that already ground buys a definition
written from the current text rather than the old one. Their quotes are already
verbatim spans of the text on disk, so product rule 2 is already satisfied for
every one of them; what would improve is the definition *prose*, which feeds the
embedding, the clustering and therefore the map's shape — all of which
`CLAUDE.md` labels as the tool's reading rather than as anything guaranteed. The
decisive objection is that **no check in this system could tell whether that
$5.8 changed anything.** A purchase with no falsifier is not a repair.

One part of it does have a falsifier and is worth a ticket of its own: the 53
papers recorded as *not* defining the concept. Some of them may have been judged
on text whose defining sentence the old extractor ate, and re-asking would show
it — the measurable outcome is how many flip to defining. That is ~$2.40, it
forces the re-cluster-and-Stage-D cascade, and it is a different question from
"finish the parked refresh". File it separately if wanted; do not attach it here.

---

## 8. What #50 still holds afterwards

- **(a)** — the two actor-on-edits checks on `/g/13`. Not in this procedure, no
  spend, and the Tester's. A CLI edit must land `by_asserted` and no `by`; a web
  edit the reverse.
- **(b)** — **already discharged**, 2026-08-03. Control ran first: `attention`
  fell 0 of 146, `embedding` fell 17, both re-ground for real.
- **(c)** — already done, 2026-08-01.
- **(d)** — discharged by section 4.5, with the branch name and the edge counts
  pasted into the issue. Not discharged if the third branch fired.
- **(e)** — is #49, and section 2.4 says whether today's rotation already
  discharged it.

With (a) done and #49 verified, #50 closes. The unbought remainder of the $8.45
is not a reason to keep it open; it is a different ticket, or it is nothing.

---

## 9. Considered and rejected

- **Bump `PROMPT_VERSION` to force re-extraction.** Mints new definition rows
  with new ids, orphaning `genealogies.nodes[].definition_ids` on both live maps,
  and re-bills all 187 papers. `--refresh` UPDATEs in place for exactly this
  reason.
- **Run the refresh as a worker trace request.** `worker/run.py`'s `stages_for`
  has no `--refresh` anywhere in it, so the trace would run Stage B's *creation*
  query — which selects only papers with no row — and refresh nothing, then
  re-cluster wholesale, re-classify all 305 edges and re-run Stages F, G and H
  for more than $8.45. The refresh is a shell operation because the pipeline is
  CLI-first and the worker adds nothing to the stages.
- **Delete the fallen definitions and let Stage B's normal path re-create them.**
  Same id problem as a version bump, and it destroys before it replaces.
- **Re-cluster first, then refresh.** Clustering from vectors that encode the old
  definitions, then replacing the definitions, produces nodes nothing stands
  behind.
- **`--no-label` on the re-cluster to keep the model out of it.** Replaces 27
  curated-quality labels with `2013–2019 sense (14 papers)` on the showcase map.
- **Re-run Stage G to recompose the threads.** Costs money; nothing about the
  threads' composition is wrong, only the stamps under their claims, and
  `stage_h_claims.py --recheck` fixes those for nothing.
- **Raise `TRACE_SPEND_CAP_USD` for the operation.** It is already too high to
  constrain anything here. The useful move is downward.

---

## 10. Open questions

1. **Does `embedding` have a sense gloss?** Section 2.2 answers it in one
   command. If it does, every Stage B command here needs `--gloss` and this
   document is wrong as written. This is the only question that changes the
   procedure rather than its inputs.
2. **Is 286 the right target for verified edges, or should the map be allowed to
   land lower?** The current text is better than the text 286 was measured
   against, so some of those 286 may have been grounding against passages the
   extractor has since corrected. The procedure treats 286 as a direction and
   201 as the hard floor; if the owner wants a pass mark, it has to be a reading
   taken after 4.4 rather than a number chosen now.
3. **Should the 53 non-defining papers be re-asked?** Priced at ~$2.40 in section
   7, with a real falsifier. Owner's call, and a separate ticket if yes.

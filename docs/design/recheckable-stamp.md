# Design: the re-checkable stamp

**Ticket: [#29](https://github.com/rgok001/Lineage/issues/29) `[F1]`.** Written
2026-08-02 against `master` @ `1883038`.

**Status: proposed.** Not yet approved, not yet implemented. `LINEAGE_NO_DB=1`
was set throughout: nothing below has been run against live data, and every
number in section 7 is a prediction stated so it can be falsified.

---

## 1. The problem

Every verification stamp this system stores is an assertion the pipeline made
about a file on the Render worker's disk at one moment, and nothing stored beside
it says which file, which bytes, or where in them the quote was found.
`definitions.quote_verified` and `edges.verified` are bare booleans; the only
link back to the evidence is `papers.extracted_text_path`, a relative path on one
machine. So a reader cannot re-check a tick, an agent cannot re-check a tick, and
the owner can re-check one only by holding the corpus and re-running the
pipeline. On a platform where strangers generate maps, that is not evidence about
a paper; it is our claim that we once looked. It is also the project's defining
incident one level up — a check whose reference is reachable only by the path the
artefact travelled — and it has already bitten twice at a smaller scale
(incidents 10 and 12, decisions 21 and 25).

## 2. The design in one paragraph

Give every stamp three things that were true at the moment the match ran: **where
in the text it matched** (character offsets), **which text it matched against**
(a SHA-256 of that file's bytes), and **which extractor produced that text** (a
digest of the extractor's own behaviour). Give `papers` the digest of the file as
it is on disk now, written by the only code that writes the file. A stamp is
displayable as verified only when its digest equals the paper's current digest;
otherwise it renders **stale, not re-checked**, whatever the boolean says. The
two digests are never copied from one another — one is written by the code that
just performed the match, the other by the code that just wrote the file — so the
comparison can actually return false.

## 3. The schema (migration 015)

`pipeline/db/migrations/015_recheckable_stamp.sql`. Additive only: `ADD COLUMN`
with no `DEFAULT` and no `NOT NULL`, so it rewrites no row and takes no table
rewrite lock on Postgres 11+. Applied by the owner with
`python pipeline/db/migrate.py`.

**`papers`** — two columns. The ticket does not name these and the feature is
impossible without them: a digest stored only on the stamp tells you what the
match ran against but not whether that is still the text, so nothing can be
concluded from stored data alone.

- `extracted_text_digest TEXT` — `sha256:<64 hex>` of the bytes of the file at
  `extracted_text_path`, as they are on disk.
- `extractor_version TEXT` — 12-character digest of the extractor's behaviour
  (section 4.2) that produced that file.

**`definitions`** — four columns, one stamp (the Stage B quote).

- `quote_start INT`, `quote_end INT` — half-open character offsets into the
  UTF-8 decoding of the file's bytes. NULL when nothing matched.
- `quote_text_digest TEXT` — the digest of the bytes actually read for the match.
- `quote_extractor_version TEXT` — the extractor version of that text.

**`edges`** — eight columns, two stamps, `source_`- and `target_`-prefixed to
match the columns already there: `source_quote_start`, `source_quote_end`,
`source_text_digest`, `source_extractor_version`, and the four `target_`
equivalents. Flat columns rather than one JSONB blob because the staleness test
is a join predicate against `papers`, and because the table already carries its
evidence in this shape.

Every new column is nullable and NULL is meaningful: **NULL means this stamp was
never made in a re-checkable way, and it renders stale.** No backfill of the
stamp columns is possible or permitted — see section 6.

No index. The staleness test always runs alongside the join to `papers` that the
evidence page and the exports already do, and the tables are in the hundreds.

## 4. The code

### 4.1 `pipeline/common.py` — one matcher, one digest, one verdict

The existing `_fold` and `quote_is_grounded` stay semantically identical. What
changes is that the matcher learns to say *where*.

- `def _fold_indexed(s: str) -> tuple[str, list[int]]` — the folded string plus,
  for each folded character, the index in `s` of the character it came from.
  Built in the same three steps and the same order as `_fold`: strip whitespace,
  remove citation marks, lowercase. Lowercasing is done per character and may
  expand (`"İ".lower()` is two characters), so every produced character maps to
  the same origin index and the folded string stays identical to `_fold`'s.
- `def grounded_span(text: str, quote: str) -> tuple[int, int] | None` — folds
  both, finds the leftmost occurrence, and maps the folded bounds back to offsets
  into `text`. Returns None when there is no match.
- `def quote_is_grounded(text, quote) -> bool` becomes
  `return grounded_span(text, quote) is not None`. **One matcher.** Two
  implementations of "is this quote in this text" would eventually disagree, and
  the disagreement would be invisible: the boolean and the span would tell
  different stories about the same stamp.
- `TEXT_DIGEST_ALGO = "sha256"` and
  `def text_digest(raw: bytes) -> str` returning
  `f"{TEXT_DIGEST_ALGO}:{hashlib.sha256(raw).hexdigest()}"`. Over **bytes**, not
  over a decoded string: a third party reproduces it with `sha256sum`, and
  nothing depends on how any platform translates newlines. The algorithm prefix
  is there so that changing it later is visible rather than silent.
- `def read_grounding_text(rel_path: str) -> tuple[str, str]` — reads
  `data_dir() / rel_path` as bytes, returns `(raw.decode("utf-8"), text_digest(raw))`.
  Every stage that grounds anything reads through this and nothing else, so the
  offsets everyone stores are offsets into the same decoding. Raises on a missing
  or undecodable file; callers already handle that and must keep handling it as
  "could not check", never as "not found".
- `STAMP_VERIFIED = "verified"`, `STAMP_INFERRED = "inferred"`,
  `STAMP_STALE = "stale"` and
  `def stamp_state(verified, stamp_digest, current_digest) -> str`:

      stale     if stamp_digest is None or current_digest is None
                or stamp_digest != current_digest
      verified  if verified
      inferred  otherwise

  **Stale dominates the boolean, in both directions.** A failed check against
  text that has since changed is no more about today's text than a passing one,
  and one rule with no exceptions is the only version of this that survives being
  copied into a second language.

### 4.2 `pipeline/extract_text.py` — the paper's side of the digest

- `def extractor_version() -> str` and `EXTRACTOR_VERSION = extractor_version()`,
  built exactly like `check_version()` in `check_extraction.py` (migration 014,
  decision 25): a `json.dumps(..., sort_keys=True)` of a **curated** dict of the
  inputs that decide what text comes out — `CITE_MACROS`, `REF_MACROS`,
  `UNKNOWN_CITE_RE`, `DEF_HEAD`, `ARGC`, `OPTIONAL_DEFAULT`,
  `MAX_EXPANSION_PASSES`, `RAW_STRIP`, `MAX_BISECT_DEPTH`, `MIN_BISECT_CHARS`,
  `MIN_LATEX_CHARS`, the pylatexenc context from `_latex_context()` and the
  pymupdf mode string — hashed with `hashlib.sha256` and truncated to 12
  characters. Regexes contribute pattern **and** flags, via the same `_rx` helper
  as 014, for the reason 014 gives.
  **Not the whole file, and not the pylatexenc/pymupdf release strings.** Hashing
  the file reddens on a docstring; hashing the library versions reddens on
  `pip install -U`. A library bump only changes a stored text when we re-extract,
  and re-extracting changes `extracted_text_digest`, which is already the thing
  that moves the stamp. A detector that fires on nearly all of its input has
  stopped measuring its input, and this project has paid for that four times.
- The write becomes `out.write_text(text, encoding="utf-8", newline="\n")`, so
  the artefact is the same bytes whichever platform extracted it. On the Linux
  worker this changes nothing.
- The digest is taken from `out.read_bytes()` **after** the write, not from the
  in-memory string: the column describes the file, not the intention.
- The single `UPDATE papers SET extracted_text_path=…` at line 517 gains
  `extracted_text_digest=%s, extractor_version=%s`. This statement is the only
  writer of `extracted_text_path` in the repository and must remain so; the
  invariant is that **path, digest and extractor version are written together or
  not at all.** A path without a digest is a file nobody can name.
- The skip path (`already extracted and the file is on this disk`) recomputes the
  digest and, when it differs from the stored one, says so loudly and updates
  `papers.extracted_text_digest`. This is the named recomputer for a derived
  value that would otherwise age: a file changed by anything other than this
  script — a hand edit, a truncated write, a restored disk — would otherwise
  leave the stamps agreeing with a digest that describes bytes that are gone.
  Updating it makes those stamps go stale, which claims *less*; it never touches
  a stamp's own digest, which would claim more. Cost is one full read of the text
  corpus per extraction run: ~300 files, tens of megabytes, seconds.

### 4.3 `pipeline/stage_b_extract.py` — the definition's stamp

Both places that write `quote_verified` now write the whole stamp.

- The creation path (`UPSERT_DEF` / `REFRESH_DEF`, around line 555) reads its
  text through `read_grounding_text`, calls `grounded_span`, and stores span,
  digest and `EXTRACTOR_VERSION` (imported from `extract_text`) beside the
  boolean.
- `reground()` does the same, and **`REGROUND_DEF` must now also fire for rows
  whose boolean did not move.** Today the loop `continue`s on `ok == was`; after
  this change that would leave a re-checked stamp with a NULL digest, i.e. still
  rendering stale after the very run that re-checked it. The condition becomes
  "anything about the stamp changed", while the printed narrative still reports
  only the rows that moved, so the log does not become noise.
- Every existing guard stays exactly as it is: the missing/empty-text branches
  still leave the stamp alone and count loudly (and now those rows keep a NULL or
  old digest, so they render stale rather than lying), the
  `checked > 1 and grounded == 0` refusal stays, and the writes stay in one
  transaction.

### 4.4 `pipeline/stage_e_ground.py` — the edge's two stamps

- The `contains()` closure becomes `match(path, quote) -> tuple[bool, span, digest]`
  and the `text_cache` holds `(text, digest)` per path, so a file is read and
  hashed once per run.
- The per-edge `UPDATE edges SET verified=…` gains the eight columns.
- **"Could not check" stops being written as "inferred".** Today a NULL
  `extracted_text_path` returns False, and a false verdict from a check that
  never ran is exactly what decision 21 and the reground's missing-file branch
  refuse to write. Now it writes `verified=false` with a NULL digest, which
  renders stale. This is the first time the schema has had somewhere to put that
  distinction.
- One new whole-run refusal, in the shape of the sweep guard above it and the
  reground guard in Stage B: **if more than one edge is checked and not one text
  file could be read, refuse and change nothing.** That is an unmounted or empty
  `DATA_DIR`, not a map that failed; the per-edge tolerance that makes one
  missing file survivable is precisely what makes a total outage invisible
  (incident 12). The boundary is zero, not a fraction. There is no threshold
  anywhere in this design.
- The assembled genealogy JSON gains `stamp` (the resolved three-state value) per
  edge alongside `verified`, and `stats` gains `stale_edges`. `verified` stays,
  so `restore_genealogy.py` and the existing exports keep working.

### 4.5 `pipeline/recheck_stamp.py` — new, and the point of the whole ticket

The columns are only worth having if something can consume them. This is the
independent re-checker, and it is what proves the tick is evidence rather than a
claim.

    python pipeline/recheck_stamp.py --concept "attention" [--arxiv ID] [--edges] [--verbose]

- **Reads `LINEAGE_READ_URL` and never `DATABASE_URL`, and issues no statement
  but `SELECT`.** It structurally cannot re-anchor a stamp, which is the failure
  mode incident 10 named as dishonest. It is therefore the one tool in this
  feature an agent may run against production.
- For each stamp it recomputes the digest from the file on disk, compares it to
  `papers.extracted_text_digest` (disagreement means the file moved under us),
  compares it to the stamp's own digest (disagreement means stale), slices
  `text[start:end]` and folds it against the stored quote (disagreement means the
  span is wrong), and re-runs `grounded_span` over the whole file (disagreement
  with the stored span means the match is not where we said).
  Those four comparisons arrive by three different paths — the database, the
  disk, and the matcher — so each of them can return false.
- Reports per stamp and in total: verified / inferred / stale / span-mismatch /
  unreadable. Exits non-zero if any span mismatches, and — the global check —
  if more than one stamp was examined and not one file could be read.
- It does **not** re-anchor, repair, or write. Ever.

### 4.6 The application

- `app/lib/stamp.ts`: `export type StampState = "verified" | "inferred" | "stale"`
  and `stampOf(verified, stampDigest, currentDigest)`, the same three lines as
  `stamp_state`. Two languages means two copies; the mitigation is that both are
  three lines with no threshold and both are pinned by the same truth table
  (section 7).
- `app/lib/genealogy.ts`: the edge query at line 439 and the map query at 305
  select `sp.extracted_text_digest` and `tp.extracted_text_digest` alongside the
  new edge columns; `Edge` and `MapEdge` gain `stamp: StampState`.
- `app/app/g/[id]/evidence/page.tsx`: the per-edge stamp at line 196 renders the
  third state as `◌ stale — not re-checked since the text changed`, in
  `var(--ink-soft)`, dotted like inferred. **No new palette token**: the UI
  tokens are owner-approved law in `CLAUDE.md` and this needs no colour of its
  own. The header count at line 30 becomes verified / inferred / stale — a count
  that folds stale into either of the other two is the same overclaim at the
  level of the summary.
- `app/app/g/[id]/p/[arxiv]/page.tsx` (line 154 onward) and
  `app/app/g/[id]/river/[sid]/page.tsx`: the same resolver, the same three
  states.
- `app/lib/export.ts` and `pipeline/export_related_work.py`: a stale quote is
  still real text a real paper contains, so it is exported with its caveat rather
  than dropped — dropping it would quietly narrow the account, which is the
  mistake Stage H already refuses to make. It must never be exported under the
  verified wording. (Open question 3.)
- `pipeline/snapshot_map.py` and `pipeline/restore_snapshot.py`: the new columns
  join the snapshot payload and the restore. A restore that omits them leaves the
  restored stamps stale, which is safe but lossy; a restore that carried a
  *stale* digest would also be safe, because the comparison is against the
  paper's current digest either way.

### 4.7 What deliberately does not change

`worker/run.py`. The worker already runs `extract_text.py`, then
`stage_b_extract.py --reground`, then `stage_e_ground.py` on every trace, and
each of those learns to write the new columns. Every future trace produces
re-checkable stamps with no orchestration change at all. If this design needed a
new worker step, it would be wrong.

`check_extraction.py` keeps its own verdict columns. `genealogies.streams` keeps
its claim-level stamps: they are a third stamp population with the same disease
and they are not in this ticket (open question 2).

## 5. Checking this design against the five faults

1. **A derived value stored and then allowed to age.** Two derived values.
   `papers.extracted_text_digest` is recomputed by `extract_text.py`, both on
   write and on the skip path (4.2), so a file that changes under us is caught.
   The stamp digests are *not* derived values at all: they are historical facts
   about a moment, like a migration-014 check version, and they are never
   refreshed — only replaced by a re-run of the match that produced them.
2. **A check that agrees with itself.** The whole ticket. The invariant that
   prevents it: *a stamp digest is written only by code that has just performed
   the match; `papers.extracted_text_digest` is written only by code that has
   just read the file; neither is ever copied from the other, and neither is ever
   copied from the stamp it qualifies.* The rejected alternative in 8.1 is the
   version of this feature that would have failed the test.
   The stored span is explicitly **not** used as a second confirmation of the
   boolean: slicing the span and finding the quote there proves nothing, because
   the same matcher put it there. It is stored so a human can look, and so
   somebody can one day measure *where* matches land (a short quote grounding
   inside a bibliography is a real failure this system currently cannot see).
3. **A threshold guessed rather than measured.** There is none in this design,
   and there must never be one, on the same reasoning as `check_record.py`. Every
   comparison is exact equality of a digest. The two refusals use the degenerate
   boundary — *not one* file readable, *not one* quote grounded — which is a
   state, not a calibration.
4. **Destroying before replacing.** The migration drops nothing and defaults
   nothing. `quote_verified` and `verified` are not cleared: a cleared boolean
   asserts a failed check, and 014 established that clearing leaves the tick
   standing alone. The old boolean stays and the NULL digest qualifies it, which
   is the replace-then-destroy ordering applied to a verdict. The re-ground
   writes in one transaction, as it already does.
5. **A per-item fallback with no global sanity check.** Stage B's
   `checked > 1 and grounded == 0` refusal is untouched; Stage E gains the
   equivalent for readability (4.4); `recheck_stamp.py` has its own (4.5). Each
   is un-immunisable by a single success only in the direction that matters: they
   test the *reading of files*, which is the thing that fails wholesale.

## 6. What it costs

**Money: $0.** No stage in this design calls a model. The re-grounding that
follows it is free by construction — it was built to be (`--reground`,
Stage H `--recheck`).

**Time.** A day of developer work; the span-mapping in 4.1 is the only part with
any subtlety. An hour of operator time to apply and re-ground.

**Risk to live data.** The migration itself rewrites nothing. Two steps do touch
live rows, and both are called out here:

> **Live-data step 1 — the papers backfill.** `papers.extracted_text_digest` and
> `papers.extractor_version` must be populated for the ~300 papers already
> extracted. This is `extract_text.py` run with no `--force`: every paper is
> skipped as already extracted, and the skip path (4.2) hashes the file and
> writes the two columns. It writes **only those two columns**; it must not touch
> `extracted_text_path`, the extraction verdict, or any stamp. `--dry-run` first.
> Honest and safe, because a digest computed now is a statement about the file
> now, and claims nothing about any past match.

> **Live-data step 2 — the re-ground.** `stage_b_extract.py <concept> --reground`
> then `stage_e_ground.py <concept>`, per map. These already rewrite
> `quote_verified` and `edges.verified` on every trace; after 015 they also write
> the stamp columns, and this is the step that will visibly move counts on the
> published maps. Take `snapshot_map.py` first (incident 4: the exports are the
> de-facto backups) and run `--reground --dry-run` first. Nothing here is new
> behaviour — it is the same free re-check the worker performs on every trace —
> but it is the first time it has been run deliberately across the corpus.

**The thing that will be alarming, said in advance.** Between the migration and
the re-ground, **every stamp in the database renders stale**, including all 287
verified edges on `attention`. That is correct and it is the feature working:
those stamps genuinely are not re-checkable, which is what the ticket says. The
window is minutes, and the fix is free. What must *not* happen is filling
`quote_text_digest` with the paper's current digest as a "backfill" — that would
turn every unproven stamp green in one statement, which is precisely the silent
re-anchoring incident 10 forbids. **There is no honest backfill of a stamp
column. The only way a stamp becomes re-checkable is by being re-checked.**

**Unblocking backlog item 4.** After this ships, "which papers' text predates the
current extractor" stops being a memory and becomes
`WHERE extractor_version IS DISTINCT FROM <EXTRACTOR_VERSION>` — the same shape
as `--only-unchecked` after 014. Re-extract those *after* this ships, so the
stamps that move do so visibly.

## 7. How it will be verified, and what would falsify it

**Offline, on a machine with no database and no corpus** (Tester; synthetic text
through the real functions). The fixture set must contain, at minimum: a quote
wrapped across a line; a quote containing `<cit.>` and `<ref>`; a citation mark
split by a newline (`<cit\n.>`), which the fold order exists to handle; a quote
occurring twice; a text containing `İ`, whose `.lower()` is two characters; a
quote that is a strict paraphrase; the empty string.

1. `_fold(s) == _fold_indexed(s)[0]` for every fixture. **Falsified by**: any
   difference — it means the span map is not describing the matcher.
2. For every fixture pair that grounds, `_fold(text[start:end]) == _fold(quote)`
   exactly. **Falsified by**: an off-by-one at either end, or a span that folds to
   more than the quote.
3. `quote_is_grounded` returns, over every fixture, exactly what the pre-change
   implementation returns. Keep the old function under a test name and compare.
   **Falsified by**: any disagreement — a refactor that moves verified counts
   would otherwise be indistinguishable from a real finding.
4. `text_digest(b"a") ` is stable across two separate Python processes and
   differs for a one-character change. **Falsified by**: instability (which is
   what `hash()` would have given, per 014's note).
5. `stamp_state` over all combinations of verified ∈ {True, False} × stamp digest
   ∈ {None, same, different} × current digest ∈ {None, value}. **Falsified by**:
   any combination returning `verified` other than (True, same, same non-NULL).
   The TS `stampOf` is run against the same table.
6. `EXTRACTOR_VERSION` moves when `MAX_EXPANSION_PASSES` is changed and does not
   move when a docstring or a comment is edited. **Falsified by**: either half.

**On the worker, against live data** (Operator; read-only where possible). State
each expectation before running it.

7. Record `SELECT count(*) FROM definitions WHERE quote_verified` and the
   per-map verified edge counts. Apply 015. Re-read them. **Falsified by**: any
   change at all — the migration must move no row.
8. Run `recheck_stamp.py --concept attention` immediately after the migration and
   before any backfill. Expect: **every** stamp reported stale, reason
   "no digest recorded". **Falsified by**: a single stamp reporting verified,
   which would mean something wrote a digest it could not know.
9. Run live-data step 1. Expect: the number of papers with a non-NULL
   `extracted_text_digest` equals the number whose text file exists on that disk,
   and the ~12 papers with no text stay NULL. **Falsified by**: a digest on a
   paper with no file.
10. Run live-data step 2 for `attention` with `--dry-run`, then for real, then
    Stage E. Expect the verified count to return to its pre-migration value minus
    exactly the definitions whose text is missing or whose quote no longer
    matches, each named by arXiv id in the output. **Falsified by**: any stamp
    moving from stale to verified for a paper whose file could not be read, or a
    count that recovers to *more* than it was.
11. Re-run `recheck_stamp.py`. Expect: zero span mismatches, and the stale set
    exactly equal to the set of papers with no text on that disk. **Falsified
    by**: any span mismatch — that is the matcher and the stored offsets
    disagreeing, and it invalidates the whole feature.
12. Hand-corrupt one character in one paper's extracted text file on the worker
    and re-run `recheck_stamp.py`. Expect: that paper's stamps flip to stale and
    the tool reports the disk/database digest disagreement. Restore the file.
    **This is the falsifying input for the entire ticket**: if the stamp survives
    a change to the text it claims to have been checked against, nothing here
    works.

**Documentation.** `docs/AS-BUILT.md` §3 (the `papers`, `definitions` and `edges`
paragraphs), `docs/PIPELINE.md` (Stage B `--reground`, Stage E), the migration
count in AS-BUILT's "`001` through `014`", `docs/RUNBOOK.md` (the two live-data
steps and `recheck_stamp.py`), and a new numbered entry in `docs/DECISIONS.md`
(30, the next free number): *a stamp names the bytes it was checked against, and
a stamp that cannot be re-checked says so.* `pipeline/check_record.py` runs
pre-commit, so any constant those files mention must be written in the resolvable
form `` `IDENT = literal` `` and every backticked symbol must exist in the code;
`check_migration_coverage` reads the `001..014` range and will need `015`.

## 8. What I considered and rejected

1. **Store the matched span's text (with surrounding context) as the evidence.**
   Re-checking a quote against a copy taken from that quote passes by
   construction. This is the project's defining incident, offered as a feature.
2. **Store the whole extracted text in Postgres.** ~30-60 MB and it moves the
   trust boundary one step rather than to the reader — the extracted text is
   itself derived from a raw file we also do not store. `arxiv_id` + extractor
   version + digest + span is a recipe a stranger can reproduce from arXiv, which
   is the reachable version of the same goal.
3. **Backfill `quote_text_digest` from the paper's current digest.** Turns every
   unproven stamp green in one statement. Forbidden, and section 6 says so twice
   on purpose.
4. **Let the extractor version make a stamp stale.** It would redden the whole
   corpus on every extractor commit, and it would be wrong: if the text on disk
   is unchanged, the stamp is still about that text. The extractor version is
   provenance and a re-extraction queue, not an invalidator.
5. **Hash `extract_text.py` (or the library versions) for the extractor
   version.** A digest over a busy file is a detector that fires on nearly every
   commit; 014 curated its inputs for exactly this reason.
6. **A hand-bumped integer version instead of a digest.** A number somebody has
   to remember to raise is a number somebody forgets — 014's own words, and the
   defect that earned them.
7. **Derive the edge stamp by joining to the definition's stamp.** The Stage E
   re-sync deliberately skips empty definitions, so an edge quote can legitimately
   differ from the definition quote; the joined stamp would then be a verdict
   about a different string. A stamp must be about the unit it is displayed on.
8. **One JSONB `stamp` column per quote.** No type discipline, awkward in the
   join, and it hides four facts inside one opaque value.
9. **Render stale as inferred.** Understates rather than overstates, so it is not
   dishonest — but it destroys the distinction the ticket exists to create, and
   the reader cannot tell "we looked and it was not there" from "we have not
   looked since".
10. **A `stale` render state for `check_extraction`'s verdict too.** Decision 21
    already clears that verdict when the text is replaced, so it has the path
    back that stamps lacked. Out of scope.

## 9. Open questions

Any of these would change the design if answered the other way.

1. **Does `CLAUDE.md` rule 2 need amending to name the third state?** The rule
   names two render states and this adds a third. I have designed it as a
   strengthening — nothing unverified is ever shown as verified, and stale is
   dotted like inferred with no new palette token — so I believe no amendment is
   required. It is the owner's call, and it is law, not mine to move.
2. **Stage H's claim-level stamps in `genealogies.streams`.** They are the third
   stamp population and 015 does not cover them, so after this ships two of three
   are re-checkable and the front-door thread pages are the one that is not.
   Recommend a follow-up ticket rather than widening this one; the JSONB payload
   makes it a different job.
3. **Exports.** Should a stale quote appear in the Markdown/BibTeX export with a
   caveat, or be omitted? I have designed for "appears with the caveat" (it is
   real text, and omission narrows the account silently), but this is a product
   decision about what an exported document claims.
4. **Backlog item 4's second half.** After re-extraction, a definition whose
   quote no longer matches the new text keeps its quote and loses its stamp for
   free. Restoring the stamp means re-paying Stage B for those papers. Free and
   honest, or paid and complete? Price it with `--dry-run` before deciding; do
   not decide it inside this ticket.

---

*Deep Thought, Architect. 2026-08-02.*

LESSONS-USED: a-stamp-must-be-a-by-product-not-an-act (the stamp digest is written only by the code that performed the match, and the extractor version digests a curated closed set rather than the file), degraded-mode-must-be-able-to-say-everything-failed (Stage E gains a whole-run refusal when not one text file could be read, and no column is cleared before its replacement exists), four-recalibrations-of-one-threshold (the extractor version does not invalidate a stamp, so the detector cannot fire on the whole corpus; no threshold anywhere), a-premise-moved-and-nothing-failed (the evidence-page header count is resolved at the same unit as the stamp, and the three stamp populations were enumerated rather than assumed covered), design-constraints-not-in-the-spec (the design is CLI-first — `recheck_stamp.py` is the reproducible shell command, and the worker gains no step)

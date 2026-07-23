# Fix log

Issues identified while reading real output, with what each one costs the
reader. Ordered by how much they damage the product's central claim, not by
effort. Fixed items are kept for the record.

---

## Open: evidence and correctness

### 1. Edge evidence does not evidence the edge
**Severity: highest. This undermines the product's core claim.**

An edge asserts "this meaning migrated into that one." The panel shows the two
papers' *definition* quotes, which establish only that each paper has a sense.
Neither quote mentions the other paper, so the reader is left to infer the
relationship from two unrelated method descriptions. Observed on the
2014 visual-semantic to 2019 video-text edge: both quotes are accurate and the
pairing still reads as meaningless.

The actual evidence exists and is discarded. Stage D fetches the Semantic
Scholar *citation context* (the sentence where the citing paper invokes the
cited one), passes it to the classifier, and never stores it. It was excluded
from display because it comes from S2's own PDF extraction and cannot pass our
verbatim string-match. That was the wrong trade: we show verifiable evidence
that is irrelevant instead of relevant evidence that is merely unverifiable.

**Fix:** add a `citation_context` column to `edges`, store what Stage D already
retrieves, and render it between the two definition quotes, explicitly labelled
as unverified provenance ("per Semantic Scholar, not matched against source
text"). Same honesty discipline as verified/inferred.

### 2. Stage B extracts sentence fragments
Quotes sometimes end mid-clause ("...such that the cosine similarity"), which
reads as noise even when technically correct. The prompt requires verbatim text
but never requires a complete sentence.
**Fix:** require complete sentences in the prompt, plus a check that the quote
ends in terminal punctuation.

### 3. Nodes conflate "defined it" with "used it"
Stage B asks whether a paper "defines **or uses**" the concept, which is
deliberately generous for recall. The cost is nodes that mix originators with
consumers: the word-vector node holds Collobert and word2vec alongside FAISS and
the Transformer, which merely consume embeddings.
**Fix:** distinguish "defines or reshapes" from "merely applies" in the Stage B
schema, and either separate or visually mark the latter. Highest-leverage single
prompt change available.

### 4. Cluster labels can be narrower than their cluster
The 46-paper node covering word vectors, t-SNE projections and latent codes is
labelled "Learned image feature vector representation". The labeller sees a
sample and can name it after the majority rather than the common thread.
**Fix:** label from the cluster centroid or a stratified sample, and show the
label as provisional until curated.

---

## Open: honesty about limits

### 5. The corpus horizon is presented as an origin
The map starts in 2011 because arXiv's CS coverage does, not because the idea
does. The real lineage runs through Bengio (2003), Latent Semantic Analysis
(1990) and distributed representations (1986), none of which are on arXiv. A
reader will naturally read the top of the timeline as the beginning.
**Fix:** an explicit "corpus horizon" marker: the story starts here because our
sources start here. Converts a silent limitation into a disclosed one.

---

## Open: making the output usable

### 6. The relationships section shows rows, not findings
305 rows are really 85 distinct meaning-pairs, each corroborated by ~3.6
independent paper-level citations. The strongest claim in the map (37 citations
carrying word vectors into image features) is invisible because it is scattered
across 37 separate rows.
**Fix:** group edges by meaning-pair, rank by corroboration count, show
"supported by N citations" per claim. Data is already there.

### 7. The export is built but not reachable
`export_related_work.py` turns a curated genealogy into a related-work skeleton
with real citations and BibTeX. It is not wired into the app, so the map stops
at "interesting picture" instead of becoming a usable draft.
**Fix:** an export button on the genealogy page.

---

## Open: performance

### 8. Stages 4 and 6 make sequential LLM calls
~143 extractions and ~300 classifications run one at a time; roughly 80% of
wall-clock is sequential network waiting. A pool of 8 would cut Stage 4 from
about ten minutes to one or two.
**Fix:** bounded concurrency inside the stage, with thread-safe spend
accounting. Not distribution: the bottleneck is waiting, not capacity, and API
rate limits are per account.

### 9. Semantic Scholar throttles anonymous traffic
Stage 6's fetch phase can take 10+ minutes on 429 backoffs.
**Fix:** a free S2 API key. Cheapest available improvement.

---

## Fixed (2026-07-21 to 07-23)

The first real cloud run exposed seven deployment-only defects, none of which
could surface locally:

| # | Defect | Fix |
|---|---|---|
| 1 | Unbounded embedding batch spiked ~2.4 GB for a 130 MB model | Capped batch size (measured 2440 MB to 342 MB) |
| 2 | Paths stored relative to the repo broke on a mounted disk | Paths relative to `DATA_DIR` (migration 008) |
| 3 | Shared DB, per-machine disks: papers flagged extracted with no local text | Skip with a warning; re-extract when the file is absent |
| 4 | Core papers silently dropped from the corpus | Extraction re-runs when the text file is missing |
| 5 | One arXiv 403 aborted a 150-paper fetch | 403/404/410 treated as unavailable; per-paper errors non-fatal |
| 6 | 1024-dim model could not load in 2 GB | Embeddings moved to a hosted API; no model in memory |
| 7 | A DB transaction held open across a 10-minute fetch was killed | Reconnect around long external phases; autocommit everywhere |

Also fixed:
- Clustering threshold recalibrated for the new embedding space (0.16 produced
  105 clusters from 134 definitions; 0.28 keeps distinct senses apart).
- Publication years: OpenAlex dated the Transformer to 2025. Now stores the
  earliest credible date (migration 009); no paper is dated in the future.
- Node member ordering after the year correction.
- Worker heartbeat now reflects "process alive" rather than "stdout active".

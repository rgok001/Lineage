"""Stage C: drift detection — embed definitions, cluster into concept-states.

Takes the papers that DEFINE the concept (Stage B, defines_concept=true), embeds
each definition, and clusters them by meaning. Each cluster is a concept-state —
one distinct sense the concept held — and becomes a node of the genealogy.

Design choices:
- Embeddings are stored (definitions.embedding, vector(1024)) using a local model
  whose dimension matches the schema, so they are computed once and reused by
  Stage D. Cached: a definition already embedded is not re-embedded.
- Agglomerative clustering with a cosine-distance cutoff, NOT k-means: the number
  of concept-states is the output, not an input we could know in advance.
- Node labelling optionally asks the LLM for a short name per cluster (cheap,
  under the spend cap); --no-label falls back to a deterministic heuristic so the
  stage runs fully offline. A label is CACHED ON ITS CLUSTER'S MEMBERSHIP, so an
  unchanged cluster keeps the words it was given (issue #189).

Writes one genealogies row per (concept, prompt_version) with nodes as JSON.

Usage:
  python pipeline/stage_c_cluster.py "attention"
  python pipeline/stage_c_cluster.py "attention" --corpus data/corpus_attention.json
  python pipeline/stage_c_cluster.py "attention" --distance-threshold 0.30
  python pipeline/stage_c_cluster.py "attention" --no-label
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, env, node_denotation, text_digest  # noqa: E402
from stage_b_extract import PRICING, cost_usd  # noqa: E402

# Embeddings come from the Voyage hosted API (see common.voyage_embed), which
# returns 1024-dim vectors matching definitions.embedding.
# Cosine-distance cutoff, RE-CALIBRATED for Voyage vectors on the 134-definition
# "embedding" corpus. Absolute distances are model-specific: the previous value
# of 0.16 was tuned for bge-large and sits at the 1st percentile of Voyage's
# pairwise distances, so almost nothing merged (105 clusters, 87 of them
# singletons). Measured Voyage distribution: p5 0.205, p25 0.273, median 0.318.
#
# Cluster counts and, more importantly, what they do to meaning:
#   0.25 -> 41 clusters   still fragmentary
#   0.28 -> 27 clusters   word / graph / recommender / knowledge-graph /
#                         latent-code / kernel-mean senses all stay separate
#   0.30 -> 20 clusters   merges graph-embedding with recommender-embedding,
#                         two senses that should not be one node
#   0.35 ->  8 clusters   collapses (largest holds 124 of 134)
#
# 0.28 is chosen because it is the loosest value that still keeps genuinely
# distinct senses apart. It over-splits weak singletons, which is the safe
# direction: merging nodes is a one-click workbench action, un-merging a
# conflated node is not. This produces a DRAFT clustering for human curation.
DEFAULT_THRESHOLD = 0.28
LABEL_MODEL = "claude-sonnet-5"

# Without --corpus a map's membership is whatever is in `definitions` for this
# concept and prompt version, which is table state rather than the papers a run
# selected: any definition row arriving by any route joins the map at the next
# clustering (issue #190). That is #169 seen from the other side — there table
# state silently REMOVES a member, here it silently ADDS one — and it is what
# makes #184's pass two abandonable, because "re-cluster the pass-one corpus"
# has to name a set of papers rather than a table.
#
# The filter is Stage B's, in the same words, and the scope is an INTERSECTION,
# not an assertion: a corpus file naming a paper with no definition row, or one
# whose row says it does not define the concept, is the ordinary case and is
# exactly what "papers that do not define the term" counts on the report.
#
# Absent, the formatted string is byte-identical to the query this stage has
# always run, so nothing existing moves.
SELECT_DEFS = """
SELECT d.id, p.arxiv_id, p.year, p.title, d.definition, d.embedding::text
FROM definitions d JOIN papers p ON p.id = d.paper_id
WHERE d.concept = %(concept)s AND d.prompt_version = %(prompt_version)s
  AND d.defines_concept = true
{corpus_filter}ORDER BY p.year NULLS LAST, p.arxiv_id
"""

CORPUS_FILTER = "  AND p.arxiv_id = ANY(%(arxiv_ids)s)\n"


def embed_definitions(conn, rows, force: bool) -> np.ndarray:
    """Return an (n, 1024) matrix; embed+store any definition missing a vector.

    Embeddings come from the Voyage hosted API (no local model to load or
    download), which is what the vector(1024) column was designed for.
    """
    from common import voyage_embed

    to_embed = [i for i, r in enumerate(rows) if force or r[5] is None]
    vectors: list[np.ndarray | None] = [None] * len(rows)

    # reuse cached embeddings
    for i, r in enumerate(rows):
        if r[5] is not None and not force:
            vectors[i] = np.fromstring(r[5].strip("[]"), sep=",")

    if to_embed:
        print(f"  embedding {len(to_embed)} definition(s) via Voyage…")
        new = voyage_embed([rows[i][4] for i in to_embed], input_type="document")
        for i, vec in zip(to_embed, new):
            vectors[i] = np.asarray(vec, dtype=float)
            vec_str = "[" + ",".join(f"{x:.6f}" for x in vectors[i]) + "]"
            conn.execute("UPDATE definitions SET embedding = %s::vector WHERE id = %s",
                         (vec_str, rows[i][0]))
        conn.commit()
    else:
        print("  all definitions already embedded (cached).")

    return np.vstack(vectors)


def cluster(mat: np.ndarray, threshold: float) -> np.ndarray:
    from sklearn.cluster import AgglomerativeClustering
    if len(mat) == 1:
        return np.array([0])
    model = AgglomerativeClustering(
        n_clusters=None, distance_threshold=threshold,
        metric="cosine", linkage="average",
    )
    return model.fit_predict(mat)


# The labelling prompt, lifted out of the call so its bytes can be hashed into
# the cache key below. Unchanged text: a label bought before this change and one
# bought after it answer the same question.
LABEL_SYSTEM = "Reply with only the label text, no quotes or punctuation around it."
LABEL_USER = ('These are definitions of how different papers use the concept "{concept}". '
              "They form one coherent sense of the concept. Give a short label (3–6 words) "
              "naming THIS specific sense — not the generic concept.\n\n{joined}")


# ── stable labels ───────────────────────────────────────────────────────────
#
# Issue #189. This stage used to buy a fresh label for every cluster on every
# run, so two runs over an identical corpus could word the same concept-state
# differently. That is a reproducibility defect on its own account — Stage D's
# classification prompt quotes these labels, so the same pair of papers could be
# handed a differently-worded question on the second run and come back a
# different edge type — and it is what would have defeated #172's classification
# cache in exactly the case the two-stage build (#184) needs it to hit: a
# re-cluster that leaves a cluster untouched would still bust the key for every
# pair touching it.
#
# So a label is cached on what it is a label OF. The key is the cluster's member
# definition ids, sorted, AND a digest of the definition text each of those ids
# holds right now. The ticket asks only for the ids; the texts are in because
# `stage_b_extract.py --refresh` rewrites a definition in place and keeps its id,
# and a label that outlives the text it was written from is the same fault as an
# edge quote that outlives its definition (decision 19). Concept, prompt version,
# model and the labelling prompt's own bytes are in for #172's reason: a cache
# that survives a prompt change serves answers to a question nobody asked.
#
# The cluster's POSITION is deliberately not in the key. Node ids are positional
# — `n1` is whichever cluster holds the earliest member year (decision 20) — so
# two runs can both produce `n3` and mean different things by it, while a member
# set cannot.
#
# Content-addressed files under DATA_DIR, the same shape and the same never-evict
# posture as `data/s2_cache`. To buy fresh labels, delete the directory.
LABEL_CACHE_DIR = "label_cache"


def label_cache_key(concept: str, prompt_version: str, model: str,
                    members: list[tuple[int, str]]) -> str:
    """The identity of the labelling question for one cluster.

    `members` is (definition_id, definition_text) for every member. Sorted here
    rather than by the caller so that a change in row order — which clustering
    input order is free to make — cannot move the key.
    """
    payload = json.dumps({
        "v": 1,
        "concept": concept,
        "prompt_version": prompt_version,
        "model": model,
        "prompt": text_digest((LABEL_SYSTEM + "\x00" + LABEL_USER).encode("utf-8")),
        "members": sorted([int(i), text_digest((t or "").encode("utf-8"))]
                          for i, t in members),
    }, sort_keys=True, ensure_ascii=False)
    return text_digest(payload.encode("utf-8")).split(":", 1)[1]


def _label_cache_file(key: str) -> Path:
    return data_dir() / LABEL_CACHE_DIR / f"{key}.json"


def cached_label(key: str) -> str | None:
    """The stored label for this key, or None.

    Anything unreadable or malformed is a MISS, never an error and never a
    guess: the cost of a miss is one cheap call, and the cost of trusting a
    half-written file is a concept-state named by whatever happens to be in it.
    """
    f = _label_cache_file(key)
    try:
        rec = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    label = rec.get("label") if isinstance(rec, dict) else None
    return label.strip() if isinstance(label, str) and label.strip() else None


def store_label(key: str, label: str, concept: str, model: str) -> None:
    """Write a bought label. Never called for a failed or empty one."""
    f = _label_cache_file(key)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"label": label, "concept": concept, "model": model}),
                     encoding="utf-8")
    except OSError as exc:
        # A cache that cannot be written is a cost, not a failure: the run has
        # the label it paid for and the map is not affected.
        print(f"    (could not cache label: {exc})", file=sys.stderr)


def label_cluster_llm(client, concept, member_defs) -> str | None:
    joined = "\n".join(f"- {d}" for d in member_defs)
    msg = LABEL_USER.format(concept=concept, joined=joined)
    try:
        resp = client.messages.create(
            model=LABEL_MODEL, max_tokens=40,
            system=LABEL_SYSTEM,
            messages=[{"role": "user", "content": msg}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        usage = resp.usage
        return text, cost_usd(LABEL_MODEL, usage.input_tokens, usage.output_tokens)
    except Exception as e:
        print(f"    (labelling failed: {e})", file=sys.stderr)
        return None, 0.0


UPSERT_GENEALOGY = """
INSERT INTO genealogies (concept, prompt_version, status, nodes, updated_at)
VALUES (%(concept)s, %(prompt_version)s, 'running', %(nodes)s, now())
ON CONFLICT (concept, prompt_version) DO UPDATE
    SET nodes = EXCLUDED.nodes, status = 'running', updated_at = now()
RETURNING id
"""

COUNT_EDGES = "SELECT count(*) FROM edges WHERE genealogy_id = %s"

# Per endpoint, not per map. An edge asserts that a paper in concept-state
# `source_node` did something to a paper in `target_node`; if both of those ids
# still denote the definitions they denoted, the assertion still holds, whatever
# happened elsewhere in the clustering. A whole-map comparison also cleared the
# edges of untouched clusters when a re-cluster merely APPENDED one — every
# existing edge still valid, all of them gone — which is a claim decision 20
# should not have been making.
CLEAR_STALE_EDGES = """
DELETE FROM edges
WHERE genealogy_id = %(gid)s
  AND (NOT (source_node = ANY(%(safe)s)) OR NOT (target_node = ANY(%(safe)s)))
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage C: cluster definitions into concept-states.")
    ap.add_argument("concept")
    ap.add_argument("--distance-threshold", type=float, default=DEFAULT_THRESHOLD,
                    help=f"cosine-distance cutoff for merging (default {DEFAULT_THRESHOLD})")
    ap.add_argument("--corpus", metavar="JSON",
                    help="restrict the map to the arxiv_ids in this corpus JSON "
                         "(from corpus_select --json), the same flag and the same "
                         "semantics as stage_b_extract.py; without it, EVERY "
                         "definition this concept has at this prompt version")
    ap.add_argument("--no-label", action="store_true", help="skip LLM node labels (offline)")
    ap.add_argument("--force", action="store_true", help="re-embed even if cached")
    ap.add_argument("--embed-only", action="store_true",
                    help="fill missing embeddings and stop, WITHOUT re-clustering. "
                         "The repair path after stage_b_extract.py --refresh: "
                         "clustering would overwrite curated nodes")
    args = ap.parse_args()

    prompt_version = env("PROMPT_VERSION", "v1")
    params: dict = {"concept": args.concept, "prompt_version": prompt_version}
    corpus_filter = ""
    if args.corpus:
        corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
        params["arxiv_ids"] = [p["arxiv_id"] for p in corpus]
        corpus_filter = CORPUS_FILTER

    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    rows = conn.execute(SELECT_DEFS.format(corpus_filter=corpus_filter), params).fetchall()
    if len(rows) < 2:
        # The advice has to name the scope, or an operator who passed the wrong
        # corpus file is told to re-run the one stage that costs money.
        if args.corpus:
            sys.exit(f"Need at least 2 definitions to cluster; found {len(rows)} for "
                     f'"{args.concept}" at prompt {prompt_version} among the '
                     f"{len(params['arxiv_ids'])} paper(s) named by {args.corpus}.\n"
                     f"  Either Stage B has not run for these papers, or this is not "
                     f"the corpus file this map was built from.")
        sys.exit(f"Need at least 2 definitions to cluster; found {len(rows)} for "
                 f'"{args.concept}" at prompt {prompt_version}. Run Stage B first.')
    if args.corpus:
        print(f"Scoped to the {len(params['arxiv_ids'])} paper(s) named by {args.corpus}: "
              f"{len(rows)} of them define this concept at prompt {prompt_version}.")

    # Clustering writes genealogies.nodes wholesale (ON CONFLICT DO UPDATE), so a
    # curated map does not survive a re-run. --embed-only exists so a refreshed
    # definition can get its vector back without that cost.
    if args.embed_only:
        embed_definitions(conn, rows, args.force)
        print(f'Embeddings filled for "{args.concept}" (prompt {prompt_version}). '
              f"Nodes untouched; re-run Stage E to re-ground.")
        return

    print(f'Clustering {len(rows)} definitions of "{args.concept}" (prompt {prompt_version})')
    mat = embed_definitions(conn, rows, args.force)
    labels = cluster(mat, args.distance_threshold)
    n_clusters = len(set(labels))
    print(f"  {n_clusters} concept-state(s) at distance-threshold {args.distance_threshold}\n")

    # LLM labelling (optional). The client is built on the first cache MISS, not
    # up front: a re-run whose clusters are all unchanged buys nothing, and it
    # should not need a key to say so.
    client = None
    spend = 0.0
    labels_cached = labels_bought = 0
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    # order clusters by earliest member year so node ids read chronologically
    order = sorted(set(labels), key=lambda c: min(rows[i][2] or 9999
                                                   for i in range(len(rows)) if labels[i] == c))
    nodes = []
    for n, c in enumerate(order, 1):
        idx = [i for i in range(len(rows)) if labels[i] == c]
        years = [rows[i][2] for i in idx if rows[i][2]]
        centroid = mat[idx].mean(axis=0)
        rep = idx[int(np.argmax(mat[idx] @ centroid))]  # member nearest centroid

        label = None
        if not args.no_label:
            key = label_cache_key(args.concept, prompt_version, LABEL_MODEL,
                                  [(rows[i][0], rows[i][4]) for i in idx])
            label = cached_label(key)
            if label:
                labels_cached += 1
            elif have_key:
                if client is None:
                    import anthropic
                    client = anthropic.Anthropic()
                label, c_spend = label_cluster_llm(client, args.concept,
                                                   [rows[i][4] for i in idx])
                spend += c_spend
                if label:
                    store_label(key, label, args.concept, LABEL_MODEL)
                    labels_bought += 1
        if not label:
            label = f"{min(years)}–{max(years)} sense ({len(idx)} papers)" if years else f"cluster {n}"

        node = {
            "node_id": f"n{n}",
            "label": label,
            "year_start": min(years) if years else None,
            "year_end": max(years) if years else None,
            "definition_ids": [rows[i][0] for i in idx],
            "representative_arxiv_id": rows[rep][1],
            "members": [{"arxiv_id": rows[i][1], "year": rows[i][2], "title": rows[i][3]}
                        for i in idx],
        }
        nodes.append(node)

        print(f"  [{node['node_id']}] {label}")
        print(f"       {node['year_start']}–{node['year_end']}, {len(idx)} papers"
              f"  (rep: {rows[rep][1]})")
        for i in idx:
            star = "*" if i == rep else " "
            print(f"       {star} {rows[i][1]:<13} {rows[i][2]}  {(rows[i][3] or '')[:50]}")
        print()

    # Read, decide and write as ONE transaction. The connection is autocommit, so
    # without this the upsert commits the new clustering the instant it runs, and
    # anything that raises between there and the edge decision leaves exactly the
    # state this gate exists to prevent: new concept-states, previous
    # clustering's edges, drawn in full on /g/<id>/evidence with the raw id where
    # a label belongs. That window did not exist before the gate did — the old
    # code put an unconditional DELETE immediately after the upsert — so the gate
    # had to own it. Reached in practice by pointing restore_genealogy.py at a
    # truncated JSON, which validates no shape, and then re-clustering.
    with conn.transaction():
        # What this map means NOW, read before the upsert overwrites it.
        prior = conn.execute(
            "SELECT id, nodes FROM genealogies WHERE concept = %s AND prompt_version = %s",
            (args.concept, prompt_version)).fetchone()

        # Persist in place: upsert on (concept, prompt_version) keeps the
        # genealogy's id stable across re-runs, so /g/<id> links and
        # trace_requests.genealogy_id survive a re-trace, and a requeued run
        # reuses its row instead of orphaning a new one. user_edits is
        # intentionally left untouched (the audit trail outlives a re-cluster).
        gen_id = conn.execute(UPSERT_GENEALOGY, {
            "concept": args.concept, "prompt_version": prompt_version,
            "nodes": psycopg.types.json.Json(nodes),
        }).fetchone()[0]

        # This DELETE used to be unconditional, with the reasoning that
        # re-clustering invalidates the old edges and Stage D rebuilds them
        # anyway. That is the reasoning Stage D itself held before incident 12:
        # it cleared first and classified second, and an exhausted balance left a
        # map with no edges at all. Stage D now defers its DELETE to the first
        # successful classification, and this one made that guard worthless — the
        # edges were already gone before Stage D was reached, so a Stage D that
        # failed for any reason left fresh nodes and nothing joining them.
        #
        # An edge survives iff BOTH the ids it names still denote the definitions
        # they denoted. Where that holds the edge still says what it said, and
        # keeping it means a failed Stage D costs nothing. Where it does not, the
        # edge is not merely at risk, it is WRONG: node ids are positional, so a
        # kept edge would be drawn between two concept-states nobody ever claimed
        # were related, with a verified stamp if Stage E can ground the quotes. A
        # wrong displayed edge is worse than a missing one under product rule 1,
        # so those clear — and what is destroyed there is already invalid, which
        # is what makes it not a repeat of incident 12.
        edges_now = conn.execute(COUNT_EDGES, (gen_id,)).fetchone()[0]
        if prior is not None and edges_now:
            prior_d = node_denotation(prior[1])
            new_d = node_denotation(nodes)
            safe = sorted(nid for nid, d in new_d.items()
                          if nid in prior_d and prior_d[nid] == d)
            # The ids whose previous denotation is actually known. Empty means
            # nothing about the old map could be established, which is a
            # different cause from "the clustering moved" and is reported as one.
            known_prior = [nid for nid, d in prior_d.items()
                           if isinstance(d, frozenset)]
            cleared = conn.execute(CLEAR_STALE_EDGES,
                                   {"gid": gen_id, "safe": safe}).rowcount
            kept = edges_now - cleared
            if not cleared:
                print(f"  every concept-state these {kept} edge(s) name still holds the "
                      f"same definitions, so all {kept} were kept.\n"
                      f"  Stage D will replace them on its first successful classification.")
            elif not known_prior:
                # The clearing is right, the usual explanation for it is not. A
                # prior blob nothing can be read out of empties `safe` and removes
                # every edge, and saying "the clustering changed" there asserts
                # something that was never established: a corrupt restore and an
                # ordinary wholesale re-cluster produced byte-identical output.
                # The cost of that was an operator re-running Stage D, which
                # spends, on a diagnosis nobody made, while the corruption that
                # caused it went unread.
                if not prior[1]:
                    why = "were not recorded at all"
                elif not prior_d:
                    why = "could not be read"
                else:
                    why = (f"did not say which definitions they held "
                           f"({len(prior_d)} recorded)")
                print(f"  the map's previous concept-states {why}, so none of the "
                      f"{edges_now} existing edge(s) could be vouched for and all "
                      f"were removed.")
                print("  This is NOT a finding that the clustering changed. Read "
                      "genealogies.nodes as it was before you trust the new map, and "
                      "check any recent restore.")
                print("  Run Stage D to rebuild the edges.")
            else:
                print(f"  {cleared} of {edges_now} edge(s) named a concept-state that no "
                      f"longer holds the same definitions, and were removed.")
                if kept:
                    print(f"  {kept} edge(s) whose concept-states are unchanged were kept.")
                print("  Run Stage D to rebuild the rest.")
    conn.close()

    print(f"Wrote genealogy: {len(nodes)} nodes for \"{args.concept}\" (prompt {prompt_version}).")
    # Printed even when it is zero, and both counts are printed beside it: a run
    # that bought nothing is a measurement (#189's whole point), and a missing
    # line reads as a run nobody costed.
    if args.no_label:
        print("Labels: none asked for (--no-label). Labelling spend: $0.0000.")
    else:
        print(f"Labels: {labels_cached} reused from cache (cluster unchanged), "
              f"{labels_bought} newly bought. Labelling spend: ${spend:.4f}.")


if __name__ == "__main__":
    main()

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
  stage runs fully offline.

Writes one genealogies row per (concept, prompt_version) with nodes as JSON.

Usage:
  python pipeline/stage_c_cluster.py "attention"
  python pipeline/stage_c_cluster.py "attention" --distance-threshold 0.30
  python pipeline/stage_c_cluster.py "attention" --no-label
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, env  # noqa: E402
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

SELECT_DEFS = """
SELECT d.id, p.arxiv_id, p.year, p.title, d.definition, d.embedding::text
FROM definitions d JOIN papers p ON p.id = d.paper_id
WHERE d.concept = %(concept)s AND d.prompt_version = %(prompt_version)s
  AND d.defines_concept = true
ORDER BY p.year NULLS LAST, p.arxiv_id
"""


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


def label_cluster_llm(client, concept, member_defs) -> str | None:
    joined = "\n".join(f"- {d}" for d in member_defs)
    msg = (f'These are definitions of how different papers use the concept "{concept}". '
           f"They form one coherent sense of the concept. Give a short label (3–6 words) "
           f"naming THIS specific sense — not the generic concept.\n\n{joined}")
    try:
        resp = client.messages.create(
            model=LABEL_MODEL, max_tokens=40,
            system="Reply with only the label text, no quotes or punctuation around it.",
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage C: cluster definitions into concept-states.")
    ap.add_argument("concept")
    ap.add_argument("--distance-threshold", type=float, default=DEFAULT_THRESHOLD,
                    help=f"cosine-distance cutoff for merging (default {DEFAULT_THRESHOLD})")
    ap.add_argument("--no-label", action="store_true", help="skip LLM node labels (offline)")
    ap.add_argument("--force", action="store_true", help="re-embed even if cached")
    args = ap.parse_args()

    prompt_version = env("PROMPT_VERSION", "v1")
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    rows = conn.execute(SELECT_DEFS, {"concept": args.concept,
                                      "prompt_version": prompt_version}).fetchall()
    if len(rows) < 2:
        sys.exit(f"Need at least 2 definitions to cluster; found {len(rows)} for "
                 f'"{args.concept}" at prompt {prompt_version}. Run Stage B first.')

    print(f'Clustering {len(rows)} definitions of "{args.concept}" (prompt {prompt_version})')
    mat = embed_definitions(conn, rows, args.force)
    labels = cluster(mat, args.distance_threshold)
    n_clusters = len(set(labels))
    print(f"  {n_clusters} concept-state(s) at distance-threshold {args.distance_threshold}\n")

    # LLM labelling (optional)
    client = None
    spend = 0.0
    if not args.no_label and os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        client = anthropic.Anthropic()

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
        if client is not None:
            label, c_spend = label_cluster_llm(client, args.concept, [rows[i][4] for i in idx])
            spend += c_spend
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

    # Persist in place: upsert on (concept, prompt_version) keeps the genealogy's
    # id stable across re-runs, so /g/<id> links and trace_requests.genealogy_id
    # survive a re-trace, and a requeued run reuses its row instead of orphaning
    # a new one. user_edits is intentionally left untouched (the audit trail
    # outlives a re-cluster). Re-clustering changes node ids/membership, which
    # invalidates the old edges; Stage D rebuilds them, but clear them now so a
    # crash before Stage D can't leave fresh nodes wired to stale edges.
    gen_id = conn.execute(UPSERT_GENEALOGY, {
        "concept": args.concept, "prompt_version": prompt_version,
        "nodes": psycopg.types.json.Json(nodes),
    }).fetchone()[0]
    conn.execute("DELETE FROM edges WHERE genealogy_id = %s", (gen_id,))
    conn.commit()
    conn.close()

    print(f"Wrote genealogy: {len(nodes)} nodes for \"{args.concept}\" (prompt {prompt_version}).")
    if spend:
        print(f"Labelling spend: ${spend:.4f}.")


if __name__ == "__main__":
    main()

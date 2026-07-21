"""Stage A (part 1): corpus selection via OpenAlex. Metadata only — no downloads.

Two ways to pick seeds:
  --search (default for concepts with no clean OpenAlex tag, e.g. "attention"):
      relevance search over arXiv+CS work title/abstract/fulltext.
  concept mode (--concept-id, or auto-resolve): works tagged with an OpenAlex
      concept. Note OpenAlex's (deprecated) concept taxonomy has no ML "attention"
      node — the bare word resolves to the ADHD sense — so search mode is the
      reliable path for the showcase concept.

Then, either way:
  - Expand one hop: works frequently referenced BY the seeds, fetched by ID in batches.
  - Rank the merged pool and print a table capped at --limit.

The embedding relevance filter (rest of Stage A) comes later; ranking here is
citation count + how often the corpus itself references the paper.

Usage:
  python pipeline/corpus_select.py "attention"                     # search mode
  python pipeline/corpus_select.py "attention" --limit 150 --json corpus.json
  python pipeline/corpus_select.py "graph neural network" --concept-id C1234
"""

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, get_json, mailto  # noqa: E402

OPENALEX = "https://api.openalex.org"
WORK_FIELDS = ("id,display_name,publication_year,cited_by_count,referenced_works,doi,"
               "locations,abstract_inverted_index")
REQUEST_PAUSE_S = 0.15  # stay well under polite-pool limits

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
# Keep the top-K seeds by relevance rather than applying an absolute cosine
# cutoff: raw similarity shifts with query phrasing and model, so a fixed number
# is brittle. Measured on "attention": junk seeds ~0.33-0.40, median ~0.46, and
# even "Attention Is All You Need" only reaches 0.567 (rank 21/400) because its
# abstract barely uses the word. Top-K is stable under all of that.
DEFAULT_KEEP_SEEDS = 150

ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([a-z\-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?", re.I)
ARXIV_DOI_RE = re.compile(r"10\.48550/arxiv\.(.+)$", re.I)


def polite(params: dict | None = None) -> dict:
    return {**(params or {}), "mailto": mailto()}


def arxiv_id_of(work: dict) -> str | None:
    doi = work.get("doi") or ""
    m = ARXIV_DOI_RE.search(doi)
    if m:
        return m.group(1)
    for loc in work.get("locations") or []:
        for url in (loc.get("landing_page_url"), loc.get("pdf_url")):
            m = ARXIV_URL_RE.search(url or "")
            if m:
                return m.group(1)
    return None


def resolve_concept(query: str) -> str:
    data = get_json(f"{OPENALEX}/concepts", polite({"search": query, "per-page": 5}))
    results = data.get("results", [])
    if not results:
        sys.exit(f'No OpenAlex concept matches "{query}".')
    print(f'Concept matches for "{query}":')
    for i, c in enumerate(results):
        marker = "→" if i == 0 else " "
        print(f'  {marker} {c["id"].rsplit("/", 1)[-1]}  {c["display_name"]}'
              f'  (level {c["level"]}, {c["works_count"]:,} works)')
    chosen = results[0]
    print(f'Using {chosen["display_name"]} — pass --concept-id to override.\n')
    return chosen["id"].rsplit("/", 1)[-1]


def _paginate_seeds(params: dict, max_seeds: int, label: str) -> list[dict]:
    params = polite({**params, "per-page": 200, "select": WORK_FIELDS, "cursor": "*"})
    seeds: list[dict] = []
    while len(seeds) < max_seeds:
        data = get_json(f"{OPENALEX}/works", params)
        batch = data.get("results", [])
        if not batch:
            break
        seeds.extend(batch)
        print(f"  {label}: {len(seeds)} fetched…")
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor
        time.sleep(REQUEST_PAUSE_S)
    return seeds[:max_seeds]


def field_clause(field: str | None) -> str:
    """OpenAlex filter clause scoping a work to one field's primary subject.

    Accepts "17", "fields/17", or None/"all". Replaces the old hardcoded
    Computer Science *concept* filter: concepts are deprecated, and a field is
    the right granularity for "which discipline is this paper in". Uses
    primary_topic.field.id (the paper's main field) rather than topics.field.id
    (any assigned field) to keep the corpus on-subject; recall within the field
    is still high, and the embedding filter refines from there.
    """
    if not field or field.lower() == "all":
        return ""
    return f"primary_topic.field.id:fields/{field.rsplit('/', 1)[-1]}"


def fetch_seeds_by_concept(concept_id: str, max_seeds: int, field: str) -> list[dict]:
    filters = [f"concepts.id:{concept_id}", "indexed_in:arxiv"]
    if (fc := field_clause(field)):
        filters.append(fc)
    return _paginate_seeds(
        {"filter": ",".join(filters), "sort": "cited_by_count:desc"},
        max_seeds, "seeds")


def fetch_seeds_by_search(query: str, max_seeds: int, field: str) -> list[dict]:
    # Relevance search over title/abstract/fulltext. Cursor paging can't sort by
    # relevance_score, so we page by citations within the matched set — good enough
    # for seeding; the embedding filter refines relevance later.
    filters = ["indexed_in:arxiv"]
    if (fc := field_clause(field)):
        filters.append(fc)
    return _paginate_seeds(
        {"search": query, "filter": ",".join(filters), "sort": "cited_by_count:desc"},
        max_seeds, "seeds")


def expand_one_hop(seeds: list[dict], max_new: int) -> tuple[list[dict], Counter]:
    """Count references across seeds; fetch the most-referenced non-seed works."""
    ref_freq: Counter = Counter()
    for w in seeds:
        ref_freq.update(w.get("referenced_works") or [])
    seed_ids = {w["id"] for w in seeds}
    # Referenced ≥2 times by the seed corpus = plausibly part of the lineage.
    candidates = [wid for wid, n in ref_freq.most_common()
                  if wid not in seed_ids and n >= 2][:max_new]
    expanded: list[dict] = []
    for i in range(0, len(candidates), 50):  # OpenAlex OR-filter cap is 50 values
        batch = candidates[i:i + 50]
        short_ids = "|".join(wid.rsplit("/", 1)[-1] for wid in batch)
        data = get_json(f"{OPENALEX}/works", polite({
            "filter": f"openalex:{short_ids}",
            "per-page": 50,
            "select": WORK_FIELDS,
        }))
        expanded.extend(data.get("results", []))
        print(f"  expansion: {len(expanded)}/{len(candidates)} fetched…")
        time.sleep(REQUEST_PAUSE_S)
    return expanded, ref_freq


def abstract_of(work: dict) -> str:
    """Rebuild an abstract from OpenAlex's inverted index ({word: [positions]})."""
    inv = work.get("abstract_inverted_index")
    if not inv:
        return ""
    pos = [(p, w) for w, ps in inv.items() for p in ps]
    return " ".join(w for _, w in sorted(pos))


def relevance_scores(concept: str, works: list[dict]) -> list[float]:
    """Cosine similarity of each work's title+abstract to the concept.

    Local model on purpose: Stage A must stay free — nothing is paid for before
    the corpus is chosen. These embeddings are ephemeral (the stored vector(1024)
    definition embeddings in Stage C are a separate, higher-quality model).
    """
    import numpy as np
    from fastembed import TextEmbedding

    docs = [f"{w.get('display_name') or ''}. {abstract_of(w)}"[:2000] for w in works]
    # Cache under DATA_DIR so a deployed worker's persistent disk keeps the
    # model between restarts (the default cache is a temp dir).
    model = TextEmbedding(EMBED_MODEL, cache_dir=str(data_dir() / "models"))
    vecs = np.array(list(model.embed([BGE_QUERY_PREFIX + concept] + docs)))
    q, d = vecs[0], vecs[1:]
    q = q / np.linalg.norm(q)
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    return (d @ q).tolist()


def score(work: dict, ref_freq: Counter) -> float:
    # In-corpus reference frequency is worth more than raw global citations:
    # we want the papers THIS lineage talks about, not just famous ones.
    return (2.0 * math.log1p(ref_freq.get(work["id"], 0))
            + math.log1p(work.get("cited_by_count") or 0))


def main() -> None:
    ap = argparse.ArgumentParser(description="Select a ranked candidate corpus (metadata only).")
    ap.add_argument("concept", help='e.g. "attention"')
    ap.add_argument("--limit", type=int, default=150, help="corpus cap (default 150)")
    ap.add_argument("--max-seeds", type=int, default=400)
    ap.add_argument("--max-expand", type=int, default=300)
    ap.add_argument("--concept-id", help="OpenAlex concept ID; enables concept mode (e.g. C66322947)")
    ap.add_argument("--concept-mode", action="store_true",
                    help="resolve the concept string to an OpenAlex tag instead of searching")
    ap.add_argument("--field", default="fields/17",
                    help="OpenAlex field scoping the corpus (default fields/17 = Computer "
                         "Science; accepts '17' or 'fields/17'; 'all' drops the field filter)")
    ap.add_argument("--gloss",
                    help="one-line sense clarification (e.g. 'kernel, as in SVM kernel methods'); "
                         "used as the relevance query instead of the bare concept")
    ap.add_argument("--keep-seeds", type=int, default=DEFAULT_KEEP_SEEDS,
                    help=f"keep the top N seeds by relevance (default {DEFAULT_KEEP_SEEDS})")
    ap.add_argument("--min-relevance", type=float, default=0.0,
                    help="optional absolute relevance floor (default off)")
    ap.add_argument("--no-relevance-filter", action="store_true",
                    help="skip the embedding relevance filter on seeds")
    ap.add_argument("--json", metavar="PATH", help="also write the ranked corpus as JSON")
    args = ap.parse_args()

    # The gloss disambiguates the sense for RANKING; the search still uses the
    # bare concept to cast a wide recall net. Wide word, tight meaning.
    rel_query = args.gloss or args.concept
    if args.concept_id or args.concept_mode:
        concept_id = args.concept_id or resolve_concept(args.concept)
        print("Fetching concept-tagged arXiv seeds from OpenAlex…")
        seeds = fetch_seeds_by_concept(concept_id, args.max_seeds, args.field)
    else:
        print(f'Searching {args.field} arXiv works for "{args.concept}" (relevance seed mode)…')
        seeds = fetch_seeds_by_search(args.concept, args.max_seeds, args.field)
    if not seeds:
        sys.exit("No seed papers found — try --field all, --concept-mode, or a different query.")

    # Embedding relevance filter — SEEDS ONLY, deliberately.
    #
    # Papers that currently discuss the concept do use its current name, so
    # semantic relevance cleans search noise out of the seeds well. The one-hop
    # expansion is left unfiltered on purpose: a concept's ancestors predate its
    # name (Bahdanau 2014, the origin of attention, never says "attention" — it
    # says "align"), so scoring them against today's vocabulary would delete
    # exactly the history this tool exists to find. Ancestors earn their place
    # via citations from the cleaned seeds instead.
    rel_by_id: dict[str, float] = {}
    if not args.no_relevance_filter:
        print(f"Scoring seed relevance to \"{rel_query}\" ({EMBED_MODEL}, local)…")
        scores = relevance_scores(rel_query, seeds)
        rel_by_id = {w["id"]: s for w, s in zip(seeds, scores)}
        by_rel = sorted(seeds, key=lambda w: rel_by_id[w["id"]], reverse=True)
        kept = [w for w in by_rel[:args.keep_seeds] if rel_by_id[w["id"]] >= args.min_relevance]
        dropped = [w for w in by_rel if w not in kept]
        if not kept:
            sys.exit("Relevance filter removed every seed — lower --min-relevance.")
        cutoff = rel_by_id[kept[-1]["id"]]
        print(f"  kept top {len(kept)}/{len(seeds)} seeds (relevance >= {cutoff:.3f})")
        for w in dropped[-3:]:
            print(f"    dropped {rel_by_id[w['id']]:.3f}  {(w.get('display_name') or '?')[:62]}")
        if len(dropped) > 3:
            print(f"    …and {len(dropped) - 3} more below the cut")
        seeds = kept

    print("Expanding one hop through the citation graph (unfiltered — protects ancestors)…")
    expanded, ref_freq = expand_one_hop(seeds, args.max_expand)

    seed_ids = {w["id"] for w in seeds}
    # Dedup on arXiv ID (the natural key): OpenAlex keeps separate preprint/published
    # records for the same paper. Keep the better record — prefer a seed, then the
    # one with more in-corpus references, then more citations.
    def better(a: dict, b: dict) -> dict:
        key = lambda w: (w["_seed"], ref_freq.get(w["id"], 0), w.get("cited_by_count") or 0)
        return a if key(a) >= key(b) else b

    pool: dict[str, dict] = {}
    for w in seeds + expanded:
        aid = arxiv_id_of(w)
        if aid is None:
            continue  # arXiv-only corpus; expansion hits can be journal-only
        w["_arxiv_id"] = aid
        w["_seed"] = w["id"] in seed_ids
        pool[aid] = better(pool[aid], w) if aid in pool else w

    ranked = sorted(pool.values(), key=lambda w: score(w, ref_freq), reverse=True)
    ranked = ranked[:args.limit]

    print(f"\nCandidate corpus for \"{args.concept}\" — {len(ranked)} papers "
          f"({sum(w['_seed'] for w in ranked)} seed, "
          f"{sum(not w['_seed'] for w in ranked)} expanded)\n")
    print(f"{'#':>3}  {'arXiv ID':<14} {'Year':<5} {'Cites':>7} {'Refs':>5} {'Rel':>5} {'Src':<4} Title")
    print("-" * 116)
    for i, w in enumerate(ranked, 1):
        title = (w.get("display_name") or "?")[:60]
        rel = rel_by_id.get(w["id"])
        rel_s = f"{rel:.2f}" if rel is not None else "  -"
        print(f"{i:>3}  {w['_arxiv_id']:<14} {w.get('publication_year') or '?':<5} "
              f"{w.get('cited_by_count') or 0:>7,} {ref_freq.get(w['id'], 0):>5} {rel_s:>5} "
              f"{'seed' if w['_seed'] else 'exp':<4} {title}")

    if args.json:
        out = [{
            "arxiv_id": w["_arxiv_id"],
            "openalex_id": w["id"],
            "title": w.get("display_name"),
            "year": w.get("publication_year"),
            "cited_by_count": w.get("cited_by_count"),
            "in_corpus_refs": ref_freq.get(w["id"], 0),
            "seed_relevance": rel_by_id.get(w["id"]),
            "seed": w["_seed"],
        } for w in ranked]
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nWrote {len(out)} papers to {args.json}")


if __name__ == "__main__":
    main()

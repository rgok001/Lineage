"""Stage A (part 1): corpus selection via OpenAlex. Metadata only — no downloads.

Two ways to pick seeds:
  --search (default for concepts with no clean OpenAlex tag, e.g. "attention"):
      relevance search over arXiv+CS work title/abstract/fulltext.
  concept mode (--concept-id, or auto-resolve): works tagged with an OpenAlex
      concept. Note OpenAlex's (deprecated) concept taxonomy has no ML "attention"
      node — the bare word resolves to the ADHD sense — so search mode is the
      reliable path for the showcase concept.

Then, either way:
  - Expand one hop BACKWARD: works frequently referenced BY the seeds, fetched by
    ID in batches. This is how ancestors enter (decision 4).
  - Expand one hop FORWARD: recent works that CITE the seeds. This is how the
    literature written after the seeds enters, and it is measured before it is
    given a seat (issue #180).
  - Rank the merged pool and print a table capped at --limit.

The embedding relevance filter (rest of Stage A) comes later; ranking here is
citation count + how often the corpus itself references the paper.

Usage:
  python pipeline/corpus_select.py "attention"                     # search mode
  python pipeline/corpus_select.py "attention" --limit 150 --json corpus.json
  python pipeline/corpus_select.py "graph neural network" --concept-id C1234
  python pipeline/corpus_select.py "dark energy" --field fields/31 --recent-since 2021
"""

import argparse
import datetime
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

# Keep the top-K seeds by relevance rather than applying an absolute cosine
# cutoff: raw similarity shifts with query phrasing and model, so a fixed number
# is brittle. Measured on "attention": junk seeds ~0.33-0.40, median ~0.46, and
# even "Attention Is All You Need" only reaches 0.567 (rank 21/400) because its
# abstract barely uses the word. Top-K is stable under all of that.
DEFAULT_KEEP_SEEDS = 150

# ── the forward hop (issue #180) ────────────────────────────────────────────
#
# How far back "recent" reaches. Five years is the window the F5 design argued
# from and the window the report's recency figure is taken over; it is a
# constant rather than a literal so the two cannot drift apart.
RECENT_YEARS = 5

# A forward candidate must cite at least this many of our seeds. Same rule and
# same number as the backward hop's `n >= 2`, and for the same reason: cited
# once is a mention, cited twice is a connection to this lineage. Measured on
# the /g/17 dark-energy query, 2021+: of 200 works citing any seed, 74 cite
# exactly one and 126 cite two or more, so the rule discriminates rather than
# formalising.
FORWARD_MIN_SEEDS_CITED = 2

# Two orderings, half the budget each, and the second one is the point.
# Measured 2026-08-08 on the dark-energy query: a batch of 50 seeds has 18,725
# works citing it since 2021, which is 94 pages and ~270MB to read whole — too
# much for every trace. So it is truncated, and the truncation has to be
# argued: the first page by `cited_by_count:desc` is 129/200 from 2021 and
# 4/200 from 2024-25, so citation-ordered truncation reproduces inside the
# window exactly the age bias the reservation exists to remove. Paging the
# newest first is the control, and it costs one extra request per batch.
FORWARD_SORTS = ("cited_by_count:desc", "publication_date:desc")

# Rows of the forward table printed. The full set runs to hundreds; the table
# is there to be read by a person deciding whether the hop found the lineage.
FORWARD_TABLE_ROWS = 30

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


def _forward_pages(seed_short_ids: list[str], since_year: int, field: str | None,
                   sort: str, max_works: int) -> list[dict]:
    """One ordering of the works citing one batch of seeds, cursor-paged."""
    filters = [f"cites:{'|'.join(seed_short_ids)}",
               f"publication_year:>{since_year - 1}", "indexed_in:arxiv"]
    if (fc := field_clause(field)):
        filters.append(fc)
    params = polite({"filter": ",".join(filters), "per-page": 200,
                     "select": WORK_FIELDS, "sort": sort, "cursor": "*"})
    out: list[dict] = []
    while len(out) < max_works:
        data = get_json(f"{OPENALEX}/works", params)
        batch = data.get("results", [])
        if not batch:
            break
        out.extend(batch)
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor
        time.sleep(REQUEST_PAUSE_S)
    return out[:max_works]


def expand_forward(seeds: list[dict], since_year: int, field: str | None,
                   max_per_batch: int) -> tuple[list[dict], Counter, dict]:
    """Recent works that CITE the seeds — the forward analogue of expand_one_hop.

    `expand_one_hop` asks what the seeds cite, so everything it can reach is
    older than the seeds by construction. Nothing asked the other direction, and
    that is where the recency gap is made: seeds arrive sorted by citations, and
    on the /g/17 query the 400th seed has 883 of them, which 2 of the 52,644
    matching arXiv works from 2022 or later clear. A 2024 paper was never in the
    pool that `score()` ranks (issue #33, issue #180).

    Returns (candidates, seeds_cited, stats). `seeds_cited` counts, per work,
    how many of the seeds it cites — the forward analogue of `ref_freq` — and it
    is counted against the WHOLE seed set, not the batch a work came back from,
    so batching cannot change a work's number. Candidates are those clearing
    FORWARD_MIN_SEEDS_CITED; `stats` carries what was looked at to find them,
    because an empty result and a result nobody paged for read the same in a log.
    """
    seed_ids = {w["id"] for w in seeds}
    short = [w["id"].rsplit("/", 1)[-1] for w in seeds]
    fetched: dict[str, dict] = {}
    per_sort: Counter = Counter()
    batches = 0
    # OpenAlex's OR-filter cap is 50 values, same as the backward hop's fetch.
    for i in range(0, len(short), 50):
        batches += 1
        for sort in FORWARD_SORTS:
            works = _forward_pages(short[i:i + 50], since_year, field, sort,
                                   max_per_batch // len(FORWARD_SORTS))
            per_sort[sort] += len(works)
            for w in works:
                fetched.setdefault(w["id"], w)
            time.sleep(REQUEST_PAUSE_S)
        print(f"  forward hop: {len(fetched)} distinct works citing the seeds "
              f"(batch {batches} of {-(-len(short) // 50)})…")

    seeds_cited: Counter = Counter()
    for wid, w in fetched.items():
        seeds_cited[wid] = len(seed_ids & set(w.get("referenced_works") or []))
    candidates = [w for wid, w in fetched.items()
                  if seeds_cited[wid] >= FORWARD_MIN_SEEDS_CITED and wid not in seed_ids]
    candidates.sort(key=lambda w: (-seeds_cited[w["id"]], -(w.get("cited_by_count") or 0)))
    stats = {"fetched": len(fetched), "batches": batches, "per_sort": dict(per_sort),
             "since": since_year}
    return candidates, seeds_cited, stats


def abstract_of(work: dict) -> str:
    """Rebuild an abstract from OpenAlex's inverted index ({word: [positions]})."""
    inv = work.get("abstract_inverted_index")
    if not inv:
        return ""
    pos = [(p, w) for w, ps in inv.items() for p in ps]
    return " ".join(w for _, w in sorted(pos))


def relevance_scores(concept: str, works: list[dict]) -> list[float]:
    """Cosine similarity of each work's title+abstract to the concept.

    Embeddings come from the Voyage hosted API (no local model), so the concept
    is embedded as a "query" and the papers as "documents". Stage A now costs a
    few cents of embedding calls rather than being strictly free, but the corpus
    is still chosen before any LLM spend.
    """
    import numpy as np
    from common import voyage_embed

    docs = [f"{w.get('display_name') or ''}. {abstract_of(w)}"[:2000] for w in works]
    q = np.asarray(voyage_embed([concept], input_type="query")[0])
    d = np.asarray(voyage_embed(docs, input_type="document"))
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
    ap.add_argument("--recent-since", type=int, metavar="YEAR",
                    help=f"first year of the recency window (default: this year "
                         f"minus {RECENT_YEARS})")
    ap.add_argument("--max-forward", type=int, default=400,
                    help="forward-hop candidates fetched per batch of 50 seeds, "
                         "split across the two orderings (default 400; 0 skips "
                         "the forward hop entirely)")
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
        print(f"Scoring seed relevance to \"{rel_query}\" (Voyage embeddings)…")
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

    print("Expanding one hop backward through the citation graph (unfiltered — protects ancestors)…")
    expanded, ref_freq = expand_one_hop(seeds, args.max_expand)

    # The forward hop. It takes no seat in this run: it is the instrument the
    # seat change is argued from, and it lands first so the "before" reading is
    # taken while the selection is still the one being complained about (#180).
    since = args.recent_since or (datetime.date.today().year - RECENT_YEARS)
    forward: list[dict] = []
    seeds_cited: Counter = Counter()
    fwd_stats: dict = {}
    if args.max_forward > 0:
        print(f"Expanding one hop forward: arXiv works from {since} citing the seeds…")
        forward, seeds_cited, fwd_stats = expand_forward(
            seeds, since, args.field, args.max_forward)

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

    # ── the forward hop, reported and nothing else (#180) ───────────────────
    #
    # Printed under the corpus table on purpose: the two numbers that matter are
    # the newest year the selection above reached and the newest year the hop
    # found, and they belong on the same screen. Everything here is metadata
    # from the polite pool; no seat above moved and nothing was paid for.
    if args.max_forward > 0:
        selected_years = [w.get("publication_year") for w in ranked
                          if w.get("publication_year")]
        in_selection = {w["_arxiv_id"] for w in ranked}
        unseen = [w for w in forward
                  if (arxiv_id_of(w) or "") not in in_selection]
        recent_selected = sum(1 for y in selected_years if y >= since)
        per_sort = ", ".join(f"{k.split(':')[0]} {v:,}"
                             for k, v in fwd_stats.get("per_sort", {}).items())
        print(f"\nForward citation hop — arXiv works from {since} citing these seeds. "
              f"Instrument only: no seat above changed.")
        print(f"  {fwd_stats['fetched']:,} distinct works fetched over "
              f"{fwd_stats['batches']} seed batch(es) x {len(FORWARD_SORTS)} orderings "
              f"({per_sort})")
        print(f"  {len(forward):,} cite >= {FORWARD_MIN_SEEDS_CITED} of the "
              f"{len(seeds)} seeds; {len(unseen):,} of those are absent from the "
              f"{len(ranked)} selected above")
        print(f"  the selection holds {recent_selected} paper(s) from {since} or later; "
              f"its newest is {max(selected_years) if selected_years else '?'}, "
              f"the hop's newest is "
              f"{max((w.get('publication_year') or 0) for w in forward) if forward else '-'}")
        if len(forward) < 50:
            # The design's own failure condition, stated as a number before the
            # reading was taken: under ~50 candidates means this field does not
            # cite its founding work densely enough for a forward hop to find the
            # lineage, and the reservation must lean on the search fallback.
            print(f"  ⚠ fewer than 50 candidates cleared {FORWARD_MIN_SEEDS_CITED} seeds — "
                  f"the citation signal is weak for this concept")
        print(f"\n{'#':>3}  {'Seeds':>5} {'arXiv ID':<14} {'Year':<5} {'Cites':>7} Title")
        print("-" * 116)
        for i, w in enumerate(forward[:FORWARD_TABLE_ROWS], 1):
            print(f"{i:>3}  {seeds_cited[w['id']]:>5} {(arxiv_id_of(w) or '-'):<14} "
                  f"{w.get('publication_year') or '?':<5} "
                  f"{w.get('cited_by_count') or 0:>7,} "
                  f"{(w.get('display_name') or '?')[:60]}")
        if len(forward) > FORWARD_TABLE_ROWS:
            print(f"     …and {len(forward) - FORWARD_TABLE_ROWS:,} more candidates")

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

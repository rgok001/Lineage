"""Stage D: edge classification.

For each pair of corpus papers linked by a citation and sitting in DIFFERENT
concept-states, classify how the newer paper's treatment of the concept relates
to the older one — one of the six edge types — using the citation context
(Semantic Scholar, public API, no key) as the signal.

Design:
- The LLM classifies only (edge_type + confidence + rationale). It does NOT
  produce quotes — evidence is assembled from grounded data we already hold: the
  ancestor's Stage-B-verified definition quote, and the verbatim citation-context
  sentence from the citing paper. Nothing is hallucinated.
- Direction is chronological: the cited (older) paper is the ancestor = source;
  the citing (newer) paper is the descendant = target. edge_type describes what
  the descendant does to the ancestor's concept.
- Grounding of the two quotes is Stage E's job; edges land here with verified=false.
- Every successful classification is CACHED ON DISK (issue #172), keyed by the
  semantic inputs of the question. A pair whose two papers, definitions, labels
  and citation contexts are unchanged is never bought twice.

Usage:
  python pipeline/stage_d_edges.py "attention"
  python pipeline/stage_d_edges.py "attention" --dry-run
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env, get_json, data_dir, text_digest  # noqa: E402
from stage_b_extract import cost_usd  # noqa: E402

# Enough failures to prove it is the call and not the edge.
CONSECUTIVE_FAILURE_LIMIT = 10

S2 = "https://api.semanticscholar.org/graph/v1"
S2_PAUSE_S = 1.1  # polite spacing on the shared unauthenticated pool
EST_OUTPUT_TOKENS = 200


class EdgeClass(BaseModel):
    edge_type: Literal["extends", "contests", "narrows", "renames", "merges", "migrates"] = Field(
        description="How the newer (descendant) paper's treatment relates to the older one."
    )
    confidence: float = Field(description="0–1 confidence in this classification.")
    rationale: str = Field(
        description="One sentence of at most 35 words justifying the type from the evidence."
    )


SYSTEM = """You classify the relationship between two papers' treatments of a \
concept, for a concept-genealogy tool. Choose exactly one of six types:
- extends: builds on / generalises the earlier idea
- contests: disputes or argues against it
- narrows: restricts it to a special case or domain
- renames: same idea, new terminology
- merges: fuses the earlier idea with another
- migrates: carries the idea into a new field or modality
Judge only from the definitions and the citation context provided. If several \
fit, pick the dominant relationship. Be calibrated with confidence."""

USER = """Concept: "{concept}"

EARLIER paper — concept-state "{src_label}":
{src_def}

NEWER paper — concept-state "{dst_label}":
{dst_def}

How the NEWER paper cites the EARLIER one (verbatim context):
{contexts}

Classify how the NEWER paper's treatment relates to the EARLIER one."""


# ── the classification cache ────────────────────────────────────────────────
#
# Issue #172. Making a rebuild all-or-nothing (#2) means a run that dies at
# candidate 200 of 305 stores nothing, and without this it has already PAID for
# those 200. An abort now costs wall-clock and no dollars. It is also what makes
# the two-stage build (#184) affordable at all: pass two re-clusters the whole
# enlarged corpus and re-runs this stage over it, and every pair whose inputs did
# not move has to come back for nothing.
#
# The key NAMES THE SEMANTIC INPUTS rather than leaning on a hash of the
# assembled prompt to carry them: concept, prompt version, model, the two arXiv
# ids, a digest of each paper's definition text, and a digest of the citation
# contexts. The prompt hash is in as well — SYSTEM and USER have changed once
# already (migration 010 added the rationale) and a cache that survives a prompt
# change serves answers to a question nobody asked — but it is not the only thing
# carrying the two papers' content.
#
# The prompt hash also carries the two concept-state labels, which is why #189
# had to land first: Stage C used to reword every label on every run, so this key
# would have missed in exactly the case #184 needs it to hit.
#
# Same shape and the same never-evict posture as `s2_cache` beside it. To buy
# fresh classifications, delete the directory.
CLASS_CACHE_DIR = "edge_class_cache"

EDGE_TYPES = ("extends", "contests", "narrows", "renames", "merges", "migrates")


def classification_key(concept: str, prompt_version: str, model: str,
                       src_arxiv: str, dst_arxiv: str, src_def: str, dst_def: str,
                       contexts: list[str], user_prompt: str) -> str:
    payload = json.dumps({
        "v": 1,
        "concept": concept,
        "prompt_version": prompt_version,
        "model": model,
        "src": src_arxiv,
        "dst": dst_arxiv,
        "src_def": text_digest((src_def or "").encode("utf-8")),
        "dst_def": text_digest((dst_def or "").encode("utf-8")),
        # Order matters and is not sorted away: it is the order the model reads
        # them in, and S2 returns them in citation order.
        "contexts": text_digest("\x00".join(contexts).encode("utf-8")),
        "prompt": text_digest((SYSTEM + "\x00" + user_prompt).encode("utf-8")),
    }, sort_keys=True, ensure_ascii=False)
    return text_digest(payload.encode("utf-8")).split(":", 1)[1]


def _class_cache_file(key: str) -> Path:
    return data_dir() / CLASS_CACHE_DIR / f"{key}.json"


def cached_classification(key: str) -> "EdgeClass | None":
    """The stored classification for this key, or None.

    Anything unreadable, malformed, or outside the six-type taxonomy is a MISS,
    never an error: a cache file is not entitled to put a value in `edges` that
    the column's own CHECK constraint would refuse, and the cost of a miss is one
    classification. Confidence is bounded here for the same reason.
    """
    try:
        rec = json.loads(_class_cache_file(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict):
        return None
    et, conf, why = rec.get("edge_type"), rec.get("confidence"), rec.get("rationale")
    if et not in EDGE_TYPES or not isinstance(conf, (int, float)) or isinstance(conf, bool):
        return None
    if not 0.0 <= float(conf) <= 1.0:
        return None
    return EdgeClass(edge_type=et, confidence=float(conf),
                     rationale=why if isinstance(why, str) else "")


def store_classification(key: str, ec: "EdgeClass", model: str) -> None:
    """Write a bought classification. Never called for a failed one."""
    f = _class_cache_file(key)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"edge_type": ec.edge_type, "confidence": ec.confidence,
                                 "rationale": ec.rationale, "model": model}),
                     encoding="utf-8")
    except OSError as exc:
        # A cache that cannot be written costs money next time and nothing now.
        # The run has its answer and the map is unaffected.
        print(f"    (could not cache classification: {exc})", file=sys.stderr)


def fetch_references(arxiv_id: str) -> list[dict]:
    """References with citation contexts, cached on disk. The shared unauthenticated
    Semantic Scholar pool throttles hard on repeat runs, so cache to survive them."""
    cache = data_dir() / "s2_cache"
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{arxiv_id.replace('/', '_')}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    # Semantic Scholar does not hold every arXiv paper. A 404 means "no citation
    # data for this one", not a broken run: treat it as an empty reference list,
    # cache that, and carry on. Any transport error is likewise per-paper, so one
    # missing id cannot abort edge classification for the whole genealogy.
    try:
        data = get_json(f"{S2}/paper/arXiv:{arxiv_id}/references", {
            "fields": "contexts,intents,isInfluential,title,externalIds", "limit": 1000,
        })
        refs = data.get("data", [])
    except Exception as e:
        print(f"    ⚠ no S2 references for {arxiv_id} ({type(e).__name__}); treating as none")
        refs = []
    f.write_text(json.dumps(refs), encoding="utf-8")
    return refs


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage D: classify genealogy edges.")
    ap.add_argument("concept")
    ap.add_argument("--model", default=env("LLM_MODEL", "claude-sonnet-5"))
    ap.add_argument("--dry-run", action="store_true", help="find candidate edges; classify none")
    args = ap.parse_args()

    prompt_version = env("PROMPT_VERSION", "v1")
    cap = float(env("TRACE_SPEND_CAP_USD", "10"))
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)

    gen = conn.execute("SELECT id, nodes FROM genealogies WHERE concept=%s AND prompt_version=%s",
                       (args.concept, prompt_version)).fetchone()
    if not gen:
        sys.exit(f'No genealogy for "{args.concept}" at prompt {prompt_version}. Run Stage C first.')
    gen_id, nodes = gen

    # arxiv_id -> node_id, and per-paper facts
    node_of = {m["arxiv_id"]: n["node_id"] for n in nodes for m in n["members"]}
    label_of = {n["node_id"]: n["label"] for n in nodes}
    papers = {r[1]: {"paper_id": r[0], "year": r[2], "definition": r[3], "quote": r[4]}
              for r in conn.execute("""
                  SELECT p.id, p.arxiv_id, p.year, d.definition, d.verbatim_quote
                  FROM definitions d JOIN papers p ON p.id=d.paper_id
                  WHERE d.concept=%s AND d.prompt_version=%s AND d.defines_concept=true
              """, (args.concept, prompt_version)).fetchall()}

    # THIS STAGE'S POPULATION IS THE MAP, NOT THE DEFINITIONS TABLE. Stage C can
    # now be scoped to a corpus (#190), so a definition of this concept can exist
    # and sit outside this map; before that, every defining definition was in the
    # map and this intersection was the identity. Without it `node_of[citing]`
    # raises KeyError on the first such paper — reproduced on a four-of-eight
    # corpus before it was written. Stage D deliberately does NOT take --corpus
    # of its own (#190): a second, independent scope is a second thing to keep in
    # agreement, and `nodes` is the one Stage C has just decided.
    corpus_ids = set(papers) & set(node_of)
    outside = len(papers) - len(corpus_ids)
    print(f'Finding citation links among {len(corpus_ids)} defining papers '
          f"across {len(nodes)} concept-states…")
    if outside:
        print(f"  ({outside} paper(s) define this concept but are not in this map, "
              f"so they are not candidates. That is what --corpus on Stage C means.)")

    # candidate edges: citing (newer, descendant) -> cited (older, ancestor), cross-node
    candidates = []
    for citing in corpus_ids:
        for ref in fetch_references(citing):
            ext = (ref.get("citedPaper") or {}).get("externalIds") or {}
            cited = ext.get("ArXiv")
            if cited not in corpus_ids or cited == citing:
                continue
            if node_of[citing] == node_of[cited]:
                continue  # same concept-state — not a genealogy edge
            ctxs = [c for c in (ref.get("contexts") or []) if c.strip()]
            candidates.append({
                "src": cited, "dst": citing,          # src=ancestor, dst=descendant
                "src_node": node_of[cited], "dst_node": node_of[citing],
                "contexts": ctxs[:4], "influential": ref.get("isInfluential"),
                "intents": ref.get("intents"),
            })
        time.sleep(S2_PAUSE_S)

    print(f"  {len(candidates)} cross-node citation link(s) found\n")
    for e in candidates:
        arrow = f"{e['src']} [{label_of[e['src_node']]}]  ->  {e['dst']} [{label_of[e['dst_node']]}]"
        print(f"  {arrow}   ({len(e['contexts'])} context(s), influential={e['influential']})")

    # One place builds the question, so the string that is hashed into the cache
    # key is the same string the model is sent — in the dry run as well as in the
    # loop. Two spellings of it would let an estimate describe a prompt nobody
    # asked.
    def prompt_for(e: dict) -> str:
        ctx_text = ("\n".join(f'- "{c}"' for c in e["contexts"])
                    or "(no context sentence available)")
        return USER.format(concept=args.concept,
                           src_label=label_of[e["src_node"]],
                           src_def=papers[e["src"]]["definition"],
                           dst_label=label_of[e["dst_node"]],
                           dst_def=papers[e["dst"]]["definition"],
                           contexts=ctx_text)

    def key_for(e: dict) -> str:
        return classification_key(args.concept, prompt_version, args.model,
                                  e["src"], e["dst"],
                                  papers[e["src"]]["definition"],
                                  papers[e["dst"]]["definition"],
                                  e["contexts"], prompt_for(e))

    if args.dry_run or not candidates:
        if args.dry_run:
            # What a dry run is for is the money, and since #172 most of a
            # re-run's candidates cost none. An estimate that counted them all as
            # spend would over-state a re-cluster by an order of magnitude, which
            # is the figure #184's pre-flight gate has to decide on.
            free = sum(1 for e in candidates if cached_classification(key_for(e)) is not None)
            print(f"\n[dry-run] no classification performed. Of {len(candidates)} candidate(s), "
                  f"{free} already classified and would cost nothing; "
                  f"{len(candidates) - free} would be bought.")
        else:
            print("\nNo edges to build.")
        return

    # The key is needed before the client is: a run whose candidates are all
    # cached spends nothing and should not be stopped for want of a key it will
    # not use. That is the abandonment fallback in #184, which has to work on the
    # bad day.
    keys = [key_for(e) for e in candidates]
    hits = [cached_classification(k) for k in keys]
    client = None
    if any(h is None for h in hits):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY not set — needed to classify edges.")
        import anthropic
        client = anthropic.Anthropic()
    print(f"\n{sum(h is not None for h in hits)} of {len(candidates)} already classified "
          f"and will cost nothing; {sum(h is None for h in hits)} to buy.")

    # Reconnect before writing. Every read this stage needs is already in memory,
    # and fetching references from Semantic Scholar can take ten minutes or more
    # under rate limiting. Holding the original connection across that gap left a
    # transaction idle and Postgres terminated it (idle-in-transaction timeout),
    # which surfaced here at the first write. A long external phase should never
    # straddle a database connection.
    conn.close()
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)

    # The old edges are NOT deleted yet. This used to clear them here, before a
    # single classification had been attempted, on the reasonable assumption that
    # the run would produce replacements. On 2026-07-31 the account ran out of
    # credit, all 305 classifications returned 400, and the map was left with 27
    # concept-states and no edges at all: the delete had already happened and
    # there was nothing to put back.
    #
    # Deletion now waits for the first successful classification, so a run that
    # cannot classify anything leaves the previous map exactly as it found it.
    # Destroy nothing until you can replace something.
    edges_cleared = False
    spend = 0.0
    written = 0
    # A run where nothing at all classifies is a broken call, not broken
    # data, and this stage has already DELETEd the map's edges by the time
    # it finds out. Stopping early keeps the log short enough to read and
    # says plainly that the edges need rebuilding.
    failures = 0
    reused = bought = 0
    print()
    for e, key, hit in zip(candidates, keys, hits):
        src, dst = papers[e["src"]], papers[e["dst"]]
        ec = hit
        if ec is None:
            user = prompt_for(e)
            # 500 was sized when this response held only {edge_type, confidence}.
            # Migration 010 added the rationale to the same call, and a long one runs
            # the JSON into the ceiling: it truncates mid-string and the parse raises.
            # A single unclassifiable edge must never cost a whole trace (decision 14),
            # so the failure is caught here and that edge skipped.
            try:
                resp = client.messages.parse(model=args.model, max_tokens=1200, system=SYSTEM,
                                             messages=[{"role": "user", "content": user}],
                                             output_format=EdgeClass)
            except Exception as exc:
                # The message, not just the class. A whole run of these printing only
                # "BadRequestError" says an edge failed and nothing about why, and
                # 305 of them in a row is a systematic fault (a bad key, an exhausted
                # balance, a rejected schema) wearing the costume of 305 unlucky
                # edges. Decision 14 says one bad edge must not cost a trace; it does
                # not say the reason should be thrown away.
                failures += 1
                print(f"  {e['src']} -> {e['dst']}: classification failed, skipped "
                      f"({type(exc).__name__}: {str(exc)[:200]})")
                if failures == CONSECUTIVE_FAILURE_LIMIT and written == 0:
                    sys.exit(f"\nAborting: {failures} classifications in a row failed and not one "
                             f"succeeded. This is the call failing, not the edges. The map's "
                             f"existing edges have NOT been touched; fix the cause and re-run.")
                continue
            spend += cost_usd(args.model, resp.usage.input_tokens, resp.usage.output_tokens)
            ec = resp.parsed_output
            if ec is None:
                print(f"  {e['src']} -> {e['dst']}: no classification")
                continue
            # Only ever after a parsed answer. A cache written from a failure
            # would make the failure permanent and free, which is the one thing
            # worse than paying for it again.
            store_classification(key, ec, args.model)
            bought += 1
        else:
            reused += 1

        # Evidence quotes must ground against OUR extracted text (Stage E), so we
        # store each paper's Stage-B definition quote — both already string-verified.
        # The Semantic Scholar citation context is a classification signal only: it
        # comes from S2's PDF extraction and would not match our LaTeX text — so we
        # keep it as the edge's BASIS (what/how), not as a groundable quote. The
        # rationale is the model's one-sentence reading of that basis. Neither may
        # ever wear the verified stamp; the app renders both as unverified context.
        target_quote = dst["quote"]
        citation_context = "\n\n".join(e["contexts"]) or None
        if not edges_cleared:
            # First success: now it is safe to replace what was there.
            conn.execute("DELETE FROM edges WHERE genealogy_id=%s", (gen_id,))
            edges_cleared = True
        conn.execute("""
            INSERT INTO edges (genealogy_id, source_node, target_node, edge_type,
                               source_paper_id, target_paper_id, source_quote,
                               target_quote, confidence, verified, rationale,
                               citation_context)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s,%s)
        """, (gen_id, e["src_node"], e["dst_node"], ec.edge_type,
              src["paper_id"], dst["paper_id"], src["quote"], target_quote, ec.confidence,
              ec.rationale, citation_context))
        conn.commit()
        written += 1
        # `spend` is the run's running total, so a cached edge says where the
        # answer came from BEFORE the number, or the number reads as its price.
        print(f"  {ec.edge_type.upper():<9} {e['src']} -> {e['dst']}  "
              f"conf={ec.confidence:.2f}  "
              f"({'from cache, run ' if hit is not None else ''}spend ${spend:.3f})")
        print(f"            {ec.rationale}")
        if spend > cap:
            print(f"\n⚠ SPEND CAP HIT (${spend:.2f} > ${cap:g}) — stopping.")
            break

    conn.close()
    print(f"\nDone: {written} edges classified ({reused} reused from cache, "
          f"{bought} newly bought). Spend ${spend:.4f}. "
          f"Run Stage E to ground and assemble.")


if __name__ == "__main__":
    main()

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

Usage:
  python pipeline/stage_d_edges.py "attention"
  python pipeline/stage_d_edges.py "attention" --dry-run
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env, get_json, data_dir  # noqa: E402
from stage_b_extract import cost_usd  # noqa: E402

S2 = "https://api.semanticscholar.org/graph/v1"
S2_PAUSE_S = 1.1  # polite spacing on the shared unauthenticated pool
EST_OUTPUT_TOKENS = 200


class EdgeClass(BaseModel):
    edge_type: Literal["extends", "contests", "narrows", "renames", "merges", "migrates"] = Field(
        description="How the newer (descendant) paper's treatment relates to the older one."
    )
    confidence: float = Field(description="0–1 confidence in this classification.")
    rationale: str = Field(description="One sentence justifying the type from the evidence.")


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


def fetch_references(arxiv_id: str) -> list[dict]:
    """References with citation contexts, cached on disk. The shared unauthenticated
    Semantic Scholar pool throttles hard on repeat runs, so cache to survive them."""
    import json
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

    corpus_ids = set(papers)
    print(f'Finding citation links among {len(corpus_ids)} defining papers '
          f"across {len(nodes)} concept-states…")

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

    if args.dry_run or not candidates:
        print("\n[dry-run] no classification performed." if args.dry_run else "\nNo edges to build.")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set — needed to classify edges.")
    import anthropic
    client = anthropic.Anthropic()

    # Reconnect before writing. Every read this stage needs is already in memory,
    # and fetching references from Semantic Scholar can take ten minutes or more
    # under rate limiting. Holding the original connection across that gap left a
    # transaction idle and Postgres terminated it (idle-in-transaction timeout),
    # which surfaced here at the first write. A long external phase should never
    # straddle a database connection.
    conn.close()
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)

    conn.execute("DELETE FROM edges WHERE genealogy_id=%s", (gen_id,))
    spend = 0.0
    written = 0
    print()
    for e in candidates:
        src, dst = papers[e["src"]], papers[e["dst"]]
        ctx_text = "\n".join(f'- "{c}"' for c in e["contexts"]) or "(no context sentence available)"
        user = USER.format(concept=args.concept,
                           src_label=label_of[e["src_node"]], src_def=src["definition"],
                           dst_label=label_of[e["dst_node"]], dst_def=dst["definition"],
                           contexts=ctx_text)
        resp = client.messages.parse(model=args.model, max_tokens=500, system=SYSTEM,
                                     messages=[{"role": "user", "content": user}],
                                     output_format=EdgeClass)
        spend += cost_usd(args.model, resp.usage.input_tokens, resp.usage.output_tokens)
        ec = resp.parsed_output
        if ec is None:
            print(f"  {e['src']} -> {e['dst']}: no classification")
            continue

        # Evidence quotes must ground against OUR extracted text (Stage E), so we
        # store each paper's Stage-B definition quote — both already string-verified.
        # The Semantic Scholar citation context is a classification signal only: it
        # comes from S2's PDF extraction and would not match our LaTeX text — so we
        # keep it as the edge's BASIS (what/how), not as a groundable quote. The
        # rationale is the model's one-sentence reading of that basis. Neither may
        # ever wear the verified stamp; the app renders both as unverified context.
        target_quote = dst["quote"]
        citation_context = "\n\n".join(e["contexts"]) or None
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
        print(f"  {ec.edge_type.upper():<9} {e['src']} -> {e['dst']}  "
              f"conf={ec.confidence:.2f}  (spend ${spend:.3f})")
        print(f"            {ec.rationale}")
        if spend > cap:
            print(f"\n⚠ SPEND CAP HIT (${spend:.2f} > ${cap:g}) — stopping.")
            break

    conn.close()
    print(f"\nDone: {written} edges classified. Spend ${spend:.4f}. "
          f"Run Stage E to ground and assemble.")


if __name__ == "__main__":
    main()

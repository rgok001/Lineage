"""Stage F: per-paper magnitude — which papers shaped the term, and how much.

Two orthogonal scores, written to `definitions.attention` and
`definitions.displacement` (migration 011). They are what the influence map
selects and sizes by, so a map without them has no front door: `/g/[id]` falls
through to the evidence view.

  attention    — on-term weighted uptake. NOT a raw citation count, which rewards
                 famous-but-incidental work (a vision backbone cited by everyone
                 for reasons unrelated to this term). Each corpus-internal
                 citation is scored 0-2 by the model for whether the citing
                 sentence engages the cited paper's contribution *to this term*,
                 then weighted by the citation's S2 intent.
  displacement — how far a paper moved the term's meaning: cosine distance of its
                 definition embedding from the centroid of every earlier
                 definition. Marks turning points, which attention structurally
                 misses, because a paper that moves a term is cited by the field
                 it moved into rather than by this corpus.

Runs after Stage D, which is what populates the S2 citation cache this reads.
The earliest paper has no earlier work, so its displacement is null by nature.

Usage:
  python pipeline/stage_f_magnitude.py "embedding"
  python pipeline/stage_f_magnitude.py "embedding" --prompt-version v2 --model claude-haiku-4-5
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, env  # noqa: E402
from stage_b_extract import cost_usd, pricing_key  # noqa: E402

# A dated snapshot, pinned so that a rebuild months later scores citations with
# the weights this map was built from. Until #205 it was also not a key in
# PRICING, and the costing function defaulted an unknown model to Opus rates
# rather than saying so, which made every figure this stage printed 5x what its
# Haiku calls cost. Pricing now resolves the date suffix; the pin stays.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
BATCH = 12  # citations per call; keeps a 300-citation corpus to ~25 calls

# S2 labels why one paper cites another. A methodology citation is the field
# building on the work; a background citation is often a courtesy.
INTENT_WEIGHT = {"methodology": 1.0, "result": 0.6, "background": 0.2}
DEFAULT_INTENT_WEIGHT = 0.3


def build_system_prompt(concept: str) -> str:
    return (
        "For each item you are given the title of a CITED paper and a SENTENCE from a "
        "later paper that cites it. Score 0-2 how much the sentence engages the cited "
        f'paper\'s contribution to the concept of "{concept}":\n'
        f"2 = builds on or engages its {concept} idea directly\n"
        "1 = related but peripheral mention\n"
        "0 = incidental: cites it as a backbone, dataset, tool, or generic prior work\n"
        "Return exactly one integer per item, in order."
    )


def collect_citations(corpus: set[str]) -> list[dict]:
    """Corpus-internal citations from the Stage D cache. A citation only counts
    when both ends are in this corpus: uptake by unrelated fields is not uptake
    of this term."""
    cache = data_dir() / "s2_cache"
    if not cache.is_dir():
        return []
    cites = []
    for f in cache.glob("*.json"):
        citing = f.stem.replace("_", "/")
        if citing not in corpus:
            continue
        try:
            refs = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # a corrupt cache entry is not worth failing a stage over
        for ref in refs:
            ext = (ref.get("citedPaper") or {}).get("externalIds") or {}
            cited = ext.get("ArXiv")
            if cited not in corpus or cited == citing:
                continue
            ctx = " ".join(s for s in (ref.get("contexts") or []) if s.strip())[:600]
            iw = max([INTENT_WEIGHT.get(i, DEFAULT_INTENT_WEIGHT)
                      for i in (ref.get("intents") or [])], default=DEFAULT_INTENT_WEIGHT)
            cites.append({"cited": cited, "ctx": ctx, "iw": iw})
    return cites


def main() -> None:
    ap = argparse.ArgumentParser(description="Score per-paper magnitude for a traced concept.")
    ap.add_argument("concept")
    ap.add_argument("--prompt-version", default=env("PROMPT_VERSION", "v1"))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()
    concept, pv = args.concept, args.prompt_version

    # Refuse an unpriced model here, before the first batch (#205). It cannot be
    # left to the loop below: `cost_usd` is called inside the batch's own
    # `try`, so an unpriced model would be swallowed as "batch failed, scored
    # neutral" — a pricing defect wearing a scoring failure's clothes, and after
    # three of them the stage aborts blaming the model's answers.
    pricing_key(args.model)

    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    rows = conn.execute("""
        SELECT p.arxiv_id, p.title, p.year, d.embedding::text
        FROM definitions d JOIN papers p ON p.id = d.paper_id
        WHERE d.concept = %s AND d.prompt_version = %s AND d.defines_concept = true
    """, (concept, pv)).fetchall()
    if not rows:
        sys.exit(f'No definitions for "{concept}" at prompt {pv}. Run Stage B first.')

    title = {r[0]: r[1] for r in rows}
    year = {r[0]: r[2] for r in rows}
    vec = {r[0]: np.array([float(x) for x in r[3].strip()[1:-1].split(",")])
           for r in rows if r[3]}
    corpus = set(title)
    print(f"{len(corpus)} papers define \"{concept}\"; {len(vec)} carry an embedding.")

    # ── attention ────────────────────────────────────────────────────────────
    cites = collect_citations(corpus)
    print(f"{len(cites)} corpus-internal citations to score.")

    import anthropic  # imported late: displacement alone needs no API key
    client = anthropic.Anthropic()
    system = build_system_prompt(concept)

    from pydantic import BaseModel

    class Scores(BaseModel):
        scores: list[int]

    spend = 0.0
    total_batches = (len(cites) + BATCH - 1) // BATCH
    failed_batches = 0
    for bi, start in enumerate(range(0, len(cites), BATCH), start=1):
        batch = cites[start:start + BATCH]
        lines = [f'{j}. CITED: "{title[it["cited"]][:80]}"\n   SENTENCE: {it["ctx"] or "(no sentence)"}'
                 for j, it in enumerate(batch, 1)]
        user = ("Score these citations (0-2 each), one integer per item in order:\n\n"
                + "\n\n".join(lines))
        try:
            r = client.messages.parse(model=args.model, max_tokens=600, system=system,
                                      messages=[{"role": "user", "content": user}],
                                      output_format=Scores)
            spend += cost_usd(args.model, r.usage.input_tokens, r.usage.output_tokens)
            sc = r.parsed_output.scores if r.parsed_output else []
        except Exception as exc:
            # A batch that will not score is a batch of neutral citations, not a
            # reason to abandon the run (decision 14). That holds for ONE batch.
            # When every batch fails the call is broken, and scoring every citation
            # neutral writes a uniform, plausible-looking number over the real
            # ranking: on 2026-07-31 an exhausted credit balance did exactly that
            # to 533 citations, and what got persisted looked like data rather than
            # like the absence of it.
            failed_batches += 1
            print(f"  batch {bi} failed, scored neutral "
                  f"({type(exc).__name__}: {str(exc)[:160]})")
            if failed_batches == bi and bi >= 3:
                sys.exit(f"\nAborting: all {bi} batches failed and nothing has been "
                         f"persisted, so the existing scores stand. Neutral for "
                         f"everything is not a measurement.")
            sc = []
        if len(sc) != len(batch):
            sc = (sc + [1] * len(batch))[:len(batch)]
        for it, s in zip(batch, sc):
            it["score"] = max(0, min(2, s))
        print(f"  [{bi}/{total_batches}] scored {min(start + BATCH, len(cites))}/{len(cites)} "
              f"citations  spend ${spend:.4f}", flush=True)

    # Every paper gets a number, including zero: the influence map selects on
    # `attention IS NOT NULL`, so a silent null would drop a paper off the map
    # rather than rank it last.
    attention = {a: 0.0 for a in corpus}
    for it in cites:
        attention[it["cited"]] += it["iw"] * (it.get("score", 1) / 2.0)

    # ── displacement ─────────────────────────────────────────────────────────
    displacement: dict[str, float | None] = {}
    for a in vec:
        earlier = [vec[b] for b in vec if year.get(b) is not None
                   and year.get(a) is not None and year[b] < year[a]]
        if not earlier:
            displacement[a] = None  # nothing to be displaced from
            continue
        cen = np.mean(earlier, axis=0)
        displacement[a] = 1.0 - float(
            np.dot(vec[a], cen) / (np.linalg.norm(vec[a]) * np.linalg.norm(cen)))

    # ── persist ──────────────────────────────────────────────────────────────
    for i, a in enumerate(sorted(corpus), start=1):
        conn.execute("""
            UPDATE definitions SET attention = %s, displacement = %s
            WHERE paper_id = (SELECT id FROM papers WHERE arxiv_id = %s)
              AND concept = %s AND prompt_version = %s
        """, (attention.get(a), displacement.get(a), a, concept, pv))
        if i % 25 == 0 or i == len(corpus):
            print(f"  [{i}/{len(corpus)}] persisted", flush=True)

    chk = conn.execute("""
        SELECT count(*), count(attention), count(displacement) FROM definitions
        WHERE concept = %s AND prompt_version = %s AND defines_concept = true
    """, (concept, pv)).fetchone()
    print(f"\n{chk[0]} papers | with attention: {chk[1]} | with displacement: {chk[2]}")
    print(f"spend ${spend:.4f}")

    top = conn.execute("""
        SELECT p.title, d.attention, d.displacement
        FROM definitions d JOIN papers p ON p.id = d.paper_id
        WHERE d.concept = %s AND d.prompt_version = %s AND d.defines_concept = true
        ORDER BY d.attention DESC NULLS LAST LIMIT 6
    """, (concept, pv)).fetchall()
    print("top by on-term uptake:")
    for t, at, ds in top:
        print(f"  att={at or 0:.2f} disp={ds if ds is None else round(ds, 3)}  {t[:52]}")
    conn.close()


if __name__ == "__main__":
    main()

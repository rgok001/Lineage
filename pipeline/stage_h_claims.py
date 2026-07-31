"""Stage H: claim-level evidence — a quote per sentence, not per paragraph.

Stage G writes an account: for each paper, what it did and a paragraph about it.
That paragraph is the model's prose, and the only thing under it carrying a
verified stamp is the paper's definition quote, which supports one of the
paragraph's assertions and not the others. The layout then lends the stamp's
authority to the rest. Nothing false is stored; the page implies more than it
demonstrates.

This asks a different question of each paper. Not "summarise it" but "state what
this paper contributed to the term, and for each statement give me the passage
that shows it". Each returned passage is then checked against our own extracted
text by the same comparison Stage E uses. A claim whose quote does not check out
keeps the claim and loses the stamp: it is the tool's reading, labelled, rather
than a deletion, because dropping it would quietly narrow the account.

Separate from Stage G on purpose. Thread membership is generated and
non-deterministic, so re-running G to change the prose reshuffles which papers
belong where. This reads the threads that exist and writes claims into them, so
evidence can be regenerated without disturbing a curated shape.

Usage:
  python pipeline/stage_h_claims.py "attention"
  python pipeline/stage_h_claims.py "attention" --thread s0     # one thread, to try it
"""

import argparse
import json
import sys
from pathlib import Path

import psycopg
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, env, quote_is_grounded  # noqa: E402
from stage_b_extract import cost_usd  # noqa: E402

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
# Enough of a paper to cover its contribution without paying for its appendices.
TEXT_BUDGET = 24_000


class Claim(BaseModel):
    text: str = Field(description="One sentence stating what this paper did for the concept.")
    quote: str = Field(description="A passage copied EXACTLY from the paper that shows it.")


class Claims(BaseModel):
    claims: list[Claim]


SYSTEM = (
    "You are given one paper's extracted text and a concept. State 2 to 4 things this paper "
    "did FOR THAT CONCEPT, each as one plain sentence. For every statement, copy the passage "
    "from the text that shows it, EXACTLY as it appears, character for character. Do not "
    "paraphrase a passage, do not join two distant sentences, do not tidy the punctuation, and "
    "do not invent one: if no passage in the text shows a statement, return an empty quote for "
    "it rather than an approximation. A passage of one or two sentences is ideal. Return only "
    "the statements the text supports; fewer good ones beat more weak ones."
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Attach a checked quote to each claim in an account.")
    ap.add_argument("concept")
    ap.add_argument("--prompt-version", default=env("PROMPT_VERSION", "v1"))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--thread", help="only this thread id, e.g. s0")
    ap.add_argument("--recheck", action="store_true",
                    help="re-ground the claim quotes already stored, without asking "
                         "the model for new ones. For when the extracted text changed "
                         "underneath them: the stamps were computed against the old "
                         "text and a stamp must never outlive the check that made it. "
                         "Costs nothing")
    args = ap.parse_args()

    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    row = conn.execute("SELECT id, streams FROM genealogies WHERE concept=%s AND prompt_version=%s",
                       (args.concept, args.prompt_version)).fetchone()
    if not row or not row[1]:
        sys.exit(f'No threads for "{args.concept}" at prompt {args.prompt_version}. Run Stage G first.')
    gen_id, river = row

    paths = {r[0]: r[1] for r in conn.execute("SELECT arxiv_id, extracted_text_path FROM papers").fetchall()}
    dd = data_dir()

    client = None
    if not args.recheck:
        import anthropic
        client = anthropic.Anthropic()
    spend = 0.0
    done = kept = unverified = skipped = 0
    targets = [s for s in river["streams"] if not args.thread or s["id"] == args.thread]
    if not targets:
        sys.exit(f'No thread "{args.thread}" on this map.')
    total = sum(len(s["papers"]) for s in targets)

    for s in targets:
        for p in s["papers"]:
            done += 1
            path = paths.get(p["arxiv"])
            text = (dd / path).read_text(encoding="utf-8", errors="replace") if path and (dd / path).exists() else ""
            if not text:
                skipped += 1
                continue
            if args.recheck:
                # Re-ground what is already stored. A claim that stops checking out
                # keeps its text and loses its stamp and its quote, exactly as it
                # would have on first generation: the prose is an honest reading
                # either way, and only the passage was ever the claim to evidence.
                claims = []
                for cl in p.get("claims") or []:
                    q = (cl.get("quote") or "").strip()
                    ok = bool(q) and quote_is_grounded(text, q)
                    claims.append({"text": cl.get("text", ""), "quote": q if ok else None,
                                   "verified": ok})
                    kept += 1
                    unverified += (not ok)
                was = sum(1 for cl in (p.get("claims") or []) if cl.get("verified"))
                now = sum(1 for cl in claims if cl["verified"])
                p["claims"] = claims
                if claims:
                    moved = "" if now == was else f"  (was {was})"
                    print(f"  [{done}/{total}] {p['arxiv']}: {now}/{len(claims)} still check "
                          f"out{moved}", flush=True)
                continue

            user = (f'CONCEPT: {args.concept}\nPAPER: {p.get("title","")} ({p.get("year","")})\n\n'
                    f"TEXT:\n{text[:TEXT_BUDGET]}")
            try:
                r = client.messages.parse(model=args.model, max_tokens=1500, system=SYSTEM,
                                          messages=[{"role": "user", "content": user}],
                                          output_format=Claims)
                spend += cost_usd(args.model, r.usage.input_tokens, r.usage.output_tokens)
                got = r.parsed_output.claims if r.parsed_output else []
            except Exception as exc:
                print(f"  [{done}/{total}] {p['arxiv']}: failed, skipped ({type(exc).__name__})")
                skipped += 1
                continue

            # The model was asked to copy. Incident 8 is what happens when that is
            # taken on trust, so every passage is checked against our own text and
            # only the ones that check out are allowed to carry the stamp.
            claims = []
            for cl in got:
                q = (cl.quote or "").strip()
                ok = bool(q) and quote_is_grounded(text, q)
                claims.append({"text": cl.text.strip(), "quote": q if ok else None, "verified": ok})
                kept += 1
                unverified += (not ok)
            p["claims"] = claims
            v = sum(1 for cl in claims if cl["verified"])
            print(f"  [{done}/{total}] {p['arxiv']}: {v}/{len(claims)} claims carry a checked quote "
                  f"(spend ${spend:.3f})", flush=True)

    conn.execute("UPDATE genealogies SET streams=%s, updated_at=now() WHERE id=%s",
                 (json.dumps(river), gen_id))
    pct = 100 * (kept - unverified) / kept if kept else 0
    print(f"\n{kept} claims across {done - skipped} papers | {kept - unverified} carry a checked "
          f"quote ({pct:.0f}%) | {skipped} papers skipped for want of text")
    print(f"spend ${spend:.4f}")
    conn.close()


if __name__ == "__main__":
    main()

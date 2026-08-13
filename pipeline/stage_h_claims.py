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

The model call is CACHED ON DISK (issue #202), keyed by the semantic inputs of
the question. The stamps are not: they are recomputed at load against the text on
disk now, because a stamp must never outlive the check that made it. Each stamp
records `checked_against`, the digest of the exact bytes its check read (#215),
so the thread page can resolve it through the same three-state rule every other
stamp already answers to — a stamp whose digest no longer matches the paper's,
or that has none, renders stale rather than wearing a verdict no check backs.

Usage:
  python pipeline/stage_h_claims.py "attention"
  python pipeline/stage_h_claims.py "attention" --thread s0     # one thread, to try it
"""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    build_row, current_row, data_dir, env, quote_is_grounded, read_grounding_text,
    text_digest, unpublished_table, unpublished_versions, version_note)
from stage_b_extract import cost_usd, pricing_key  # noqa: E402

# Sonnet, not Haiku, and this one was measured rather than assumed. On thread
# s0 of attention, six papers and the same prompt: Haiku got 16 of 22 passages
# to check out, Sonnet got 22 of 22. One paper (2111.07624) went from 0 of 4
# to 4 of 4, so its whole account had rested on prose with nothing under it.
# The failure is the model paraphrasing when told to copy, which is precisely
# what the grounding check exists to catch, and the check was catching it all
# along. ~3.7c a paper against ~1.2c: about $2 more per map, for the
# difference between 78% and 100% of claims carrying evidence, on a product
# whose whole premise is that a claim carries evidence.
DEFAULT_MODEL = "claude-sonnet-5"
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


def user_prompt(concept: str, title: str, year, sent_text: str) -> str:
    """The question, built in one place so the string hashed into the cache key is
    the string the model is sent. Two spellings of it would let a key describe a
    prompt nobody asked."""
    return (f'CONCEPT: {concept}\nPAPER: {title} ({year})\n\nTEXT:\n{sent_text}')


# ── the claims cache ────────────────────────────────────────────────────────
#
# Issue #202. This call depends on the paper and on nothing else: not on the
# map's shape, not on `genealogies.streams`, not on which thread a paper landed
# in. So a rebuild re-asked every paper a question it had already paid for — at
# ~3.7c a paper, about $3.00 a map, 25% of what a map costs. Worse than the
# money: decision 38 caps auto-requeues at three on the argument that "restarts
# are cheap, since every LLM stage caches per paper", and that premise was false
# here. Incident 15 is two deploys four minutes apart, and each one re-bought
# this whole stage. Decision 39 records the correction.
#
# Same shape, same key discipline and the same never-evict posture as
# `edge_class_cache` (#172) and `label_cache` (#189) beside it. To buy fresh
# claims, delete the directory.
#
# The key NAMES THE SEMANTIC INPUTS rather than leaning on a hash of the
# assembled prompt to carry them: concept, prompt version, model, the arXiv id,
# and a digest of the exact text sent — the post-TEXT_BUDGET slice, not the whole
# file, because the tail of a paper the model never saw cannot have moved its
# answer. The prompt hash is in as well, for #172's reason: `SYSTEM` can change
# and a cache that survives a prompt change serves answers to a question nobody
# asked.
#
# WHAT IS NOT IN THE CACHE IS THE STAMP. Only the claim text and the passage the
# model returned are stored, exactly as returned; `verified` is recomputed at
# load by grounding that passage against the extracted text as it is on disk now.
# Decision 30 and issue #57: a stamp must never outlive the check that made it,
# and a restored stamp would assert a check that ran against a document since
# re-extracted. This is what keeps the cache clear of rule 2 — nothing on disk
# here can put a stamp on anything.
CLAIMS_CACHE_DIR = "claims_cache"


def claims_key(concept: str, prompt_version: str, model: str, arxiv_id: str,
               sent_text: str, prompt: str) -> str:
    payload = json.dumps({
        "v": 1,
        "concept": concept,
        "prompt_version": prompt_version,
        "model": model,
        "arxiv": arxiv_id,
        "text": text_digest(sent_text.encode("utf-8")),
        "prompt": text_digest((SYSTEM + "\x00" + prompt).encode("utf-8")),
    }, sort_keys=True, ensure_ascii=False)
    return text_digest(payload.encode("utf-8")).split(":", 1)[1]


def _claims_cache_file(key: str) -> Path:
    return data_dir() / CLAIMS_CACHE_DIR / f"{key}.json"


def cached_claims(key: str, model: str) -> "tuple[list[dict], float] | None":
    """The stored answer for this key and what it cost when it was bought, or None.

    Anything unreadable, malformed, or not a list of `{text, quote}` strings is a
    MISS, never an error: a file on disk is not entitled to put a value into
    `genealogies.streams` that generation would not have produced, and the cost of
    a miss is one call. An empty claim list IS a valid answer and hits — the model
    is told that fewer good statements beat more weak ones — but only a *parsed*
    empty list is ever written, so this cannot be a parse failure wearing an
    answer's clothes.

    The price is read back rather than modelled: the record carries the tokens the
    call actually used, and the model is in the key, so the figure the hit avoids
    is the figure that was paid. A record with no usage in it contributes nothing,
    which makes the reported saving a lower bound and never an invention.
    """
    try:
        rec = json.loads(_claims_cache_file(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or not isinstance(rec.get("claims"), list):
        return None
    out = []
    for cl in rec["claims"]:
        if not isinstance(cl, dict):
            return None
        t, q = cl.get("text"), cl.get("quote")
        if not isinstance(t, str) or not isinstance(q, str):
            return None
        out.append({"text": t, "quote": q})
    ti, to = rec.get("input_tokens"), rec.get("output_tokens")
    priced = 0.0
    if isinstance(ti, int) and isinstance(to, int) and not isinstance(ti, bool):
        priced = cost_usd(model, ti, to)
    return out, priced


def store_claims(key: str, claims: list[dict], concept: str, model: str,
                 input_tokens: int, output_tokens: int) -> None:
    """Write a bought answer. Never called for a failed or unparsed one — caching a
    failure would make the failure permanent and free."""
    f = _claims_cache_file(key)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"claims": claims, "concept": concept, "model": model,
                                 "input_tokens": input_tokens,
                                 "output_tokens": output_tokens}), encoding="utf-8")
    except OSError as exc:
        # A cache that cannot be written costs money next time and nothing now:
        # the run has the answer it paid for and the map is unaffected.
        print(f"    (could not cache claims: {exc})", file=sys.stderr)


def ground(text: str, digest: str, raw: list[dict]) -> list[dict]:
    """Turn what the model returned into what gets stored, checking every passage.

    One grounding path for a freshly bought answer and a cached one, deliberately:
    a claim that came out of the cache must be indistinguishable from one bought a
    second earlier, and two spellings of this would eventually disagree about a
    stamp. Incident 8 is what happens when "the model was asked to copy" is taken
    on trust. A claim whose passage fails keeps its text and loses its stamp and
    its quote, which is what narrows the account honestly rather than in silence.

    `checked_against` is the digest of the exact bytes this check ran against
    (#215, decision 30's rule extended to the third stamp population). It is
    computed by `read_grounding_text` at the moment the text is read, in the same
    act as the check, and NEVER copied from `papers.extracted_text_digest` — the
    two are written by different code at different moments, which is what lets
    the app's `stampOf` comparison return false and render a stamp stale once
    the extraction of record moves. Every stamp carries it, failed checks too:
    "the check ran against these bytes and could not find it" is exactly what
    inferred means, and it is only claimable while the bytes are named.
    """
    out = []
    for cl in raw:
        q = (cl.get("quote") or "").strip()
        ok = bool(q) and quote_is_grounded(text, q)
        out.append({"text": (cl.get("text") or "").strip(),
                    "quote": q if ok else None, "verified": ok,
                    "checked_against": digest})
    return out


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
    ap.add_argument("--genealogy-id", type=int, metavar="ID",
                    help="act on this exact version of the map instead of the "
                         "one the build in flight owns")
    args = ap.parse_args()

    # Refuse an unpriced --model before anything is read or bought (#205). It
    # matters on the free path too: `cached_claims` prices a stored call to report
    # what the hit avoided, so even a fully cached run needs rates it can stand by.
    pricing_key(args.model)

    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    # Two questions, and `--recheck` asks the other one (#207b). Buying accounts
    # belongs to the build in flight, which owns the newest unpublished version
    # and whose threads Stage G has just written. `--recheck` re-grounds stamps
    # that are already stored and costs nothing: it is the repair an operator
    # runs on the LIVE map after its papers were re-extracted (the procedure in
    # RUNBOOK section 8 for #215), and resolving the build's row there would
    # refuse the one map the procedure is about.
    resolve = current_row if args.recheck else build_row
    # **A row resolved by rule may not be bought for while the concept has a live
    # map** (#242, the same rule and the same shape as Stage E's #241 refusal).
    # `build_row` reads `status <> 'complete' ORDER BY version DESC`, and nothing
    # ever clears `running`, so the row it finds is a build in flight or the
    # residue of one that died and this stage cannot tell them apart. That matters
    # more here than almost anywhere: this is the most expensive stage in the
    # pipeline, roughly doubling what a map costs, and the RUNBOOK's own #215
    # procedure prints `python pipeline/stage_h_claims.py "attention"` for an
    # operator to type on the Render shell, where the API key is set. Measured, on
    # a database with a corpse: "0 of 1 paper(s) already have claims and will cost
    # nothing; 1 to buy", aimed at a row nobody can see. `--recheck` (the live map,
    # free) and `--genealogy-id` (a named version) are the two ways through, and
    # they are the two the refusal prints.
    if not args.recheck and args.genealogy_id is None:
        live = current_row(conn, args.concept, args.prompt_version, "id, version")
        if live:
            lines = [
                "",
                f'Refusing to buy accounts for a version of "{args.concept}" this run '
                f"resolved by rule: the concept's live map is",
                f"  v{live[1]} (genealogy {live[0]}), and a row that is not `complete` "
                f"is a build in flight OR the residue of one",
                "  that died — nothing ever clears `running`, and from here those are "
                "the same row. This is the most",
                "  expensive stage in the pipeline; nothing was read, nothing was "
                "bought and nothing was written.",
                f"  {version_note(conn, args.concept, args.prompt_version)}",
                "",
                "  Versions this concept has that are not published:",
                "",
            ]
            lines += unpublished_table(
                unpublished_versions(conn, args.concept, args.prompt_version))
            lines += [
                "",
                "  Say which one you mean:",
                f'    python pipeline/stage_h_claims.py "{args.concept}" '
                f"--genealogy-id <genealogy>",
                "        buys the accounts for that version.",
                f'    python pipeline/stage_h_claims.py "{args.concept}" --recheck',
                "        re-grounds the claim quotes already stored on the LIVE map, "
                "for nothing.",
            ]
            sys.exit("\n".join(lines))
    row = resolve(conn, args.concept, args.prompt_version, "id, streams",
                  genealogy_id=args.genealogy_id)
    if not row or not row[1]:
        which = "the live map" if args.recheck else "an unpublished version"
        sys.exit(f'No threads on {which} of "{args.concept}" at prompt '
                 f"{args.prompt_version}. Run Stage G first, or name a version with "
                 f"--genealogy-id.\n"
                 f"  {version_note(conn, args.concept, args.prompt_version)}")
    gen_id, river = row

    paths = {r[0]: r[1] for r in conn.execute("SELECT arxiv_id, extracted_text_path FROM papers").fetchall()}
    dd = data_dir()

    spend = avoided = 0.0
    done = kept = unverified = skipped = reused = bought = 0
    targets = [s for s in river["streams"] if not args.thread or s["id"] == args.thread]
    if not targets:
        sys.exit(f'No thread "{args.thread}" on this map.')
    total = sum(len(s["papers"]) for s in targets)

    # Every paper's extracted text is read once, up front. The cache lookup needs
    # it (its digest is half the key), the grounding check needs it either way,
    # and knowing before the loop starts how much of this run is already paid for
    # is what lets the client be built only when something has to be bought.
    # The read goes through `read_grounding_text` like every other stage that
    # grounds anything (#215): the digest it returns is the one the stamps below
    # record as `checked_against`. A file that is missing or undecodable is
    # "could not check", never "not found" (decision 21) — the paper is skipped
    # and its stored stamps are left exactly as they are, because a stamp is a
    # by-product of a check and no check ran here. The render path says the
    # truth about such a stamp: with no digest to compare, it is stale.
    work = []
    for s in targets:
        for p in s["papers"]:
            path = paths.get(p["arxiv"])
            text = digest = ""
            if path:
                try:
                    text, digest = read_grounding_text(path)
                except (OSError, ValueError):
                    pass
            work.append((p, text, digest))

    client = None
    keys: list[str | None] = [None] * len(work)
    hits: list[tuple[list[dict], float] | None] = [None] * len(work)
    if not args.recheck:
        for i, (p, text, _digest) in enumerate(work):
            if not text:
                continue
            keys[i] = claims_key(args.concept, args.prompt_version, args.model, p["arxiv"],
                                 text[:TEXT_BUDGET],
                                 user_prompt(args.concept, p.get("title", ""), p.get("year", ""),
                                             text[:TEXT_BUDGET]))
            hits[i] = cached_claims(keys[i], args.model)
        readable = sum(1 for _, t, _d in work if t)
        free = sum(1 for h in hits if h is not None)
        print(f"{free} of {readable} paper(s) already have claims and will cost nothing; "
              f"{readable - free} to buy.")
        # A rebuild whose papers are all cached must not be stopped for want of a
        # key it will never use — that is exactly the run this ticket exists to
        # make free — and a run that IS going to buy should say so before it has
        # half a map's claims in memory and nowhere to write them.
        if readable - free:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                sys.exit("ANTHROPIC_API_KEY not set — needed to write claims.")
            import anthropic
            client = anthropic.Anthropic()

    no_text: list[str] = []
    for i, (p, text, digest) in enumerate(work):
        done += 1
        if not text:
            skipped += 1
            no_text.append(p["arxiv"])
            continue
        if args.recheck:
            # Re-ground what is already stored, and KEEP the passage either way.
            # Generation nulls a passage that fails, which is right there: a
            # paraphrase the model invented has no provenance value. Here it is
            # wrong. A passage that checked out once and stops may have stopped
            # because OUR text changed, and destroying it makes that
            # unrecoverable without paying to regenerate. The stamp is what must
            # follow the check; the evidence of what was returned is not ours to
            # throw away. The thread page renders a claim's quote only under a
            # resolved verified or stale stamp, labelled as such — never as
            # verified while unproven (#215). `checked_against` is rewritten
            # here for the same reason the stamp is: this is the other spelling
            # of the grounding, and a digest that only one path wrote would let
            # the two drift.
            claims = []
            for cl in p.get("claims") or []:
                q = (cl.get("quote") or "").strip()
                ok = bool(q) and quote_is_grounded(text, q)
                claims.append({"text": cl.get("text", ""), "quote": q or None,
                               "verified": ok, "checked_against": digest})
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

        got = hits[i]
        if got is None:
            user = user_prompt(args.concept, p.get("title", ""), p.get("year", ""),
                               text[:TEXT_BUDGET])
            try:
                r = client.messages.parse(model=args.model, max_tokens=1500, system=SYSTEM,
                                          messages=[{"role": "user", "content": user}],
                                          output_format=Claims)
                spend += cost_usd(args.model, r.usage.input_tokens, r.usage.output_tokens)
            except Exception as exc:
                # The message, not just the class: a whole run of these printing
                # only "BadRequestError" says a paper failed and nothing about why.
                print(f"  [{done}/{total}] {p['arxiv']}: failed, skipped "
                      f"({type(exc).__name__}: {str(exc)[:200]})")
                skipped += 1
                continue
            raw = [{"text": (c.text or "").strip(), "quote": (c.quote or "").strip()}
                   for c in (r.parsed_output.claims if r.parsed_output else [])]
            if r.parsed_output is not None:
                # Only ever after a parsed answer. An unparsed response still
                # produces an empty account for this paper, as it always has, but
                # it must not become a permanent free one.
                store_claims(keys[i], raw, args.concept, args.model,
                             r.usage.input_tokens, r.usage.output_tokens)
            bought += 1
        else:
            raw, priced = got
            avoided += priced
            reused += 1

        # The model was asked to copy. Incident 8 is what happens when that is
        # taken on trust, so every passage is checked against our own text — the
        # text as it is on disk NOW, whether the answer was bought a second ago or
        # a month ago — and only the ones that check out carry the stamp.
        claims = ground(text, digest, raw)
        kept += len(claims)
        unverified += sum(1 for cl in claims if not cl["verified"])
        p["claims"] = claims
        v = sum(1 for cl in claims if cl["verified"])
        # A cached paper says where the answer came from BEFORE the number, or the
        # running total reads as its price.
        src = "from cache, run " if got is not None else ""
        print(f"  [{done}/{total}] {p['arxiv']}: {v}/{len(claims)} claims carry a checked quote "
              f"({src}spend ${spend:.3f})", flush=True)

    conn.execute("UPDATE genealogies SET streams=%s, updated_at=now() WHERE id=%s",
                 (json.dumps(river), gen_id))
    pct = 100 * (kept - unverified) / kept if kept else 0
    print(f"\n{kept} claims across {done - skipped} papers | {kept - unverified} carry a checked "
          f"quote ({pct:.0f}%) | {skipped} papers skipped for want of text")
    if no_text:
        # Named, not just counted (#215): these papers' stored stamps met no
        # check this run, so their claims render stale until a run can read
        # their text. An operator deciding whether to re-fetch needs the ids.
        print("no text to check, claims left as stored (they render stale): "
              + ", ".join(no_text))
    if not args.recheck:
        # A cache whose hit rate nobody can read is a cache nobody can tell has
        # broken. The avoided figure is what those calls actually billed when they
        # were bought, read back out of the records, not a model of what they
        # would cost. It deliberately does not use the word the worker's spend
        # regex looks for: this stage's spend is the line below, and only that one.
        print(f"claims for {reused} paper(s) came from cache and cost nothing "
              f"(avoided ${avoided:.4f}); {bought} bought")
    print(f"spend ${spend:.4f}")
    conn.close()


if __name__ == "__main__":
    main()

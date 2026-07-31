"""Stage B: per-paper definition extraction via the Anthropic API.

For each fetched+extracted paper, ask Claude how *that paper* defines the
concept, and get back structured JSON: {defines_concept, definition,
verbatim_quote, section, novelty_claims}.

Three things make this the pipeline's semantic gate and cost centre:

- `defines_concept` is the filter Stage A deliberately defers to. Stage A
  optimises recall, so generically-cited papers (Adam, scikit-learn) ride along;
  asked how they define the concept, they answer "they don't", produce no
  definition, and fall out here.
- Every extraction carries a verbatim quote, string-verified against the
  extracted text on arrival (`quote_verified`). A paraphrase is flagged at the
  moment it is created, not at display time. `--reground` re-answers that same
  question later, for nothing, when the text has moved underneath the stamp.
- This is where money is spent. --dry-run estimates cost without calling the
  model; a hard spend cap aborts the run cleanly.

Cached per paper: UNIQUE(paper_id, concept, prompt_version) means an extraction
is computed once and reused across traces. Bump PROMPT_VERSION to invalidate.

Usage:
  python pipeline/stage_b_extract.py "attention" --dry-run
  python pipeline/stage_b_extract.py "attention" --limit 5
  python pipeline/stage_b_extract.py "attention" --model claude-haiku-4-5
  python pipeline/stage_b_extract.py "attention" --reground --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

import psycopg
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import quote_is_grounded, REPO_ROOT, data_dir, env  # noqa: E402

DEFAULT_MODEL = "claude-opus-4-8"

# USD per million tokens (input, output). Keep in sync with docs.claude.com/pricing.
PRICING = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Definitions usually live in the abstract/intro/method. Truncating trades a
# small recall risk for a large cost saving; raise it if extractions come back
# empty for papers that clearly do discuss the concept.
DEFAULT_MAX_CHARS = 40_000
EST_OUTPUT_TOKENS = 350  # structured JSON only; raise if --thinking is on
TITLE_MATCH_MIN = 0.5  # never send a paper whose text/metadata disagree

SYSTEM = """You extract how a specific paper defines or uses a concept, for a \
concept-genealogy tool that traces how ideas evolve across papers.

Rules you must follow exactly:
- Judge only what THIS paper says. Do not use outside knowledge of the concept.
- A paper may use the concept under a different name than the one asked about \
(ideas are often renamed years later). Judge by meaning, not vocabulary.
- If the paper does not meaningfully define or use the concept, set \
defines_concept to false and leave the other fields empty. Many papers are \
cited for unrelated reasons; saying "no" is the correct, expected answer.
- verbatim_quote MUST be copied character-for-character from the paper text \
given to you. Never paraphrase, correct, shorten with ellipses, or reconstruct \
it. It is checked by exact string match and a mismatch is treated as a failure."""

USER = """Concept: "{concept}"{sense}

Below is the extracted text of a paper. How does THIS paper define or use the \
concept above?

<paper>
{text}
</paper>"""

# Injected only when the request carries a gloss. Makes the yes/no question
# sense-specific, so a polysemous word (OS "kernel" vs ML "kernel") is judged
# against the intended meaning rather than the bare token.
SENSE = """
Intended sense: {gloss}
Judge the concept in THIS sense only. A different, unrelated sense of the same \
word does not count as defining the concept."""


class Extraction(BaseModel):
    defines_concept: bool = Field(
        description="Does this paper meaningfully define or use the concept "
                    "(possibly under a different name)? False is a valid, common answer."
    )
    definition: str = Field(
        default="", description="How this paper frames the concept, in one or two sentences."
    )
    verbatim_quote: str = Field(
        default="", description="Exact sentence(s) copied character-for-character from the paper."
    )
    section: str = Field(
        default="", description="Section the quote came from, if identifiable."
    )
    novelty_claims: list[str] = Field(
        default_factory=list, description="What this paper claims is new about its treatment."
    )


def estimate_tokens(client, model: str, system: str, user: str) -> int:
    """Exact count via the API when a key exists; heuristic otherwise.

    count_tokens is free but needs a key. Never use tiktoken here — it is
    OpenAI's tokenizer and miscounts Claude tokens badly.
    """
    if client is not None:
        try:
            return client.messages.count_tokens(
                model=model, system=system, messages=[{"role": "user", "content": user}]
            ).input_tokens
        except Exception:
            pass
    # Fallback ratio measured against count_tokens on this corpus: 102,162 chars
    # -> 39,072 tokens = 2.6 chars/token. Academic text (LaTeX artifacts, math,
    # citations) tokenizes far worse than the ~3.5 typical of plain prose; the
    # optimistic constant under-estimated the 150-paper cost by 34%.
    return int(len(system + user) / 2.6)


def cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    p_in, p_out = PRICING.get(model, PRICING[DEFAULT_MODEL])
    return in_tok / 1e6 * p_in + out_tok / 1e6 * p_out


# The papers table is shared across ALL traced concepts. Without --corpus this
# selects every extracted paper in the DB — right when the DB holds one
# concept's corpus (research CLI use), wrong for the worker: a new trace would
# re-bill the LLM against every paper any previous trace ever fetched.
SELECT_PAPERS = f"""
SELECT p.id, p.arxiv_id, p.title, p.extracted_text_path
FROM papers p
WHERE p.extracted_text_path IS NOT NULL
  AND COALESCE(p.text_title_match, 0) >= {TITLE_MATCH_MIN}
  AND NOT EXISTS (
      SELECT 1 FROM definitions d
      WHERE d.paper_id = p.id AND d.concept = %(concept)s
        AND d.prompt_version = %(prompt_version)s
  )
{{corpus_filter}}{{arxiv_filter}}ORDER BY p.cited_by_count DESC NULLS LAST
"""

INSERT_DEF = """
INSERT INTO definitions (paper_id, concept, prompt_version, defines_concept,
                         definition, verbatim_quote, quote_verified, section,
                         novelty_claims, model)
VALUES (%(paper_id)s, %(concept)s, %(prompt_version)s, %(defines_concept)s,
        %(definition)s, %(verbatim_quote)s, %(quote_verified)s, %(section)s,
        %(novelty_claims)s, %(model)s)
ON CONFLICT (paper_id, concept, prompt_version) DO NOTHING
"""

# --refresh re-extracts papers that already have a row, which the cache exists to
# prevent. It is for one situation: the extracted text changed underneath a
# stored quote, so the quote is answering a question about a document that no
# longer exists.
#
# It UPDATEs rather than DELETEs and re-INSERTs, and that is the whole point.
# `genealogies.nodes` holds definition_ids, so a delete would mint new ids and
# orphan the curated node membership on every map built from this concept. The
# id is the thing being protected.
#
# The embedding is nulled because the definition text it encodes has changed.
# Stale is worse than absent: absent is visible to the re-embed step, stale is
# not visible to anything.
REFRESH_DEF = """
UPDATE definitions SET
    defines_concept = %(defines_concept)s,
    definition      = %(definition)s,
    verbatim_quote  = %(verbatim_quote)s,
    quote_verified  = %(quote_verified)s,
    section         = %(section)s,
    novelty_claims  = %(novelty_claims)s,
    model           = %(model)s,
    embedding       = NULL
WHERE paper_id = %(paper_id)s AND concept = %(concept)s
  AND prompt_version = %(prompt_version)s
"""

# The mirror of SELECT_PAPERS: papers that DO have a row, so they can be redone.
SELECT_PAPERS_REFRESH = f"""
SELECT p.id, p.arxiv_id, p.title, p.extracted_text_path
FROM papers p
JOIN definitions d ON d.paper_id = p.id
WHERE p.extracted_text_path IS NOT NULL
  AND COALESCE(p.text_title_match, 0) >= {TITLE_MATCH_MIN}
  AND d.concept = %(concept)s AND d.prompt_version = %(prompt_version)s
{{corpus_filter}}{{arxiv_filter}}ORDER BY p.cited_by_count DESC NULLS LAST
"""

# --reground re-answers the grounding question for definitions that already
# exist, against the text on disk now. It exists because `quote_verified` was the
# one stamp in the system with no way back: Stage E re-grounds every edge on
# every run and Stage H's --recheck re-grounds every claim, both free, while a
# definition's stamp could only be refreshed by paying for a fresh extraction. A
# stamp that cannot be recomputed outlives the check that made it, and on
# `embedding` it did: its papers were re-extracted on 2026-07-31 and its
# definitions were not, so its quotes were copied out of a document no longer on
# disk while their stamps still said the text had been searched for them.
#
# No TITLE_MATCH_MIN guard and no NOT NULL test on the text path, unlike the two
# queries above. Those guards exist to stop money being spent against the wrong
# paper's text. Here the row already exists and its stamp is already on a page,
# so excluding it would only hide it from the count this flag exists to make
# visible; a definition whose paper has no text path is reported as unchecked
# instead.
SELECT_DEFS_REGROUND = """
SELECT d.id, p.arxiv_id, p.extracted_text_path, d.verbatim_quote,
       d.quote_verified, d.defines_concept
FROM definitions d
JOIN papers p ON p.id = d.paper_id
WHERE d.concept = %(concept)s
  AND d.prompt_version = %(prompt_version)s
{corpus_filter}{arxiv_filter}ORDER BY p.arxiv_id
"""

# The stamp, and nothing else. `verbatim_quote` is what the model returned and is
# not ours to edit here: incident 10's lesson is that repairing the data to
# satisfy a check hides what the check found. The embedding is left alone too,
# unlike REFRESH_DEF, which nulls it — there the definition text changed, here
# only our verdict about it did.
#
# Scoped by concept and prompt version as well as by id, though the id alone is
# already unique. `definitions` is shared across every concept ever traced, and
# an UPDATE in this file that is wrong about its scope rewrites another map's
# stamps in silence.
REGROUND_DEF = """
UPDATE definitions SET quote_verified = %(quote_verified)s
WHERE id = %(def_id)s AND concept = %(concept)s
  AND prompt_version = %(prompt_version)s
"""


def reground(conn, concept: str, prompt_version: str, params: dict,
             corpus_filter: str, arxiv_filter: str, dry_run: bool) -> None:
    """Re-check every stored definition quote against the text on disk now.

    Costs nothing: no model, no network, no key, disk reads only. Mirrors
    stage_h_claims.py --recheck deliberately, down to keeping the payload and
    moving only the stamp, and it calls the same `quote_is_grounded` every other
    stage calls. One comparison function is why "verified" means one thing
    across this system.
    """
    rows = conn.execute(
        SELECT_DEFS_REGROUND.format(corpus_filter=corpus_filter,
                                    arxiv_filter=arxiv_filter), params).fetchall()
    if not rows:
        print(f'No definitions to re-check for "{concept}" at prompt {prompt_version}.')
        return

    if dry_run:
        print("[dry-run] Re-checking every stamp. Nothing will be written.\n")
    dd = data_dir()
    total = len(rows)
    before = sum(1 for r in rows if r[4])
    checked = gained = lost = 0
    unchecked: list[tuple[str, bool]] = []

    for i, (def_id, arxiv, tpath, quote, was, defines) in enumerate(rows, 1):
        was = bool(was)
        stamp = "verified" if was else "unverified"
        tfile = (dd / tpath) if tpath else None
        if tfile is None or not tfile.exists():
            # The open question, answered the only way a script is entitled to
            # answer it. `quote_verified` is NOT NULL DEFAULT false, so there is
            # no "unknown" to write: leaving it true perpetuates the stale claim
            # this flag exists to kill, and writing false asserts a check that
            # never ran and would mass-flip every stamp on a worker whose disk is
            # incomplete. Both are decisions about the product, so neither is
            # taken here. The stamp stands and the count is printed loudly.
            unchecked.append((arxiv, was))
            why = "no extracted text recorded" if tpath is None else "no extracted text on this disk"
            print(f"  [{i}/{total}] {arxiv}: {why}, stamp left as {stamp}", flush=True)
            continue
        try:
            # The same read Stage B does when it creates the stamp. A recompute
            # that reads the file differently from the compute is not a recompute.
            text = tfile.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            unchecked.append((arxiv, was))
            print(f"  [{i}/{total}] {arxiv}: text unreadable ({exc}), "
                  f"stamp left as {stamp}", flush=True)
            continue

        checked += 1
        # `defines_concept` is in the test because it is in the test at creation
        # (see the extract loop below). A row that says the paper does not define
        # the concept has no definition quote to stand behind, whatever string
        # happens to sit in the column.
        ok = bool(defines) and bool(quote) and quote_is_grounded(text, quote)
        if ok == was:
            print(f"  [{i}/{total}] {arxiv}: still {stamp}", flush=True)
            continue

        gained += ok
        lost += not ok
        if not dry_run:
            conn.execute(REGROUND_DEF, {"def_id": def_id, "concept": concept,
                                        "prompt_version": prompt_version,
                                        "quote_verified": ok})
        moved = ("not found before, found in the text now" if ok
                 else "NO LONGER FOUND in the text")
        print(f"  [{i}/{total}] {arxiv}: {moved}", flush=True)

    after = before - lost + gained
    print(f'\n"{concept}" at prompt {prompt_version}: {total} definitions, '
          f"{checked} re-checked against the text on disk.")
    print(f"  verified before: {before}")
    print(f"  verified after:  {after}  ({gained} newly verified, "
          f"{lost} no longer found in the text)")
    if unchecked:
        still = sum(1 for _, was in unchecked if was)
        print(f"\n  Could NOT be checked, the paper's extracted text is not on this "
              f"disk: {len(unchecked)} of {total}")
        print(f"  Of those, still stamped verified with nothing here to prove it: {still}")
        print("  Their stamps were left exactly as they were. Whether an unprovable "
              "stamp should stand or fall is a decision about the product, not one "
              "for this script.")
        shown = ", ".join(a for a, _ in unchecked[:20])
        print(f"    {shown}{', and more' if len(unchecked) > 20 else ''}")
    if dry_run:
        print("\n[dry-run] Nothing was written. Re-run without --dry-run to move "
              "the stamps.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage B: extract per-paper concept definitions.")
    ap.add_argument("concept", help='e.g. "attention"')
    ap.add_argument("--model", default=env("LLM_MODEL", DEFAULT_MODEL))
    ap.add_argument("--limit", type=int, help="process at most N papers")
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                    help=f"truncate paper text (default {DEFAULT_MAX_CHARS:,})")
    ap.add_argument("--thinking", action="store_true",
                    help="enable adaptive thinking (better reasoning, more output tokens)")
    ap.add_argument("--dry-run", action="store_true",
                    help="estimate cost across models; makes no billable call. "
                         "With --reground, report the counts and write nothing")
    ap.add_argument("--corpus", metavar="JSON",
                    help="restrict to the arxiv_ids in this corpus JSON "
                         "(from corpus_select --json); without it, ALL extracted papers")
    ap.add_argument("--gloss",
                    help="one-line sense clarification; makes the extraction question "
                         "sense-specific for polysemous concepts")
    ap.add_argument("--refresh", action="store_true",
                    help="re-extract papers that already have a definition, updating "
                         "the row in place. For when the extracted text changed under "
                         "a stored quote; scope it with --only")
    ap.add_argument("--only", metavar="ARXIV_ID", nargs="+",
                    help="restrict to these arxiv ids (use with --refresh to redo "
                         "just the papers an audit flagged)")
    ap.add_argument("--reground", action="store_true",
                    help="re-check the definition quotes already stored against the "
                         "extracted text as it is now, and rewrite quote_verified "
                         "only. For when the text changed underneath a stamp: the "
                         "stamp was computed against the old text and a stamp must "
                         "never outlive the check that made it. Costs nothing and "
                         "needs no API key")
    args = ap.parse_args()

    if args.reground and args.refresh:
        sys.exit("--reground and --refresh are different jobs: --reground re-checks the "
                 "definitions you already have and spends nothing, --refresh buys new "
                 "ones. Run them one at a time.")
    if args.reground and args.limit:
        sys.exit("--reground reports the verified count for the whole concept, and "
                 "--limit would make that count describe a subset of it. Use --only "
                 "or --corpus to scope which papers are checked.")

    sense = SENSE.format(gloss=args.gloss) if args.gloss else ""
    params: dict = {"concept": args.concept}
    corpus_filter = ""
    if args.corpus:
        corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
        params["arxiv_ids"] = [p["arxiv_id"] for p in corpus]
        corpus_filter = "  AND p.arxiv_id = ANY(%(arxiv_ids)s)\n"
    arxiv_filter = ""
    if args.only:
        params["only_ids"] = list(args.only)
        arxiv_filter = "  AND p.arxiv_id = ANY(%(only_ids)s)\n"
    elif args.refresh:
        print("Refreshing EVERY paper for this concept. --only <ids> scopes it to "
              "the papers an audit flagged, which is almost always what you want.")

    prompt_version = env("PROMPT_VERSION", "v1")
    cap = float(env("TRACE_SPEND_CAP_USD", "10"))
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    params["prompt_version"] = prompt_version

    # Ahead of everything that costs or needs a key, because this path must stay
    # runnable on a machine with no Anthropic credit. That is the state the map
    # that needs it most is in.
    if args.reground:
        reground(conn, args.concept, prompt_version, params,
                 corpus_filter, arxiv_filter, args.dry_run)
        conn.close()
        return

    query = SELECT_PAPERS_REFRESH if args.refresh else SELECT_PAPERS
    rows = conn.execute(query.format(corpus_filter=corpus_filter,
                                     arxiv_filter=arxiv_filter), params).fetchall()
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        if args.refresh:
            print(f'Nothing to refresh for "{args.concept}" at prompt {prompt_version} '
                  f"(no matching papers already have a definition).")
        else:
            print(f'Nothing to extract for "{args.concept}" (all cached at prompt {prompt_version}, '
                  f"or no papers pass text_title_match >= {TITLE_MATCH_MIN}).")
        return
    if args.refresh:
        print(f"Refreshing {len(rows)} papers in place (definition ids preserved, "
              f"embeddings cleared for re-embedding).")

    import os
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    client = None
    if have_key:
        import anthropic
        client = anthropic.Anthropic()

    # ---- estimate -----------------------------------------------------------
    prompts = []
    for pid, aid, title, tpath in rows:
        # The DB is shared across machines but the files are per-disk: a paper
        # extracted on another worker is flagged extracted here, yet its text
        # file may be absent on this disk. Skip rather than crash the whole run.
        tfile = data_dir() / tpath
        if not tfile.exists():
            print(f"    ⚠ text missing for {aid} on this disk ({tpath}); skipping")
            continue
        text = tfile.read_text(encoding="utf-8")[:args.max_chars]
        prompts.append((pid, aid, title, USER.format(concept=args.concept, sense=sense, text=text)))

    total_in = sum(estimate_tokens(client, args.model, SYSTEM, u) for _, _, _, u in prompts)
    out_tok = (EST_OUTPUT_TOKENS + (1200 if args.thinking else 0)) * len(prompts)

    if args.dry_run:
        exact = "exact (count_tokens)" if have_key else "APPROXIMATE (no API key; chars/3.5)"
        print(f'[dry-run] "{args.concept}" — {len(prompts)} papers, prompt {prompt_version}')
        print(f"  input tokens:  {total_in:,}  [{exact}]")
        print(f"  output tokens: {out_tok:,}  [estimated {EST_OUTPUT_TOKENS}/paper"
              f"{' + thinking' if args.thinking else ''}]")
        print(f"\n  {'model':<20} {'in $':>8} {'out $':>8} {'total':>9}   vs cap ${cap:g}")
        print("  " + "-" * 62)
        for m in PRICING:
            ci = total_in / 1e6 * PRICING[m][0]
            co = out_tok / 1e6 * PRICING[m][1]
            flag = "OVER CAP" if ci + co > cap else "ok"
            mark = " <- selected" if m == args.model else ""
            print(f"  {m:<20} {ci:>8.2f} {co:>8.2f} {ci + co:>9.2f}   {flag}{mark}")
        print(f"\n  Scaled to 150 papers: ~${cost_usd(args.model, total_in, out_tok) / len(prompts) * 150:.2f} "
              f"on {args.model}")
        print("\n  No API call was made. Choose a model with --model or LLM_MODEL in .env.")
        return

    if not have_key:
        sys.exit("ANTHROPIC_API_KEY is not set in .env — add it, or use --dry-run.")

    est = cost_usd(args.model, total_in, out_tok)
    if est > cap:
        sys.exit(f"Estimated ${est:.2f} exceeds TRACE_SPEND_CAP_USD=${cap:g}. "
                 f"Lower --limit, use a cheaper --model, or raise the cap.")

    # ---- extract ------------------------------------------------------------
    text_path_by_id = {aid: tpath for _, aid, _, tpath in rows}
    spend = 0.0
    kept = dropped = unverified = 0
    for i, (pid, aid, title, user_prompt) in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] {aid}: {(title or '?')[:52]}")
        kwargs = dict(model=args.model, max_tokens=4000, system=SYSTEM,
                      messages=[{"role": "user", "content": user_prompt}],
                      output_format=Extraction)
        if args.thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        resp = client.messages.parse(**kwargs)

        spend += cost_usd(args.model, resp.usage.input_tokens, resp.usage.output_tokens)
        ex = resp.parsed_output
        if ex is None:
            print("    ✗ model returned no parseable extraction")
            continue

        # Grounding check at the point of creation: the quote must literally
        # occur in the text we sent, or it is not evidence.
        verified = False
        if ex.defines_concept and ex.verbatim_quote:
            full = (data_dir() / text_path_by_id[aid]).read_text(encoding="utf-8")
            verified = quote_is_grounded(full, ex.verbatim_quote)

        # Always record the verdict — "does not define it" is a finding worth
        # caching, not an absence of one. Without a row, every re-run re-pays
        # the LLM for papers already known to be irrelevant.
        conn.execute(REFRESH_DEF if args.refresh else INSERT_DEF, {
            "paper_id": pid, "concept": args.concept, "prompt_version": prompt_version,
            "defines_concept": ex.defines_concept,
            "definition": ex.definition or "", "verbatim_quote": ex.verbatim_quote or "",
            "quote_verified": verified, "section": ex.section or None,
            "novelty_claims": psycopg.types.json.Json(ex.novelty_claims),
            "model": args.model,
        })
        conn.commit()

        if not ex.defines_concept:
            dropped += 1
            print(f"    – does not define \"{args.concept}\" — no node (spend ${spend:.2f})")
        else:
            kept += 1
            if not verified:
                unverified += 1
            mark = "✓ verified" if verified else "⚠ QUOTE NOT FOUND IN TEXT"
            print(f"    ✓ definition captured, {mark} (spend ${spend:.2f})")

        if spend > cap:
            print(f"\n⚠ SPEND CAP HIT: ${spend:.2f} > ${cap:g} — aborting cleanly after "
                  f"{i}/{len(prompts)} papers. Extractions so far are cached.")
            break

    conn.close()
    print(f"\nDone: {kept} definitions ({unverified} with unverified quotes), "
          f"{dropped} papers dropped as not defining the concept.")
    print(f"Total spend: ${spend:.4f} of ${cap:g} cap.")


if __name__ == "__main__":
    main()

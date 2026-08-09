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
import re
import sys
from datetime import date
from pathlib import Path

import psycopg
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (grounded_span, quote_is_grounded, read_grounding_text,  # noqa: E402
                    REPO_ROOT, data_dir, env)

DEFAULT_MODEL = "claude-opus-4-8"

# USD per million tokens (input, output), from Anthropic's published pricing
# (platform.claude.com/docs/en/about-claude/pricing, read 2026-08-09 for #205).
# Keyed by the model FAMILY: a dated snapshot id resolves to its family in
# `pricing_key` below, because a snapshot bills at the rates of the family it was
# cut from.
PRICING = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# A published rate that is a function of the DATE as well as the model, and the
# day the discount ends. Sonnet 5 bills at introductory rates through
# 2026-08-31 and at the standard rates above from 2026-09-01; every paying stage
# but F and G runs on it, so a table holding one of those two numbers is wrong on
# one side of that date by 50% (#205, found by checking the published page rather
# than trusting the table). Keeping both, with the switchover, is the only form
# that is right today AND in September without anybody remembering to edit it.
INTRODUCTORY = {
    "claude-sonnet-5": (date(2026, 9, 1), (2.00, 10.00)),
}

# Anthropic's dated snapshot ids are the family id plus `-YYYYMMDD`
# (`claude-haiku-4-5-20251001`), and Stages F and G pin one deliberately, so that
# a rebuild months later asks the same weights the map was built from. Pricing
# resolves it to the family instead of demanding a table row per snapshot: a new
# snapshot of a priced family then prices correctly on the day it is pinned,
# rather than failing a build over a date suffix.
SNAPSHOT_SUFFIX = re.compile(r"-\d{8}$")


class UnpricedModel(Exception):
    """No published rates for this model id, so no honest figure can be produced.

    Raised rather than defaulted (#205). This lookup used to be
    `PRICING.get(model, PRICING[DEFAULT_MODEL])`, and because Stages F and G pass
    the dated snapshot `claude-haiku-4-5-20251001`, which was not a key, every
    dollar those two stages printed for months was Haiku work billed at Opus
    rates: 5x reality, scraped into `genealogies.spend_usd` (#85), into the
    per-stage record (#47), into the progress feed, and checked against
    TRACE_SPEND_CAP_USD. A lookup with a default converts an unknown model into a
    confident wrong number, and it guessed at the most expensive row in the table,
    so the error was not even bounded in a known direction. A bill that announces
    it cannot be computed beats a plausible one that is fiction.
    """

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


def pricing_key(model: str) -> str:
    """The PRICING key that prices `model`, or raise. Never guesses.

    Call it on its own, before a client is built, to refuse an unpriced model
    while the run has spent nothing — every stage that pays does, because the
    alternative is discovering it after the first call, and in Stage F's batch
    loop an exception from costing is caught by the batch's own `except` and
    reported as a failed batch, which is a pricing defect wearing a scoring
    failure's clothes.
    """
    key = model if model in PRICING else SNAPSHOT_SUFFIX.sub("", model)
    if key not in PRICING:
        raise UnpricedModel(
            f"no published rates for model {model!r}"
            + (f" (nor for {key!r}, the family its date suffix names)" if key != model else "")
            + f": add it to PRICING in {Path(__file__).name}, from Anthropic's "
              f"published pricing. Priced today: {', '.join(sorted(PRICING))}. "
              f"Refusing to price it at another model's rates — this figure is "
              f"what the map's record publishes and what the spend cap decides on."
        )
    return key


def rates_for(model: str, on: "date | None" = None) -> "tuple[float, float]":
    """(input, output) USD per million tokens, on a given day. Raises for unknown.

    The day matters because one published rate moves (see INTRODUCTORY). It
    defaults to today, which is the day of the call being priced. Two consequences
    worth knowing rather than discovering: a run straddling midnight on 2026-08-31
    prices its early calls at the old rate and its later ones at the new one, which
    is what the invoice will do too; and a Stage H cache hit re-prices an old call
    at today's rates, so the "avoided" figure it prints drifts across that date. A
    caller that must price a specific day passes it.
    """
    key = pricing_key(model)
    intro = INTRODUCTORY.get(key)
    if intro is not None and (on or date.today()) < intro[0]:
        return intro[1]
    return PRICING[key]


def cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    p_in, p_out = rates_for(model)
    return in_tok / 1e6 * p_in + out_tok / 1e6 * p_out


def write_estimate(args, prompt_version: str, papers: int, in_tok: int,
                   out_tok: int, cap: float) -> None:
    """The dry run's estimate as a file, for a caller that must DECIDE on it.

    Issue #192. The two-stage build asks this stage what pass two would cost and
    abandons the pass if the remaining spend cap cannot cover it. Scraping that
    number out of the table below would make a spend decision depend on a column
    width, which is the weakness the one existing run-cost figure already has
    (#85, a regex over stdout). The human table is unchanged and still prints.

    **It is written on every dry-run path, including the one where there is
    nothing to extract**, and that path is the one that matters most: a build
    that was killed after pass two's Stage B and requeued (#178) finds every
    pass-two paper already cached, and a missing file there would make the
    resumed build abandon a pass the killed one had already paid for. `papers`
    and `nothing_to_buy` say that state explicitly rather than leaving a caller
    to read it out of a zero — an estimate of $0 over no papers is "there is
    nothing here to buy", which is a different fact from a cheap job.

    `model` and `cap_usd` travel with it because an estimate is a claim about a
    model and a limit, and the abandonment message has to be able to name both.
    """
    if not args.estimate_json:
        return
    path = Path(args.estimate_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "concept": args.concept, "prompt_version": prompt_version,
        "papers": papers, "model": args.model,
        "input_tokens": in_tok, "output_tokens": out_tok,
        "estimate_usd": round(cost_usd(args.model, in_tok, out_tok), 6),
        "cap_usd": cap,
        "nothing_to_buy": papers == 0,
    }, indent=2), encoding="utf-8")


# In what order the money is spent, which is the order the papers are read
# (issue #185). This used to be `p.cited_by_count DESC NULLS LAST` and that was
# the one order this stage must not use.
#
# The spend cap aborts a run cleanly, which is correct, and the papers left
# unread are whichever the ORDER BY put last. Reading most-cited-first makes
# those the least-cited papers, and since #181 the least-cited papers are
# precisely the reserved recent seats: a trace that hit its cap would select the
# recent partition at Stage A, pay for it, and then not read it, and every
# recency figure on the report would say the fix did not work for a reason that
# has nothing to do with selection.
#
# Corpus rank is chosen over interleaving because Stage A already ranked these
# papers and the rank is in the file: `--corpus` hands us the arxiv ids in
# selection order, so `array_position` reads them in it. Interleaving would have
# invented a second ordering policy here, in the stage least able to defend one.
#
# Without --corpus there is no rank to honour — that path takes every extracted
# paper in a table shared across concepts — so it falls back to `p.id`, the
# order the rows were inserted, which is the order some earlier trace's
# corpus_select ranked them in. Arbitrary across concepts, but it is the one
# available order that carries no citation bias, and that is what matters when
# the cap lands.
ORDER_BY_CORPUS_RANK = "ORDER BY array_position(%(arxiv_ids)s::text[], p.arxiv_id)"
ORDER_BY_INSERTION = "ORDER BY p.id"

# The papers table is shared across ALL traced concepts. Without --corpus this
# selects every extracted paper in the DB — right when the DB holds one
# concept's corpus (research CLI use), wrong for the worker: a new trace would
# re-bill the LLM against every paper any previous trace ever fetched.
SELECT_PAPERS = f"""
SELECT p.id, p.arxiv_id, p.title, p.extracted_text_path, p.extractor_version
FROM papers p
WHERE p.extracted_text_path IS NOT NULL
  AND COALESCE(p.text_title_match, 0) >= {TITLE_MATCH_MIN}
  AND NOT EXISTS (
      SELECT 1 FROM definitions d
      WHERE d.paper_id = p.id AND d.concept = %(concept)s
        AND d.prompt_version = %(prompt_version)s
  )
{{corpus_filter}}{{arxiv_filter}}{{order_by}}
"""

# The stamp is the boolean AND the four columns migration 015 added: where in
# the text the quote was found, a digest of the bytes it was found in, and which
# extractor produced them. They are written by the same statement as the boolean
# because they are one fact about one moment; a boolean whose digest arrived
# separately would be a stamp qualified by something that might not describe it.
INSERT_DEF = """
INSERT INTO definitions (paper_id, concept, prompt_version, defines_concept,
                         definition, verbatim_quote, quote_verified, section,
                         novelty_claims, model,
                         quote_start, quote_end, quote_text_digest,
                         quote_extractor_version)
VALUES (%(paper_id)s, %(concept)s, %(prompt_version)s, %(defines_concept)s,
        %(definition)s, %(verbatim_quote)s, %(quote_verified)s, %(section)s,
        %(novelty_claims)s, %(model)s,
        %(quote_start)s, %(quote_end)s, %(quote_text_digest)s,
        %(quote_extractor_version)s)
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
    embedding       = NULL,
    quote_start             = %(quote_start)s,
    quote_end               = %(quote_end)s,
    quote_text_digest       = %(quote_text_digest)s,
    quote_extractor_version = %(quote_extractor_version)s
WHERE paper_id = %(paper_id)s AND concept = %(concept)s
  AND prompt_version = %(prompt_version)s
"""

# The mirror of SELECT_PAPERS: papers that DO have a row, so they can be redone.
SELECT_PAPERS_REFRESH = f"""
SELECT p.id, p.arxiv_id, p.title, p.extracted_text_path, p.extractor_version
FROM papers p
JOIN definitions d ON d.paper_id = p.id
WHERE p.extracted_text_path IS NOT NULL
  AND COALESCE(p.text_title_match, 0) >= {TITLE_MATCH_MIN}
  AND d.concept = %(concept)s AND d.prompt_version = %(prompt_version)s
{{corpus_filter}}{{arxiv_filter}}{{order_by}}
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
       d.quote_verified, d.defines_concept,
       d.quote_start, d.quote_end, d.quote_text_digest,
       d.quote_extractor_version, p.extractor_version
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
UPDATE definitions SET quote_verified = %(quote_verified)s,
       quote_start             = %(quote_start)s,
       quote_end               = %(quote_end)s,
       quote_text_digest       = %(quote_text_digest)s,
       quote_extractor_version = %(quote_extractor_version)s
WHERE id = %(def_id)s AND concept = %(concept)s
  AND prompt_version = %(prompt_version)s
"""


def reground(conn, concept: str, prompt_version: str, params: dict,
             corpus_filter: str, arxiv_filter: str, dry_run: bool) -> None:
    """Re-check every stored definition quote against the text on disk now.

    Costs nothing: no model, no network, no key, disk reads only. Mirrors
    stage_h_claims.py --recheck deliberately, down to keeping the payload and
    moving only the stamp, and it calls the same matcher every other stage calls.
    One comparison function is why "verified" means one thing across this system.

    Since migration 015 the stamp is four columns and a boolean, so a row is
    rewritten when ANYTHING about it moved, not only when the verdict flipped.
    The old `continue` on an unchanged boolean would have left every re-checked
    stamp with a NULL digest — still rendering stale after the very run that
    re-checked it. The printed narrative still reports only the rows whose
    verdict moved, so the log does not become one line per definition saying
    nothing happened.
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
    checked = grounded = 0
    unchecked: list[tuple[str, bool]] = []
    # Every verdict is decided before any of them is written. The stage used to
    # UPDATE inside this loop on an autocommit connection, which meant the first
    # rows were committed before the last row had been looked at, and there was
    # no point at which the run as a whole could be refused.
    pending: list[tuple[int, str, bool, dict]] = []
    moved_rows = moved_gained = 0

    for i, (def_id, arxiv, tpath, quote, was, defines,
            had_start, had_end, had_digest, had_ever, paper_ever) in enumerate(rows, 1):
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
            # The same read Stage B does when it creates the stamp, through the
            # one helper both use, so the offsets stored here are offsets into
            # the same decoding of the same bytes. A recompute that reads the
            # file differently from the compute is not a recompute.
            text, digest = read_grounding_text(tpath)
        except (OSError, UnicodeDecodeError) as exc:
            unchecked.append((arxiv, was))
            print(f"  [{i}/{total}] {arxiv}: text unreadable ({exc}), "
                  f"stamp left as {stamp}", flush=True)
            continue

        if not text.strip():
            # An empty file is not "the text, and the quote is not in it". It is
            # the absence of text wearing a text file's name, which is what an
            # interrupted extract_text.py or a full DATA_DIR leaves behind, and
            # answering the grounding question against it would assert a check
            # that never ran. Same treatment as a missing file: a distinction of
            # kind, not a threshold on size.
            unchecked.append((arxiv, was))
            print(f"  [{i}/{total}] {arxiv}: extracted text file is empty, "
                  f"stamp left as {stamp}", flush=True)
            continue

        checked += 1
        # `defines_concept` is in the test because it is in the test at creation
        # (see the extract loop below). A row that says the paper does not define
        # the concept has no definition quote to stand behind, whatever string
        # happens to sit in the column.
        attempted = bool(defines) and bool(quote)
        span = grounded_span(text, quote) if attempted else None
        ok = span is not None
        grounded += ok
        # The extractor version is copied from the paper's row, not taken from
        # the running extract_text: it is provenance about the TEXT, and this
        # code did not produce the text. Claiming otherwise would be a false
        # provenance claim on exactly the papers backlog item 4 is about, whose
        # text predates the current extractor. NULL there means the text predates
        # the column, which is the whole truth about it.
        #
        # No digest when no match was attempted (issue #62). A digest on a stamp
        # is the assertion "a check ran against these bytes", so writing one from
        # the branch that skipped the check made a row with no quote resolve to
        # `inferred`, whose published meaning is "could not be string-matched"
        # — a failed check that never ran, which is the thing decision 21 and the
        # missing-file branch above both refuse to write. NULL renders stale,
        # which is what an unattempted check is, and it matches what the creation
        # path in this same file already writes for these rows.
        after = {"quote_start": span[0] if span else None,
                 "quote_end": span[1] if span else None,
                 "quote_text_digest": digest if attempted else None,
                 "quote_extractor_version": paper_ever if attempted else None}
        # The "has anything moved?" test is derived from `after` rather than
        # written beside it (issue #64). Spelling the comparison out a second time
        # let the two drift the moment the write learned about `attempted`: the
        # predicate went on asking about the raw `digest`, so a row already in the
        # correct all-NULL state was rewritten on every run forever, and a row
        # still carrying a digest written before that fix was judged unchanged and
        # so could never be repaired by the only thing that repairs it. Comparing
        # against the dict that is about to be written makes both impossible.
        # `stored`, not `before`: `before` is the verified count this function
        # reports at the end, and shadowing it here made the summary arithmetic
        # subtract an int from a dict on every run that reached this line.
        stored = {"quote_start": had_start, "quote_end": had_end,
                  "quote_text_digest": had_digest,
                  "quote_extractor_version": had_ever}
        if ok == was and stored == after:
            print(f"  [{i}/{total}] {arxiv}: still {stamp}", flush=True)
            continue

        pending.append((def_id, arxiv, ok, after))
        if ok == was:
            # The verdict did not move; the stamp became re-checkable, or the
            # text under it changed identity. Not narrated per row, because on
            # the first run after 015 that is every row and the log would drown
            # the definitions that actually moved.
            continue
        moved_rows += 1
        moved_gained += ok
        moved = ("not found before, found in the text now" if ok
                 else "not found in the extracted text as it is on disk now")
        print(f"  [{i}/{total}] {arxiv}: {moved}", flush=True)

    # Incident 12's lesson, in a stage that spends nothing but publishes a
    # verdict: a per-item result needs a global sanity check. One definition
    # failing to ground is a finding. EVERY definition failing to ground, when
    # more than one was checked, is not a finding — it is what a truncated or
    # half-written DATA_DIR looks like, and nothing here can tell that apart from
    # a map that is genuinely wrong. So the run is refused rather than reported,
    # in the direction that changes nothing.
    #
    # The boundary is zero, not a percentage. This project has shipped three bad
    # calibrations (decision 3, incident 9, and the turning-point cutoff) and a
    # guessed fraction here would be the fourth. "None at all" is a degenerate
    # case, not a tuned one.
    if checked > 1 and grounded == 0:
        sys.exit(
            f'\nRefusing to trust this result: {checked} definitions were checked for "{concept}" '
            f"and not one quote grounded.\n"
            "  That is what an empty, truncated or half-written DATA_DIR looks like, and this\n"
            "  stage cannot tell it apart from the map genuinely being wrong. Nothing was\n"
            "  written and every stamp stands as it was.\n"
            f"  Check the extracted text first: {dd}\n"
            "  If the text really is intact and every quote really is stale, the answer is to\n"
            "  re-extract or re-run Stage B, not to mass-flip the stamps from here.")

    if pending and not dry_run:
        # One transaction. The connection is autocommit, so without this each
        # UPDATE commits on its own and a failure partway leaves the concept
        # half-flipped, which is a third state nobody can read.
        with conn.transaction():
            for def_id, _arxiv, ok, stamp_cols in pending:
                conn.execute(REGROUND_DEF, {"def_id": def_id, "concept": concept,
                                            "prompt_version": prompt_version,
                                            "quote_verified": ok, **stamp_cols})

    # Counted over the rows whose VERDICT moved, not over every row written.
    # Since 015 a row is written when its span or its digest moved too, and
    # folding those into "newly verified" would report a re-check that changed
    # nobody's mind as a corpus of stamps flipping.
    gained, lost = moved_gained, moved_rows - moved_gained
    after_count = before - lost + gained
    print(f'\n"{concept}" at prompt {prompt_version}: {total} definitions, '
          f"{checked} re-checked against the text on disk.")
    print(f"  verified before: {before}")
    print(f"  verified after:  {after_count}  ({gained} newly verified, "
          f"{lost} not found in the extracted text now on disk)")
    print(f"  stamps rewritten: {len(pending)} of {checked} re-checked "
          f"(a stamp is rewritten when its span, its text digest or its "
          f"verdict moved, so the first run after migration 015 rewrites "
          f"every one it could check)")
    if unchecked:
        still = sum(1 for _, was in unchecked if was)
        print(f"\n  Could NOT be checked, the paper's extracted text is missing or "
              f"empty on this disk: {len(unchecked)} of {total}")
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
    ap.add_argument("--estimate-json", metavar="PATH",
                    help="with --dry-run, also write the estimate here as JSON, for a "
                         "caller that has to decide on it rather than read it (#192's "
                         "pre-flight spend gate)")
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
    if args.estimate_json and not (args.dry_run and not args.reground):
        # Refused rather than ignored: the caller of --estimate-json is a spend
        # gate, and a gate that reads a file nobody wrote is a gate that decides
        # on the last run's number or on nothing at all.
        sys.exit("--estimate-json is the dry run's estimate written to a file, so it "
                 "needs --dry-run and cannot be combined with --reground, which buys "
                 "nothing and has nothing to estimate.")
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

    # Below this line every path either estimates money or spends it, so an
    # unpriced --model (or LLM_MODEL) is refused here rather than after the first
    # call (#205). Deliberately below --reground, which buys nothing and must stay
    # runnable whatever the environment names as a model.
    pricing_key(args.model)

    query = SELECT_PAPERS_REFRESH if args.refresh else SELECT_PAPERS
    order_by = ORDER_BY_CORPUS_RANK if args.corpus else ORDER_BY_INSERTION
    rows = conn.execute(query.format(corpus_filter=corpus_filter,
                                     arxiv_filter=arxiv_filter,
                                     order_by=order_by), params).fetchall()
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        if args.refresh:
            print(f'Nothing to refresh for "{args.concept}" at prompt {prompt_version} '
                  f"(no matching papers already have a definition).")
        else:
            print(f'Nothing to extract for "{args.concept}" (all cached at prompt {prompt_version}, '
                  f"or no papers pass text_title_match >= {TITLE_MATCH_MIN}).")
        # Nothing to buy is an estimate too, and the resumed-build case depends on
        # it being written here (see write_estimate).
        if args.dry_run:
            write_estimate(args, prompt_version, 0, 0, 0, cap)
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
    for pid, aid, title, tpath, _ever in rows:
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
        # The estimate as a file, for a caller that has to DECIDE on it rather
        # than read it (#192). The two-stage build asks this stage what pass two
        # would cost and abandons the pass if the remaining cap cannot cover it;
        # scraping that number out of the table below would make a spend decision
        # depend on a column width. The human table is unchanged and still prints.
        #
        # It is written before the table, so a caller reading the file has it
        # even if stdout is being consumed by something that stops early. `model`
        # and `cap` travel with it because an estimate is a claim about a model
        # and a limit, and the abandonment message has to name both.
        write_estimate(args, prompt_version, len(prompts), total_in, out_tok, cap)
        exact = "exact (count_tokens)" if have_key else "APPROXIMATE (no API key; chars/3.5)"
        print(f'[dry-run] "{args.concept}" — {len(prompts)} papers, prompt {prompt_version}')
        print(f"  input tokens:  {total_in:,}  [{exact}]")
        print(f"  output tokens: {out_tok:,}  [estimated {EST_OUTPUT_TOKENS}/paper"
              f"{' + thinking' if args.thinking else ''}]")
        # Rates come from `rates_for` rather than straight out of PRICING, so the
        # table shows what today's calls are billed at (one family is on
        # introductory pricing), and the marker is on the key that prices the
        # SELECTED model rather than on a string equal to it: Stages F and G pass
        # a dated snapshot, and a marker keyed on equality quietly marked nothing
        # at all. #205's habit — print the key that was found, not only the money.
        priced_as = pricing_key(args.model)
        print(f"\n  {'model':<20} {'in $':>8} {'out $':>8} {'total':>9}   vs cap ${cap:g}")
        print("  " + "-" * 62)
        for m in PRICING:
            r_in, r_out = rates_for(m)
            ci = total_in / 1e6 * r_in
            co = out_tok / 1e6 * r_out
            flag = "OVER CAP" if ci + co > cap else "ok"
            mark = " <- selected" if m == priced_as else ""
            print(f"  {m:<20} {ci:>8.2f} {co:>8.2f} {ci + co:>9.2f}   {flag}{mark}")
        if priced_as != args.model:
            print(f"  ({args.model} is a dated snapshot of {priced_as} and bills at its rates)")
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
    text_path_by_id = {aid: tpath for _, aid, _, tpath, _ever in rows}
    extractor_by_id = {aid: ever for _, aid, _, _, ever in rows}
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
        # occur in the text we sent, or it is not evidence. The stamp records
        # what was true of that moment — where it matched, and the digest of the
        # bytes it matched against — so it can be re-checked by somebody who was
        # not here (migration 015). A quote we never looked for leaves all four
        # NULL, and NULL renders stale, which is exactly the claim it deserves.
        verified = False
        span = None
        digest = None
        if ex.defines_concept and ex.verbatim_quote:
            full, digest = read_grounding_text(text_path_by_id[aid])
            span = grounded_span(full, ex.verbatim_quote)
            verified = span is not None

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
            "quote_start": span[0] if span else None,
            "quote_end": span[1] if span else None,
            "quote_text_digest": digest,
            # The extractor version of the TEXT, read from the paper's row rather
            # than from the running extract_text: this stage did not produce the
            # file, and extract_text skips papers already extracted, so the
            # running version is not reliably the one that made these bytes.
            "quote_extractor_version": extractor_by_id.get(aid),
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

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
- The rebuild is ATOMIC (issue #2). Every candidate is classified into memory
  first; the DELETE of the old edges and the INSERT of the new set share one
  short transaction at the very end, entered only when the run has consumed its
  whole candidate list. A spend-cap hit aborts with nothing swapped and marks a
  mid-build row aborted_spend_cap; ten consecutive call failures abort with
  nothing swapped; a swept source none of whose reference fetches got an answer
  of any kind aborts before anything is bought (#217: the floor measures call
  success, not corpus shape — a 404 is an answer, and failures are never
  cached); and ANY paper whose reference fetch failed aborts the run at the end
  of the sweep, before a single classification is bought (#219: the same
  accounting identity that guards the swap, carried back to the sweep — a
  candidate list built without every paper's references is not a smaller map,
  it is an unknown one). Under --dry-run the floors report instead of aborting:
  the dry run's exit code never depends on corpus data. The slow, failure-prone
  half — S2 fetches and LLM calls — happens on no database connection at all.

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
from stage_b_extract import cost_usd, pricing_key  # noqa: E402

# Enough failures to prove it is the call and not the edge.
CONSECUTIVE_FAILURE_LIMIT = 10

S2 = "https://api.semanticscholar.org/graph/v1"
S2_PAUSE_S = 1.1  # polite spacing on the shared unauthenticated pool
EST_OUTPUT_TOKENS = 200


class EdgeClass(BaseModel):
    edge_type: Literal["extends", "contests", "narrows", "renames", "merges", "migrates"] = Field(
        description="How the newer (descendant) paper's treatment relates to the older one."
    )
    # No ge/le bounds, on purpose (#216): pydantic would turn an out-of-range
    # value into a parse failure, which the loop counts as a failed CALL and
    # feeds the consecutive-failure guard. The call answered; it is the ANSWER
    # that is unusable, and the loop counts that as "no classification" instead.
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
    """Write a bought classification. Never called for a failed call or an
    out-of-range answer — `cached_classification` would refuse either as a miss,
    so storing one would re-buy its candidate on every future run (#216)."""
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


def s2_cache_file(arxiv_id: str) -> Path:
    """Where this paper's reference answer is kept, if it has one.

    Factored out of `fetch_references` because the sweep PROBES it before
    calling (#219): a paper this file answers for cost no call, and the abort
    has to say how many of each. One spelling of the path, so the probe can
    never disagree with the read that follows it.
    """
    return data_dir() / "s2_cache" / f"{arxiv_id.replace('/', '_')}.json"


def fetch_references(arxiv_id: str) -> "list[dict] | None":
    """References with citation contexts, cached on disk. The shared unauthenticated
    Semantic Scholar pool throttles hard on repeat runs, so cache to survive them.

    Three outcomes, and the caller's floor runs on the distinction (#217):
    a list of references; an HONEST EMPTY `[]` — HTTP 200 with no data, or a
    404, because Semantic Scholar does not hold every arXiv paper and "no
    citation data for this one" is an answer, not a broken run; or None for a
    transport FAILURE — retries exhausted, a connection error, any non-404 HTTP
    error. Only answers are cached. The old code cached `[]` on every
    exception, which was the entire cache-poisoning mechanism: an outage's
    failures replayed from disk forever, indistinguishable from honest data,
    and the abort text taught operators to delete entries that may have been
    real answers. The claims cache beside this states the house law: caching a
    failure would make the failure permanent and free. A re-run after an
    outage retries exactly the failed papers (paced by S2_PAUSE_S) and hits
    cache for the rest. Legacy `[]` entries written during past outages stand —
    they cannot be told from honest empties, and invalidating every honest
    entry to chase a suspicion would cost a full re-sweep per map; an operator
    who suspects one deletes that file and the re-fetch answers honestly.
    """
    f = s2_cache_file(arxiv_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    try:
        data = get_json(f"{S2}/paper/arXiv:{arxiv_id}/references", {
            "fields": "contexts,intents,isInfluential,title,externalIds", "limit": 1000,
        })
        refs = data.get("data", [])
    except Exception as e:
        # get_json raises requests.HTTPError from raise_for_status, which
        # carries the response; only a 404 is an answer. Everything else —
        # including the RuntimeError it raises when retries run out — is a
        # failure, returned as None and written nowhere.
        resp = getattr(e, "response", None)
        if resp is not None and getattr(resp, "status_code", None) == 404:
            refs = []
        else:
            print(f"    ⚠ reference fetch failed for {arxiv_id} "
                  f"({type(e).__name__}: {str(e)[:120]}); not cached, a re-run retries it")
            return None
    f.write_text(json.dumps(refs), encoding="utf-8")
    return refs


def mark_aborted_spend_cap(gen_id: int) -> bool:
    """Record a cap abort on the genealogy row, on a fresh connection.

    Guarded to the mid-build state: only a 'running' row takes the mark, which
    is the first thing ever to write this status (it has been a legal value
    since migration 001). A published map this stage was run against by hand
    keeps its status — its edges were not touched, so 'complete' is still the
    truth about it, and migration 025's CHECK would refuse the write on a
    current row anyway.
    """
    c = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    try:
        cur = c.execute(
            "UPDATE genealogies SET status='aborted_spend_cap', updated_at=now() "
            "WHERE id=%s AND status='running'", (gen_id,))
        return cur.rowcount == 1
    finally:
        c.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage D: classify genealogy edges.")
    ap.add_argument("concept")
    ap.add_argument("--model", default=env("LLM_MODEL", "claude-sonnet-5"))
    ap.add_argument("--dry-run", action="store_true", help="find candidate edges; classify none")
    args = ap.parse_args()

    # An unpriced --model (or LLM_MODEL) is refused before a candidate is fetched
    # or a call is made (#205): what this stage prints is scraped into the map's
    # record and checked against the cap, so a figure it cannot compute honestly
    # is worse than a stage that will not start.
    pricing_key(args.model)

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

    # Every read this stage needs is now in memory, and nothing below touches
    # the database again until the swap at the very end. The reference sweep can
    # take ten minutes or more under rate limiting and the classification loop
    # is longer still; holding a connection across a long external phase once
    # left a transaction idle and Postgres terminated it. So: no connection at
    # all through the slow, failure-prone half.
    conn.close()

    print(f'Finding citation links among {len(corpus_ids)} defining papers '
          f"across {len(nodes)} concept-states…")
    if outside:
        print(f"  ({outside} paper(s) define this concept but are not in this map, "
              f"so they are not candidates. That is what --corpus on Stage C means.)")

    # candidate edges: citing (newer, descendant) -> cited (older, ancestor), cross-node.
    # The sweep also keeps the books the floors below read: which sources
    # contributed papers, how many of each source's fetches got an honest
    # answer of any kind, whether any paper of a source returned a reference at
    # all, and — since #219 — which answers came from a call and which from
    # disk. `fetch_references` has two provenances behind one return value, so
    # a count taken from it alone cannot tell a sweep that worked from a sweep
    # that read one cached entry while every call failed.
    candidates = []
    papers_by_source: dict[str, int] = {}
    honest_by_source: dict[str, int] = {}
    sources_with_refs: set[str] = set()
    failed_fetches = answered_live = answered_cache = 0
    for citing in corpus_ids:
        # Probed before the call, never inferred after it: the file is written
        # by the fetch itself, so asking afterwards would call every fresh
        # answer a cache hit.
        from_cache = s2_cache_file(citing).exists()
        refs = fetch_references(citing)
        # papers.source does not exist yet: every paper this stage can see was
        # fetched from arXiv, so the label is a constant until F7's migration
        # adds the column, at which point it is read per paper. The floor is
        # built per-source NOW because designing it into an atomic rebuild is
        # cheaper than retrofitting it (#2's F7 note), and because the failure
        # it catches — an id scheme S2 rejects for every paper of one source —
        # produces no candidates at all, which no floor over candidates can see.
        src = "arxiv"
        papers_by_source[src] = papers_by_source.get(src, 0) + 1
        if refs is None:
            failed_fetches += 1
            time.sleep(S2_PAUSE_S)
            continue
        if from_cache:
            answered_cache += 1
        else:
            answered_live += 1
        honest_by_source[src] = honest_by_source.get(src, 0) + 1
        if refs:
            sources_with_refs.add(src)
        for ref in refs:
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

    # THE FLOORS, measuring call success rather than corpus shape (#217). The
    # old floor counted references returned — a fact about the corpus — when
    # the failure it exists to catch is the call failing — a fact about the
    # transport. A corpus S2 genuinely holds no references for (young or
    # obscure papers, #186's shape) could then never complete this stage, with
    # an error blaming an outage that never happened. fetch_references' own
    # per-paper comment had it right all along: a 404 is an answer. No ratio
    # anywhere, nothing to recalibrate (decisions 24, 25). #219 added the third
    # arm: measuring call success is not the same as requiring it, and the
    # per-source floor fed on `honest_by_source` could be satisfied by answers
    # no call was made for.
    would_abort: list[str] = []

    def floor(sentence: str) -> None:
        # Under --dry-run a floor is a finding for the report, never an exit:
        # the engineering rule's contract is "estimates cost without calling
        # the LLM", and the estimate's answer may be "nothing — the real run
        # would abort". A dry run's exit code must not depend on corpus data.
        if args.dry_run:
            would_abort.append(sentence)
        else:
            sys.exit("\nAborting: " + sentence)

    # A source that got no honest answer at all has its own message below,
    # which names the source; it is the total case of the same fault the
    # partial abort catches, said better, so the partial arm stands down for it
    # rather than saying it twice. Computed rather than inferred from `floor`
    # having exited, because under --dry-run nothing exits.
    all_failed_sources = [s for s in papers_by_source
                          if honest_by_source.get(s, 0) == 0]
    for src in sorted(papers_by_source):
        if honest_by_source.get(src, 0) == 0:
            # The transport floor: at least one paper and not one honest
            # answer of any kind — every fetch failed. Degenerate zero,
            # nothing to calibrate. This is the incident-12 shape the floor
            # was built for, and it can never fire on a corpus of honest
            # 404s, because those are answers.
            floor(f"all {papers_by_source[src]} reference fetches for the swept "
                  f"{src} paper(s) failed — not one answered, not even with an "
                  f"empty list. That is the reference "
                  f"call failing for the whole source, not the corpus. The map's "
                  f"edges have NOT been touched, and failures are never cached, "
                  f"so a re-run after the cause is fixed retries exactly these "
                  f"papers.")
        elif src not in sources_with_refs and sources_with_refs:
            # The differential arm, for F7's actual failure: every honest
            # answer for this source empty while another source proved the
            # call works is an id scheme S2 rejects wholesale, not that many
            # papers' bad luck. Dormant today — one source, no comparator —
            # live the moment papers.source exists.
            floor(f"every honest answer for the {papers_by_source[src]} swept "
                  f"{src} paper(s) was empty ({honest_by_source[src]} answered, "
                  f"0 with references) while another source returned references. "
                  f"That looks like an id scheme the reference call rejects for "
                  f"every {src} paper. The map's edges have NOT been touched.")
    if failed_fetches and not all_failed_sources:
        # #219: the accounting identity that guards the swap, carried back to
        # the sweep. The swap replaces the WHOLE edge set, so a candidate list
        # assembled without one paper's references does not build a smaller
        # map, it builds an unknown one: the edges those papers would have
        # contributed are indistinguishable from edges that do not exist, and
        # the map ends up asserting their absence. Zero failures is the only
        # number that permits proceeding — there is no ratio here to calibrate,
        # for the reason decisions 24 and 25 give.
        #
        # Aborting here, before the classification loop, is free precisely
        # because of #217: failures are never cached, so a re-run retries
        # exactly these papers and reads the rest from disk. Measured on the
        # ticket: the same corpus previously paid for two classifications and
        # swapped two edges over a map that had thirty.
        attempted = failed_fetches + answered_live
        floor(f"{failed_fetches} of the {attempted} reference fetch(es) this run "
              f"attempted failed, so the sweep is incomplete. Of the swept "
              f"papers, {answered_live + answered_cache} answered "
              f"({answered_live} from the reference call, {answered_cache} "
              f"already on disk from an earlier run) and {failed_fetches} did "
              f"not answer at all. A map built from a partial sweep cannot be "
              f"told from a map that genuinely has fewer edges, and this swap "
              f"replaces every edge, so the run stops before buying anything. "
              f"The map's edges have NOT been touched. The failed fetches were "
              f"not cached, so a re-run retries exactly those {failed_fetches} "
              f"paper(s) and reads the rest from cache; anything classified by "
              f"an earlier run is still cached, so the retry re-buys none of "
              f"it.")
    if papers_by_source and not sources_with_refs and not failed_fetches and not would_abort:
        # Everything empty, everything honest: the corpus S2 holds no
        # references for. The honest edge-less map this corpus produced
        # before #2's floor, now with the reason stated.
        print(f"  ⚠ all {len(corpus_ids)} swept paper(s) returned no reference "
              f"data from S2 (honest empties, not failures); this map will "
              f"have no edges.")

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
            # A floor finding is part of the report the human asked for, not a
            # failure of the reporter (#217): the run still exits 0.
            for sentence in would_abort:
                print(f"[dry-run] the real run would abort at the sweep: {sentence}")
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

    # EVERYTHING IS CLASSIFIED INTO MEMORY FIRST; the database is not touched
    # until the swap at the end. Two incidents shaped this. On 2026-07-31 the
    # account ran out of credit, all 305 classifications returned 400, and the
    # map was left with 27 concept-states and no edges at all: the DELETE had
    # already run and there was nothing to put back. The interim fix deleted on
    # first success, which narrowed that window and could not close it — a cap
    # hit at edge 40 of 305 still left a 40-edge map that Stage E would publish
    # (#2). Now the previous edges exist until the replacement set is complete.
    # Destroy nothing until you can replace everything.
    #
    # All-or-nothing costs money only if classifications are unpaid-for on
    # abort, which is what the disk cache (#172) exists to prevent: an abort
    # here costs wall clock and no dollars, because everything bought before it
    # is cached and a re-run reuses it.
    spend = 0.0
    to_write = []
    skipped = failed = 0
    consecutive_failures = 0
    reused = bought = 0
    print()
    for done, (e, key, hit) in enumerate(zip(candidates, keys, hits), 1):
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
                failed += 1
                consecutive_failures += 1
                print(f"  {e['src']} -> {e['dst']}: classification failed, skipped "
                      f"({type(exc).__name__}: {str(exc)[:200]})")
                # CONSECUTIVE means consecutive now: the counter resets on any
                # answered call. The old guard tripped only when `written == 0`,
                # so one success out of 305 immunised the whole run against it
                # (#2), and `failures` was cumulative despite the constant's
                # name, so ten failures scattered across three hundred healthy
                # candidates could trip a guard called CONSECUTIVE.
                if consecutive_failures == CONSECUTIVE_FAILURE_LIMIT:
                    sys.exit(f"\nAborting: {consecutive_failures} classifications in a row "
                             f"failed. This is the call failing, not the edges. The map's "
                             f"existing edges have NOT been touched, and everything "
                             f"classified before the failures is cached, so a re-run "
                             f"after the cause is fixed re-buys none of it.")
                continue
            consecutive_failures = 0
            spend += cost_usd(args.model, resp.usage.input_tokens, resp.usage.output_tokens)
            ec = resp.parsed_output
            if ec is None:
                skipped += 1
                print(f"  {e['src']} -> {e['dst']}: no classification")
            elif not 0.0 <= ec.confidence <= 1.0:
                # A parse that succeeded around a confidence outside 0..1 is an
                # unusable ANSWER, not a failed call (#216). `edges.confidence`
                # carries CHECK (>= 0 AND <= 1), so letting it into `to_write`
                # crashes the swap with a raw constraint error after the whole
                # run is paid; and `cached_classification` refuses out-of-range
                # as a miss, so caching it would re-buy this candidate on every
                # future run, forever. It is counted exactly like parsed_output
                # None — skipped, never cached, never written — and the call
                # still resets the consecutive counter above, because it
                # answered. The comparison also catches NaN, which fails every
                # bound. Confidence is the one hole: edge_type is Literal-typed
                # (a bad one fails the parse), and no constraint bounds
                # rationale.
                skipped += 1
                print(f"  {e['src']} -> {e['dst']}: no classification "
                      f"(the model answered confidence {ec.confidence!r}, outside "
                      f"0..1 — a value the edges table would refuse; not cached)")
                ec = None
            else:
                # Only ever after a parsed, in-range answer. A cache written from
                # a failure or an unusable answer would make it permanent and
                # free, which is the one thing worse than paying for it again.
                store_classification(key, ec, args.model)
                bought += 1
        else:
            reused += 1

        if ec is not None:
            # Evidence quotes must ground against OUR extracted text (Stage E), so we
            # store each paper's Stage-B definition quote — both already string-verified.
            # The Semantic Scholar citation context is a classification signal only: it
            # comes from S2's PDF extraction and would not match our LaTeX text — so we
            # keep it as the edge's BASIS (what/how), not as a groundable quote. The
            # rationale is the model's one-sentence reading of that basis. Neither may
            # ever wear the verified stamp; the app renders both as unverified context.
            to_write.append((gen_id, e["src_node"], e["dst_node"], ec.edge_type,
                             src["paper_id"], dst["paper_id"], src["quote"], dst["quote"],
                             ec.confidence, ec.rationale,
                             "\n\n".join(e["contexts"]) or None))
            # `spend` is the run's running total, so a cached edge says where the
            # answer came from BEFORE the number, or the number reads as its price.
            print(f"  {ec.edge_type.upper():<9} {e['src']} -> {e['dst']}  "
                  f"conf={ec.confidence:.2f}  "
                  f"({'from cache, run ' if hit is not None else ''}spend ${spend:.3f})")
            print(f"            {ec.rationale}")

        if spend > cap:
            # An abort, not a break (#2): a cap is a limit on a whole run, and a
            # run it stopped did not produce a map. The classification just paid
            # for is already cached, so the money is kept even though the run is
            # not.
            print(f"\n⚠ SPEND CAP HIT (${spend:.2f} > ${cap:g}) — aborting with nothing swapped.")
            marked = mark_aborted_spend_cap(gen_id)
            sys.exit(f"The cap was reached at candidate {done} of {len(candidates)}. The "
                     f"map's edges are exactly as this run found them"
                     + (", and the row is marked aborted_spend_cap."
                        if marked else
                        "; the row was not mid-build, so its status was left alone.")
                     + " Everything classified before the cap is cached, so a re-run "
                       "under a higher cap re-buys none of it.")

    # THE SWAP, guarded by an accounting identity rather than a proportion: it
    # happens only if the run consumed its whole candidate list. Nobody can say
    # whether 60% of candidates classifying is a healthy run or a broken one —
    # this project has recalibrated a threshold four times to no effect — but
    # "every candidate was looked at" needs no number choosing, and every abort
    # above leaves the identity unsatisfiable by exiting before this line.
    # Beside it, the degenerate floor at zero, in the posture of Stage E's
    # all-reads-failed refusal: at least one candidate and not one classified is
    # a broken dependency, whatever mixture of failures and non-answers it wore.
    if candidates and not to_write:
        sys.exit(f"\nAborting: {len(candidates)} candidate(s) and not one classified "
                 f"({failed} failed, {skipped} returned no classification). The map's "
                 f"existing edges have NOT been touched.")
    if len(to_write) + skipped + failed != len(candidates):
        sys.exit(f"\nAborting: this run cannot account for its own candidates "
                 f"({len(to_write)} classified + {skipped} unclassified + {failed} failed "
                 f"!= {len(candidates)}). That is a bug in this stage, not in the data. "
                 f"Nothing was swapped.")

    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    with conn.transaction():
        conn.execute("DELETE FROM edges WHERE genealogy_id=%s", (gen_id,))
        for row in to_write:
            conn.execute("""
                INSERT INTO edges (genealogy_id, source_node, target_node, edge_type,
                                   source_paper_id, target_paper_id, source_quote,
                                   target_quote, confidence, verified, rationale,
                                   citation_context)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s,%s)
            """, row)
    conn.close()
    left_out = (f"; {failed} failed and {skipped} unclassifiable candidate(s) are not "
                f"in the set" if failed or skipped else "")
    print(f"\nDone: {len(to_write)} edges classified ({reused} reused from cache, "
          f"{bought} newly bought), swapped in as one set{left_out}. "
          f"Spend ${spend:.4f}. Run Stage E to ground and assemble.")


if __name__ == "__main__":
    main()

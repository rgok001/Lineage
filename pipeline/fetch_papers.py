"""Acquisition: download arXiv source for a selected corpus. Writes to `papers`.

Input is a corpus JSON produced by corpus_select.py (--json). For each paper we
download the arXiv source — LaTeX preferred, PDF fallback — store the raw file
under DATA_DIR/raw/, and upsert a row into the papers table.

HARD RULE (CLAUDE.md): arXiv gets at most one request every 3 seconds, a proper
User-Agent (set in common.session), and exponential backoff on 429/5xx. "One
request" means one HTTP request and not one call of a helper that may retry
inside itself (#231), so the throttle is passed into `get_bytes` and runs before
every attempt.

Downloading and text extraction are separate stages: this script only fetches +
records. It skips papers already fetched unless --force, so re-runs are cheap.

Usage:
  python pipeline/fetch_papers.py corpus.json
  python pipeline/fetch_papers.py corpus.json --limit 10
  python pipeline/fetch_papers.py corpus.json --dry-run
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CONSECUTIVE_FAILURE_LIMIT, REPO_ROOT, data_dir, env, get_bytes)

ARXIV_EPRINT = "https://arxiv.org/e-print/{id}"  # LaTeX source (usually a .tar.gz)
ARXIV_PDF = "https://arxiv.org/pdf/{id}"          # fallback when no source posted
RATE_LIMIT_S = 3.0  # hard rule: 1 arXiv request / 3 s

# The statuses that mean arXiv answered about THIS PAPER, named the way
# `get_bytes` names 403/404/410 — never inferred from "a response object exists"
# (#239). That inference cost us the whole outage bound: an authenticating proxy
# whose credential expired answers every request 407, and 150 papers of 407 ran
# to the end of the corpus with no abort, 7.5 minutes, exit 0, each line telling
# the operator "arXiv answered HTTP 407 for this paper" about a service the run
# never reached (measured at c5e0325). A response proves something answered; only
# a named status proves who.
#
# 451 is the whole list, and the list is short because `get_bytes` already owns
# the rest: 403 (withheld source), 404 (no such id) and 410 (gone) return None
# from it, which is the "no source available" branch below and resets the counter
# there. 451 is arXiv withholding a paper for legal reasons — an answer about a
# paper exactly as a 404 is, and a corpus of withheld sources must never look
# like an outage (#235, which this narrows rather than reverses).
#
# 400/401/407/408 and stray 3xx are deliberately out. Every one of them is
# something a hop between us and arXiv emits about the connection rather than
# about a paper, and a 400 arXiv itself sent would mean our request was malformed
# for every paper alike — an abort is the right answer to that too.
ARXIV_ANSWERS_ABOUT_PAPER = (451,)

_last_request = 0.0


def pace_arxiv() -> None:
    """Block until RATE_LIMIT_S has passed since the last arXiv request, and
    stamp this one as it goes out.

    This is the whole of the hard rule, in one place, and `get_bytes` calls it
    before every attempt it makes (#231). It used to wrap the call instead: the
    wait happened once per `get_bytes`, so when #223 gave that helper five
    attempts, the retries went out inside the window the rule reserves — the
    first retry re-hit arXiv 2.0 seconds after the failed request, measured with
    a real clock, because the backoff schedule starts at 2s and the throttle
    could not see it. The stamp is taken before the request rather than after it
    for the same reason: the rule is about how often we ASK, and a slow response
    is not permission to ask again sooner.
    """
    global _last_request
    wait = RATE_LIMIT_S - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def throttled_get(url: str) -> tuple[bytes, str] | None:
    """get_bytes, but never faster than one arXiv request per RATE_LIMIT_S."""
    return get_bytes(url, pace=pace_arxiv)


ARXIV_NEW_RE = re.compile(r"^(\d{2})(\d{2})\.\d{4,5}$")          # 1706.03762
ARXIV_OLD_RE = re.compile(r"^[a-z\-\.]+/(\d{2})(\d{2})\d{3}$")   # cs/0701907


def arxiv_year(arxiv_id: str) -> int | None:
    """Submission year encoded in the arXiv id itself (YYMM...)."""
    m = ARXIV_NEW_RE.match(arxiv_id) or ARXIV_OLD_RE.match(arxiv_id)
    if not m:
        return None
    yy = int(m.group(1))
    return 1900 + yy if yy >= 91 else 2000 + yy


def earliest_year(arxiv_id: str, openalex_year: int | None) -> int | None:
    """The earliest credible date for a paper.

    A genealogy is ordered by when an idea first appeared publicly, so the
    earlier of the two dates we hold is both the right semantics and the safer
    one. OpenAlex metadata is sometimes wrong in the *forward* direction (it
    dated "Attention Is All You Need" to 2025), and a future date corrupts the
    whole chronology. Taking the minimum neutralises that, while still honouring
    genuinely old work posted to arXiv years later, where OpenAlex holds the
    true, earlier date and the arXiv id does not.
    """
    ay = arxiv_year(arxiv_id)
    candidates = [y for y in (ay, openalex_year) if y]
    return min(candidates) if candidates else None


def detect_format(content: bytes) -> str | None:
    if content[:5] == b"%PDF-":
        return "pdf"
    if content[:2] == b"\x1f\x8b":  # gzip magic — a source tarball / gzipped .tex
        return "latex"
    return None


def fetch_source(arxiv_id: str) -> tuple[bytes, str, str] | None:
    """Return (content, source_format, ext) or None if nothing downloadable."""
    got = throttled_get(ARXIV_EPRINT.format(id=arxiv_id))
    if got:
        content, _ = got
        fmt = detect_format(content)
        if fmt == "latex":
            return content, "latex", "tar.gz"
        if fmt == "pdf":  # some papers serve a PDF from the e-print endpoint
            return content, "pdf", "pdf"
    got = throttled_get(ARXIV_PDF.format(id=arxiv_id))
    if got:
        content, _ = got
        if content[:5] == b"%PDF-":
            return content, "pdf", "pdf"
    return None


# `papers.cited_by_count` is a SNAPSHOT, and this statement is the only writer of
# it in the repository (issue #185). It records what OpenAlex said on the day the
# paper entered this system, timestamped by the `fetched_at` written beside it,
# and nothing refreshes it afterwards: it moves only if some later trace happens
# to fetch the same paper again. Selection does not read it — corpus_select.py
# takes citation counts live from OpenAlex on every run — and since #185 no query
# in the pipeline orders by it either, so it is stored provenance and not an
# input to anything.
#
# Named here because the next person wanting an age-normalised figure for the
# report will reach for this column, and a stale citation count on a table whose
# whole subject is how citation counts mislead is exactly the wrong number to
# reach for. If a figure needs current citations, fetch them; do not read these.
UPSERT = """
INSERT INTO papers (arxiv_id, openalex_id, title, year, cited_by_count,
                    source_format, raw_path, fetched_at)
VALUES (%(arxiv_id)s, %(openalex_id)s, %(title)s, %(year)s, %(cited_by_count)s,
        %(source_format)s, %(raw_path)s, now())
ON CONFLICT (arxiv_id) DO UPDATE SET
    openalex_id    = EXCLUDED.openalex_id,
    title          = EXCLUDED.title,
    year           = EXCLUDED.year,
    cited_by_count = EXCLUDED.cited_by_count,
    source_format  = EXCLUDED.source_format,
    raw_path       = EXCLUDED.raw_path,
    fetched_at     = now()
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch arXiv source for a corpus (LaTeX-first).")
    ap.add_argument("corpus", help="corpus JSON from corpus_select.py --json")
    ap.add_argument("--limit", type=int, help="fetch at most N papers")
    ap.add_argument("--force", action="store_true", help="re-download even if a raw file exists")
    ap.add_argument("--dry-run", action="store_true", help="list what would be fetched; no downloads/DB")
    args = ap.parse_args()

    papers = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    if args.limit:
        papers = papers[:args.limit]

    raw_root = data_dir() / "raw"
    if args.dry_run:
        print(f"[dry-run] would fetch {len(papers)} papers into {raw_root}")
        for p in papers:
            print(f"  {p['arxiv_id']:<16} {(p.get('title') or '?')[:70]}")
        return

    raw_root.mkdir(parents=True, exist_ok=True)
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)

    fetched = skipped = failed = replaced = 0
    # #231's bound on an outage, the same one and the same reason as the
    # reference sweep's. A total arXiv outage used to cost 150 papers x 10
    # requests: measured at 17877b8, 750 requests and about 82 minutes of
    # waiting, ending "0 fetched, 150 failed" and exiting 0, against a
    # definition of done of fifteen minutes for a whole trace.
    #
    # **The counter counts every call that ended without an answer about the
    # paper, and only a status in ARXIV_ANSWERS_ABOUT_PAPER resets it** (#235,
    # narrowed by #239). It once said "transport failures and nothing else" and
    # was not — ten papers arXiv answered 451 about aborted the stage blaming
    # the download — and the repair for that then reset on any status at all,
    # which let a proxy answering 407 spend the whole corpus. A named list is
    # the only thing that tells those two apart. It cannot hide a real outage:
    # 429 and 5xx never arrive here as a status, because `get_bytes` retries
    # them five times and then raises the transport-class RuntimeError, which is
    # a service that failed rather than a paper that was answered about. A
    # skipped paper makes no request, so it neither counts nor resets.
    consecutive_failures = 0
    last_failure = None
    for i, p in enumerate(papers, 1):
        aid = p["arxiv_id"]
        stem = aid.replace("/", "_")  # old IDs like cond-mat/9910332 have a slash
        existing = next(raw_root.glob(f"{stem}.*"), None)
        if existing and not args.force:
            print(f"[{i}/{len(papers)}] {aid}: already have {existing.name}, skipping")
            skipped += 1
            continue

        print(f"[{i}/{len(papers)}] {aid}: fetching…")
        # One unfetchable paper must never abort the corpus. arXiv can refuse,
        # rate-limit, time out or serve something broken for a single id; log it,
        # count it, keep going. The corpus is large enough to absorb a few losses.
        try:
            result = fetch_source(aid)
        except Exception as e:
            # 240, not 120: `get_bytes` raises "Gave up after 5 attempts: <url> —
            # last failure <class>: <message>", and a 120-character slice cuts
            # off inside the URL, so every outage printed the wrapper and hid the
            # cause (the same measurement that resized Stage D's slice).
            note = f"{type(e).__name__}: {str(e)[:240]}"
            failed += 1
            # `.response` rather than an isinstance test, as fetch_references
            # does it: the RuntimeError `get_bytes` raises when its retries run
            # out carries none. But a response only says something answered, so
            # the status has to be one we named before the run can call it arXiv
            # answering about this paper (#239).
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in ARXIV_ANSWERS_ABOUT_PAPER:
                print(f"    ✗ arXiv answered HTTP {status} for this paper, skipping")
                consecutive_failures = 0
                continue
            # An unnamed status is counted, and is described as what we can
            # actually see: a status came back from somewhere on the way to
            # arXiv. Naming arXiv here sent an operator to arXiv's status page
            # over an expired proxy credential (#239).
            if status is not None:
                note = (f"HTTP {status} from something between us and arXiv — "
                        f"not a status arXiv answers about a paper with")
            print(f"    ✗ fetch failed ({note}), skipping")
            consecutive_failures += 1
            last_failure = f"{aid} ({note})"
            if consecutive_failures == CONSECUTIVE_FAILURE_LIMIT:
                conn.close()
                sys.exit(
                    f"\nAborting: {consecutive_failures} arXiv fetches in a row failed, so "
                    f"the run stopped at paper {i} of {len(papers)} instead of spending the "
                    f"rest of the corpus proving the same thing. That is the fetch "
                    f"failing, not the papers: a paper arXiv itself answered about — a "
                    f"source it withholds, an id it does not have — resets the counter, "
                    f"so {CONSECUTIVE_FAILURE_LIMIT} in a row means "
                    f"{CONSECUTIVE_FAILURE_LIMIT} calls that arXiv never answered about "
                    f"a paper. A status from something on the way to arXiv counts here "
                    f"rather than resetting, because it says nothing about the paper, so "
                    f"read the last failure before assuming arXiv is down: it was "
                    f"{last_failure}.\n\n"
                    # The counts this run kept, not a sentence about the run it
                    # was expected to be (#236). `--force` re-downloads over
                    # files that are already there, so "nothing has been deleted
                    # or overwritten" was false whenever it was used: measured,
                    # 2 raw files replaced and 2 `papers` rows upserted before
                    # this printed. Nothing is deleted on any path, so that half
                    # of the sentence stands on its own.
                    f"What this run did: {fetched} paper(s) were downloaded and recorded "
                    f"before it stopped and are on disk, {skipped} were already there, "
                    + (f"and {replaced} existing raw file(s) were replaced by --force "
                       f"(their papers rows were updated to match). Nothing has been "
                       f"deleted. A re-run starts at the papers this one did not reach "
                       f"and, with --force, downloads the earlier ones again."
                       if replaced else
                       "and nothing has been deleted or overwritten. A re-run after the "
                       "cause is fixed skips everything already downloaded and starts at "
                       "the papers this one did not reach."))
            continue
        if result is None:
            print(f"    ✗ no source or PDF available")
            failed += 1
            consecutive_failures = 0
            continue
        consecutive_failures = 0

        content, source_format, ext = result
        out = raw_root / f"{stem}.{ext}"
        # Counted before the write, because after it there is nothing left to
        # ask: this is what the abort's "nothing has been deleted or
        # overwritten" is allowed to say (#236). Only --force can reach here
        # over an existing file; without it the loop skipped above.
        if out.exists():
            replaced += 1
        out.write_bytes(content)
        # Store paths relative to DATA_DIR, not the repo: on a deployed worker
        # DATA_DIR is a separate mounted disk (e.g. /data) outside the repo, so
        # relative_to(REPO_ROOT) raised ValueError. DATA_DIR always holds the
        # file, and every reader resolves via data_dir(), so this stays portable.
        rel_path = str(out.relative_to(data_dir())).replace("\\", "/")

        conn.execute(UPSERT, {
            "arxiv_id": aid,
            "openalex_id": p.get("openalex_id"),
            "title": p.get("title"),
            "year": earliest_year(aid, p.get("year")),
            "cited_by_count": p.get("cited_by_count") or 0,
            "source_format": source_format,
            "raw_path": rel_path,
        })
        conn.commit()
        print(f"    ✓ {source_format}, {len(content):,} bytes -> {rel_path}")
        fetched += 1

    conn.close()
    print(f"\nDone: {fetched} fetched, {skipped} skipped, {failed} failed.")

    # ── the zero floor (issue #244) ────────────────────────────────────────
    #
    # A run that ended with nothing on disk and nothing already there is not a
    # corpus of unavailable papers, it is a fetch that did not work, and until
    # now it printed "0 fetched, 150 failed" and exited 0 — so the worker went on
    # to extraction and Stage B against an empty corpus.
    #
    # **It is a floor and not a fraction, and it is deliberately not a fifth
    # calibration of the consecutive-failure bound.** That bound has been tuned at
    # #223, #231, #235 and #239, and a fifth number would be the tell that the
    # number was never the problem: at the transport boundary 150 honest 451s and
    # a middlebox blocking the whole corpus are indistinguishable, so nothing here
    # can tell them apart and this does not try. It asks the one question that has
    # an answer — did this run produce anything at all — and 451 stays on
    # `ARXIV_ANSWERS_ABOUT_PAPER`, because a 451 IS an answer about a paper
    # exactly as a 404 is.
    #
    # What it does not fix, stated because the honest cost belongs beside the
    # guard: a corpus answered 451 all the way through still burns the full
    # politeness delay, ~7.5 minutes for 150 papers. What it no longer does is
    # hand an empty corpus to the stage that spends money.
    #
    # `papers` non-empty is the condition that keeps this from firing on an empty
    # corpus file, where `failed == len(papers)` is 0 == 0 and every count is
    # zero: that is a different fault, upstream in corpus selection, and it is not
    # this stage's to diagnose (the #93 lesson — the bug is at zero).
    if papers and fetched == 0 and skipped == 0 and failed == len(papers):
        sys.exit(
            f"\nThis fetch produced nothing: all {len(papers)} paper(s) failed, none "
            f"was already on disk, and no file was written.\n"
            f"  The last failure was {last_failure or 'not recorded'}.\n"
            "  Whatever the per-paper reasons say, a corpus of which not one paper "
            "could be fetched is\n"
            "  the download failing rather than the papers being unavailable, and "
            "the stages after this\n"
            "  one would read an empty corpus and buy definitions for nothing. "
            "Nothing was deleted.\n"
            "  A re-run after the cause is fixed starts from scratch, since there "
            "is nothing to skip.")


if __name__ == "__main__":
    main()

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

    fetched = skipped = failed = 0
    # #231's bound on an outage, the same one and the same reason as the
    # reference sweep's. A total arXiv outage used to cost 150 papers x 10
    # requests: measured at 17877b8, 750 requests and about 82 minutes of
    # waiting, ending "0 fetched, 150 failed" and exiting 0, against a
    # definition of done of fifteen minutes for a whole trace.
    #
    # **The counter counts calls that ended without an answer about the paper,
    # and any status arXiv answers with resets it** (#235). It said "transport
    # failures and nothing else" and was not: `get_bytes` classifies 200,
    # 403/404/410 and the retryable 429/5xx, and everything else reaches
    # `raise_for_status`, so ten papers arXiv answered 451 about aborted the
    # stage telling the operator the download was failing — measured. A status
    # is arXiv speaking about that paper, exactly as a 404 is, and a corpus of
    # withheld sources must never look like an outage; this is the sweep's own
    # discipline, that the counter resets on any answer. It cannot hide a real
    # outage: 429 and 5xx never arrive here as a status, because `get_bytes`
    # retries them five times and then raises the transport-class RuntimeError,
    # which is a service that failed rather than a paper that was answered
    # about. A skipped paper makes no request, so it neither counts nor resets.
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
            # does it: what matters is whether a response came back, and the
            # RuntimeError `get_bytes` raises when its retries run out carries
            # none. A status here is one `get_bytes` does not classify — 451,
            # 400, a stray 3xx — and it is an answer about this paper (#235).
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None:
                print(f"    ✗ arXiv answered HTTP {status} for this paper, skipping")
                consecutive_failures = 0
                continue
            print(f"    ✗ fetch failed ({note}), skipping")
            consecutive_failures += 1
            last_failure = f"{aid} ({note})"
            if consecutive_failures == CONSECUTIVE_FAILURE_LIMIT:
                conn.close()
                sys.exit(
                    f"\nAborting: {consecutive_failures} arXiv fetches in a row failed, so "
                    f"the run stopped at paper {i} of {len(papers)} instead of spending the "
                    f"rest of the corpus proving the same thing. That is the download "
                    f"failing, not the papers: any status arXiv answers with — a withheld "
                    f"source, an id it does not have, anything else it says about a "
                    f"paper — resets the counter, so only a call that got no answer at "
                    f"all can produce {CONSECUTIVE_FAILURE_LIMIT} in a row. The last "
                    f"failure was {last_failure}.\n\n"
                    f"What this run did: {fetched} paper(s) were downloaded and recorded "
                    f"before it stopped and are on disk, {skipped} were already there, and "
                    f"nothing has been deleted or overwritten. A re-run after the cause is "
                    f"fixed skips everything already downloaded and starts at the papers "
                    f"this one did not reach.")
            continue
        if result is None:
            print(f"    ✗ no source or PDF available")
            failed += 1
            consecutive_failures = 0
            continue
        consecutive_failures = 0

        content, source_format, ext = result
        out = raw_root / f"{stem}.{ext}"
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


if __name__ == "__main__":
    main()

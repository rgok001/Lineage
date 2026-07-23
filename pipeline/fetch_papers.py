"""Acquisition: download arXiv source for a selected corpus. Writes to `papers`.

Input is a corpus JSON produced by corpus_select.py (--json). For each paper we
download the arXiv source — LaTeX preferred, PDF fallback — store the raw file
under DATA_DIR/raw/, and upsert a row into the papers table.

HARD RULE (CLAUDE.md): arXiv gets at most one request every 3 seconds, a proper
User-Agent (set in common.session), and exponential backoff on 429/5xx.

Downloading and text extraction are separate stages: this script only fetches +
records. It skips papers already fetched unless --force, so re-runs are cheap.

Usage:
  python pipeline/fetch_papers.py corpus.json
  python pipeline/fetch_papers.py corpus.json --limit 10
  python pipeline/fetch_papers.py corpus.json --dry-run
"""

import argparse
import json
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, data_dir, env, get_bytes  # noqa: E402

ARXIV_EPRINT = "https://arxiv.org/e-print/{id}"  # LaTeX source (usually a .tar.gz)
ARXIV_PDF = "https://arxiv.org/pdf/{id}"          # fallback when no source posted
RATE_LIMIT_S = 3.0  # hard rule: 1 arXiv request / 3 s

_last_request = 0.0


def throttled_get(url: str) -> tuple[bytes, str] | None:
    """get_bytes, but never faster than one arXiv request per RATE_LIMIT_S."""
    global _last_request
    wait = RATE_LIMIT_S - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    try:
        return get_bytes(url)
    finally:
        _last_request = time.monotonic()


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
    conn = psycopg.connect(env("DATABASE_URL"))

    fetched = skipped = failed = 0
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
            print(f"    ✗ fetch failed ({type(e).__name__}: {str(e)[:120]}), skipping")
            failed += 1
            continue
        if result is None:
            print(f"    ✗ no source or PDF available")
            failed += 1
            continue

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
            "year": p.get("year"),
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

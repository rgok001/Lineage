"""Shared plumbing for pipeline CLI scripts: env loading and polite HTTP."""

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Windows consoles default to cp1252, which chokes on paper titles.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent

# .env lives at the repo root; fall back to .env.example values being absent.
load_dotenv(REPO_ROOT / ".env")

USER_AGENT = "Lineage/0.1 (concept genealogy demonstrator; mailto:{mailto})"


def env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        sys.exit(f"Missing required env var {name} (set it in .env — see .env.example)")
    return val


def mailto() -> str:
    return env("OPENALEX_MAILTO", "lineage@example.com")


_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = USER_AGENT.format(mailto=mailto())
    return _session


def get_json(url: str, params: dict | None = None, max_retries: int = 5) -> dict:
    """GET with exponential backoff on 429/5xx. Raises on persistent failure."""
    delay = 2.0
    for attempt in range(max_retries):
        resp = session().get(url, params=params, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else delay
            print(f"  [http {resp.status_code}] retrying in {wait:.0f}s…", file=sys.stderr)
            time.sleep(wait)
            delay *= 2
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Gave up after {max_retries} retries: {url}")


def get_bytes(url: str, max_retries: int = 5) -> tuple[bytes, str] | None:
    """Binary GET with backoff. Returns (content, content_type), or None when the
    resource simply isn't available to us.

    403 counts as unavailable, not as an error: arXiv refuses source downloads
    for some papers (withheld or licence-restricted). Raising there killed a
    whole 150-paper fetch over one paper; the caller treats None as "no source",
    falls back to the PDF, and moves on.
    """
    delay = 2.0
    for attempt in range(max_retries):
        resp = session().get(url, timeout=120)
        if resp.status_code == 200:
            return resp.content, resp.headers.get("Content-Type", "")
        if resp.status_code in (403, 404, 410):
            return None
        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else delay
            print(f"  [http {resp.status_code}] retrying in {wait:.0f}s…", file=sys.stderr)
            time.sleep(wait)
            delay *= 2
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Gave up after {max_retries} retries: {url}")


VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"


def voyage_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed texts with the Voyage AI hosted embedding API.

    Replaces local embedding models: nothing is loaded into memory or downloaded,
    so the worker stays lightweight. This is what the vector(1024) schema was
    designed for (voyage-3 is 1024-dim). `input_type` is "query" for a search
    query or "document" for corpus/definition text — Voyage embeds the two
    asymmetrically. Batches to respect the API's per-request input limit, and
    retries on transient errors.
    """
    key = env("VOYAGE_API_KEY")
    model = env("VOYAGE_MODEL", "voyage-3")
    out: list[list[float]] = []
    BATCH = 128  # Voyage's max inputs per request
    for start in range(0, len(texts), BATCH):
        chunk = texts[start:start + BATCH]
        delay = 2.0
        for attempt in range(5):
            resp = requests.post(
                VOYAGE_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={"input": chunk, "model": model, "input_type": input_type},
                timeout=120,
            )
            if resp.status_code == 200:
                break
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"  [voyage {resp.status_code}] retrying in {delay:.0f}s…", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue
            sys.exit(f"Voyage API error {resp.status_code}: {resp.text[:300]}")
        else:
            raise RuntimeError("Voyage API: gave up after retries")
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        out.extend(d["embedding"] for d in data)
    if out and len(out[0]) != 1024:
        sys.exit(f"Voyage model {model} returned dim {len(out[0])}, expected 1024 "
                 "(definitions.embedding is vector(1024); pick a 1024-dim model).")
    return out


def data_dir() -> Path:
    """DATA_DIR from env (default ./data), resolved relative to the repo root."""
    raw = os.environ.get("DATA_DIR", "./data")
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p

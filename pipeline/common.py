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
    """Binary GET with backoff. Returns (content, content_type), or None on 404."""
    delay = 2.0
    for attempt in range(max_retries):
        resp = session().get(url, timeout=120)
        if resp.status_code == 200:
            return resp.content, resp.headers.get("Content-Type", "")
        if resp.status_code == 404:
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


def data_dir() -> Path:
    """DATA_DIR from env (default ./data), resolved relative to the repo root."""
    raw = os.environ.get("DATA_DIR", "./data")
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p

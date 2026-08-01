"""Shared plumbing for pipeline CLI scripts: env loading and polite HTTP."""

import getpass
import os
import socket
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


# ── who made a curatorial edit ──────────────────────────────────────────────
#
# Nothing here authenticates anyone, and that is the point. A CLI edit is made
# by whoever holds the .env, so the name goes in `by_asserted` and never in
# `by`, which is reserved for a GitHub login the app got from a session. A
# reader that has not been taught about `by_asserted` sees no `by` and degrades
# to "unattributed"; it can never degrade to "authenticated".


ACTOR_MAX = 64
_ACTOR_BLANK = {c for c in range(0x20)} | {0x7F} | set(range(0x80, 0xA0)) | {0xFEFF}


def tidy_actor_name(raw: object) -> str:
    """Make a name safe to render, in markdown as well as in React.

    LINEAGE_ACTOR is free text and an interior newline escapes the `> `
    blockquote in the export, landing as body prose in a researcher's paper.
    React escapes, markdown does not. Parentheses and the middle dot go too:
    they are the delimiters this product prints a *basis* with, and a label must
    not be able to spell a trust level it does not have. That is a rule about
    our own syntax rather than a blocklist of phrases, which is the distinction
    incidents 10 and 11 were about.

    Anything that is not a string is not a name. `user_edits` is JSONB, so these
    fields really can hold a number, a boolean, an array or null, and a reader
    that raises on one takes a public page down with it.
    """
    if not isinstance(raw, str):
        return ""
    folded = "".join(" " if ord(c) in _ACTOR_BLANK else c for c in raw)
    folded = folded.replace("(", "").replace(")", "").replace("·", "")
    return " ".join(folded.split())[:ACTOR_MAX]


def actor() -> str:
    """The name the running process asserts about itself.

    LINEAGE_ACTOR first, because on Render the container user is noise and an
    operator should be able to say who they are. It is free text supplied by
    whoever holds the .env: a label, not a credential, which is why it is only
    ever written to `by_asserted`.

    Every lookup here can fail and none of them may abort the edit they were
    about to record: getuser() consults the password database when no env var
    names the user, and gethostname() can fail on a misconfigured host. When a
    half is unnameable it is said to be unnameable rather than dropped, because
    "@somehost" is plausible junk that reads like a real name. The return is
    never empty: an entry with no actor key at all would join the legacy set
    that decision 18 fixed at deploy time, and that set must never grow.
    """
    override = tidy_actor_name(os.environ.get("LINEAGE_ACTOR", ""))
    if override:
        return override
    try:
        user = tidy_actor_name(getpass.getuser())
    except Exception:
        user = ""
    try:
        host = tidy_actor_name(socket.gethostname())
    except Exception:
        host = ""
    if user or host:
        return f"{user or 'unknown'}@{host or 'unknown'}"
    return "unnamed process"


def edit_actor(edit: object) -> tuple[str | None, str]:
    """(name, basis) for one genealogies.user_edits entry.

    Twin of `editActor` in app/lib/genealogy.ts; the two must agree on every
    input, well-formed or not. The precedence lives here rather than at each
    print site: `by` outranks `by_asserted`, and an entry carrying neither is a
    legacy entry from before either key was written. Absence is reported as
    absence and never as a claim about origin, which is the "(cli)" the evidence
    page used to fabricate — and junk degrades the same way, downwards, never
    up into an authenticated claim.
    """
    if not isinstance(edit, dict):
        return None, "actor not recorded"
    by = tidy_actor_name(edit.get("by"))
    if by:
        return by, "signed in"
    asserted = tidy_actor_name(edit.get("by_asserted"))
    if asserted:
        return asserted, "from the command line, name not verified"
    return None, "actor not recorded"


def edit_op(edit: object) -> str:
    """Same contract for `op`: it may be missing or hold something that is not a
    string, and neither the export nor the snapshot may crash on one."""
    op = edit.get("op") if isinstance(edit, dict) else None
    return op.strip() if isinstance(op, str) and op.strip() else "unrecorded change"


def edit_when(edit: object) -> str:
    """Same again for `at`. No parsing: the stored ISO string is printed as it
    stands, and anything unusable is named as missing rather than guessed.

    Its twin `editWhen` in app/lib/genealogy.ts does NOT agree with this on every
    input, and the difference is deliberate: the page formats for a viewer's
    locale and so must parse, which means an unparseable string reads there as
    "date not recorded" while this echoes it. Neither invents a date. Any other
    divergence between the twins is a bug.
    """
    at = edit.get("at") if isinstance(edit, dict) else None
    return at.strip() if isinstance(at, str) and at.strip() else "date not recorded"


# What counts as curation, in one place, because four surfaces claim it.
#
# These are exactly the operations the workbench performs: workbench.py's
# subcommands and lib/actions.ts's Server Actions write no other op. `restore` is
# absent on purpose. It is written by restore_genealogy.py and
# restore_snapshot.py, and putting a map back after an incident is not somebody
# curating it — `embedding` carries one restore from incident 12 and nothing
# else, and calling that "1 curatorial change" is the false curation claim this
# change exists to remove, with a number attached to make it worse.
#
# A closed list fails by undercounting: an op nobody adds here is not counted as
# curation. That is the direction this product is allowed to be wrong in, and it
# is why the list is not "anything in user_edits except restore".
CURATORIAL_OPS = ("rename", "merge", "delete-node", "delete-edge", "reclassify")


def is_curatorial(edit: object) -> bool:
    return edit_op(edit) in CURATORIAL_OPS


def curatorial_edits(edits: object) -> list:
    """The subset of a user_edits array that is somebody curating the map."""
    if not isinstance(edits, list):
        return []
    return [e for e in edits if is_curatorial(e)]


def actor_tally(edits: list) -> tuple[list[str], bool]:
    """Who made these edits, counted per actor, highest evidence first.

    Returns the clauses and whether any actor is known at all. Twin of
    `actorTally` in app/lib/genealogy.ts: the export, the CLI export and the two
    pages all say this, and they must all say it the same way.
    """
    rank = {"signed in": 0, "from the command line, name not verified": 1}
    tally: dict[tuple[str | None, str], int] = {}
    for e in edits:
        key = edit_actor(e)
        tally[key] = tally.get(key, 0) + 1
    known = sorted(((n, b, c) for (n, b), c in tally.items() if n),
                   key=lambda t: (rank.get(t[1], 9), -t[2], t[0]))
    parts = [f"{c} by {n} ({b})" for n, b, c in known]
    unattributed = sum(c for (n, _), c in tally.items() if not n)
    if unattributed:
        parts.append(f"{unattributed} with no actor recorded")
    return parts, bool(known)


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


# ── grounding comparison ────────────────────────────────────────────────────

import re as _re
_MATCH_MARK = _re.compile(r"<(?:cit\.?|ref)>")


def _fold(s: str) -> str:
    """Whitespace and citation marks removed. These are the two things that are
    ours rather than the paper's: line wrapping is an artifact of extraction, and
    a citation mark stands where the paper had a citation. Nothing else is folded,
    so a paraphrase, a dropped word or an altered figure still fails."""
    return _MATCH_MARK.sub("", "".join(s.split())).lower()


def quote_is_grounded(text: str, quote: str) -> bool:
    """Is this quote genuinely a span of that text?

    A raw substring test was failing roughly a quarter of good quotes on where
    the line wrapped or whether a citation left a mark, and a failure renders as
    "inferred", which tells a reader the tool could not stand behind a passage it
    had copied correctly. Folding those two away makes the check test what it
    claims to test. It is not fuzzy matching: every other character must be
    identical and in order.
    """
    if not text or not quote:
        return False
    return _fold(quote) in _fold(text)


# ── reading genealogies.nodes ───────────────────────────────────────────────
#
# `nodes` is JSONB written by Stage C and rewritten by the workbench, the two
# restore scripts and anything holding the .env. Two stages have to reason about
# it — Stage C to decide whether stored edges still mean what they meant, Stage E
# to decide which edges name a concept-state that is still there — and they must
# read it the same way, so it is read here.
#
# One posture, applied throughout: anything malformed is DROPPED, never guessed
# at and never raised on. Dropping is the safe direction for both callers,
# because both of them treat "not a concept-state I can vouch for" as a reason to
# remove an edge, and removing an edge is recoverable while displaying a wrong
# one is not. Raising is not safe: it used to happen between Stage C's node
# upsert and its edge decision, which is precisely the window that leaves new
# concept-states wired to old edges.


def node_denotation(nodes: object) -> dict:
    """{node_id: what that id denotes} for a genealogies.nodes blob.

    A node id is positional (`n1` is whichever cluster holds the earliest member
    year), so it names a slot rather than a concept-state. What it *denotes* is
    the set of definitions it groups, and that is the only thing worth comparing
    across two clusterings.

    A node that does not say which definitions it holds denotes UNKNOWN, and
    unknown is deliberately never equal to unknown: each gets a fresh sentinel,
    so two blobs that both fail to say what they hold compare unequal and their
    edges are cleared. Reading absence as "the empty set" would make them compare
    EQUAL and keep the edges, which is the one direction this must not fail in.
    """
    out: dict[str, object] = {}
    for n in nodes if isinstance(nodes, list) else []:
        if not isinstance(n, dict):
            continue
        nid = n.get("node_id")
        if not isinstance(nid, str) or not nid.strip():
            continue
        defs = n.get("definition_ids")
        # object() rather than a shared constant: a shared one would compare
        # equal to itself and reintroduce absence-as-sameness.
        # `type(d) is int`, not isinstance: bool subclasses int, so isinstance
        # let [True] compare equal to [1]. No writer emits booleans here, but a
        # type gate that reads stricter than it is will be trusted as if it were.
        out[nid.strip()] = (frozenset(defs)
                            if isinstance(defs, list) and defs
                            and all(type(d) is int for d in defs)
                            else object())
    return out


def node_ids(nodes: object) -> list[str]:
    """The concept-state ids a map actually has, sorted.

    Same posture on malformed input as `node_denotation` — dropped, never raised
    on — but deliberately NOT the same answer, because the two callers ask
    different questions. Stage E asks whether a concept-state exists, so a node
    whose `definition_ids` are unreadable still counts: the id is there and an
    edge naming it is not dangling. Stage C asks whether it denotes what it
    denoted, and unreadable is not an answer, so that same node is not safe and
    its edges clear. A node with a usable id and junk definitions is therefore in
    this list and out of Stage C's safe set, which is correct for both.
    """
    return sorted(node_denotation(nodes))

"""Acquisition: fill in real author lists from OpenAlex, falling back to arXiv.

The fetcher records the metadata the corpus JSON carried (title, year, citations)
but not authors — and BibTeX without authors is useless. CLAUDE.md rule 4 forbids
fabricating paper metadata, so authors must come from a real source rather than
be invented at export time.

**arXiv is the primary source, OpenAlex only the fallback.** We key by arxiv_id,
which the fetcher proved correct by downloading that paper's source and passing the
title-match guard, so arXiv cannot return another paper's authors. A stored
openalex_id can be wrong — OpenAlex metadata mismatches are recurrent in this
corpus — and a wrong key silently yields the *wrong* authors, which is worse than
none. arXiv's id_list also batches, so it is both safer and faster.

Usage:
  python pipeline/enrich_authors.py            # all papers missing authors
  python pipeline/enrich_authors.py --force    # refetch everything
"""

import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env, get_json, mailto, session  # noqa: E402

OPENALEX = "https://api.openalex.org"
ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"


def arxiv_authors_batch(arxiv_ids: list[str], max_retries: int = 5) -> dict[str, list[str]]:
    """{arxiv_id: [authors]} straight from arXiv. id_list batches, so this is one
    request for many papers — still 1 request / 3 s (hard rule).

    arXiv answers 429 "Rate exceeded" / 503 when pushed, so this backs off like the
    rest of the pipeline rather than failing the batch on a transient throttle.
    """
    delay = 3.0
    resp = None
    for _ in range(max_retries):
        resp = session().get(ARXIV_API, params={"id_list": ",".join(arxiv_ids),
                                                "max_results": len(arxiv_ids)}, timeout=90)
        if resp.status_code == 200:
            break
        if resp.status_code in (429, 500, 502, 503, 504):
            print(f"  [arxiv {resp.status_code}] backing off {delay:.0f}s…", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
    if resp is None or resp.status_code != 200:
        raise RuntimeError(f"arXiv gave up after {max_retries} retries "
                           f"(last status {resp.status_code if resp else '?'})")
    out: dict[str, list[str]] = {}
    for entry in ET.fromstring(resp.text).findall(f"{ATOM}entry"):
        el = entry.find(f"{ATOM}id")
        if el is None or not el.text:
            continue
        # <id> is http://arxiv.org/abs/1409.0473v7 -> 1409.0473
        aid = re.sub(r"v\d+$", "", el.text.rsplit("/abs/", 1)[-1])
        names = [n.text.strip() for a in entry.findall(f"{ATOM}author")
                 if (n := a.find(f"{ATOM}name")) is not None and n.text]
        if names:
            out[aid] = names
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill papers.authors (arXiv first).")
    ap.add_argument("--force", action="store_true", help="refetch even if authors present")
    ap.add_argument("--concept", help="only papers in this concept's genealogy — the ones "
                                      "an export will actually cite (far fewer requests)")
    args = ap.parse_args()

    conn = psycopg.connect(env("DATABASE_URL"))
    clauses = [] if args.force else ["jsonb_array_length(authors) = 0"]
    params: list = []
    if args.concept:
        gen = conn.execute("SELECT nodes FROM genealogies WHERE concept=%s AND prompt_version=%s",
                           (args.concept, env("PROMPT_VERSION", "v1"))).fetchone()
        if not gen:
            sys.exit(f'No genealogy for "{args.concept}".')
        cited = [m["arxiv_id"] for n in gen[0] for m in n["members"]]
        clauses.append("arxiv_id = ANY(%s)")
        params.append(cited)
        print(f'Scoped to the {len(cited)} paper(s) cited by the "{args.concept}" genealogy.')
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(f"SELECT id, arxiv_id, openalex_id FROM papers {where}", params).fetchall()
    if not rows:
        print("Nothing to enrich — every paper already has authors.")
        return

    def store(pid: str, aid: str, names: list[str], src: str) -> None:
        conn.execute("UPDATE papers SET authors=%s WHERE id=%s",
                     (psycopg.types.json.Json(names), pid))
        print(f"  {aid:<15} {len(names)} author(s) via {src}: "
              f"{names[0]}{' et al.' if len(names) > 1 else ''}")

    todo = {r[1]: (r[0], r[2]) for r in rows}  # arxiv_id -> (paper_id, openalex_id)
    filled = 0

    # 1) arXiv — authoritative, keyed by the verified arxiv_id, batched
    ids = list(todo)
    print(f"Fetching authors for {len(ids)} paper(s) from arXiv (authoritative)…")
    for i in range(0, len(ids), 40):
        batch = ids[i:i + 40]
        try:
            found = arxiv_authors_batch(batch)
        except Exception as e:
            print(f"  arXiv batch failed ({type(e).__name__}); falling back for these")
            found = {}
        for aid, names in found.items():
            if aid in todo:
                pid, _ = todo.pop(aid)
                store(pid, aid, names, "arXiv")
                filled += 1
        conn.commit()
        time.sleep(3.0)  # hard rule: 1 arXiv request / 3 s

    # 2) OpenAlex fallback for anything arXiv did not return
    by_oa = {oa.rsplit("/", 1)[-1]: (pid, aid)
             for aid, (pid, oa) in todo.items() if oa}
    if by_oa:
        print(f"\n{len(by_oa)} not returned by arXiv — trying OpenAlex…")
        oa_ids = list(by_oa)
        for i in range(0, len(oa_ids), 50):
            data = get_json(f"{OPENALEX}/works", {
                "filter": f"openalex:{'|'.join(oa_ids[i:i + 50])}", "per-page": 50,
                "select": "id,authorships", "mailto": mailto(),
            })
            for w in data.get("results", []):
                oa = w["id"].rsplit("/", 1)[-1]
                if oa not in by_oa:
                    continue
                names = [a["author"]["display_name"] for a in (w.get("authorships") or [])
                         if a.get("author", {}).get("display_name")]
                if not names:
                    continue
                pid, aid = by_oa[oa]
                store(pid, aid, names, "OpenAlex")
                todo.pop(aid, None)
                filled += 1
            conn.commit()
            time.sleep(0.15)

    conn.close()
    print(f"\nDone: authors filled for {filled}/{len(rows)} paper(s).")
    if todo:
        print(f"Still unknown ({len(todo)}): {', '.join(todo)}")
        print("These are omitted from BibTeX rather than guessed (never fabricate metadata).")


if __name__ == "__main__":
    main()

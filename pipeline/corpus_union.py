"""Join two passes' corpus files into the one file the union re-cluster is scoped by.

Ticket #192, the orchestration designed on #184. Pass two ADDS papers rather than
displacing them, and Stage C then re-clusters the whole enlarged corpus — which
is the design's second load-bearing choice, because incremental assignment is a
different algorithm and would make a two-stage map not the map a one-stage build
over the same papers would produce.

**Why this is a file and not a set the worker holds in memory.** Since #190 a
map's membership is the corpus file Stage B and Stage C were scoped by; without
one, membership is whatever is in `definitions` for the concept, and the
abandonment fallback would silently produce a third map that is neither pass. So
"the union corpus" has to be a nameable thing on disk, reproducible by hand: an
Operator repeating a build, or repairing one, runs the same command the worker
ran rather than reconstructing a set with `jq`.

**Order is pass one's, then whatever pass two adds**, and duplicates keep their
FIRST position. That matters because `stage_b_extract.py --corpus` reads papers
in corpus-rank order (`ORDER_BY_CORPUS_RANK`), so re-ordering the union would
re-order the extraction of a re-run for no reason. It also keeps this file
honest as a record of what was read: a paper pass one already held is a pass-one
paper, whatever pass two thinks of it. `pass_rank` in the build record is taken
from each pass's OWN file (`record_pass.py`) and never from this one, so nothing
downstream reads a rank out of the union.

Usage:
  python pipeline/corpus_union.py --json data/corpus_x_union.json \
      data/corpus_x.json data/corpus_x_pass2.json
"""

import argparse
import json
import sys
from pathlib import Path


def read_corpus(path: str) -> list[dict]:
    """A corpus file's entries, with the same tolerance every other reader has.

    An entry with no usable `arxiv_id` is dropped rather than repaired: it names
    no paper, so it can scope nothing, and `stage_b_extract.py --corpus` would
    put a null in the id list.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.exit(f"Could not read the corpus file {path}: {exc}")
    if not isinstance(data, list):
        sys.exit(f"{path} is not a corpus file: the shape --corpus reads is a JSON "
                 f"array of objects, and this holds {type(data).__name__}.")
    return [e for e in data
            if isinstance(e, dict) and isinstance(e.get("arxiv_id"), str)
            and e["arxiv_id"].strip()]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Join corpus files into one, in order, de-duplicated by arXiv id.")
    ap.add_argument("corpus", nargs="+", metavar="JSON",
                    help="the corpus files to join, in the order they were read")
    ap.add_argument("--json", metavar="PATH", required=True,
                    help="where to write the union")
    args = ap.parse_args()

    seen: dict[str, dict] = {}
    counts = []
    for path in args.corpus:
        entries = read_corpus(path)
        added = 0
        for entry in entries:
            aid = entry["arxiv_id"].strip()
            if aid in seen:
                continue
            seen[aid] = entry
            added += 1
        counts.append((path, len(entries), added))

    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(list(seen.values()), indent=2), encoding="utf-8")

    for path, held, added in counts:
        overlap = held - added
        print(f"  {path}: {held} paper(s), {added} new"
              + (f", {overlap} already held by an earlier file" if overlap else ""))
    print(f"Wrote the union of {len(args.corpus)} corpus file(s) — {len(seen)} paper(s) "
          f"— to {args.json}")


if __name__ == "__main__":
    main()

"""Record which pass of a two-stage build read which papers, and how the second
pass ended.

Ticket #192, the orchestration designed on #184. The report's whole pass block
(#193, migration `020`) reads two views; migration `022` points them at the two
tables this command writes. Nothing else writes them.

**It records, it does not decide.** Every number here comes from a file the run
already produced — the corpus files the passes were selected into, and the stats
file `pass_two_select.py --stats-json` writes — or from an argument the worker
computed and printed in the progress feed. This command has no opinion about
which papers a pass read; it reads the same file Stage B and Stage C were scoped
by, so the record and the map cannot disagree about the membership.

**`--pass 1` clears the map's whole pass record before writing.** A build that
runs again — a requeue after a deploy killed it (#178), a re-trace — is
re-stating what it read, not adding to it. Without the clear, a paper that pass
two seated on the killed run and did not seat on the re-run would keep a pass-2
row for a map that no longer holds it, and the report would count a paper into a
pass the build did not read it on. Re-running the whole build therefore converges
on exactly the record a first run would have written, which is what makes the
requeue safe.

**The pass is stored per paper and read back per definition** (migration `022`
says why). A paper with no definition row for this concept and prompt version
contributes nothing to the report, and that is right: it is not one of the papers
the report counts (#123).

Usage:
  python pipeline/record_pass.py "attention" --pass 1 --corpus data/corpus_attention.json
  python pipeline/record_pass.py "attention" --pass 2 --corpus data/corpus_attention_pass2.json
  python pipeline/record_pass.py "attention" --build --passes 2 \
      --outcome "filled all 15 of its seats" --seats 15 --candidates 611 --cleared 45
  python pipeline/record_pass.py "attention" --show
"""

import argparse
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env  # noqa: E402

# Papers named by a corpus file that this database has never seen. Fetching
# writes the row, so this is normally zero; above zero it means the corpus file
# and the papers table disagree, which is worth a line rather than a silent
# shorter record.
SELECT_PAPER_IDS = """
SELECT arxiv_id, id FROM papers WHERE arxiv_id = ANY(%(arxiv_ids)s)
"""

UPSERT_PAPER_PASS = """
INSERT INTO map_build_pass_papers (genealogy_id, paper_id, build_pass, pass_rank)
VALUES (%(gid)s, %(paper_id)s, %(build_pass)s, %(pass_rank)s)
ON CONFLICT (genealogy_id, paper_id) DO UPDATE
    SET build_pass = EXCLUDED.build_pass,
        pass_rank  = EXCLUDED.pass_rank,
        recorded_at = now()
"""

UPSERT_BUILD = """
INSERT INTO map_build_passes (genealogy_id, passes, pass_two_outcome,
                              pass_two_seats, pass_two_candidates,
                              pass_two_candidates_cleared)
VALUES (%(gid)s, %(passes)s, %(outcome)s, %(seats)s, %(candidates)s, %(cleared)s)
ON CONFLICT (genealogy_id) DO UPDATE
    SET passes = EXCLUDED.passes,
        pass_two_outcome = EXCLUDED.pass_two_outcome,
        pass_two_seats = EXCLUDED.pass_two_seats,
        pass_two_candidates = EXCLUDED.pass_two_candidates,
        pass_two_candidates_cleared = EXCLUDED.pass_two_candidates_cleared,
        recorded_at = now()
"""


def map_id(conn, concept: str, prompt_version: str) -> int:
    row = conn.execute(
        "SELECT id FROM genealogies WHERE concept = %s AND prompt_version = %s",
        (concept, prompt_version)).fetchone()
    if not row:
        # The genealogy row is created by Stage C, so this means the build has
        # not clustered yet — recording a pass before there is a map to attach it
        # to is a caller ordering error, not a missing map.
        sys.exit(f'No map for "{concept}" at prompt {prompt_version}. The pass record '
                 f"attaches to a genealogy row, which Stage C creates; record a pass "
                 f"after the clustering that pass fed, not before it.")
    return row[0]


def corpus_arxiv_ids(path: str) -> list[str]:
    """The arXiv ids of a corpus file, in the file's own order.

    The order IS the pass's selection rank: `corpus_select.py` writes `ranked`,
    which is the read order it prints, and `pass_two_select.py` writes `selected`,
    which is its ranking. Both are 1-based positions in that pass's own list,
    which is exactly what `pass_rank` means (#193's seam semantics).

    Read with the same tolerance `stage_b_extract.py --corpus` reads it with and
    no more: a list of objects carrying `arxiv_id`. A second, stricter reader of
    the same file would be a second thing to keep in agreement (#190).
    """
    corpus = json.loads(Path(path).read_text(encoding="utf-8"))
    ids: list[str] = []
    for entry in corpus if isinstance(corpus, list) else []:
        aid = entry.get("arxiv_id") if isinstance(entry, dict) else None
        if isinstance(aid, str) and aid.strip() and aid not in ids:
            ids.append(aid.strip())
    return ids


def record_papers(conn, gid: int, build_pass: int, path: str) -> None:
    ids = corpus_arxiv_ids(path)
    if build_pass == 1:
        # The clear that makes a re-run converge. Scoped to this map, because a
        # pass record belongs to one build of one map and there is nothing else
        # in this table to protect.
        gone = conn.execute(
            "DELETE FROM map_build_pass_papers WHERE genealogy_id = %s", (gid,)).rowcount
        if gone:
            print(f"  cleared {gone} paper(s) from this map's previous pass record — "
                  f"this build is re-stating what it read, not adding to it")
    if not ids:
        print(f"Pass {build_pass}: {path} names no papers, so nothing was recorded. "
              f"That is a finding rather than an error: an empty pass-two corpus is "
              f"what 'the map nominated nobody' looks like on disk.")
        return

    by_arxiv = dict(conn.execute(SELECT_PAPER_IDS, {"arxiv_ids": ids}).fetchall())
    written = 0
    for rank, aid in enumerate(ids, start=1):
        pid = by_arxiv.get(aid)
        if pid is None:
            continue
        conn.execute(UPSERT_PAPER_PASS, {"gid": gid, "paper_id": pid,
                                         "build_pass": build_pass, "pass_rank": rank})
        written += 1
    conn.commit()
    unknown = len(ids) - written
    print(f"Pass {build_pass}: recorded {written} paper(s) from {path}, ranked 1 to "
          f"{written}." + (f"\n  {unknown} paper(s) the file names are not in this "
                           f"database and were not recorded; fetching is what writes "
                           f"them." if unknown else ""))


def record_build(conn, gid: int, args) -> None:
    outcome = (args.outcome or "").strip()
    if not outcome:
        # The column refuses a blank one too, but the message a CHECK gives is
        # about the constraint and this one is about the page: `020` prints this
        # text verbatim under "why the second pass ended".
        sys.exit("--outcome is the sentence a reader sees on the report under 'why the "
                 "second pass ended'. It cannot be blank, and it must be words rather "
                 "than a code, because nothing between here and the page translates it.")
    conn.execute(UPSERT_BUILD, {"gid": gid, "passes": args.passes, "outcome": outcome,
                                "seats": args.seats, "candidates": args.candidates,
                                "cleared": args.cleared})
    conn.commit()
    print(f"Build record: {args.passes} pass(es) — {outcome}")
    print(f"  seats {args.seats if args.seats is not None else 'not recorded'}, "
          f"candidates {args.candidates if args.candidates is not None else 'not recorded'}, "
          f"cleared the gate {args.cleared if args.cleared is not None else 'not recorded'}")


def show(conn, gid: int) -> None:
    """What is recorded, read back through the seam the report reads.

    Through `map_pass_papers` and `map_pass_build` rather than the tables, so an
    Operator checking a build by hand and the report page cannot disagree — the
    same reasoning `check_map.py` follows about `map_invariant`.
    """
    build = conn.execute(
        "SELECT passes, pass_two_outcome, pass_two_seats, pass_two_candidates, "
        "pass_two_candidates_cleared FROM map_pass_build WHERE genealogy_id = %s",
        (gid,)).fetchone()
    if build is None:
        print(f"Map {gid} has no build record, so the report reads 'this map was built "
              f"in one pass' and draws no pass figures.")
    else:
        passes, outcome, seats, cands, cleared = build
        print(f"Map {gid}: {passes} pass(es) recorded — {outcome}")
        print(f"  seats {seats}, candidates {cands}, cleared the gate {cleared}")
    rows = conn.execute(
        "SELECT build_pass, count(*), min(pass_rank), max(pass_rank) "
        "FROM map_pass_papers WHERE genealogy_id = %s GROUP BY build_pass "
        "ORDER BY build_pass", (gid,)).fetchall()
    if not rows:
        print("  no paper on this map is marked with a pass.")
    for build_pass, n, lo, hi in rows:
        print(f"  pass {build_pass}: {n} paper(s) with a definition, ranks {lo}-{hi}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Record which pass of a two-stage build read which papers.")
    ap.add_argument("concept")
    ap.add_argument("--prompt-version", default=None,
                    help="default: PROMPT_VERSION from the environment, or v1")
    ap.add_argument("--pass", type=int, dest="build_pass", choices=(1, 2),
                    help="record the papers this pass read, from --corpus")
    ap.add_argument("--corpus", metavar="JSON",
                    help="the corpus file that pass was selected into and scoped by")
    ap.add_argument("--build", action="store_true",
                    help="record how the build's second pass ended")
    ap.add_argument("--passes", type=int, default=1,
                    help="how many passes actually read papers (1 or 2)")
    ap.add_argument("--outcome", help="the reader's sentence for why the second pass "
                                      "ended as it did; printed verbatim on the report")
    ap.add_argument("--seats", type=int, help="R, the seats pass two was given")
    ap.add_argument("--candidates", type=int,
                    help="recent papers citing this map that the hop found at all")
    ap.add_argument("--cleared", type=int,
                    help="how many of those cleared both signals of the gate")
    ap.add_argument("--show", action="store_true",
                    help="print what is recorded for this map and write nothing")
    args = ap.parse_args()

    if not (args.build or args.show or args.build_pass):
        sys.exit("Nothing to do: pass --pass N --corpus PATH, --build, or --show.")
    if args.build_pass and not args.corpus:
        sys.exit("--pass needs --corpus: the record says which papers a pass read, and "
                 "the corpus file it was scoped by is what says that.")

    prompt_version = args.prompt_version or env("PROMPT_VERSION", "v1")
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    try:
        gid = map_id(conn, args.concept, prompt_version)
        if args.show:
            show(conn, gid)
            return
        if args.build_pass:
            record_papers(conn, gid, args.build_pass, args.corpus)
        if args.build:
            record_build(conn, gid, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

"""Record which of a map's papers a person named at request time.

Ticket #198, accepted on the consolidated ruling on #184. Migration `023` holds
the table and the report view; this command is the only writer of that table, and
`pipeline/map_report.py` and `/g/<id>/report` are its only readers.

**It records, it does not decide.** The named ids come from the corpus file the
build was scoped by, where `corpus_select.py` marked them `"anchor": true`. So the
disclosure on the report and the corpus Stage B and Stage C were pointed at cannot
disagree about which papers a person named, for the same reason `record_pass.py`
reads the corpus file rather than re-deriving membership.

**It clears the map's whole anchor record before writing, on every run.** A
rebuild is re-stating what a person named, not adding to it: a map anchored once
and rebuilt with the field left empty must come back saying nobody named a paper,
or the report would carry a claim about a build that no longer exists. That also
makes it right to run on every build, anchored or not, and the worker does.

**The actor is decision 18's split, unchanged.** `--named-by` is an authenticated
GitHub login, which is what the app obtained from a session and stored on the
request row; the worker only relays it. With no `--named-by`, the row carries
`named_by_asserted` instead, from `common.actor()`, which is all a script running
for whoever holds the `.env` can honestly claim. A row may carry one, the other,
or neither, and absence is reported as absence rather than as a claim about
origin.

**A named paper that could not be fetched is still recorded.** The row is keyed on
the arXiv id and has no foreign key to `papers`, so an id that named nothing this
system could read survives in the record and shows on the report as named, not
read. That is condition 4's whole point: a silently dropped name is a requester
believing their paper is in a map that does not contain it.

Usage:
  python pipeline/record_anchors.py "dark energy" --corpus data/corpus_dark_energy.json
  python pipeline/record_anchors.py "dark energy" --corpus <path> --named-by rgok001
  python pipeline/record_anchors.py "dark energy" --show
"""

import argparse
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import actor, env, tidy_actor_name  # noqa: E402

INSERT_ANCHOR = """
INSERT INTO map_anchor_papers (genealogy_id, arxiv_id, named_by, named_by_asserted,
                               named_rank)
VALUES (%(gid)s, %(arxiv_id)s, %(named_by)s, %(named_by_asserted)s, %(named_rank)s)
ON CONFLICT (genealogy_id, arxiv_id) DO UPDATE
    SET named_by          = EXCLUDED.named_by,
        named_by_asserted = EXCLUDED.named_by_asserted,
        named_rank        = EXCLUDED.named_rank,
        recorded_at       = now()
"""


def map_id(conn, concept: str, prompt_version: str) -> int:
    row = conn.execute(
        "SELECT id FROM genealogies WHERE concept = %s AND prompt_version = %s",
        (concept, prompt_version)).fetchone()
    if not row:
        # Stage C creates the genealogy row, so this means the build has not
        # clustered yet: a caller ordering error rather than a missing map.
        sys.exit(f'No map for "{concept}" at prompt {prompt_version}. The anchor record '
                 f"attaches to a genealogy row, which Stage C creates; record the named "
                 f"papers after the clustering, not before it.")
    return row[0]


def anchored_ids(path: str) -> list[str]:
    """The arXiv ids the corpus file marks as named, in the file's own order.

    Read with the same tolerance `record_pass.py` and `stage_b_extract.py
    --corpus` read it with and no more: a list of objects carrying `arxiv_id`.
    A file written before `023` carries no `anchor` key at all and yields an
    empty list, which is correct: nobody could name a paper for that build.
    """
    corpus = json.loads(Path(path).read_text(encoding="utf-8"))
    ids: list[str] = []
    for entry in corpus if isinstance(corpus, list) else []:
        if not isinstance(entry, dict) or not entry.get("anchor"):
            continue
        aid = entry.get("arxiv_id")
        if isinstance(aid, str) and aid.strip() and aid.strip() not in ids:
            ids.append(aid.strip())
    return ids


def record(conn, gid: int, path: str, named_by: str | None) -> None:
    ids = anchored_ids(path)
    # The clear that makes a rebuild converge, and it runs whether or not this
    # build named anybody. Scoped to this map: an anchor record belongs to one
    # build of one map and there is nothing else in the table to protect.
    gone = conn.execute(
        "DELETE FROM map_anchor_papers WHERE genealogy_id = %s", (gid,)).rowcount
    if gone:
        print(f"  cleared {gone} named paper(s) from this map's previous record — this "
              f"build is re-stating what was named, not adding to it")
    if not ids:
        conn.commit()
        print(f"Nobody named a paper for this map: {path} marks none. The report says so "
              f"in words, and that is a fact about the request rather than a gap.")
        return

    # Folded before it is stored as well as before it is rendered (decision 18):
    # the login arrives from GitHub and is already tame, but a name that can spell
    # this product's own delimiters is a name that can spell a trust level it does
    # not have, and the fold is one call.
    by = tidy_actor_name(named_by) if named_by else ""
    asserted = "" if by else actor()
    for rank, aid in enumerate(ids, start=1):
        conn.execute(INSERT_ANCHOR, {"gid": gid, "arxiv_id": aid,
                                     "named_by": by or None,
                                     "named_by_asserted": asserted or None,
                                     "named_rank": rank})
    conn.commit()
    who = (f"named by {by}, signed in" if by
           else f"named by {asserted}, from the command line, name not verified")
    print(f"Recorded {len(ids)} paper(s) a person named for this map ({who}): "
          f"{', '.join(ids)}")
    print("  The report discloses the count and the list. Being named bought each of "
          "them a reading and nothing else.")


def show(conn, gid: int) -> None:
    """What is recorded, read back through the view the report reads.

    Through `map_report_anchors` rather than the table, so an Operator checking a
    build by hand and the report page cannot disagree — the same reasoning
    `record_pass.py --show` and `check_map.py` follow.
    """
    row = conn.execute(
        "SELECT papers_named, papers_named_read, papers_named_defining, "
        "papers_named_linked, named_by, named_by_asserted, named_papers "
        "FROM map_report_anchors WHERE genealogy_id = %s", (gid,)).fetchone()
    if row is None:
        print(f"Map {gid} is not on the report view at all, which should not happen: "
              f"every map that exists gets a row. Check that migration 023 applied.")
        return
    named, read, defining, linked, by, asserted, papers = row
    if not named:
        print(f"Map {gid}: nobody named a paper for it. Every paper in it was chosen by "
              f"this system.")
        return
    who = (f"{by}, signed in" if by else
           f"{asserted}, from the command line, name not verified" if asserted else
           "actor not recorded")
    print(f"Map {gid}: {named} paper(s) named by {who}; {read} of them were read, "
          f"{defining} define the term, {linked} carry a relationship.")
    for p in papers or []:
        # "no reading" rather than "defines nothing" where the paper never
        # arrived: Stage B gave no verdict on it, and the stronger phrase would
        # report a reading that never happened.
        defines = ("defines" if p["defines"]
                   else "defines nothing" if p["read"] else "no reading")
        print(f"  {p['arxiv_id']:<14} {p.get('year') or '?':<5} "
              f"{'read' if p['read'] else 'NOT READ':<9}"
              f"{defines:<16}"
              f"{p['relationships']:>3} relationship(s)  "
              f"{(p.get('title') or '?')[:52]}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Record which of a map's papers a person named at request time.")
    ap.add_argument("concept")
    ap.add_argument("--prompt-version", default=None,
                    help="default: PROMPT_VERSION from the environment, or v1")
    ap.add_argument("--corpus", metavar="JSON",
                    help="the corpus file the build was scoped by; its entries carry "
                         "\"anchor\": true for the papers a person named")
    ap.add_argument("--named-by", metavar="LOGIN",
                    help="the authenticated login of the person who named them. Omit it "
                         "and the row records what this process asserts about itself "
                         "instead, which is what a command-line run can honestly claim")
    ap.add_argument("--show", action="store_true",
                    help="print what is recorded for this map and write nothing")
    args = ap.parse_args()

    if not (args.corpus or args.show):
        sys.exit("Nothing to do: pass --corpus PATH, or --show.")

    prompt_version = args.prompt_version or env("PROMPT_VERSION", "v1")
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    try:
        gid = map_id(conn, args.concept, prompt_version)
        if args.show:
            show(conn, gid)
            return
        record(conn, gid, args.corpus, args.named_by)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

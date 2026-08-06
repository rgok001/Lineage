"""Re-check the verification stamps from stored data, without trusting any of it.

Ticket #29 ([F1]); the design is docs/design/recheckable-stamp.md. This is the
point of migration 015. The columns are only worth having if something can
consume them, and this is the thing that proves a tick is evidence rather than a
claim: it re-derives every stamp from the paper's own file and says where the
answer differs from what the database asserts.

**It reads LINEAGE_READ_URL and never DATABASE_URL, and it issues no statement
but SELECT.** It structurally cannot re-anchor a stamp, which is the failure
incident 10 named as dishonest, and it is therefore the one tool in this feature
an agent may run against production. It does not repair. Ever. When it disagrees
with the database, the answer is to re-run the free re-check that produced the
stamp (`stage_b_extract.py <concept> --reground`, then `stage_e_ground.py`), not
to write anything from here.

Four comparisons per stamp, arriving by three different paths — the database, the
disk, and the matcher — so each of them can actually return false:

  1. the file's digest now vs papers.extracted_text_digest   (the file moved)
  2. the file's digest now vs the stamp's own digest         (the stamp is stale)
  3. the stored span vs every span the matcher grounds this  (the span names
     quote at in this file                                    something else)
  4. the stored span vs the leftmost of those                (the match is not
                                                              where we said)

Usage:
  python pipeline/recheck_stamp.py --concept "attention"
  python pipeline/recheck_stamp.py --concept "attention" --edges --verbose
  python pipeline/recheck_stamp.py --concept "attention" --arxiv 1706.03762
"""

import argparse
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (STAMP_STALE, STAMP_VERIFIED, data_dir, env,  # noqa: E402
                    grounded_spans, stamp_state, text_digest)

# Only the read-only role. Named deliberately unlike DATABASE_URL so that no
# existing code path can route through it by accident (CLAUDE.md), and read here
# rather than through any helper that knows the writable one.
READ_URL = "LINEAGE_READ_URL"

DEFS = """
SELECT p.arxiv_id, d.id, d.verbatim_quote, d.quote_verified,
       d.quote_start, d.quote_end, d.quote_text_digest, d.quote_extractor_version,
       p.extracted_text_path, p.extracted_text_digest, p.extractor_version
FROM definitions d JOIN papers p ON p.id = d.paper_id
WHERE d.concept = %(concept)s AND d.prompt_version = %(pv)s
  AND d.defines_concept = true
{arxiv_filter}ORDER BY p.arxiv_id
"""

EDGES = """
SELECT sp.arxiv_id, tp.arxiv_id, e.id, e.verified,
       e.source_quote, e.source_quote_start, e.source_quote_end,
       e.source_text_digest, e.source_extractor_version,
       sp.extracted_text_path, sp.extracted_text_digest,
       e.target_quote, e.target_quote_start, e.target_quote_end,
       e.target_text_digest, e.target_extractor_version,
       tp.extracted_text_path, tp.extracted_text_digest
FROM edges e
JOIN genealogies g ON g.id = e.genealogy_id
JOIN papers sp ON sp.id = e.source_paper_id
JOIN papers tp ON tp.id = e.target_paper_id
WHERE g.concept = %(concept)s AND g.prompt_version = %(pv)s
{arxiv_filter}ORDER BY e.id
"""


class Tally:
    def __init__(self) -> None:
        self.examined = 0
        self.verified = 0
        self.inferred = 0
        self.stale = 0
        self.span_mismatch = 0
        self.unreadable = 0
        self.file_moved = 0
        self.render_disagrees = 0
        self.files_read = 0


def load(path: str | None, cache: dict) -> tuple[str, str] | None:
    """(text, digest) for one paper's file, or None when it cannot be read.

    Read once per path per run and never through any code that also writes: this
    tool's entire value is that its answer arrives by a different route from the
    one that made the stamp.
    """
    if not path:
        return None
    if path not in cache:
        try:
            raw = (data_dir() / path).read_bytes()
            cache[path] = (raw.decode("utf-8"), text_digest(raw))
        except (OSError, UnicodeDecodeError) as exc:
            cache[path] = None
            print(f"  ! {path}: {exc}")
    return cache[path]


def check_one(label: str, quote: str | None, verified: object,
              start: int | None, end: int | None,
              stamp_digest: str | None, stamp_extractor: str | None,
              path: str | None, paper_digest: str | None,
              cache: dict, tally: Tally, verbose: bool) -> bool:
    """Re-check one stamp. Returns False when this stamp is a finding.

    Two rules earned by issue #56, both of them about a check that could only
    agree with itself:

    **The verdict is resolved against the bytes on disk, not against the
    database's claim about them.** Resolving against `papers.extracted_text_digest`
    is the comparison the application already makes from the database alone; it
    needs no disk and it re-derives nothing. This tool's whole reason to exist is
    that it holds the file, and the design's falsifier 12 — corrupt one character
    and re-run — passed silently for exactly that reason: it printed the
    disk/database disagreement as a note and then asked the database whether the
    stamp was fresh.

    **Every row is counted exactly once, after all of its checks have run.** The
    first version incremented `verified` before the span checks, so a stamp could
    be reported verified in the same breath as having its span declared wrong.
    """
    tally.examined += 1
    loaded = load(path, cache)
    if loaded is None:
        tally.unreadable += 1
        tally.stale += 1
        print(f"  {label}: UNREADABLE — no text on this disk, so nothing here can "
              f"be checked. Renders stale.")
        return True
    text, disk_digest = loaded
    findings: list[str] = []

    # 1. The disk against the database's claim about the disk. These are written
    #    by different code at different moments; extract_text.py's skip path is
    #    what keeps papers.extracted_text_digest honest, and if it has not run
    #    since the file changed, this is where that shows. It is a finding and not
    #    a note: the database is describing a file that is not there.
    moved = paper_digest is not None and disk_digest != paper_digest
    if moved:
        tally.file_moved += 1
        findings.append("file moved")
        print(f"  {label}: THE FILE ON DISK IS NOT THE FILE THE DATABASE DESCRIBES")
        print(f"      papers.extracted_text_digest {paper_digest}")
        print(f"      the bytes on disk now        {disk_digest}")

    # 2. The stamp against the bytes this tool just read. Same three lines the
    #    pipeline and the app use, given the digest of the file rather than the
    #    database's opinion of it, so a change to the file makes the stamp stale
    #    here even when nothing has told the database yet.
    state = stamp_state(verified, stamp_digest, disk_digest)
    why = ""
    if state == STAMP_STALE:
        why = ("no digest recorded" if not stamp_digest
               else "the stamp names bytes this file does not have")

    # 2b. And the same three lines given the digest the READER's page compares
    #     against, which is the database's. Issue #66: resolving only against the
    #     disk answers a truer question than the product asks, and then reports
    #     the answer to a question nobody asked as though it were the site's. With
    #     papers.extracted_text_digest NULL — the state left by running the
    #     runbook's live-data step 2 before step 1 — the file agrees with the
    #     stamp, so this tool said "verified, everything re-checks out" over a
    #     corpus every page was rendering stale.
    #
    #     Both are reported, and a disagreement is a finding. The tool holds both
    #     digests and is the only thing that does; saying which of the two answers
    #     it is giving costs one line and is the difference between an instrument
    #     and an opinion.
    render_state = stamp_state(verified, stamp_digest, paper_digest)
    if render_state != state:
        tally.render_disagrees += 1
        findings.append("render disagrees")
        print(f"  {label}: THE PAGE AND THE FILE DISAGREE ABOUT THIS STAMP")
        print(f"      against the bytes on disk:  {state}")
        print(f"      against papers.extracted_text_digest (what every reader "
              f"sees): {render_state}")
        if not paper_digest:
            print("      the paper has no recorded digest at all, so every surface "
                  "renders this stale.")
            print("      Run `python pipeline/extract_text.py` (no --force) — that "
                  "is live-data step 1,")
            print("      and it is meant to run BEFORE the re-ground.")

    # 3. The stored span against the places this file actually grounds the quote.
    #    This does NOT confirm the boolean — the same matcher put the span there,
    #    so agreement proves nothing. It confirms that the offsets name a passage
    #    that really is this quote, which is what a reader would use them for.
    #
    #    Asked of the matcher, not of a slice (issue #63). The first version tested
    #    `_fold(text[start:end]) == _fold(quote)`, which is a stricter contract than
    #    `grounded_span` grants and than its docstring claims: a span is widened to
    #    whole source characters, so the slice can fold longer, and folding is
    #    context-sensitive, so a slice can fold *differently* — "ΑΣ".lower() is "ας"
    #    and "Σ".lower() is "σ", and the final-sigma rule fires after any cased
    #    letter, Latin included. Spans `grounded_span` had itself returned therefore
    #    failed this check, and a span mismatch is the one finding that exits
    #    non-zero "which invalidates the stamps". A verifier that re-derives its own
    #    contract eventually polices something nothing promised.
    #
    #    Every occurrence rather than the leftmost, because "these offsets name the
    #    quote" and "these offsets name the *first* occurrence" are two different
    #    claims and check 4 below is the one making the second. One pass over the
    #    file serves both.
    everywhere = list(grounded_spans(text, quote)) if quote else []
    if quote and start is not None and end is not None:
        if not (0 <= start <= end <= len(text)):
            findings.append("span out of range")
            print(f"  {label}: SPAN OUT OF RANGE — [{start}, {end}) in a "
                  f"{len(text)}-character file")
        elif (start, end) not in everywhere:
            findings.append("span mismatch")
            print(f"  {label}: SPAN MISMATCH — the matcher does not ground this "
                  f"quote at [{start}, {end})")
            print(f"      at the span: {text[start:end][:120]!r}")
            print(f"      the quote:   {quote[:120]!r}")
            print(f"      the matcher grounds it at: "
                  f"{everywhere[:5] if everywhere else 'nowhere in this file'}")

    # 4. And the leftmost match, which is the one the pipeline stores. A stored
    #    span that check 3 accepted but that is not this one means the match is not
    #    where we said it was: two identical passages, and the offsets naming the
    #    second.
    if quote:
        found = everywhere[0] if everywhere else None
        if start is not None and end is not None and found != (start, end):
            findings.append("span disagrees with the matcher")
            print(f"  {label}: SPAN DISAGREES WITH THE MATCHER — stored "
                  f"[{start}, {end}), found {found}")
        elif start is None and found is not None and not moved:
            # Not a failure: a stamp that recorded no span against text that has
            # since been re-extracted is exactly what a stale stamp is. Worth
            # saying, because it is free to fix with a re-ground.
            print(f"  {label}: no span stored, but the quote is in the file at "
                  f"{found} — a re-ground would make this stamp re-checkable")

    # One row, one tally, after every check. A stamp whose span is broken is not
    # also a verified stamp, whatever its digests say.
    span_broken = any(f.startswith("span") for f in findings)
    if span_broken:
        tally.span_mismatch += 1
    elif state == STAMP_STALE:
        tally.stale += 1
        print(f"  {label}: STALE — {why}")
    elif state == STAMP_VERIFIED:
        tally.verified += 1
    else:
        tally.inferred += 1

    if verbose and not findings:
        ext = stamp_extractor or "extractor not recorded"
        print(f"  {label}: {state}, span [{start}, {end}), {ext}")
    return not findings


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Re-check verification stamps against the papers on this disk "
                    "(read-only; SELECT and nothing else).")
    ap.add_argument("--concept", required=True)
    ap.add_argument("--prompt-version", default=None,
                    help="defaults to PROMPT_VERSION from the environment")
    ap.add_argument("--arxiv", metavar="ID", nargs="+",
                    help="restrict to these arxiv ids")
    ap.add_argument("--edges", action="store_true",
                    help="re-check the edge stamps too (two per edge)")
    ap.add_argument("--verbose", action="store_true",
                    help="print a line for every stamp, not only the findings")
    args = ap.parse_args()

    pv = args.prompt_version or env("PROMPT_VERSION", "v1")
    dsn = env(READ_URL)
    params = {"concept": args.concept, "pv": pv}
    def_filter = edge_filter = ""
    if args.arxiv:
        params["ids"] = list(args.arxiv)
        def_filter = "  AND p.arxiv_id = ANY(%(ids)s)\n"
        edge_filter = "  AND (sp.arxiv_id = ANY(%(ids)s) OR tp.arxiv_id = ANY(%(ids)s))\n"

    tally = Tally()
    cache: dict[str, tuple[str, str] | None] = {}
    clean = True

    with psycopg.connect(dsn) as conn:
        defs = conn.execute(DEFS.format(arxiv_filter=def_filter), params).fetchall()
        print(f'Re-checking {len(defs)} definition stamp(s) for "{args.concept}" '
              f"at prompt {pv}, against {data_dir()}\n")
        for (arxiv, did, quote, verified, start, end, sdig, sext,
             path, pdig, _pext) in defs:
            clean &= check_one(f"{arxiv} def {did}", quote, verified, start, end,
                               sdig, sext, path, pdig, cache, tally, args.verbose)

        if args.edges:
            edges = conn.execute(EDGES.format(arxiv_filter=edge_filter), params).fetchall()
            print(f"\nRe-checking {2 * len(edges)} edge stamp(s) "
                  f"({len(edges)} edges, two quotes each)\n")
            for row in edges:
                (s_arxiv, t_arxiv, eid, verified,
                 s_quote, s_start, s_end, s_dig, s_ext, s_path, s_pdig,
                 t_quote, t_start, t_end, t_dig, t_ext, t_path, t_pdig) = row
                clean &= check_one(f"edge {eid} src {s_arxiv}", s_quote, verified,
                                   s_start, s_end, s_dig, s_ext, s_path, s_pdig,
                                   cache, tally, args.verbose)
                clean &= check_one(f"edge {eid} tgt {t_arxiv}", t_quote, verified,
                                   t_start, t_end, t_dig, t_ext, t_path, t_pdig,
                                   cache, tally, args.verbose)

    tally.files_read = sum(1 for v in cache.values() if v is not None)
    print(f"\n{tally.examined} stamp(s) examined across {tally.files_read} readable "
          f"file(s) of {len(cache)}:")
    print(f"  verified      {tally.verified}")
    print(f"  inferred      {tally.inferred}")
    print(f"  stale         {tally.stale}")
    print(f"  unreadable    {tally.unreadable}   (counted as stale as well)")
    print(f"  file moved    {tally.file_moved}   (disk and database disagree about "
          f"the bytes)")
    print(f"  span mismatch {tally.span_mismatch}")
    print(f"  page differs  {tally.render_disagrees}   (this tool's verdict against "
          f"the file is not what a reader is shown)")
    print("\nThe verdicts above are resolved against the bytes on this disk. A "
          "reader's page resolves against\npapers.extracted_text_digest, and where "
          "the two differ the line above says so per stamp.")

    # The global check, in the shape Stage B's --reground and Stage E carry: a
    # per-stamp tolerance that survives one missing file is exactly what makes a
    # total outage invisible (incident 12). The boundary is zero, not a fraction.
    if tally.examined > 1 and not tally.files_read:
        sys.exit("\nRefusing to report this as a result: not one file could be read.\n"
                 "  That is an unmounted or empty DATA_DIR, not a corpus of stale "
                 "stamps.\n"
                 f"  Expected the papers under {data_dir()}.")
    if tally.span_mismatch:
        sys.exit(f"\n{tally.span_mismatch} span mismatch(es). The stored offsets and "
                 f"the matcher disagree about the same file, which invalidates the "
                 f"stamps rather than describing the corpus. Nothing was written; "
                 f"this tool does not repair.")
    # A file the database is wrong about fails the run (issue #56). It used to be
    # printed and then ignored, so the design's own falsifier 12 — corrupt one
    # character, re-run — reported the disagreement and exited 0 under the line
    # "Every stamp examined re-checks out." The repair is free and is named here
    # rather than left to be remembered.
    if tally.file_moved:
        sys.exit(
            f"\n{tally.file_moved} stamp(s) belong to a file the database describes "
            f"wrongly: the bytes on disk are not the bytes\n"
            f"papers.extracted_text_digest names. Every stamp on those papers is "
            f"stale whatever the app currently shows,\nbecause the app compares "
            f"against the database's value and only this tool has read the file.\n"
            f"  Run `python pipeline/extract_text.py` (no --force) to record the "
            f"bytes that are actually there, then\n"
            f"  re-ground the affected maps. Nothing was written; this tool does "
            f"not repair.")
    # A corpus every reader sees as stale must never leave this tool under a clean
    # exit (issue #66). The tool's answer may be the truer one — the stamp really
    # is about the bytes on disk — but its audience is somebody deciding whether
    # the published map is honest, and "every stamp re-checks out" over pages that
    # all say "not re-checked" is a sentence that will be believed.
    if tally.render_disagrees:
        sys.exit(
            f"\n{tally.render_disagrees} stamp(s) re-check against the file but are "
            f"NOT what a reader is shown.\n"
            f"  This tool resolves against the bytes on disk; every page resolves "
            f"against papers.extracted_text_digest.\n"
            f"  Where those disagree the site is the one the public sees, so the "
            f"map is not yet saying what this\n"
            f"  tool has just proved. The usual cause is the two live-data steps "
            f"run in the wrong order: the papers\n"
            f"  backfill (`python pipeline/extract_text.py`, no --force) comes "
            f"before the re-ground, not after.\n"
            f"  Nothing was written; this tool does not repair.")
    if not clean:
        sys.exit("\nFindings above.")
    print("\nEvery stamp examined re-checks out, and every one of them re-checks "
          "out the same way a reader's page resolves it.")


if __name__ == "__main__":
    main()

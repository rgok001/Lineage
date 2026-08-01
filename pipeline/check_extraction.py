"""Audit: how faithful is our extracted text to the papers it came from?

Everything the grounding check guarantees rests on one file per paper: the
extracted text under DATA_DIR. Stage E certifies that a quote is a span of that
file. Whether that file is a faithful rendering of the paper has never been
measured, and incident 10 is what an unmeasured answer costs: the extractor was
silently eating natbib citations, quotes read "a model should, detect the
objects, and, segment them", and every one of them passed grounding, because
both sides of the comparison came from the same damaged file. No string check
can catch that. Both sides agree.

This is the cheap half of answering it: a scan for the marks damage leaves
behind. It calls no model and no API, and it is a LOWER BOUND, not a verdict. A
paper it flags is a paper worth opening on arXiv; a paper it passes is a paper
it found no evidence against.

Every signal below was checked against what the real extractor emits, not
assumed:

  unknown macros  the big one, and the generalisation of incident 10. pylatexenc
                  renders the macros it knows and drops the rest WITHOUT A WORD,
                  taking their content with them. A paper's own
                  `\\newcommand{\\dmodel}{d_{model}}` is unknown to it, so
                  "dimension $\\dmodel$" extracts to "dimension." while plain
                  "dimension $d_{model}$" extracts correctly to "dimension
                  d_model". Verified both ways. This is almost certainly why
                  Attention Is All You Need reads "vectors of dimension ." and
                  leaves 17 of embedding's edges inferred: not math mode, which
                  works, but a paper-defined macro, which is invisible. We ask
                  pylatexenc's own macro database what it knows, so the answer
                  cannot drift from the parser we actually run.
  latex residue   `$`, `{`, `}` surviving into the text. A healthy parse emits
                  none of these (verified: math renders as d_model, √(d_k)).
                  The raw-strip fallback (extract_text.py:168) strips backslash
                  macros but leaves dollars and braces standing, so residue is
                  how a degraded parse announces itself after the fact. It
                  announces itself live only on stderr, during a batch nobody is
                  watching.
  lost symbols    for each short inline math group in the source, did any
                  rendering of it survive anywhere in the text?
  short text      extracted characters against the inlined source. A missing or
                  circular \\input is dropped in silence (extract_text.py:91),
                  so a whole section can leave without a word about it.
  gaps            punctuation standing where a token used to be, detected by
                  shape and never by vocabulary. Guessing at words that "never"
                  take a following comma flagged "the batch size." and "And,";
                  writing the shapes with `\s` made every indented line a gap.
                  What is left is anchored to word characters and literal spaces.
  stale text      the useful half of what those attempts kept finding. "dimension
                  .", "extracting  features" and "model ()." were fed back
                  through the current extractor and it removes all three, so a
                  file containing them was not written by it. That is not damage
                  in the pipeline, it is a file the fixes never reached, and the
                  answer is re-extraction rather than a warning. Reported, and
                  deliberately kept out of the verdict.
  bad decode      U+FFFD, from the "replace" decode in read_archive.
  no structure    neither a references nor an introduction heading survived.

PDF-sourced papers are reported separately throughout. They are categorically
less faithful (column order, ligatures, running heads, maths) and averaging them
in with LaTeX papers hides both numbers.

Quotes get their own pass, because the paper-level rate is not the rate that
matters: what matters is how much of the evidence a reader is actually shown
sits in damaged text.

Usage:
  python pipeline/check_extraction.py
  python pipeline/check_extraction.py --concept "embedding"
  python pipeline/check_extraction.py --concept "embedding" --sample 8
  python pipeline/check_extraction.py --json data/extraction_audit.json
  python pipeline/check_extraction.py --clear-verdicts --concept "embedding" --dry-run
"""

import argparse
import json
import re
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, env  # noqa: E402
from extract_text import (expand_own_macros, find_main_tex, inline_inputs,  # noqa: E402
                          read_archive)

# Our own marks. Expected, folded away by quote_is_grounded, rendered as an
# elision by readableQuote. Counted for context, never as damage.
OUR_MARKS = re.compile(r"<cit\.>|<ref>")

# A healthy pylatexenc parse emits no dollars and no braces; the raw-strip
# fallback leaves both (measured: 8 dollars, 2 braces on a 6-line sample).
LATEX_RESIDUE = re.compile(r"[${}]|\\[a-zA-Z@]{2,}")
# Calibrated on the first real run: 4 flagged papers whose parse was fine.
# The raw-strip fallback leaves residue in the hundreds, so the bar for
# 'this parse degraded' sits far above where a stray brace lands.
RESIDUE_DAMAGED = 150
RESIDUE_SUSPECT = 25

REPLACEMENT = "�"
REPLACEMENT_DAMAGED = 20
REPLACEMENT_SUSPECT = 1

# Macros used in the body. The preamble is excluded: \usepackage and friends are
# declarations, not content, and their loss costs the reader nothing.
MACRO_USE = re.compile(r"\\([a-zA-Z@]{2,})")
MACRO_DEF = re.compile(r"\\(?:newcommand|renewcommand|providecommand|def|DeclareMathOperator)\*?\s*\{?\\([a-zA-Z@]+)")
# A macro the paper defines and then uses is content by construction: nobody
# writes \newcommand for something they would not mind losing. One use is worth
# reporting.
OWN_DAMAGED, OWN_SUSPECT = 10, 1

# An unknown macro the paper did NOT define is usually a package's formatting,
# and these were calibrated on the "embedding" corpus after the first real run,
# because the synthetic sample they were guessed against did not resemble a
# paper. At 60 for damaged, 160 of 182 papers came back damaged, driven almost
# entirely by package macros: one paper alone had 506. A verdict that fires on
# 88% of a corpus is not a verdict, and it would have put a warning on nearly
# every paper page.
#
# So package macros can no longer reach "damaged" at all. That follows from what
# this file already argued: their loss costs a reader nothing. Rating them the
# same as lost content was the incoherence, not the number.
OTHER_SUSPECT = 200

# Structural macros whose disappearance is the intended behaviour rather than a
# loss: they carry no prose, and pylatexenc drops or handles them by design.
HARMLESS_MACROS = frozenset("""
    documentclass usepackage begin end newcommand renewcommand providecommand def
    label bibliography bibliographystyle input include includegraphics
    maketitle newtheorem setlength definecolor DeclareMathOperator
    vspace hspace noindent centering toprule midrule bottomrule
""".split())

# Inline maths short enough to be a symbol rather than an equation. A symbol is
# content: unlike a citation it cannot be folded away in the comparison, so a
# lost one correctly fails grounding for the whole sentence.
SRC_MATH = re.compile(r"\$([^$\n]{1,60})\$")
SYMBOL_MIN, SYMBOL_MAX = 2, 14
SYMBOL_LOSS_DAMAGED = 0.50
SYMBOL_LOSS_SUSPECT = 0.20
SYMBOL_MIN_CHECKED = 10  # below this the rate is noise, so it is not scored

# Extracted characters against inlined source characters. Source carries all the
# markup, so a healthy ratio sits well under 1; the floor is what catches a
# section that left without saying so.
RATIO_DAMAGED = 0.10
RATIO_SUSPECT = 0.18

# Words that never take a following comma, and nouns that never end a sentence
# bare. "a model should, detect the objects" is incident 10 as it reads today,
# once tidy_marks has closed the space the citation left behind.
# Every part anchors to a word character and to LITERAL spaces (\x20), never to
# \s. \s matches a newline, and a paper's text is full of wrapped and indented
# lines, so "\s{2,}" quietly meant "any indented line" and reported 892 gaps in a
# paper that had a handful. Whitespace that spans a line break is layout; only
# whitespace inside a line can be a hole where a token stood.
# Marks TODAY'S EXTRACTOR CANNOT MAKE. tidy_marks closes the space before
# punctuation, collapses runs of spaces, and deletes an emptied bracket pair;
# each was fed back through it and verified gone. So finding one is not evidence
# of damage in the current pipeline. It is proof that this text was written by an
# older one and never re-extracted, which is a different and more useful finding:
# the fix exists and this file has not had it.
STALE_MARKS = re.compile(
    r"\w\x20+[.,;:]"       # "vectors of dimension ."
    r"|\w\x20{2,}\w"       # "extracting  features"
    r"|\(\x20*[)\]]"       # "a neural ranking model ()."
    r"|\[\x20*\]")

# Damage the current extractor still can leave. tidy_marks does not touch either.
GAP_STRONG = re.compile(
    r"\(\x20+\S"           # the front of a group left: "( 200 dimensions)"
    r"|[,;:]\x20*[.,;:]")  # two marks with nothing between them
GAP_WEAK = re.compile(r"(?!)")  # nothing: see the note above
GAP_SUSPECT = 3

SECTION_HINTS = (re.compile(r"^[\s§]*(?:\d+\.?\s*)?references\b", re.I | re.M),
                 re.compile(r"^[\s§]*(?:\d+\.?\s*)?(?:introduction|abstract)\b", re.I | re.M))

_known_cache: dict[str, bool] = {}


def parser_knows(name: str) -> bool:
    """Does the parser we actually run know this macro? Asked of pylatexenc's own
    database rather than a list of ours, so the answer cannot drift from the
    extractor. An unknown name is dropped silently along with its argument, which
    is the whole failure mode."""
    if name not in _known_cache:
        from pylatexenc.latex2text import get_default_latex_context_db
        spec = get_default_latex_context_db().get_macro_spec(name)
        # Unknown names come back as a generic fallback spec carrying a different
        # macroname, so identity of the name is the test.
        _known_cache[name] = getattr(spec, "macroname", None) == name
    return _known_cache[name]


def _dropped_in(latex: str, defined: set[str]) -> dict[str, int]:
    """Body macros the parser will drop in silence, counted by name.

    Anything containing "cite" is excluded: normalise_cite_macros folds those to
    one mark before parsing, so they are handled rather than lost.
    """
    body = latex.split(r"\begin{document}", 1)
    body = body[1] if len(body) > 1 else latex
    counts: dict[str, int] = {}
    for name in MACRO_USE.findall(body):
        if "cite" in name.lower() or name in HARMLESS_MACROS or parser_knows(name):
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def unknown_macros(source_latex: str) -> dict:
    """What this paper loses to macros, asked of the pipeline as it now stands.

    The question changed when the extractor learned to expand a paper's own
    definitions, and asking the old one would report a fixed bug as a live
    finding. So it is asked twice:

      before  what the parser alone would have dropped. Not a live defect. It is
              the measurement of what the macro fix was worth, on real corpora,
              and it is the number worth reporting.
      after   what still disappears once expansion has run. This is the live
              finding: a definition too exotic to parse (delimited \\def
              parameters), a macro used with arguments the definition does not
              promise, or a package's own command.

    The own/package split survives expansion because the names a paper defined
    are collected from the original source, before those definitions are stripped.
    A macro the paper defined is content by construction; a package's `\\linebreak`
    is a typesetting instruction nobody misses.
    """
    defined = set(MACRO_DEF.findall(source_latex))
    before = _dropped_in(source_latex, defined)
    after = _dropped_in(expand_own_macros(source_latex), defined)
    ranked = sorted(((n, c, n in defined) for n, c in after.items()),
                    key=lambda t: (not t[2], -t[1]))
    return {
        "before_own": sum(c for n, c in before.items() if n in defined),
        "before_other": sum(c for n, c in before.items() if n not in defined),
        "own": sum(c for n, c in after.items() if n in defined),
        "other": sum(c for n, c in after.items() if n not in defined),
        "ranked": ranked,
    }


def fold_alnum(s: str) -> str:
    """Letters and digits only, lowercased. Symbol presence is asked at this
    resolution because we are testing whether the symbol survived at all, not how
    pylatexenc chose to spell it: d_{model} counts as present whether it rendered
    as d_model, dmodel or d model."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def symbol_survival(source_latex: str, text: str) -> tuple[int, int, list[str]]:
    """(checked, missing, examples) for short inline maths groups in the source.

    Single-character symbols are skipped: a bare "n" is present in any English
    text, so asking the question of them would only manufacture passes.
    """
    folded_text = fold_alnum(text)
    checked = missing = 0
    examples: list[str] = []
    seen: set[str] = set()
    for group in SRC_MATH.findall(source_latex):
        token = fold_alnum(re.sub(r"\\[a-zA-Z]+", "", group))
        if not (SYMBOL_MIN <= len(token) <= SYMBOL_MAX) or token in seen:
            continue
        seen.add(token)
        checked += 1
        if token not in folded_text:
            missing += 1
            if len(examples) < 6:
                examples.append(group.strip())
    return checked, missing, examples


def source_latex_for(raw_path: Path) -> str | None:
    """The inlined LaTeX body the extractor would have parsed, or None when the
    raw file is a PDF, is unreadable, or is simply not on this machine. The last
    case is ordinary rather than exceptional: the database is shared and the
    disks are not (incident 7c)."""
    try:
        raw = raw_path.read_bytes()
    except OSError:
        return None
    try:
        texs, _ = read_archive(raw)
    except Exception:
        return None
    main = find_main_tex(texs)
    if not main:
        return None
    try:
        return inline_inputs(main, texs)
    except (KeyError, RecursionError):
        return texs[main]


def scan_paper(row: dict) -> dict:
    """One paper's signals and verdict. Absent evidence is recorded as absent,
    never as a pass: a paper whose text file is missing gets its own verdict so
    it cannot quietly inflate the clean rate."""
    out: dict = {
        "arxiv_id": row["arxiv_id"], "title": row["title"],
        "source_format": row["source_format"], "title_match": row["text_title_match"],
        "signals": [], "verdict": "clean",
    }
    try:
        text = (data_dir() / row["extracted_text_path"]).read_text(encoding="utf-8")
    except OSError:
        out["verdict"] = "no text on this machine"
        return out

    out["chars"] = len(text)
    out["our_marks"] = len(OUR_MARKS.findall(text))

    residue = len(LATEX_RESIDUE.findall(OUR_MARKS.sub("", text)))
    out["latex_residue"] = residue
    if residue >= RESIDUE_DAMAGED:
        out["signals"].append(("damaged", f"latex residue x{residue} (parse fell back to raw strip)"))
    elif residue >= RESIDUE_SUSPECT:
        out["signals"].append(("suspect", f"latex residue x{residue}"))

    bad = text.count(REPLACEMENT)
    out["replacement_chars"] = bad
    if bad >= REPLACEMENT_DAMAGED:
        out["signals"].append(("damaged", f"undecodable bytes x{bad}"))
    elif bad >= REPLACEMENT_SUSPECT:
        out["signals"].append(("suspect", f"undecodable bytes x{bad}"))

    stale = len(STALE_MARKS.findall(text))
    out["stale_marks"] = stale
    if stale:
        out["signals"].append(("stale", f"text predates the current extractor "
                                        f"({stale} marks it can no longer make)"))

    strong = len(GAP_STRONG.findall(text))
    out["gap_hits"] = strong
    out["gap_examples"] = [m.group(0) for m in list(GAP_STRONG.finditer(text))[:4]]
    if strong >= GAP_SUSPECT:
        out["signals"].append(("suspect", f"gaps where a token was x{strong}"))

    if not any(p.search(text) for p in SECTION_HINTS):
        out["signals"].append(("suspect", "no references or introduction heading"))

    if row["source_format"] == "latex" and row["raw_path"]:
        source = source_latex_for(data_dir() / row["raw_path"])
        if source:
            ratio = len(text) / max(len(source), 1)
            out["length_ratio"] = round(ratio, 3)
            if ratio < RATIO_DAMAGED:
                out["signals"].append(("damaged", f"text is {ratio:.0%} of source (content dropped)"))
            elif ratio < RATIO_SUSPECT:
                out["signals"].append(("suspect", f"text is {ratio:.0%} of source"))

            m = unknown_macros(source)
            out["own_macro_uses"], out["other_macro_uses"] = m["own"], m["other"]
            out["macro_uses_before_fix"] = m["before_own"] + m["before_other"]
            out["own_macro_uses_before_fix"] = m["before_own"]
            out["unknown_macros"] = m["ranked"][:8]
            if m["own"] >= OWN_DAMAGED:
                out["signals"].append(("damaged", f"{m['own']} uses of the paper's own macros still dropped"))
            elif m["own"] >= OWN_SUSPECT:
                out["signals"].append(("suspect", f"{m['own']} uses of the paper's own macros still dropped"))
            if m["other"] >= OTHER_SUSPECT:
                out["signals"].append(("suspect", f"{m['other']} uses of unknown package macros dropped"))

            checked, missing, examples = symbol_survival(source, text)
            out["symbols_checked"], out["symbols_missing"] = checked, missing
            out["symbol_examples"] = examples
            if checked >= SYMBOL_MIN_CHECKED:
                rate = missing / checked
                out["symbol_loss"] = round(rate, 3)
                if rate >= SYMBOL_LOSS_DAMAGED:
                    out["signals"].append(("damaged", f"{missing}/{checked} symbols left no trace"))
                elif rate >= SYMBOL_LOSS_SUSPECT:
                    out["signals"].append(("suspect", f"{missing}/{checked} symbols left no trace"))

    # "stale" says which extractor made this file, not how good the file is, so
    # it is reported and then kept out of the verdict. Re-extracting is the
    # answer to it, and that is a decision about the corpus rather than a
    # warning about a paper.
    levels = {s[0] for s in out["signals"]} - {"stale"}
    out["verdict"] = "damaged" if "damaged" in levels else "suspect" if levels else "clean"
    return out


# The quote pass. Our own marks are excluded: they are expected, folded by the
# check and rendered as an elision, so counting them here would report the design
# as damage.
QUOTE_TELLS = (
    ("undecodable bytes", lambda q: REPLACEMENT in q),
    ("latex residue", lambda q: bool(LATEX_RESIDUE.search(OUR_MARKS.sub("", q)))),
    ("gap where a token was", lambda q: bool(GAP_STRONG.search(q))),
    ("copied from text the extractor has since fixed", lambda q: bool(STALE_MARKS.search(q))),
)


def scan_quotes(conn, concept: str | None, pv: str) -> dict:
    where, params = "", {}
    if concept:
        where = "WHERE d.concept = %(c)s AND d.prompt_version = %(pv)s"
        params = {"c": concept, "pv": pv}
    rows = conn.execute(f"""
        SELECT p.arxiv_id, d.verbatim_quote, d.quote_verified
        FROM definitions d JOIN papers p ON p.id = d.paper_id
        {where}
    """, params).fetchall()

    counts = {name: 0 for name, _ in QUOTE_TELLS}
    touched, examples = 0, []
    for arxiv_id, quote, verified in rows:
        hits = [name for name, test in QUOTE_TELLS if test(quote or "")]
        if not hits:
            continue
        touched += 1
        for name in hits:
            counts[name] += 1
        if len(examples) < 12:
            examples.append({"arxiv_id": arxiv_id, "verified": verified,
                             "tells": hits, "quote": (quote or "")[:240]})
    return {"total": len(rows), "touched": touched, "counts": counts, "examples": examples}


# --clear-verdicts marks papers unaudited again, so the free pass that runs at
# every worker start picks them up. It is the retrospective half of the line
# extract_text.py now runs when it rewrites a file: that line protects every
# future re-extraction, and this is for the rows frozen before it existed. All
# 292 of them were written in one batch on 2026-07-31 by the calibration this
# file replaced twenty minutes later, against text that has since been
# re-extracted, and --only-unchecked filters on the timestamp being null, so
# nothing revisits them ever (as-built 11.11).
#
# It touches three columns and reads no disk at all, which is the point: it is
# the only mode of this file that does anything useful on a machine holding the
# database but not the corpus, and that is the machine the owner has. Where the
# corpus IS present, `--write` on its own is the better instrument — it recomputes
# in place and never leaves a paper with no verdict at all.
#
# extraction_signals is NOT NULL DEFAULT '[]' (migration 013), so it empties
# rather than nulls; NULL there would abort the statement.
CLEAR_VERDICTS = """
UPDATE papers p
   SET extraction_verdict = NULL,
       extraction_signals = '[]'::jsonb,
       extraction_checked_at = NULL
 WHERE p.extraction_checked_at IS NOT NULL
{scope}"""

# The same WHERE, asked as a question. --dry-run renders THIS and never the
# UPDATE, rather than sharing a statement and branching on a flag: a preview that
# runs the write is one edit away from being the write. The checked-at range is
# reported because it is the evidence — one batch is one timestamp, and a stamp
# older than the text under it is the entire defect.
PREVIEW_VERDICTS = """
SELECT COALESCE(p.extraction_verdict, 'no verdict') AS verdict, count(*) AS n,
       min(p.extraction_checked_at) AS oldest,
       max(p.extraction_checked_at) AS newest
FROM papers p
WHERE p.extraction_checked_at IS NOT NULL
{scope}GROUP BY 1
ORDER BY 1
"""

# The papers table is shared across every concept ever traced, so an unscoped
# statement here reaches another map's rows. Scoped exactly as extract_text.py
# --concept scopes itself, prompt version and all (it has none): a rewrite of the
# text is what invalidates a verdict, so the two must be able to name the same
# set of papers, and a paper belongs to a map whichever prompt version its
# definition was extracted at.
CONCEPT_SCOPE = ("   AND EXISTS (SELECT 1 FROM definitions d\n"
                 "               WHERE d.paper_id = p.id AND d.concept = %(concept)s)\n")
ONLY_SCOPE = "   AND p.arxiv_id = ANY(%(only_ids)s)\n"


def clear_verdicts(conn, concept: str | None, only: list[str] | None,
                   dry_run: bool) -> None:
    """Hand these papers back to the free audit.

    Costs nothing and calls nothing: three columns of `papers`, no model, no
    network, no disk. Deliberately shaped like stage_b_extract.py --reground and
    stage_h_claims.py --recheck minus the recompute, because the recompute needs
    the corpus and this exists for the machine that has not got one.

    A cleared verdict is not "clean". It is "unchecked", which is what these rows
    honestly are, and while it stands the dossier says nothing about the text
    rather than something false about it.
    """
    scope, params = "", {}
    if concept:
        scope += CONCEPT_SCOPE
        params["concept"] = concept
    if only:
        scope += ONLY_SCOPE
        params["only_ids"] = list(only)

    rows = conn.execute(PREVIEW_VERDICTS.format(scope=scope), params).fetchall()
    named = f'"{concept}"' if concept else "every concept"
    if not rows:
        print(f"No stored verdicts in scope ({named}); nothing to clear.")
        return

    total = sum(r[1] for r in rows)
    oldest = min(r[2] for r in rows)
    newest = max(r[3] for r in rows)
    print(f"\nStored extraction verdicts in scope ({named}): {total} "
          f"paper{'' if total == 1 else 's'}\n")
    for verdict, n, _, _ in rows:
        print(f"    {verdict:<12} {n:>4}")
    when = (f"all audited {oldest:%Y-%m-%d %H:%M:%S%z}" if oldest == newest
            else f"audited between {oldest:%Y-%m-%d %H:%M:%S%z} and {newest:%Y-%m-%d %H:%M:%S%z}")
    print(f"\n  {when}")

    if not concept and not only:
        print("  This is EVERY audited paper in the table, across all concepts. "
              "--concept scopes it to one map.")

    if dry_run:
        print("\n[dry-run] Nothing was written. Re-run without --dry-run to clear "
              "these verdicts.")
        return

    cleared = conn.execute(CLEAR_VERDICTS.format(scope=scope), params).rowcount
    conn.commit()
    print(f"\n  Cleared {cleared} verdicts. Nothing else was touched: the extracted "
          f"text,\n  the quotes and the stamps on them are exactly as they were.")
    print("  These papers are now unaudited, so the free pass at the worker's next "
          "start\n  (--only-unchecked --write) will re-measure them against the text "
          "as it is now.\n  Until it does, their dossiers say nothing about the "
          "extraction rather than\n  something computed from text that is gone. "
          "Nothing else re-audits them, so if\n  the worker is never restarted the "
          "verdicts never come back.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit extracted-text fidelity (no model, no network)")
    ap.add_argument("--concept", help="scope to one corpus; omit to scan every extracted paper")
    ap.add_argument("--prompt-version", default=env("PROMPT_VERSION", "v2"))
    ap.add_argument("--sample", type=int, default=0, help="print this many flagged papers in full")
    ap.add_argument("--json", help="write the full per-paper audit here")
    ap.add_argument("--only-unchecked", action="store_true",
                    help="skip papers already audited. Makes this cheap enough to "
                         "run on every worker start, so the backfill needs nobody "
                         "to remember it")
    ap.add_argument("--write", action="store_true",
                    help="store each verdict on papers.extraction_verdict (migration 013), "
                         "so the app can tell a reader what it knows about the text "
                         "a quote was matched against")
    ap.add_argument("--clear-verdicts", action="store_true",
                    help="remove the stored verdict, signals and checked-at from the "
                         "papers in scope, so the free audit measures them again. For "
                         "when the text was rewritten under a verdict, or the check "
                         "that made it was. Reads no text and needs no corpus on this "
                         "machine; scope it with --concept or --only")
    ap.add_argument("--only", metavar="ARXIV_ID", nargs="+",
                    help="restrict --clear-verdicts to these arxiv ids")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --clear-verdicts, report what would be cleared and "
                         "write nothing")
    args = ap.parse_args()

    if args.clear_verdicts and (args.write or args.only_unchecked):
        sys.exit("--clear-verdicts is the opposite job to --write: it removes the stored\n"
                 "verdicts so the free audit will measure again, and it reads no text at\n"
                 "all. Run it on its own, then let the worker's --only-unchecked --write\n"
                 "pass do the measuring.")
    # Without this, `--dry-run --write` would be read as a safe rehearsal and
    # would write every verdict. The audit is already read-only without --write,
    # so there is nothing else here for the flag to mean.
    if args.dry_run and not args.clear_verdicts:
        sys.exit("--dry-run applies to --clear-verdicts. This audit writes nothing "
                 "unless\nyou pass --write, so leaving --write off IS the read-only run.")
    if args.only and not args.clear_verdicts:
        sys.exit("--only scopes --clear-verdicts. To audit selected papers, use "
                 "--concept.")

    # Cheap re-runs are what let this live in the worker's startup rather than in
    # somebody's terminal history.
    unchecked = "AND p.extraction_checked_at IS NULL" if args.only_unchecked else ""

    with psycopg.connect(env("DATABASE_URL")) as conn:
        if args.clear_verdicts:
            # Ahead of the scan, and it returns rather than falling through: this
            # mode asks the database only, and the machine most likely to run it
            # has no corpus for the scan below to read.
            clear_verdicts(conn, args.concept, args.only, args.dry_run)
            return

        if args.concept:
            rows = conn.execute("""
                SELECT p.arxiv_id, p.title, p.source_format, p.raw_path,
                       p.extracted_text_path, p.text_title_match
                FROM papers p JOIN definitions d ON d.paper_id = p.id
                WHERE d.concept = %(c)s AND d.prompt_version = %(pv)s
                  AND p.extracted_text_path IS NOT NULL
                  {unchecked}
                ORDER BY p.arxiv_id
            """.format(unchecked=unchecked), {"c": args.concept, "pv": args.prompt_version}).fetchall()
        else:
            rows = conn.execute("""
                SELECT arxiv_id, title, source_format, raw_path,
                       extracted_text_path, text_title_match
                FROM papers WHERE extracted_text_path IS NOT NULL
                  {unchecked}
                ORDER BY arxiv_id
            """.format(unchecked=unchecked.replace("p.", ""))).fetchall()

        cols = ("arxiv_id", "title", "source_format", "raw_path",
                "extracted_text_path", "text_title_match")
        papers = [scan_paper(dict(zip(cols, r))) for r in rows]
        quotes = scan_quotes(conn, args.concept, args.prompt_version)

        if args.write:
            # A paper whose text is not on this machine is left alone rather than
            # recorded as unchecked: another machine has the file, and its verdict
            # is the one worth keeping (incident 7c).
            stored = 0
            for p in papers:
                if p["verdict"] == "no text on this machine":
                    continue
                conn.execute("""
                    UPDATE papers SET extraction_verdict = %(v)s,
                                      extraction_signals = %(s)s,
                                      extraction_checked_at = now()
                    WHERE arxiv_id = %(a)s
                """, {"v": p["verdict"], "a": p["arxiv_id"],
                      "s": json.dumps([f"{lvl}: {why}" for lvl, why in p["signals"]])})
                stored += 1
            conn.commit()
            print(f"  Wrote {stored} verdicts to papers.extraction_verdict.\n")

    scope = f'"{args.concept}"' if args.concept else "every extracted paper"
    print(f"\nExtraction audit: {scope} ({len(papers)} papers)\n")

    for fmt in ("latex", "pdf", None):
        group = [p for p in papers if p["source_format"] == fmt]
        if not group:
            continue
        n = len(group)
        tally = {v: sum(1 for p in group if p["verdict"] == v) for v in
                 ("clean", "suspect", "damaged", "no text on this machine")}
        print(f"  {str(fmt or 'unknown'):<8} {n:>4} papers   "
              + "   ".join(f"{v}: {c} ({c / n:.0%})" for v, c in tally.items() if c))

        checked = sum(p.get("symbols_checked", 0) for p in group)
        missing = sum(p.get("symbols_missing", 0) for p in group)
        if checked:
            print(f"           symbols: {missing} of {checked} left no trace ({missing / checked:.1%})")
        own = sum(p.get("own_macro_uses", 0) for p in group)
        affected = sum(1 for p in group if p.get("own_macro_uses", 0) >= OWN_SUSPECT)
        if own:
            print(f"           still dropped after macro expansion: {own} uses of the "
                  f"papers' own macros, across {affected} papers ({affected / n:.0%})")
        # What the macro fix was worth, measured rather than argued. This is the
        # number for the write-up: it is the size of a silent failure that no
        # grounding check could have caught, because both sides agreed.
        stale_papers = sum(1 for p in group if p.get("stale_marks", 0))
        if stale_papers:
            print(f"           text predating the current extractor: {stale_papers} papers "
                  f"({stale_papers / n:.0%}); re-extract to apply the fixes")
        was = sum(p.get("own_macro_uses_before_fix", 0) for p in group)
        was_papers = sum(1 for p in group if p.get("own_macro_uses_before_fix", 0) >= OWN_SUSPECT)
        if was:
            print(f"           would have been dropped before the macro fix: {was} uses "
                  f"across {was_papers} papers ({was_papers / n:.0%})")

    if quotes["total"]:
        t, n = quotes["touched"], quotes["total"]
        print(f"\n  quotes   {n:>4} stored     {t} carry a damage tell ({t / n:.1%})")
        for name, c in quotes["counts"].items():
            if c:
                print(f"             {name}: {c}")

    flagged = [p for p in papers if p["verdict"] in ("suspect", "damaged")]
    print(f"\n  {len(flagged)} of {len(papers)} papers worth opening on arXiv. "
          f"This is a lower bound:\n  it finds damage that leaves a mark, and silence leaves none.\n")

    for p in sorted(flagged, key=lambda p: p["verdict"] != "damaged")[:args.sample]:
        print(f"  [{p['verdict']}] {p['arxiv_id']}  {p['title'][:70]}")
        for level, why in p["signals"]:
            print(f"      {level}: {why}")
        if p.get("unknown_macros"):
            names = ", ".join(f"\\{n} x{c}{'' if own else ' (pkg)'}"
                              for n, c, own in p["unknown_macros"][:5])
            print(f"      dropped: {names}")
        for ex in p.get("symbol_examples", [])[:3]:
            print(f"      lost symbol: ${ex}$")
        for ex in p.get("gap_examples", [])[:2]:
            print(f"      gap: ...{ex}...")
        print()

    if args.sample and quotes["examples"]:
        print("  Quotes carrying a tell (the evidence a reader is actually shown):\n")
        for e in quotes["examples"][:args.sample]:
            stamp = "verified" if e["verified"] else "inferred"
            print(f"  {e['arxiv_id']} [{stamp}] {', '.join(e['tells'])}")
            print(f"      {e['quote']}\n")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"papers": papers, "quotes": quotes}, indent=2),
                       encoding="utf-8")
        print(f"  Full audit written to {out}")


if __name__ == "__main__":
    main()

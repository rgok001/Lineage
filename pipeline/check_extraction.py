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
                  writing the shapes with `\\s` made every indented line a gap.
                  What is left is anchored to word characters and literal spaces.
                  Reported and kept out of the verdict since 2026-08-01: it fires
                  on faithful renderings of `\\left(`, `\\big(` and `$(\\,x\\,)$`,
                  which lost nothing, and on 304 papers it was the sole reason 33
                  of them carried a warning.
  stale text      the useful half of what those attempts kept finding. "dimension
                  .", "extracting  features" and "model ()." were fed back
                  through the current extractor and it removes all three, so a
                  file containing them was not written by it. That is not damage
                  in the pipeline, it is a file the fixes never reached, and the
                  answer is re-extraction rather than a warning. Reported, and
                  deliberately kept out of the verdict.
  bad decode      U+FFFD, from the "replace" decode in read_archive.
  no structure    neither a references nor an introduction heading survived.

Three of these are REPORTED AND DO NOT DECIDE THE VERDICT: `stale`, `gaps`, and
the package half of `unknown macros`. Each is true, each is worth an operator's
attention, and none of them means "the passage you are reading may be missing
wording the paper had", which is the only thing the dossier note can say. The
answers they imply are re-extract the corpus, open the paper on arXiv, and teach
the extractor a package, and a reader can act on none of the three. That split is
the fifth calibration of this file and the first one taken from a measurement
rather than from a rate (as-built section 4).

Every stored verdict records which calibration produced it
(`extraction_check_version`, migration 014). Change a threshold or a pattern in
this file and every verdict written by the old one counts as unchecked, so the
worker's free pass re-measures them at its next start. Nobody has to remember.

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
  python pipeline/check_extraction.py --compare-verdicts
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
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

# Verdicts that are not verdicts: the scan could not be finished, so there is
# nothing to store. `--write` skips them, they are counted and printed, and the
# row stays unaudited so the machine that can answer will.
NO_TEXT = "no text on this machine"
NO_SOURCE = "no source archive on this machine"
SOURCE_UNUSABLE = "source archive unusable"
UNSTORABLE = (NO_TEXT, NO_SOURCE, SOURCE_UNUSABLE)

# ── naming the signals ──────────────────────────────────────────────────────
#
# A signal is (level, key, prose). The key exists because this detector has been
# recalibrated four times (as-built section 4) and every attempt read the rate
# and moved a number, which is the check agreeing with itself. Grouping by cause
# needs a stable name for the cause, and the prose is not one: it carries counts
# and percentages, it is written for a reader, and parsing it back out would make
# every wording change a silent behaviour change. The prose is a sentence; the
# key is the identifier.
SIGNAL_KEYS = ("residue", "undecodable", "stale", "gaps", "no_headings",
               "short_text", "own_macros", "package_macros", "symbols")

# Signals that are reported and deliberately do not decide the verdict. `stale`
# invented this position: it says which extractor wrote a file, not how good the
# file is, and the answer to it is re-extraction, which is a decision about the
# corpus rather than a warning about a paper.
#
# `gaps` and `package_macros` joined it on 2026-08-01, after the measurement
# decision 24 exists to take and not before. Over all 304 papers on the Render
# disk, demoting the two together takes the dossier note from 218 papers (72%) to
# 113 (37%) and moves nothing stricter in either direction: 105 papers go suspect
# to clean and no cell below the diagonal is occupied. They were sole cause on 33
# and 44 papers respectively, which sums to 77 against a joint effect of 105 —
# the 28-paper gap is co-occurrence, and it is why demoting one alone lands
# around 63% and reads as failure.
#
# They are still emitted, still stored in extraction_signals and still printed.
# 134 of 304 papers drop package macros and that is worth an operator's
# attention; what changed is who it is addressed to. The action `gaps` implies is
# "open this paper on arXiv", the action `package_macros` implies is "the
# extractor could learn this package", and the dossier note says neither of those
# — it tells a reader their quote may be missing wording the paper had, which on
# these papers is mostly not true.
NOTE_SIGNALS = frozenset({"gaps", "package_macros"})

# The levels a verdict ignores. Data rather than a literal inside verdict_from,
# because CHECK_VERSION below hashes it: demoting a signal is then a change the
# stored verdicts notice by themselves, instead of one somebody has to remember
# to announce.
NOTE_LEVELS = frozenset({"stale", "note"})

# The next hypothesis, and empty because the fifth one shipped above.
# --compare-verdicts demotes whatever is named here and prints today's verdict
# against the result; with nothing named the crosstab is the identity matrix, so
# the mode says there is no proposal rather than printing a diagonal that reads
# like a finding. Still a module constant and not a flag, for decision 24's
# reason: a --what-if taking arbitrary thresholds leaves no record of what was
# actually proposed on the day the number was taken.
PROPOSED_NOTE_SIGNALS: frozenset[str] = frozenset()

# A key in either set that no signal emits would demote nothing, and the
# comparison would print two identical columns and look like a finding.
_UNKNOWN_KEYS = (PROPOSED_NOTE_SIGNALS | NOTE_SIGNALS) - set(SIGNAL_KEYS)
if _UNKNOWN_KEYS:
    raise ValueError("NOTE_SIGNALS/PROPOSED_NOTE_SIGNALS name signals nothing "
                     f"emits: {sorted(_UNKNOWN_KEYS)}")

# A literal `...` is folded to `…` before the shape tests, in the paper scan and
# in the quote tells alike. `\ldots` and `\dots` already render as `…` and score
# no hit (measured through the real extractor), so the literal form was being
# read as damage purely for being spelled differently: tidy_marks closes the
# space in front of the dots, "$x_1, ..., x_n$" extracts to "x_1,..., x_n", and
# GAP_STRONG's second branch matches the ",." in it.
#
# Deleting the dots is the obvious alternative and it is wrong: it turns
# "a,..., z" into "a,, z", which the same branch matches, so it manufactures the
# false positive it was removing. Two dots fold as well as three, since ",.."
# matches that branch exactly as ",..." does.
#
# Measured over the 393 stored quotes: gap tells 5 -> 2, quotes carrying any tell
# 11 -> 10.
LITERAL_ELLIPSIS = re.compile(r"\.{2,}")
ELLIPSIS = "…"


def fold_ellipsis(s: str) -> str:
    """One definition of what an ellipsis is, so the paper scan and the quote
    pass cannot come to different answers about the same passage."""
    return LITERAL_ELLIPSIS.sub(ELLIPSIS, s)


# ── the version of the check that wrote a verdict ───────────────────────────
#
# A verdict about a paper's text is invalidated by two different things and only
# one of them was ever handled. The text can be replaced, and extract_text.py
# clears the verdict in the same statement that records the new file (decision
# 21). The CODE that computes the verdict can be replaced, and nothing noticed:
# --only-unchecked selects on extraction_checked_at being null, so a stamped row
# stayed stamped however far the calibration moved underneath it. The 292
# verdicts written at 10:08:43 on 2026-07-31 were computed by a calibration that
# three commits replaced between 10:19 and 10:31, and they were still on the page
# weeks later. That is what forgetting looks like, and this is the column that
# makes forgetting impossible.
#
# A digest and not a hand-bumped integer, for that reason exactly: a number
# somebody has to remember to raise is a number somebody forgets, and nobody
# noticed the defect above for weeks.
#
# What it covers is the calibration INPUTS: every threshold, every pattern and
# its flags, which signals exist, which of them are notes, and which levels the
# verdict ignores. It does not cover the rest of the file, so a change to the
# arithmetic touching none of these will not move it. Anything that decides a
# verdict therefore belongs in this dict, and NOTE_SIGNALS and NOTE_LEVELS are in
# it precisely because this ticket's own change is a change of data: a demotion
# the stored verdicts could not see would be the same defect again.
#
# This also retires the --clear-verdicts-then-restart ritual for a calibration
# change. Clearing NULLs the verdict, and on the dossier the note is the only
# qualifier on "verified verbatim against the source text", so a cleared row
# leaves the tick standing alone and the page claiming MORE than it did
# (decision 21). A version mismatch leaves the old verdict in place until the new
# one replaces it: replace before destroying, applied to the verdict itself.
# --clear-verdicts stays for the job it was built for, a machine that holds the
# database and not the papers.


def _rx(p: re.Pattern) -> list:
    """A pattern's identity for the digest: source AND flags, because re.M is the
    whole difference between "any indented line" and "a hole inside a line", and
    that mistake has already shipped once (the third calibration)."""
    return [p.pattern, p.flags]


def check_version() -> str:
    """A short digest of this file's calibration.

    Reads the module globals when called rather than closing over them, so a test
    can move a constant and ask for the version again.
    """
    inputs = {
        "residue": [_rx(LATEX_RESIDUE), RESIDUE_DAMAGED, RESIDUE_SUSPECT],
        "replacement": [REPLACEMENT, REPLACEMENT_DAMAGED, REPLACEMENT_SUSPECT],
        "macros": [_rx(MACRO_USE), _rx(MACRO_DEF), OWN_DAMAGED, OWN_SUSPECT,
                   OTHER_SUSPECT, sorted(HARMLESS_MACROS)],
        "symbols": [_rx(SRC_MATH), SYMBOL_MIN, SYMBOL_MAX, SYMBOL_LOSS_DAMAGED,
                    SYMBOL_LOSS_SUSPECT, SYMBOL_MIN_CHECKED],
        "ratio": [RATIO_DAMAGED, RATIO_SUSPECT],
        "gaps": [_rx(GAP_STRONG), _rx(GAP_WEAK), GAP_SUSPECT],
        "stale": [_rx(STALE_MARKS)],
        "headings": [_rx(p) for p in SECTION_HINTS],
        "our_marks": [_rx(OUR_MARKS)],
        "ellipsis": [_rx(LITERAL_ELLIPSIS), ELLIPSIS],
        "signals": [list(SIGNAL_KEYS), sorted(NOTE_SIGNALS), sorted(NOTE_LEVELS)],
    }
    # sort_keys, so a dict reordering is not a calibration change; and json's own
    # number formatting, so 0.2 and 0.20 agree and 0.20 and 0.25 do not. Nothing
    # here is hash()ed: str.__hash__ is salted per process and this value has to
    # survive a restart.
    blob = json.dumps(inputs, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


CHECK_VERSION = check_version()


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


def source_latex_for(raw_path: Path) -> tuple[str | None, str | None]:
    """(inlined LaTeX body, why not) for the source the extractor would have parsed.

    The two failures used to be the same `None`, and that is what let a paper the
    scanner never looked at come back "clean": the archive-fed signals were
    skipped in silence and the absence of a finding read as the finding of an
    absence. They are separated because they mean opposite things about where
    the answer lives.

      absent    not on THIS machine. Ordinary rather than exceptional, because
                the database is shared and the disks are not (incident 7c), and
                the answer exists on the machine that holds the file.
      unusable  here and no use to us: an archive holding only a PDF, one
                pylatexenc cannot open, one with no main .tex. The answer is the
                same on every machine, so nothing is gained by waiting for one.
    """
    try:
        raw = raw_path.read_bytes()
    except OSError:
        return None, "absent"
    try:
        texs, _ = read_archive(raw)
    except Exception:
        return None, "unusable"
    main = find_main_tex(texs)
    if not main:
        return None, "unusable"
    try:
        return inline_inputs(main, texs), None
    except (KeyError, RecursionError):
        return texs[main], None


def verdict_from(signals: list, demoted: frozenset = frozenset(),
                 source_scan: str | None = None) -> str:
    """The verdict these signals add up to, with `demoted` treated as notes.

    Split out of the tail of `scan_paper` so that today's verdict and a proposed
    one are the same code given different inputs. Two copies of this arithmetic
    would drift, and a comparison table computed from a drifted copy is worse
    than no table: it would look like a finding.

    NOTE_LEVELS is the set of levels that report without deciding. "stale" says
    which extractor made this file, not how good the file is, and "note" is the
    same position given a name once a second and a third signal needed it: the
    action each of them implies is not a warning to a reader. `demoted` puts a
    named signal there for the length of one call, which is how --compare-verdicts
    prices a proposal before it ships.

    `source_scan` is here because dropping it is decision 23's mistake wearing
    different clothes: a paper whose archive is not on this machine had six
    signals skipped, so once its remaining signals are demoted away the answer is
    "we did not look", never "clean".
    """
    levels = {lvl for lvl, key, _ in signals
              if lvl not in NOTE_LEVELS and key not in demoted}
    if "damaged" in levels:
        return "damaged"
    if levels:
        return "suspect"
    if source_scan in ("absent", "unusable"):
        # Nothing was found, and six of the signals never ran. "Clean" here would
        # mean "we looked and found nothing" when what happened is that we did
        # not look. The two are indistinguishable on the page and opposite in
        # what they are worth to a reader.
        return NO_SOURCE if source_scan == "absent" else SOURCE_UNUSABLE
    return "clean"


def scan_paper(row: dict) -> dict:
    """One paper's signals and verdict. Absent evidence is recorded as absent,
    never as a pass: a paper whose text file is missing gets its own verdict so
    it cannot quietly inflate the clean rate.

    That promise was kept for the text file and broken for the source archive.
    Six of the signals below need the archive, `source_latex_for` returned a
    silent `None` when it was not on this machine, and the paper fell through to
    "clean" with an empty signals array. Measured on 224 papers with the archives
    removed and nothing else changed: 47 verdicts moved and 39 of them became
    "clean". `--write` stored those. A warning that is wrong is at least visible;
    a reassurance nobody computed is not.

    So the rule is now: **report the damage you measured, never the cleanliness
    you did not establish.** A partial scan may still return "suspect" or
    "damaged", because residue, undecodable bytes and gaps are read off the text
    alone and a finding there is true whatever else was skipped. It may not
    return "clean", because "clean" is the one verdict that asserts an absence.
    """
    out: dict = {
        "arxiv_id": row["arxiv_id"], "title": row["title"],
        "source_format": row["source_format"], "title_match": row["text_title_match"],
        "signals": [], "verdict": "clean",
    }
    try:
        text = (data_dir() / row["extracted_text_path"]).read_text(encoding="utf-8")
    except OSError:
        out["verdict"] = NO_TEXT
        return out

    out["chars"] = len(text)
    out["our_marks"] = len(OUR_MARKS.findall(text))

    # The shape tests read this and nothing else does: it is one character
    # shorter per ellipsis, and the length ratio and the residue count are about
    # the file as it stands. See LITERAL_ELLIPSIS for why the dots are folded
    # rather than removed.
    shaped = fold_ellipsis(text)

    residue = len(LATEX_RESIDUE.findall(OUR_MARKS.sub("", text)))
    out["latex_residue"] = residue
    if residue >= RESIDUE_DAMAGED:
        out["signals"].append(("damaged", "residue", f"latex residue x{residue} (parse fell back to raw strip)"))
    elif residue >= RESIDUE_SUSPECT:
        out["signals"].append(("suspect", "residue", f"latex residue x{residue}"))

    bad = text.count(REPLACEMENT)
    out["replacement_chars"] = bad
    if bad >= REPLACEMENT_DAMAGED:
        out["signals"].append(("damaged", "undecodable", f"undecodable bytes x{bad}"))
    elif bad >= REPLACEMENT_SUSPECT:
        out["signals"].append(("suspect", "undecodable", f"undecodable bytes x{bad}"))

    stale = len(STALE_MARKS.findall(shaped))
    out["stale_marks"] = stale
    if stale:
        out["signals"].append(("stale", "stale", f"text predates the current extractor "
                                                 f"({stale} marks it can no longer make)"))

    strong = len(GAP_STRONG.findall(shaped))
    out["gap_hits"] = strong
    out["gap_examples"] = [m.group(0) for m in list(GAP_STRONG.finditer(shaped))[:4]]
    if strong >= GAP_SUSPECT:
        out["signals"].append(("suspect", "gaps", f"gaps where a token was x{strong}"))

    if not any(p.search(text) for p in SECTION_HINTS):
        out["signals"].append(("suspect", "no_headings", "no references or introduction heading"))

    # PDF papers are not scanned here and are not incomplete for it: there is no
    # LaTeX to measure the text against, so these six signals are inapplicable
    # rather than uncomputed. A LaTeX paper with no raw_path recorded IS
    # incomplete, because the archive exists and we simply never got it.
    if row["source_format"] == "latex":
        source, why = (source_latex_for(data_dir() / row["raw_path"])
                       if row["raw_path"] else (None, "absent"))
        out["source_scan"] = why or "complete"
        if source:
            ratio = len(text) / max(len(source), 1)
            out["length_ratio"] = round(ratio, 3)
            if ratio < RATIO_DAMAGED:
                out["signals"].append(("damaged", "short_text", f"text is {ratio:.0%} of source (content dropped)"))
            elif ratio < RATIO_SUSPECT:
                out["signals"].append(("suspect", "short_text", f"text is {ratio:.0%} of source"))

            m = unknown_macros(source)
            out["own_macro_uses"], out["other_macro_uses"] = m["own"], m["other"]
            out["macro_uses_before_fix"] = m["before_own"] + m["before_other"]
            out["own_macro_uses_before_fix"] = m["before_own"]
            out["unknown_macros"] = m["ranked"][:8]
            if m["own"] >= OWN_DAMAGED:
                out["signals"].append(("damaged", "own_macros", f"{m['own']} uses of the paper's own macros still dropped"))
            elif m["own"] >= OWN_SUSPECT:
                out["signals"].append(("suspect", "own_macros", f"{m['own']} uses of the paper's own macros still dropped"))
            if m["other"] >= OTHER_SUSPECT:
                out["signals"].append(("suspect", "package_macros", f"{m['other']} uses of unknown package macros dropped"))

            checked, missing, examples = symbol_survival(source, text)
            out["symbols_checked"], out["symbols_missing"] = checked, missing
            out["symbol_examples"] = examples
            if checked >= SYMBOL_MIN_CHECKED:
                rate = missing / checked
                out["symbol_loss"] = round(rate, 3)
                if rate >= SYMBOL_LOSS_DAMAGED:
                    out["signals"].append(("damaged", "symbols", f"{missing}/{checked} symbols left no trace"))
                elif rate >= SYMBOL_LOSS_SUSPECT:
                    out["signals"].append(("suspect", "symbols", f"{missing}/{checked} symbols left no trace"))

    # One pass rather than a branch at each of the nine appends above. The
    # thresholds keep computing the level they always computed, and NOTE_SIGNALS
    # alone decides which of them reaches a reader, so promoting one back is a
    # change to that frozenset and to nothing else. Prose and order are untouched:
    # the stored string only changes its prefix, from "suspect: " to "note: ".
    out["signals"] = [("note" if key in NOTE_SIGNALS else lvl, key, why)
                      for lvl, key, why in out["signals"]]

    out["verdict"] = verdict_from(out["signals"], frozenset(), out.get("source_scan"))
    return out


# The quote pass. Our own marks are excluded: they are expected, folded by the
# check and rendered as an elision, so counting them here would report the design
# as damage.
#
# The two shape tells fold the ellipsis themselves rather than trusting a caller
# to do it first, so a quote cannot be read one way here and another way in
# scan_paper. Measured over the 393 stored quotes when this shipped: gap tells
# fell from 5 to 2 and quotes carrying any tell from 11 to 10.
QUOTE_TELLS = (
    ("undecodable bytes", lambda q: REPLACEMENT in q),
    ("latex residue", lambda q: bool(LATEX_RESIDUE.search(OUR_MARKS.sub("", q)))),
    ("gap where a token was", lambda q: bool(GAP_STRONG.search(fold_ellipsis(q)))),
    ("copied from text the extractor has since fixed",
     lambda q: bool(STALE_MARKS.search(fold_ellipsis(q)))),
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

    # This loop used to count every tell twice, once with a literal "..." folded
    # to "…" and once without, so that the fold could be previewed before it
    # shipped. It has shipped: the tells fold it themselves now, and a second
    # column would be identical to the first and read like a finding.
    counts = {name: 0 for name, _ in QUOTE_TELLS}
    touched = 0
    examples: list[dict] = []
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
    return {"total": len(rows), "touched": touched, "counts": counts,
            "examples": examples}


# ── the comparison ──────────────────────────────────────────────────────────
#
# This detector has been calibrated four times: 88% flagged, then 73%, then
# 100%, then 76% (as-built section 4). Every attempt picked patterns, ran the
# corpus, disliked the rate and adjusted, which is the detector agreeing with
# itself four times over. A rate can only tell you the check is wrong. It cannot
# tell you WHICH signal is wrong, and it cannot tell you what removing one would
# cost, so each round guessed and each round found out afterwards.
#
# Two known causes sat behind that 76%, of near-equal size, and fixing either
# alone lands around 63% and reads as failure. That is the specific thing a rate
# hides and the sole-cause table below shows: for each signal, how many papers
# would be clean if it alone stopped deciding the verdict.
#
# The fifth round then ran this on the Render disk and shipped what it read:
# gaps and package_macros are NOTE_SIGNALS now, 72% became 37%, and nothing moved
# stricter. The instrument stays, because the sixth round will want it and
# because a proposal that leaves no record is what decision 24 is about. With
# PROPOSED_NOTE_SIGNALS empty the crosstab would be the identity matrix, so the
# mode prints the sole-cause table and says plainly that there is no proposal.
#
# --compare-verdicts is read-only by construction. It stores nothing, so the
# measurement can be taken before anything is changed and disagreed with
# afterwards. PREVIEW_VERDICTS is the precedent: a preview that can write is one
# edit away from being the write.

# Long verdicts make unreadable column headers, and the cross-tab needs the
# incomplete-scan values in it or a paper would silently leave the table.
VERDICT_ORDER = ("clean", "suspect", "damaged") + UNSTORABLE
VERDICT_LABEL = {NO_TEXT: "no text", NO_SOURCE: "no source",
                 SOURCE_UNUSABLE: "unusable"}

# What the dossier renders the note on: `quality && quality !== "clean"` in
# app/app/g/[id]/p/[arxiv]/page.tsx. The unstorable verdicts never reach the
# column, so this is the reader-facing set exactly.
READER_FACING = ("suspect", "damaged")


def verdicts_for(paper: dict, demoted: frozenset) -> str:
    """One paper's verdict under a proposal.

    A paper whose text is not on this machine never reached a signal, so there is
    nothing to demote and the answer is the same either way. Recomputing it from
    the empty signals list would say "clean", which is the reassurance-nobody-
    computed bug (decision 23) reappearing in the preview rather than the write.
    """
    if paper["verdict"] == NO_TEXT:
        return NO_TEXT
    return verdict_from(paper["signals"], demoted, paper.get("source_scan"))


def compare_verdicts(papers: list[dict], quotes: dict) -> dict:
    """Every number the two tables print, computed once so --json hands back
    exactly what was on the screen."""
    formats: list[dict] = []
    groups = [(fmt, [p for p in papers if p["source_format"] == fmt])
              for fmt in ("latex", "pdf", None)]
    groups = [(f, g) for f, g in groups if g]
    if len(groups) > 1:
        groups.append(("all", papers))

    # No proposal means no crosstab. Every cell would land on the diagonal, and a
    # table of zero movement is indistinguishable on the page from a proposal
    # measured and found to cost nothing.
    if not PROPOSED_NOTE_SIGNALS:
        groups = []

    for fmt, group in groups:
        pairs = [(verdicts_for(p, frozenset()),
                  verdicts_for(p, PROPOSED_NOTE_SIGNALS)) for p in group]
        crosstab: dict[str, dict[str, int]] = {}
        for now, proposed in pairs:
            crosstab.setdefault(now, {})
            crosstab[now][proposed] = crosstab[now].get(proposed, 0) + 1
        formats.append({
            "source_format": fmt if fmt else "unknown",
            "papers": len(group),
            "crosstab": crosstab,
            "note_now": sum(1 for now, _ in pairs if now in READER_FACING),
            "note_proposed": sum(1 for _, pr in pairs if pr in READER_FACING),
        })

    # Sole cause. "Only reason not clean" is the question the ticket asks and the
    # one nobody has ever measured; "only reason for the note" is the same
    # question asked of the page, and the two differ exactly on papers whose
    # source archive is not on this disk, where removing the last signal leaves
    # "we did not look" rather than "clean". Both are printed because reading one
    # as the other is how a signal gets blamed for a missing file.
    signals = []
    for key in SIGNAL_KEYS:
        fires = [p for p in papers if any(k == key for _, k, _ in p["signals"])]
        sole_clean = sum(1 for p in fires
                         if verdicts_for(p, frozenset()) != "clean"
                         and verdicts_for(p, frozenset({key})) == "clean")
        sole_note = sum(1 for p in fires
                        if verdicts_for(p, frozenset()) in READER_FACING
                        and verdicts_for(p, frozenset({key})) not in READER_FACING)
        signals.append({"key": key, "papers": len(fires),
                        "sole_cause_clean": sole_clean,
                        "sole_cause_note": sole_note,
                        # A shipped note reads zero in both sole-cause columns by
                        # construction: it is already out of the verdict, so
                        # demoting it again frees nobody. That is the answer, not
                        # a gap in the table, and the flag is what says so.
                        "reports_as_note": key in NOTE_SIGNALS,
                        "demoted_by_proposal": key in PROPOSED_NOTE_SIGNALS})

    return {
        # Taken off the papers rather than written out here: `stale` is out of the
        # verdict by its LEVEL and the other two by their KEY, so a hand-written
        # list of the three would be a fourth place to forget.
        "note_signals": sorted(NOTE_SIGNALS | {k for p in papers
                                               for lvl, k, _ in p["signals"]
                                               if lvl in NOTE_LEVELS}),
        "proposed_note_signals": sorted(PROPOSED_NOTE_SIGNALS),
        "papers": len(papers),
        "formats": formats,
        "signals": signals,
        "quotes": {"total": quotes["total"],
                   "touched": quotes["touched"],
                   "counts": quotes["counts"]},
    }


def print_comparison(report: dict) -> None:
    proposed = ", ".join(report["proposed_note_signals"])
    print(f"\nVerdict comparison over {report['papers']} papers. "
          "Nothing was written and no verdict changed.")
    print("  Reported and already out of the verdict: "
          f"{', '.join(report['note_signals'])}.")
    if proposed:
        print(f"  Proposal under test: {proposed} report as a note and stop "
              "deciding the verdict.\n")
    else:
        # Said rather than shown. An empty crosstab and no sentence would read as
        # "the proposal moves nothing", which is the opposite of "nobody has
        # proposed anything".
        print("  No proposal is under test: PROPOSED_NOTE_SIGNALS is empty, so "
              "there is no\n  crosstab below. Name a signal in it to price "
              "demoting that signal. The sole\n  cause table stands on its own "
              "and is the half worth reading first.\n")

    for f in report["formats"]:
        n = f["papers"]
        cols = [v for v in VERDICT_ORDER
                if any(v in row for row in f["crosstab"].values())]
        rows = [v for v in VERDICT_ORDER if v in f["crosstab"]]
        head = "".join(f"{VERDICT_LABEL.get(v, v):>11}" for v in cols)
        print(f"  {f['source_format']:<8} {n:>4} papers          proposed →")
        print(f"      {'current ↓':<16}{head}")
        for v in rows:
            cells = "".join(f"{f['crosstab'][v].get(c, 0) or '·':>11}" for c in cols)
            print(f"      {VERDICT_LABEL.get(v, v):<16}{cells}")
        now, prop = f["note_now"], f["note_proposed"]
        print(f"      would show the dossier note:  now {now} ({now / n:.0%})"
              f"   proposed {prop} ({prop / n:.0%})\n")

    # These two columns are MARGINAL, and saying so is load-bearing. A paper
    # carrying two of these signals is sole-caused by neither and appears in
    # neither row, so the column does not sum to the effect of demoting several
    # at once. Measured on all 304 papers on the Render disk, which is the run
    # that decided the fifth calibration: gaps alone freed 33, package_macros
    # alone 44, both together 105. An operator who adds 33 and 44 concludes that
    # demoting both buys 77, and is 28 papers short — the co-occurrence — which is
    # the "fix one and land at 63%" reasoning this ticket was split in two to
    # prevent.
    print("  Sole cause: papers this signal fires on, and how many of them it is "
          "the only\n  reason for. Use it to find which signal to suspect, not to "
          "add up.\n  These columns are per signal: a paper carrying two of them "
          "is counted in\n  neither, so demoting several frees more papers than "
          "the rows suggest. The\n  joint effect of a proposal is its crosstab, "
          "never the sum of these rows.\n  A signal already reporting as a note "
          "reads zero in both: it is out of the\n  verdict, so demoting it again "
          "frees nobody.\n")
    print(f"      {'signal':<24}{'fires on':>10}{'only reason':>13}{'only reason':>13}")
    print(f"      {'':<24}{'':>10}{'not clean':>13}{'for the note':>13}")
    for s in report["signals"]:
        mark = " (note)" if s["reports_as_note"] else (
            " (proposed)" if s["demoted_by_proposal"] else "")
        print(f"      {s['key'] + mark:<24}{s['papers']:>10}"
              f"{s['sole_cause_clean']:>13}{s['sole_cause_note']:>13}")
    print("\n      'not clean' and 'for the note' differ only on papers whose source "
          "archive\n      is not on this machine: removing their last signal leaves "
          "\"we did not look\".")

    q = report["quotes"]
    if q["total"]:
        print(f"\n  Quote tells over {q['total']} stored quotes. A literal "
              "\"...\" is folded to \"…\"\n  before the shape tells, which is what "
              "`\\ldots` already renders as.\n")
        print(f"      {'tell':<50}{'quotes':>8}")
        for name, _ in QUOTE_TELLS:
            print(f"      {name:<50}{q['counts'][name]:>8}")
        print(f"      {'quotes carrying any tell':<50}{q['touched']:>8}")
    print()


# --clear-verdicts marks papers unaudited again, so the free pass that runs at
# every worker start picks them up. It is the retrospective half of the line
# extract_text.py now runs when it rewrites a file: that line protects every
# future re-extraction, and this is for the rows frozen before it existed. All
# 292 of them were written in one batch on 2026-07-31 by the calibration this
# file replaced twenty minutes later, against text that has since been
# re-extracted, and --only-unchecked filtered on the timestamp alone, so nothing
# revisited them (as-built 11.11). The timestamp half of that defect is closed:
# CHECK_VERSION would have caught those rows without anybody noticing them.
#
# It reads no disk at all, which is the point: it is the only mode of this file
# that does anything useful on a machine holding the database but not the corpus,
# and that is the machine the owner has. Where the corpus IS present, `--write` on
# its own is the better instrument — it recomputes in place and never leaves a
# paper with no verdict at all.
#
# It is no longer the tool for a calibration change. CHECK_VERSION is: the stored
# verdict stays on the page until a new one replaces it, where a clear leaves the
# verified stamp unqualified in the gap (decision 21). This is for a rewritten
# text on a machine that cannot re-measure it.
#
# extraction_signals is NOT NULL DEFAULT '[]' (migration 013), so it empties
# rather than nulls; NULL there would abort the statement. The check version goes
# with the verdict it describes: a version standing over no verdict claims a
# measurement nobody made.
CLEAR_VERDICTS = """
UPDATE papers p
   SET extraction_verdict = NULL,
       extraction_signals = '[]'::jsonb,
       extraction_check_version = NULL,
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

# What is about to be destroyed, one row per paper, written to a file before the
# UPDATE runs and on --dry-run too. `snapshot_map.py` is the precedent and commit
# 3b65766 is the rule: destroy nothing until you can replace something. The
# preview above is GROUP BY, so it says three papers were damaged and not WHICH
# three, and incident 14 has already lost this exact data once by having no copy
# of it. Restoring is deliberately not automated, for the same reason it is not
# in snapshot_map.py and one more: these values are stale by construction, so
# putting one back is a decision somebody has to make deliberately, and the file
# is plain JSON so the decision stays available.
#
# The check version is in the copy because it is half of what the row meant: a
# verdict without the calibration that produced it cannot be told from a verdict
# somebody would compute today, and telling those apart is the whole reason the
# column exists.
DUMP_VERDICTS = """
SELECT p.arxiv_id, p.extraction_verdict, p.extraction_signals,
       p.extraction_check_version, p.extraction_checked_at
FROM papers p
WHERE p.extraction_checked_at IS NOT NULL
{scope}ORDER BY p.arxiv_id
"""

# --only-unchecked's scope, and the reason migration 014 exists. The timestamp
# alone answers "has anybody audited this row", which is not the question: 292
# rows were audited by a calibration three commits replaced within half an hour
# and stayed frozen for weeks because the timestamp said yes. A row whose stored
# version is not the version this process computes is a row whose verdict was
# decided by code that no longer exists.
#
# IS DISTINCT FROM and not <>: the column is NULL on every row written before it
# existed, and `NULL <> 'abc'` is NULL, which is not TRUE, so those rows — the
# exact rows this was built for — would never be selected.
#
# {p} is the table alias, because the concept query joins and the unscoped one
# does not. It used to be a str.replace("p.", "") on the rendered clause, which
# worked and was one column name away from not working.
UNCHECKED_SCOPE = (
    "AND ({p}extraction_checked_at IS NULL\n"
    # The continuation sits under the opening paren in both callers, which happen
    # to share their indentation. Cosmetic, and the rendered statement is read by
    # people before it is run on a corpus.
    "                       OR {p}extraction_check_version IS DISTINCT FROM %(v)s)")

# The papers table is shared across every concept ever traced, so an unscoped
# statement here reaches another map's rows. Scoped exactly as extract_text.py
# --concept scopes itself, prompt version and all (it has none): a rewrite of the
# text is what invalidates a verdict, so the two must be able to name the same
# set of papers, and a paper belongs to a map whichever prompt version its
# definition was extracted at.
CONCEPT_SCOPE = ("   AND EXISTS (SELECT 1 FROM definitions d\n"
                 "               WHERE d.paper_id = p.id AND d.concept = %(concept)s)\n")
ONLY_SCOPE = "   AND p.arxiv_id = ANY(%(only_ids)s)\n"


def refuse_if_nothing_scanned(papers: list[dict]) -> None:
    """Incident 12's rule, in the one stage that publishes straight to readers: a
    per-item skip needs a global check.

    Some papers unscannable is an incomplete disk, which is ordinary here and
    always was (incident 7c). EVERY paper unscannable is an empty, unmounted or
    wrong `DATA_DIR`, and a run that writes nothing while reporting success is
    how that stays invisible until somebody wonders why no verdict ever changes.

    The boundary is zero and not a fraction, on the same reasoning as the
    `--reground` guard: three bad calibrations have shipped already and a guessed
    proportion here would be the fourth. It is deliberately NOT a "this machine
    looks partial" test. That test cannot be written: the Render worker's own
    disk was visibly partial on the run that produced the frozen batch, 12 of its
    papers having no text on it, so any threshold low enough to catch a laptop
    would have stopped the worker auditing anything at all (decision 23).

    Split out of `main` so it can be driven with a list of scans and no database.
    """
    unfinished = [p for p in papers if p["verdict"] in UNSTORABLE]
    if len(papers) > 1 and len(unfinished) == len(papers):
        sys.exit(
            f"\nRefusing to write: not one of {len(papers)} papers could be scanned "
            "through on this machine.\n"
            "  That is what an empty, unmounted or wrong DATA_DIR looks like, and this "
            "scan\n  cannot tell it apart from a corpus that genuinely is not here.\n"
            "  Nothing was written and every stored verdict stands.\n"
            f"  Looked in: {data_dir()}")


def clear_verdicts(conn, concept: str | None, only: list[str] | None,
                   dry_run: bool, out_path: str | None = None) -> None:
    """Hand these papers back to the free audit.

    Costs nothing and calls nothing: three columns of `papers`, no model, no
    network, no LLM. Deliberately shaped like stage_b_extract.py --reground and
    stage_h_claims.py --recheck minus the recompute, because the recompute needs
    the corpus and this exists for the machine that has not got one.

    A cleared verdict is not "clean", it is "unchecked", which is what these rows
    honestly are. But it is not therefore the safe direction, and decision 21
    says why: on the dossier the note sits directly under "verified verbatim
    against the source text" and is the only qualifier on that tick, so clearing
    it leaves the tick standing alone and the page claiming MORE than it did.
    That is the argument for treating the restart as part of this operation
    rather than as the next line of a runbook.
    """
    scope, params = "", {}
    if concept:
        scope += CONCEPT_SCOPE
        params["concept"] = concept
    if only:
        scope += ONLY_SCOPE
        params["only_ids"] = list(only)

    rows = conn.execute(PREVIEW_VERDICTS.format(scope=scope), params).fetchall()
    # Every scope the statement carries, in the line an operator reads before
    # deciding to proceed. --only used to print "every concept", which is the
    # widest possible reading of the narrowest possible scope.
    named = " and ".join(
        p for p in (f'"{concept}"' if concept else "",
                    f"{len(only)} named paper{'' if only and len(only) == 1 else 's'}"
                    if only else "") if p) or "every concept"
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

    # Before the UPDATE, and on the rehearsal too: a dry run that does not
    # produce the file has not rehearsed the part that matters.
    dumped = conn.execute(DUMP_VERDICTS.format(scope=scope), params).fetchall()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # The filename outlives the printed line by months, so it carries every
    # scope the statement carried. A two-paper copy filed as "all" is how
    # somebody later restores the wrong thing, or believes they already hold a
    # whole-table backup they never took.
    parts = [re.sub(r"[^a-z0-9]+", "_", concept.lower())] if concept else []
    if only:
        parts.append(f"{len(only)}paper" + ("s" if len(only) > 1 else ""))
    tag = "_".join(parts) or "all"
    dump = Path(out_path) if out_path else (
        data_dir() / "snapshots" / f"extraction_verdicts_{tag}_{stamp}.json")
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(json.dumps(
        {"taken_at": stamp, "concept": concept, "only": only,
         "papers": [{"arxiv_id": a, "extraction_verdict": v,
                     "extraction_signals": s, "extraction_check_version": cv,
                     "extraction_checked_at": t}
                    for a, v, s, cv, t in dumped]},
        indent=2, default=str), encoding="utf-8")
    print(f"\n  {len(dumped)} verdicts copied to {dump}")
    print("  Restoring one is a decision and is deliberately not automated; the "
          "file is plain JSON.")

    if dry_run:
        print("\n[dry-run] Nothing was written to the database. Re-run without "
              "--dry-run to clear these verdicts.")
        return

    cleared = conn.execute(CLEAR_VERDICTS.format(scope=scope), params).rowcount
    conn.commit()
    print(f"\n  Cleared {cleared} verdicts. Nothing else was touched: the extracted "
          f"text,\n  the quotes and the stamps on them are exactly as they were.")
    print("  These papers are now unaudited, so the free pass at the worker's next "
          "start\n  (--only-unchecked --write) will re-measure them against the text "
          "as it is now.")
    # Not "the safe direction". On the dossier this note is the only qualifier on
    # "verified verbatim against the source text", so removing it leaves the tick
    # unqualified and the page claiming more than it did a moment ago.
    print("\n  RESTART THE WORKER NOW. Until it boots, those papers show no note "
          "about\n  their text at all, which leaves the verified stamp on each of "
          "them standing\n  with nothing next to it. Nothing else re-audits them: "
          "not a timer, not the\n  app. If the worker is never restarted the "
          "verdicts never come back.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit extracted-text fidelity (no model, no network)")
    ap.add_argument("--concept", help="scope to one corpus; omit to scan every extracted paper")
    ap.add_argument("--prompt-version", default=env("PROMPT_VERSION", "v2"))
    ap.add_argument("--sample", type=int, default=0, help="print this many flagged papers in full")
    ap.add_argument("--json", help="write the full per-paper audit here, or with "
                                   "--compare-verdicts the comparison instead")
    ap.add_argument("--compare-verdicts", action="store_true",
                    help="scan as usual, then print today's verdicts against the "
                         "ones a named proposal would give, and a table of which "
                         "signal is the sole reason each paper is not clean. "
                         "Stores nothing and changes no threshold; it exists so "
                         "the next calibration is decided on a measurement rather "
                         "than on a rate")
    ap.add_argument("--only-unchecked", action="store_true",
                    help="skip papers already audited by this calibration. A paper "
                         "whose stored check version is not the one this process "
                         "computes counts as unaudited, so a change to a threshold "
                         "or a pattern re-measures itself at the next worker start "
                         "and nobody has to remember that it should. Makes this "
                         "cheap enough to run on every start")
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
    ap.add_argument("--out", metavar="PATH",
                    help="where --clear-verdicts copies the verdicts it is about to "
                         "remove (default DATA_DIR/snapshots/, timestamped)")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --clear-verdicts, report what would be cleared and "
                         "write nothing to the database. It still saves the copy, "
                         "because a rehearsal that skips the file has not "
                         "rehearsed the part that can fail")
    args = ap.parse_args()

    # First, so the refusal names the flag the operator actually typed. The rule
    # is the one PREVIEW_VERDICTS was built on: a preview that can write is one
    # edit away from being the write, and this one exists to be run before
    # anything is changed and argued with afterwards.
    if args.compare_verdicts and (args.write or args.clear_verdicts or args.dry_run
                                  or args.only_unchecked or args.sample):
        # --only-unchecked is in here because it is the flag most likely to be
        # copied by hand: it sits in the worker's own boot command. After a
        # refresh it selects only the papers nobody could audit, so the
        # comparison would come back over a handful of unscannable rows, with
        # percentages, every reader-facing cell at zero, and look like a finding.
        sys.exit("--compare-verdicts reads and prints only, over every audited "
                 "paper. It\nstores no verdict, clears none and rehearses nothing, "
                 "and it compares whole\ncolumns rather than sampling, so --write, "
                 "--clear-verdicts, --dry-run,\n--only-unchecked and --sample have "
                 "no meaning alongside it. --only-unchecked\nwould scope it to the "
                 "papers nobody has audited, which after a refresh is\nusually none "
                 "of them. Run it on its own, read the crosstab and then the sole\n"
                 "cause table, and decide.")
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
    if args.out and not args.clear_verdicts:
        sys.exit("--out is where --clear-verdicts copies the verdicts it removes. "
                 "The audit's own\nreport goes to --json.")

    # Cheap re-runs are what let this live in the worker's startup rather than in
    # somebody's terminal history. "Unchecked" now means unchecked OR checked by
    # a calibration this process is not running; the parameter only exists when
    # the clause does, so the unflagged query still carries no parameters at all.
    scoped = args.only_unchecked
    version_param = {"v": CHECK_VERSION} if scoped else {}

    with psycopg.connect(env("DATABASE_URL")) as conn:
        if args.clear_verdicts:
            # Ahead of the scan, and it returns rather than falling through: this
            # mode asks the database only, and the machine most likely to run it
            # has no corpus for the scan below to read.
            clear_verdicts(conn, args.concept, args.only, args.dry_run, args.out)
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
            """.format(unchecked=UNCHECKED_SCOPE.format(p="p.") if scoped else ""),
                {"c": args.concept, "pv": args.prompt_version, **version_param}).fetchall()
        else:
            rows = conn.execute("""
                SELECT arxiv_id, title, source_format, raw_path,
                       extracted_text_path, text_title_match
                FROM papers WHERE extracted_text_path IS NOT NULL
                  {unchecked}
                ORDER BY arxiv_id
            """.format(unchecked=UNCHECKED_SCOPE.format(p="") if scoped else ""),
                version_param or None).fetchall()

        cols = ("arxiv_id", "title", "source_format", "raw_path",
                "extracted_text_path", "text_title_match")
        papers = [scan_paper(dict(zip(cols, r))) for r in rows]
        quotes = scan_quotes(conn, args.concept, args.prompt_version)

        if args.compare_verdicts:
            # Returns before the write block and before the usual report: the
            # question here is what a proposal would do, and the corpus tallies
            # underneath answer a different one loudly enough to be mistaken for
            # it. Nothing above this line issues anything but SELECT.
            comparison = compare_verdicts(papers, quotes)
            print_comparison(comparison)
            if args.json:
                out = Path(args.json)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
                print(f"  Comparison written to {out}")
            return

        if args.write:
            # A paper this machine could not scan through is left alone rather
            # than recorded: another machine has the file, and its verdict is the
            # one worth keeping (incident 7c). The row stays unaudited, which is
            # what it is, and the free pass collects it wherever the file lives.
            unfinished = [p for p in papers if p["verdict"] in UNSTORABLE]
            refuse_if_nothing_scanned(papers)
            stored = 0
            for p in papers:
                if p["verdict"] in UNSTORABLE:
                    continue
                conn.execute("""
                    UPDATE papers SET extraction_verdict = %(v)s,
                                      extraction_signals = %(s)s,
                                      extraction_check_version = %(cv)s,
                                      extraction_checked_at = now()
                    WHERE arxiv_id = %(a)s
                """, {"v": p["verdict"], "a": p["arxiv_id"], "cv": CHECK_VERSION,
                      # The stored string is unchanged by the key: this column is
                      # read by people and by the dossier, never parsed back. A
                      # demoted signal shows as "note: ..." here, which is the one
                      # visible difference the demotion makes to an operator.
                      "s": json.dumps([f"{lvl}: {why}" for lvl, _key, why in p["signals"]])})
                stored += 1
            conn.commit()
            print(f"  Wrote {stored} verdicts to papers.extraction_verdict "
                  f"at calibration {CHECK_VERSION}.\n")
            if unfinished:
                # Named, not just counted. This is the line that says the corpus
                # on this machine is not the whole corpus, and it is the one an
                # operator running --write off the worker needs to see.
                print(f"  {len(unfinished)} of {len(papers)} could not be scanned "
                      f"through here and were left unaudited:")
                for verdict in UNSTORABLE:
                    c = sum(1 for p in unfinished if p["verdict"] == verdict)
                    if c:
                        print(f"      {verdict}: {c}")
                print("  Their rows are untouched, so whichever machine holds the "
                      "files will\n  audit them. If that is not this machine, "
                      "these verdicts are not yours to write.\n")

    scope = f'"{args.concept}"' if args.concept else "every extracted paper"
    print(f"\nExtraction audit: {scope} ({len(papers)} papers)\n")

    for fmt in ("latex", "pdf", None):
        group = [p for p in papers if p["source_format"] == fmt]
        if not group:
            continue
        n = len(group)
        tally = {v: sum(1 for p in group if p["verdict"] == v) for v in
                 ("clean", "suspect", "damaged") + UNSTORABLE}
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
        for level, _key, why in p["signals"]:
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

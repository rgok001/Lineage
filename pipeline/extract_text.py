"""Acquisition: turn downloaded arXiv source into clean text for the pipeline.

Reads each fetched paper's raw file (from the papers table), converts LaTeX
source (or PDF fallback) to plain text, writes it under DATA_DIR/text/, and
records extracted_text_path on the row.

This text is the ground truth the Stage E grounding check string-matches quotes
against, so "clean" here means: real prose, comments stripped, \\input sub-files
inlined, math reduced to readable placeholders.

Separate from fetching and from Stage B extraction: this only converts source ->
text. Skips papers already extracted unless --force.

Usage:
  python pipeline/extract_text.py
  python pipeline/extract_text.py --limit 10 --force
"""

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, data_dir, env, text_digest  # noqa: E402


def read_archive(raw_bytes: bytes) -> tuple[dict[str, str], dict[str, bytes]]:
    """Return ({tex_name: content}, {pdf_name: bytes}) from the source archive.

    Some arXiv 'source' archives are really a PDF wrapped in a trivial \\includepdf
    stub, so we surface embedded PDFs as a fallback text source too.
    """
    texs: dict[str, str] = {}
    pdfs: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(raw_bytes), mode="r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                f = tf.extractfile(m)
                if not f:
                    continue
                if m.name.lower().endswith(".tex"):
                    texs[m.name] = f.read().decode("utf-8", "replace")
                elif m.name.lower().endswith(".pdf"):
                    pdfs[m.name] = f.read()
    except tarfile.ReadError:
        # Not a tarball — arXiv sometimes serves a single gzipped .tex.
        try:
            data = gzip.decompress(raw_bytes).decode("utf-8", "replace")
            if "\\" in data:
                texs["main.tex"] = data
        except OSError:
            pass
    return texs, pdfs


def find_main_tex(texs: dict[str, str]) -> str | None:
    for name, content in texs.items():
        if "\\begin{document}" in content:
            return name
    for name, content in texs.items():
        if "\\documentclass" in content:
            return name
    return max(texs, key=lambda n: len(texs[n])) if texs else None


INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")


def inline_inputs(main: str, texs: dict[str, str]) -> str:
    """Recursively splice \\input/\\include sub-files in by basename."""
    by_base = {Path(n).stem: c for n, c in texs.items()}

    def expand(content: str, seen: set[str], depth: int) -> str:
        if depth > 15:
            return content

        def repl(m: re.Match) -> str:
            key = Path(m.group(1).strip()).stem
            if key in by_base and key not in seen:
                return expand(by_base[key], seen | {key}, depth + 1)
            return ""  # missing/circular include -> drop the directive

        return INPUT_RE.sub(repl, content)

    return expand(texs[main], set(), 0)


# Citation and cross-reference macros. pylatexenc knows \cite and renders it
# `<cit.>`, but it does not know natbib and friends, and an unknown macro is
# dropped silently: the citation vanishes and its surrounding punctuation stays,
# so "as shown by \citep{x}, the model" extracted as "as shown by , the model"
# and a paper read as ungrammatical when the fault was ours. Every one of these
# now leaves the same mark, which downstream renders as an elision.
CITE_MACROS = [
    "cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear",
    "citeyearpar", "shortcite", "shortcites", "citen", "citenum", "onlinecite",
    "parencite", "textcite", "autocite", "footcite", "fullcite", "nocite",
]
REF_MACROS = ["ref", "autoref", "cref", "Cref", "eqref", "pageref", "vref", "nameref"]


# The list above is the fast path, not the guarantee. Papers define their own
# citation macros (\newcommand{\mycite}...), packages invent more, and an
# unknown macro is dropped silently, which is the failure this whole fix exists
# to stop. Any macro whose name contains "cite" is normalised to \cite before
# parsing, so the rule covers the names nobody has thought of yet. Matching is
# case-insensitive and the arguments are consumed with it.
# Case-insensitive, because \Citet and \Cref are as common as their lowercase
# forms. The whitespace allowance sits INSIDE each optional argument group: put
# it outside and a macro with no arguments eats the space after it, welding the
# mark to the next word.
UNKNOWN_CITE_RE = re.compile(
    r"\\[a-zA-Z@]*cite[a-zA-Z@*]*(?:\s*\[[^\]]*\]){0,2}(?:\s*\{[^{}]*\})?",
    re.IGNORECASE,
)


def normalise_cite_macros(latex: str) -> str:
    return UNKNOWN_CITE_RE.sub(r"\\cite{x}", latex)


# Macros the paper defines for itself. Same failure as the citation macros above,
# one class wider: pylatexenc drops an unknown macro in silence and takes its
# content with it. `\newcommand{\dmodel}{d_{model}}` turns "dimension $\dmodel$"
# into "dimension.", which is why Attention Is All You Need carried a quote
# reading "vectors of dimension ." and left 17 edges inferred. Plain
# `$d_{model}$` was never the problem: it extracts correctly.
#
# Nobody writes \newcommand for something they would not mind losing, so these
# are expanded rather than marked. The definitions are collected and their uses
# substituted before pylatexenc ever sees the source.
DEF_HEAD = re.compile(
    r"\\(newcommand|renewcommand|providecommand|DeclareMathOperator|def)\s*\*?\s*"
    r"(?:\{\s*\\([a-zA-Z@]+)\s*\}|\\([a-zA-Z@]+))")
ARGC = re.compile(r"\A\s*\[\s*(\d)\s*\]")
OPTIONAL_DEFAULT = re.compile(r"\A\s*\[[^\]]*\]")
MAX_EXPANSION_PASSES = 4  # a macro defined in terms of another; bounded so a
                          # self-referential \renewcommand cannot spin forever


def read_group(s: str, i: int) -> tuple[str | None, int]:
    """Read a brace-balanced group starting at s[i] == '{'.

    Balanced braces are not a regular language, so this is a scanner rather than
    a pattern. An escaped brace is skipped with its backslash, because `\\{` is a
    literal character in the body, not a nesting level.
    """
    if i >= len(s) or s[i] != "{":
        return None, i
    depth, start, j = 0, i + 1, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:j], j + 1
        j += 1
    return None, len(s)  # unbalanced source; leave it to pylatexenc to survive


def collect_own_macros(latex: str) -> tuple[dict[str, tuple[int, str]], list[tuple[int, int]]]:
    """({name: (argument count, body)}, spans of the definitions themselves).

    The spans are returned so the definitions can be removed once their uses are
    substituted: leaving them behind would let a later pass expand a macro inside
    its own definition body.
    """
    defs: dict[str, tuple[int, str]] = {}
    spans: list[tuple[int, int]] = []
    for m in DEF_HEAD.finditer(latex):
        name = m.group(2) or m.group(3)
        kind, i = m.group(1), m.end()
        nargs = 0
        if kind == "def":
            # \def\foo#1#2{...}: the parameter text is whatever sits before the
            # body. Only the plain numbered form is handled; delimited parameters
            # are rare in papers and too sharp to guess at.
            params = re.match(r"\A((?:#\d)*)\s*", latex[i:])
            nargs = len(params.group(1)) // 2
            i += params.end()
        else:
            if am := ARGC.match(latex[i:]):
                nargs = int(am.group(1))
                i += am.end()
                if dm := OPTIONAL_DEFAULT.match(latex[i:]):
                    i += dm.end()  # a default value makes the first argument optional
        body, after = read_group(latex, i)
        if body is None or not name:
            continue
        defs[name] = (nargs, body)
        spans.append((m.start(), after))
    return defs, spans


def expand_own_macros(latex: str) -> str:
    """Substitute the paper's own macro definitions into its text.

    Runs before normalise_cite_macros so that a paper's `\\newcommand{\\mycite}`
    wrapper expands to the real citation command, which the citation rule then
    folds to a single mark.
    """
    defs, spans = collect_own_macros(latex)
    if not defs:
        return latex

    use = re.compile(r"\\(" + "|".join(sorted(map(re.escape, defs), key=len, reverse=True)) + r")(?![a-zA-Z@])")

    def once(s: str) -> tuple[str, bool]:
        out, i, changed = [], 0, False
        while True:
            m = use.search(s, i)
            if not m:
                out.append(s[i:])
                break
            nargs, body = defs[m.group(1)]
            j, args = m.end(), []
            for _ in range(nargs):
                arg, j2 = read_group(s, skip_ws(s, j))
                if arg is None:
                    break
                args.append(arg)
                j = j2
            if len(args) != nargs:  # arguments not where the definition promised
                out.append(s[i:m.end()])
                i = m.end()
                continue
            expanded = body
            for k, arg in enumerate(args, 1):
                expanded = expanded.replace(f"#{k}", arg)
            out.append(s[i:m.start()])
            out.append(expanded)
            i, changed = j, True
        return "".join(out), changed

    # Definitions first, so a body is never expanded into itself.
    kept, last = [], 0
    for start, end in sorted(spans):
        kept.append(latex[last:start])
        last = end
    kept.append(latex[last:])
    stripped = "".join(kept)

    for _ in range(MAX_EXPANSION_PASSES):
        stripped, changed = once(stripped)
        if not changed:
            break
    return stripped


def skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\n":
        i += 1
    return i


# The marks we inject into pylatexenc's context, as data, so the extractor
# version below can digest them without importing pylatexenc. `_latex_context`
# builds its MacroTextSpecs from this same list, so the digest covers the marks
# actually used rather than a second copy of them.
CITE_MARK = "<cit.>"
REF_MARK = "<ref>"
# pylatexenc and pymupdf are asked for these modes and no others. They are the
# rest of "what text comes out" that is not one of our own patterns.
PARSE_MATH_MODE = "text"
PARSE_STRICT_SPACES = False
PDF_TEXT_MODE = "text"


def _lineage_macro_specs() -> list[tuple[str, str]]:
    return ([(m, CITE_MARK) for m in CITE_MACROS]
            + [(m, REF_MARK) for m in REF_MACROS])


def _latex_context():
    from pylatexenc.latex2text import get_default_latex_context_db, MacroTextSpec
    db = get_default_latex_context_db()
    db.add_context_category(
        "lineage-citations",
        prepend=True,
        macros=[MacroTextSpec(name, simplify_repl=repl)
                for name, repl in _lineage_macro_specs()],
    )
    return db




def tidy_marks(text: str) -> str:
    """Punctuation left stranded once a citation is reduced to a mark: a tie
    (`~`) that used to bind the citation to the word before it, the empty
    brackets a `(\\cite{x})` leaves behind, and the space that opens up in front
    of the comma. Cosmetic only, and applied at extraction so the text a quote is
    matched against is the text a reader sees."""
    text = re.sub(r"~\s*(<cit\.>|<ref>)", r" \1", text)
    text = re.sub(r"[(\[]\s*(<cit\.>|<ref>)\s*[)\]]", r"\1", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"[(\[]\s*[)\]]", "", text)
    return re.sub(r"[ \t]{2,}", " ", text)


RAW_STRIP = re.compile(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?")
MAX_BISECT_DEPTH = 6      # 64 pieces at most, so a pathological file cannot spin
MIN_BISECT_CHARS = 2_000  # below this, a piece is small enough to strip whole


def _parse(latex: str) -> str | None:
    """pylatexenc's text, or None if it could not read this. Its tolerant mode is
    already on by default (checked), so an exception here is not something a flag
    will fix."""
    from pylatexenc.latex2text import LatexNodes2Text
    try:
        return LatexNodes2Text(latex_context=_latex_context(),
                               math_mode=PARSE_MATH_MODE,
                               strict_latex_spaces=PARSE_STRICT_SPACES
                               ).latex_to_text(latex)
    except Exception:
        return None


def _split_point(latex: str) -> int | None:
    """A paragraph break near the middle. Splitting between paragraphs keeps most
    environments whole; one that does span the cut fails on both sides and is
    stripped there, which is the same outcome it had before, confined to itself."""
    mid = len(latex) // 2
    before = latex.rfind("\n\n", 0, mid)
    after = latex.find("\n\n", mid)
    candidates = [i for i in (before, after) if i > 0]
    return min(candidates, key=lambda i: abs(i - mid)) if candidates else None


def _parse_or_bisect(latex: str, depth: int = 0) -> tuple[str, int]:
    """(text, characters that had to be stripped rather than parsed).

    One unreadable construct used to cost a paper its entire text: the whole file
    fell to a regex that leaves braces and dollars standing and loses every
    heading. On the attention corpus that was 17 papers of 146. The construct is
    still unreadable, but it is now the size of the problem rather than the file
    being the size of the problem, so the rest of the paper parses properly and
    only the piece that defeats the parser is stripped.
    """
    text = _parse(latex)
    if text is not None:
        return text, 0
    if depth >= MAX_BISECT_DEPTH or len(latex) < MIN_BISECT_CHARS:
        return RAW_STRIP.sub(" ", latex), len(latex)
    cut = _split_point(latex)
    if cut is None:
        return RAW_STRIP.sub(" ", latex), len(latex)
    left, l_stripped = _parse_or_bisect(latex[:cut], depth + 1)
    right, r_stripped = _parse_or_bisect(latex[cut:], depth + 1)
    return left + "\n\n" + right, l_stripped + r_stripped


def latex_to_text(latex: str) -> str:
    latex = normalise_cite_macros(expand_own_macros(latex))
    text, stripped = _parse_or_bisect(latex)
    if stripped:
        print(f"    (pylatexenc could not read {stripped:,} of {len(latex):,} chars; "
              f"that part stripped, the rest parsed)", file=sys.stderr)
    return normalize(tidy_marks(text))


def pdf_to_text(source) -> str:
    """Extract text from a PDF given a path or raw bytes."""
    import fitz  # pymupdf
    if isinstance(source, (bytes, bytearray)):
        doc = fitz.open(stream=source, filetype="pdf")
    else:
        doc = fitz.open(source)
    with doc:
        raw = "\n".join(page.get_text(PDF_TEXT_MODE) for page in doc)
    # PDF layout splits words across line breaks ("con-\nvergence"); rejoin them
    # so exact-match grounding isn't defeated by hyphenation artifacts.
    raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw)
    return normalize(raw)


# Title words carrying no signal — ignored when scoring title-vs-text agreement.
STOPWORDS = {
    "with", "from", "using", "their", "this", "that", "than", "then", "into",
    "over", "under", "between", "through", "towards", "toward", "based", "very",
    "your", "ours", "about", "which", "while", "were", "have", "been", "does",
}
TITLE_MATCH_MIN = 0.5  # below this, metadata and text probably describe different papers


def title_match(title: str | None, text: str) -> float | None:
    """Fraction of significant title words that appear in the extracted text.

    A fetch can succeed while returning the *wrong* paper (upstream metadata can
    pair a title with another paper's arXiv ID). The title almost always appears
    in a paper's own text, so weak agreement means the two disagree.
    """
    if not title:
        return None
    toks = {t for t in re.findall(r"[a-z0-9]+", title.lower())
            if len(t) > 3 and t not in STOPWORDS}
    if not toks:
        return None
    hay = text.lower()
    return sum(1 for t in toks if t in hay) / len(toks)


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse runs of blank lines
    return text.strip() + "\n"


MIN_LATEX_CHARS = 500  # below this, a .tex is probably just an \includepdf stub


# ── which extractor produced a paper's text ─────────────────────────────────
#
# Ticket #29. A stamp says which bytes it was checked against; this says which
# code produced those bytes. It is provenance and a re-extraction queue, not an
# invalidator: if the text on disk has not changed, a stamp against it is still
# about that text, whatever the extractor has since learned. Letting this redden
# a stamp would redden the whole corpus on every extractor commit, and a detector
# that fires on nearly all of its input has stopped measuring its input — this
# project has paid for that four times (decisions 24 and 25).
#
# Built exactly like check_version() in check_extraction.py (migration 014,
# decision 25), for the reasons it gives, and curated for the same reason:
#
# - NOT a hash of this file. A digest over a busy file is a detector that fires
#   on nearly every commit, including on a docstring.
# - NOT the pylatexenc or pymupdf release strings. Those redden on
#   `pip install -U` while nothing on disk has changed. A library bump only
#   changes a stored text when we re-extract, and re-extracting moves
#   papers.extracted_text_digest, which is already the thing that moves a stamp.
# - A digest and not a hand-bumped integer: a number somebody has to remember to
#   raise is a number somebody forgets, and 014 earned that sentence.
#
# Declared here rather than beside _latex_context because it reads every constant
# above it and the module is evaluated top to bottom. The inputs are the ones the
# design names; adding to the list changes what "the same extractor" means, so it
# belongs in a commit that says so.


def _rx(p: re.Pattern) -> list:
    """A pattern's identity: source AND flags. `re.IGNORECASE` on
    UNKNOWN_CITE_RE is the difference between catching \\Citep and dropping it,
    and a digest blind to flags would call those two the same extractor."""
    return [p.pattern, p.flags]


def extractor_version() -> str:
    """A short digest of what decides the text this module emits.

    Reads the module globals when called rather than closing over them, so a test
    can move a constant and ask for the version again.
    """
    inputs = {
        "citations": [sorted(CITE_MACROS), sorted(REF_MACROS),
                      _rx(UNKNOWN_CITE_RE), _lineage_macro_specs()],
        "own_macros": [_rx(DEF_HEAD), _rx(ARGC), _rx(OPTIONAL_DEFAULT),
                       MAX_EXPANSION_PASSES],
        "fallback": [_rx(RAW_STRIP), MAX_BISECT_DEPTH, MIN_BISECT_CHARS,
                     MIN_LATEX_CHARS],
        "parsers": [PARSE_MATH_MODE, PARSE_STRICT_SPACES, PDF_TEXT_MODE],
    }
    # sort_keys, so a dict reordering is not an extractor change; and json's own
    # number formatting, so 4 and 4.0 do not read as the same input. Nothing here
    # is hash()ed: str.__hash__ is salted per process and this value is stored.
    blob = json.dumps(inputs, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


EXTRACTOR_VERSION = extractor_version()


def extract_one(raw_path: Path, source_format: str) -> str | None:
    raw = raw_path.read_bytes()
    if source_format == "pdf":
        return pdf_to_text(raw_path)
    if source_format != "latex":
        return None

    texs, pdfs = read_archive(raw)
    latex_text = ""
    if texs:
        main = find_main_tex(texs)
        if main:
            merged = inline_inputs(main, texs)
            latex_text = latex_to_text(merged)
            # A preamble full of custom \newcommand macros can make pylatexenc
            # emit nothing at all (observed on Bahdanau 2014: 57k chars -> 37
            # newlines). Retry on the body alone, which parses fine. Only as a
            # fallback: the preamble holds \title, and dropping it universally
            # would sink text_title_match for papers that convert correctly.
            if len(latex_text.strip()) < MIN_LATEX_CHARS:
                m = re.search(r"\\begin\{document\}", merged)
                if m:
                    body_text = latex_to_text(merged[m.end():])
                    if len(body_text.strip()) > len(latex_text.strip()):
                        latex_text = body_text

    # Fall back to (or prefer) an embedded PDF when the LaTeX is a thin wrapper.
    if len(latex_text.strip()) < MIN_LATEX_CHARS and pdfs:
        biggest = max(pdfs.values(), key=len)
        pdf_text = pdf_to_text(biggest)
        return pdf_text if len(pdf_text.strip()) > len(latex_text.strip()) else latex_text
    return latex_text or None


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert fetched arXiv source to clean text.")
    ap.add_argument("--limit", type=int, help="process at most N papers")
    ap.add_argument("--force", action="store_true", help="re-extract even if text already exists")
    ap.add_argument("--concept", metavar="NAME",
                    help="restrict to the papers of one map. The papers table is "
                         "shared across every concept ever traced, so --force "
                         "without this re-extracts the whole table, and changing "
                         "text under a curated map's quotes is not something to "
                         "do as a side effect of repairing a different one")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be extracted and which papers' "
                         "extracted_text_digest would be written or corrected, "
                         "and write nothing — no file and no row. This is the "
                         "rehearsal for the digest backfill (RUNBOOK section 8)")
    args = ap.parse_args()

    text_root = data_dir() / "text"
    if not args.dry_run:
        text_root.mkdir(parents=True, exist_ok=True)
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)

    params: dict = {}
    scope = ""
    if args.concept:
        scope = ("  AND EXISTS (SELECT 1 FROM definitions d WHERE d.paper_id = papers.id "
                 "AND d.concept = %(concept)s)\n")
        params["concept"] = args.concept
    sql = ("SELECT arxiv_id, source_format, raw_path, extracted_text_path, title, "
           "extracted_text_digest "
           f"FROM papers WHERE raw_path IS NOT NULL\n{scope}ORDER BY arxiv_id")
    rows = conn.execute(sql, params).fetchall()
    if args.force and not args.concept:
        print("Re-extracting EVERY paper in the table, across all concepts. "
              "--concept scopes it to one map.")
    if args.limit:
        rows = rows[:args.limit]

    if not rows:
        print("Nothing to extract (no fetched papers).")
        return

    if args.dry_run:
        print("[dry-run] Nothing will be written: no text file, no row.\n")

    done = failed = skipped = 0
    digests_written = digests_changed = digests_unreadable = 0
    flagged: list[tuple[str, float]] = []
    for i, (aid, fmt, raw_path, etpath, title, stored_digest) in enumerate(rows, 1):
        # Skip only if already extracted AND the text file is on THIS disk. The
        # DB is shared across machines but files are per-disk, so a paper marked
        # extracted on another worker still needs its text produced here.
        if not args.force and etpath and (data_dir() / etpath).exists():
            skipped += 1
            # The named recomputer for papers.extracted_text_digest (ticket #29).
            # A derived value stored and then left to age is this project's first
            # named fault, and this column would age silently: a file changed by
            # anything other than this script — a hand edit, a truncated write, a
            # restored disk — would leave every stamp on that paper agreeing with
            # a digest that describes bytes which are gone.
            #
            # Updating it makes those stamps go stale, which claims LESS. It never
            # touches a stamp's own digest, which would claim more and is the
            # silent re-anchoring incident 10 named as dishonest.
            #
            # extractor_version is deliberately NOT written here. A skip knows the
            # bytes and not who made them; claiming this extractor produced a file
            # it merely read would be a false provenance claim, and would empty
            # the `extractor_version IS DISTINCT FROM <current>` queue that is the
            # whole point of the column. It stays NULL until a real extraction.
            try:
                digest = text_digest((data_dir() / etpath).read_bytes())
            except OSError as exc:
                digests_unreadable += 1
                print(f"[{i}/{len(rows)}] {aid}: text present but unreadable "
                      f"({etpath}): {exc}")
                continue
            if digest == stored_digest:
                continue
            if stored_digest is None:
                digests_written += 1
            else:
                digests_changed += 1
                print(f"[{i}/{len(rows)}] {aid}: ⚠ THE TEXT ON DISK IS NOT THE TEXT "
                      f"THE DATABASE DESCRIBES ({etpath})")
                print(f"    stored {stored_digest}")
                print(f"    on disk {digest}")
                print("    Recording the file as it is. Every stamp checked against "
                      "the old bytes now renders stale, which is the truth about it.")
            if not args.dry_run:
                conn.execute(
                    "UPDATE papers SET extracted_text_digest=%s WHERE arxiv_id=%s",
                    (digest, aid))
                conn.commit()
            continue
        raw = data_dir() / raw_path  # paths are stored relative to DATA_DIR
        if not raw.exists():
            print(f"[{i}/{len(rows)}] {aid}: raw file missing ({raw_path}), skipping")
            failed += 1
            continue
        print(f"[{i}/{len(rows)}] {aid}: extracting ({fmt})…")
        try:
            text = extract_one(raw, fmt)
        except Exception as e:
            print(f"    ✗ {type(e).__name__}: {e}")
            failed += 1
            continue
        if not text or len(text.strip()) < 200:
            print(f"    ✗ no usable text extracted")
            failed += 1
            continue

        out = text_root / f"{aid.replace('/', '_')}.txt"
        rel = str(out.relative_to(data_dir())).replace("\\", "/")
        score = title_match(title, text)
        if args.dry_run:
            print(f"    [dry-run] would write {len(text):,} chars -> {rel}")
            done += 1
            continue
        # newline="\n" so the artefact is the same bytes whichever platform
        # extracted it, and the digest below is therefore comparable across them.
        # On the Linux worker this changes nothing.
        out.write_text(text, encoding="utf-8", newline="\n")
        # From the file, after the write, and not from the string in memory: the
        # column describes the bytes on disk, not the intention that produced
        # them. A truncated or partially-written file must digest as what it is.
        digest = text_digest(out.read_bytes())
        # The extraction verdict goes out with the file it describes. It is a
        # measurement of one specific text, and the line above has just replaced
        # that text; leaving the stamp behind is how every verdict in the table
        # came to describe a corpus that no longer exists (as-built 11.11). NULL
        # is not "no damage", it is "unchecked", which is exactly true here and
        # is what check_extraction.py --only-unchecked --write looks for, so the
        # worker re-audits this paper free at its next start.
        # extraction_signals is NOT NULL DEFAULT '[]' (migration 013), so it
        # empties rather than nulls; NULL there would abort the extraction.
        # The check version (migration 014) goes with the verdict it qualifies:
        # a version left standing over no verdict names a calibration for a
        # measurement that no longer exists.
        # The digest and the extractor version (migration 015) go in the same
        # statement as the path, and this is the only statement in the repository
        # that writes extracted_text_path. The invariant is that path, digest and
        # extractor version are written together or not at all: a path without a
        # digest is a file nobody can name, and a digest without the path it
        # describes is worse.
        conn.execute(
            "UPDATE papers SET extracted_text_path=%s, text_title_match=%s, "
            "extracted_text_digest=%s, extractor_version=%s, "
            "extraction_verdict=NULL, extraction_signals='[]'::jsonb, "
            "extraction_check_version=NULL, "
            "extraction_checked_at=NULL WHERE arxiv_id=%s",
            (rel, score, digest, EXTRACTOR_VERSION, aid),
        )
        conn.commit()
        score_str = "title n/a" if score is None else f"title match {score:.0%}"
        print(f"    ✓ {len(text):,} chars, {score_str} -> {rel}")
        if score is not None and score < TITLE_MATCH_MIN:
            print(f"    ⚠ METADATA MISMATCH: text does not look like \"{title}\"")
            flagged.append((aid, score))
        done += 1

    conn.close()
    verb = "would be extracted" if args.dry_run else "extracted"
    print(f"\nDone: {done} {verb}, {skipped} already present, {failed} failed.")
    print(f"Extractor version: {EXTRACTOR_VERSION}")
    if digests_written or digests_changed or digests_unreadable:
        w = "would be written" if args.dry_run else "written"
        print(f"\nDigests of text already on this disk (migration 015), {w}: "
              f"{digests_written} newly recorded, {digests_changed} corrected "
              f"because the file had changed under us, {digests_unreadable} "
              f"unreadable.")
        if digests_changed:
            print("  A corrected digest makes that paper's stamps render stale. "
                  "They are stale: they were checked against bytes that are gone.")
    if flagged:
        print(f"\n⚠ {len(flagged)} paper(s) below the {TITLE_MATCH_MIN:.0%} title-match "
              f"threshold — text and metadata likely describe different papers:")
        for aid, score in flagged:
            print(f"    {aid}  ({score:.0%})")
        print("  Downstream stages must filter on text_title_match >= "
              f"{TITLE_MATCH_MIN}; inspect before trusting these.")


if __name__ == "__main__":
    main()

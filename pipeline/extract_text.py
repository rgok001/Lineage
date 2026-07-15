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
import io
import re
import sys
import tarfile
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, data_dir, env  # noqa: E402


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


def latex_to_text(latex: str) -> str:
    from pylatexenc.latex2text import LatexNodes2Text
    try:
        text = LatexNodes2Text(math_mode="text", strict_latex_spaces=False).latex_to_text(latex)
    except Exception as e:  # pylatexenc can choke on exotic macros; degrade, don't die
        print(f"    (pylatexenc fell back to raw strip: {e})", file=sys.stderr)
        text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", latex)
    return normalize(text)


def pdf_to_text(source) -> str:
    """Extract text from a PDF given a path or raw bytes."""
    import fitz  # pymupdf
    if isinstance(source, (bytes, bytearray)):
        doc = fitz.open(stream=source, filetype="pdf")
    else:
        doc = fitz.open(source)
    with doc:
        raw = "\n".join(page.get_text() for page in doc)
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
            latex_text = latex_to_text(inline_inputs(main, texs))

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
    args = ap.parse_args()

    text_root = data_dir() / "text"
    text_root.mkdir(parents=True, exist_ok=True)
    conn = psycopg.connect(env("DATABASE_URL"))

    where = "raw_path IS NOT NULL" + ("" if args.force else " AND extracted_text_path IS NULL")
    sql = f"SELECT arxiv_id, source_format, raw_path, title FROM papers WHERE {where} ORDER BY arxiv_id"
    rows = conn.execute(sql).fetchall()
    if args.limit:
        rows = rows[:args.limit]

    if not rows:
        print("Nothing to extract (all fetched papers already have text; use --force to redo).")
        return

    done = failed = 0
    flagged: list[tuple[str, float]] = []
    for i, (aid, fmt, raw_path, title) in enumerate(rows, 1):
        raw = REPO_ROOT / raw_path
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
        out.write_text(text, encoding="utf-8")
        rel = str(out.relative_to(REPO_ROOT)).replace("\\", "/")
        score = title_match(title, text)
        conn.execute(
            "UPDATE papers SET extracted_text_path=%s, text_title_match=%s WHERE arxiv_id=%s",
            (rel, score, aid),
        )
        conn.commit()
        score_str = "title n/a" if score is None else f"title match {score:.0%}"
        print(f"    ✓ {len(text):,} chars, {score_str} -> {rel}")
        if score is not None and score < TITLE_MATCH_MIN:
            print(f"    ⚠ METADATA MISMATCH: text does not look like \"{title}\"")
            flagged.append((aid, score))
        done += 1

    conn.close()
    print(f"\nDone: {done} extracted, {failed} failed.")
    if flagged:
        print(f"\n⚠ {len(flagged)} paper(s) below the {TITLE_MATCH_MIN:.0%} title-match "
              f"threshold — text and metadata likely describe different papers:")
        for aid, score in flagged:
            print(f"    {aid}  ({score:.0%})")
        print("  Downstream stages must filter on text_title_match >= "
              f"{TITLE_MATCH_MIN}; inspect before trusting these.")


if __name__ == "__main__":
    main()

"""Why did this paper's LaTeX parse fall back to the raw strip?

`latex_to_text` catches every pylatexenc exception and degrades to a regex that
strips macros, which produces much worse text: braces and dollars survive, and
structure does not. It says so on stderr and carries on, which is right for a
150-paper batch and useless for finding out what happened.

This runs one paper through the pipeline in stages, each with the previous step
disabled, so the step that breaks the parse is the one where the exception stops
appearing:

    full        what extract_text.py actually does today
    no expand   without expand_own_macros (the paper's own \\newcommand)
    no cite     without normalise_cite_macros as well
    raw         pylatexenc on the untouched source

If "full" throws and "no expand" does not, macro expansion is producing LaTeX
pylatexenc cannot read, and the fix is ours. If all four throw, the source
defeats pylatexenc on its own and the fallback is doing its job.

Usage:
  python pipeline/diagnose_parse.py 1512.08756
  python pipeline/diagnose_parse.py 1512.08756 --show 400
"""

import argparse
import sys
import traceback
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, env  # noqa: E402
from extract_text import (expand_own_macros, find_main_tex, inline_inputs,  # noqa: E402
                          normalise_cite_macros, normalize, read_archive, tidy_marks)


def parse_with(latex: str) -> tuple[str | None, str | None]:
    """(text, error). Deliberately does NOT catch, unlike latex_to_text: the
    exception is the thing we came for."""
    from pylatexenc.latex2text import LatexNodes2Text
    from extract_text import _latex_context
    try:
        text = LatexNodes2Text(latex_context=_latex_context(), math_mode="text",
                               strict_latex_spaces=False).latex_to_text(latex)
        return normalize(tidy_marks(text)), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Find which step breaks a paper's LaTeX parse")
    ap.add_argument("arxiv_id")
    ap.add_argument("--show", type=int, default=0, help="print this many characters of each result")
    ap.add_argument("--traceback", action="store_true", help="full traceback for the first failure")
    args = ap.parse_args()

    with psycopg.connect(env("DATABASE_URL")) as conn:
        row = conn.execute("SELECT raw_path, source_format FROM papers WHERE arxiv_id = %s",
                           (args.arxiv_id,)).fetchone()
    if not row:
        sys.exit(f"No paper {args.arxiv_id} in the papers table.")
    raw_path, fmt = row
    if fmt != "latex":
        sys.exit(f"{args.arxiv_id} is a {fmt} paper; this only diagnoses LaTeX parses.")

    raw = (data_dir() / raw_path).read_bytes()
    texs, _ = read_archive(raw)
    main_tex = find_main_tex(texs)
    if not main_tex:
        sys.exit("No main .tex found in the archive.")
    source = inline_inputs(main_tex, texs)
    print(f"{args.arxiv_id}: {len(source):,} chars of inlined LaTeX from {main_tex}\n")

    stages = [
        ("full      (expand + cite)", normalise_cite_macros(expand_own_macros(source))),
        ("no expand (cite only)    ", normalise_cite_macros(source)),
        ("no cite   (expand only)  ", expand_own_macros(source)),
        ("raw       (neither)      ", source),
    ]
    results = []
    for name, latex in stages:
        text, err = parse_with(latex)
        results.append((name, text, err))
        status = f"FELL BACK  {err}" if err else f"ok  {len(text):,} chars"
        print(f"  {name}  {status}")
        if args.show and text:
            print(f"      {text[:args.show]!r}\n")

    full_err = results[0][2]
    no_expand_err = results[1][2]
    print()
    if full_err and not no_expand_err:
        print("  VERDICT: macro expansion is breaking this parse. The fix is ours.")
    elif full_err and no_expand_err:
        print("  VERDICT: pylatexenc cannot read this source either way. The fallback")
        print("           is doing its job and expansion is not the cause.")
    elif not full_err:
        print("  VERDICT: parses cleanly now. The fallback seen during extraction came")
        print("           from a different version of the code than this one.")

    if args.traceback and full_err:
        print("\n  Full traceback for the current pipeline:\n")
        from pylatexenc.latex2text import LatexNodes2Text
        from extract_text import _latex_context
        try:
            LatexNodes2Text(latex_context=_latex_context(), math_mode="text",
                            strict_latex_spaces=False).latex_to_text(stages[0][1])
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    main()

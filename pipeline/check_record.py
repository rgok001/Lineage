#!/usr/bin/env python3
"""Resolve the record's claims against the code, and fail when they disagree.

Ticket #54. The design is `docs/design/record-drift-check.md`; read section 5
before changing anything here, because three of the obvious improvements are
deliberate omissions.

The record declares in every file's first lines who keeps it true and nothing
checked that they did. Eleven drift instances in one working session were each
found by a human or an agent sweeping for something else. This is the instrument
that goes red without anyone remembering to look, and it goes red about the
*code* rather than about the documents' agreement with each other: two files can
be perfectly consistent and both wrong about `pipeline/`.

**There is no threshold in this file, and there must never be one.** Every check
is exact equality or existence. This project has shipped four bad calibrations of
a threshold that had a real corpus behind it (decisions 24 and 25); a threshold
over prose would have nothing to measure against at all. The two checks that
would have needed one, dangling-path detection over prose and contradiction
detection between documents, were prototyped and rejected: the path check
measured 8 hits and 8 false positives, because the record's most valuable habit,
naming a deleted file as a cautionary example, is textually indistinguishable
from the defect.

Pure standard library. Opens no database, imports nothing under `pipeline/` that
does, and honours LINEAGE_NO_DB by never needing it.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAIL = "FAIL"
WARN = "WARN"

VALID_CLASSES = {"law", "derived", "history", "ticket", "inbox"}

# The record proper. `docs/design/` is deliberately not here: a design document
# quotes the wrong value on purpose as its evidence (this check's own design
# quotes `DEFAULT_THRESHOLD = 0.16` to prove it is stale), so resolving its
# claims against the code inverts what it is for. It is also absent from the
# destinations table in CLAUDE.md, which is an owner question, not this script's.
RECORD_ROOT_FILES = ("CLAUDE.md", "README.md")
RECORD_GLOBS = ("docs/*.md", ".claude/memory/*.md")

# `.claude/memory/` is gitignored, so a commit can never contain it. Blocking a
# commit on a dashboard defect is how you teach a team `--no-verify`, so findings
# there are WARN unless --all asks for them.
MEMORY_PREFIX = ".claude/memory/"

CODE_DIRS = ("pipeline", "worker", "app")
CODE_FILES = ("render.yaml", "docker-compose.yml", ".claude/settings.json")

# This file is not evidence about itself. It lives in `pipeline/`, so it is in
# the corpus it reads, and its comments quote the stale values on purpose:
# during the first run of this check the comment explaining why
# `DEFAULT_THRESHOLD = 0.16` is stale satisfied the claim that it is stale, and
# the known drift instance went green. That is the project's own named fault, a
# check that agrees with itself, arriving inside the check written to prevent it.
CODE_SELF = "pipeline/check_record.py"
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sql", ".json",
                 ".yaml", ".yml", ".sh", ".toml"}
SKIP_DIRS = {"node_modules", ".next", "__pycache__", ".git", ".venv", "out",
             "data", "dist", "coverage"}

CITED_SUFFIXES = ("md", "py", "ts", "tsx", "js", "jsx", "mjs", "sql", "json",
                  "yaml", "yml", "sh", "toml", "txt")


@dataclass
class RecordFile:
    path: str          # repo-relative, posix
    lines: list[str]
    klass: str | None
    recomputed_by: str | None

    @property
    def tracked(self) -> bool:
        return not self.path.startswith(MEMORY_PREFIX)


@dataclass
class Finding:
    level: str
    path: str
    line: int
    message: str


@dataclass
class CheckResult:
    name: str
    resolved: int = 0
    findings: list[Finding] = field(default_factory=list)
    suppressed: int = 0
    # Checks whose floor was measured on 2026-08-02 against master @ 5177253.
    # See zero_guard() for why this is a property of the check and not a number.
    guarded: bool = True
    note: str = ""


# A suppression is written on the line it suppresses and carries its reason, so
# it is visible next to the claim and dies when the claim does. There is
# deliberately no allowlist file: a separate list of exceptions is exactly where
# drift would hide, which is the failure this check exists to fix.
#
# The count is printed because it is the falsification criterion. The design
# holds that if the FAIL-level checks need more than two of these in the first
# month, the forms chosen are not how this record writes, and the honest response
# is to drop the failing check rather than grow the exceptions.
_SUPPRESS = re.compile(r"<!--\s*record-check:\s*(?P<why>[^>]*?)\s*-->")


def _suppressed(line: str) -> bool:
    m = _SUPPRESS.search(line)
    return bool(m and m.group("why"))


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def _rel(p: Path) -> str:
    """Repo-relative posix path. The hook runs from Git Bash and from
    PowerShell, so every path this script prints or compares is normalised to
    one spelling rather than whatever the platform handed us."""
    return p.resolve().relative_to(ROOT).as_posix()


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def load_record() -> list[RecordFile]:
    paths: list[Path] = []
    for name in RECORD_ROOT_FILES:
        p = ROOT / name
        if p.is_file():
            paths.append(p)
    for pattern in RECORD_GLOBS:
        paths.extend(sorted(ROOT.glob(pattern)))

    out: list[RecordFile] = []
    for p in sorted(set(paths)):
        lines = _read(p).splitlines()
        klass, recomputed = _parse_header(lines)
        out.append(RecordFile(_rel(p), lines, klass, recomputed))
    return out


def _parse_header(lines: list[str]) -> tuple[str | None, str | None]:
    """CLASS: on one of the opening lines, RECOMPUTED BY: on the next.

    The design says lines 2 and 3; every file in the record actually puts them
    at 3 and 4, under a title and a blank. Requiring adjacency rather than a
    fixed line number keeps the check structural without letting the declaration
    drift to the bottom of the file where nobody reads it.
    """
    for i, line in enumerate(lines[:6]):
        if line.startswith("CLASS:"):
            klass = line[len("CLASS:"):].strip()
            klass = klass.split()[0].strip(",.;:") if klass else ""
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            recomputed = (nxt[len("RECOMPUTED BY:"):].strip()
                          if nxt.startswith("RECOMPUTED BY:") else None)
            return klass, recomputed
    return None, None


def load_code() -> dict[str, str]:
    out: dict[str, str] = {}
    for d in CODE_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        # os.walk with the skip list pruned in place, not rglob. `app/` carries
        # node_modules and .next; walking them and then discarding by suffix
        # costs 470 ms of the 500 the whole check takes, and this runs on every
        # commit.
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(x for x in dirnames if x not in SKIP_DIRS)
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if p.suffix not in CODE_SUFFIXES:
                    continue
                rel = _rel(p)
                if rel == CODE_SELF:
                    continue
                out[rel] = _read(p)
    for name in CODE_FILES:
        p = ROOT / name
        if p.is_file():
            out[_rel(p)] = _read(p)
    return out


# --------------------------------------------------------------------------
# check_classes
# --------------------------------------------------------------------------

def check_classes(record: list[RecordFile]) -> CheckResult:
    """CLAUDE.md's `grep -A1 "^CLASS: derived"` turned from a listing into a
    check. It is also what tells every other check which class a claim lives in,
    so it runs first and its failure is everyone's."""
    res = CheckResult("check_classes")
    for rf in record:
        level = FAIL if rf.tracked else WARN
        if rf.klass is None:
            res.findings.append(Finding(level, rf.path, 1,
                                        "no CLASS: declared in the opening lines"))
            continue
        res.resolved += 1
        if rf.klass not in VALID_CLASSES:
            res.findings.append(Finding(
                level, rf.path, 1,
                f"CLASS: {rf.klass} is not one of "
                f"{' | '.join(sorted(VALID_CLASSES))}"))
        if rf.recomputed_by is None:
            res.findings.append(Finding(
                level, rf.path, 1,
                "CLASS: is not followed by RECOMPUTED BY:"))
        elif rf.klass == "derived" and not rf.recomputed_by:
            res.findings.append(Finding(
                level, rf.path, 1,
                "derived file names no recomputer; CLAUDE.md says such a file "
                "is deleted, not fixed"))
    return res


# --------------------------------------------------------------------------
# check_assignments
# --------------------------------------------------------------------------

# Three forms, because the record quotes all three and the code declares in all
# three: `IDENT = literal` (Python, TS), `"IDENT": literal` (JSON, YAML) and
# `IDENT=literal` (env, shell). The JSON form exists specifically so that
# CLAUDE.md's `LINEAGE_NO_DB=1` resolves against `.claude/settings.json`, which
# declares it as JSON. That was the one false positive the design's prototype
# produced, and a check that cries wolf once gets bypassed forever.
#
# On the record side the key must be quoted for the colon form to count.
# Unquoted, `note: ...` in a sentence, `suspect: ...`, and the dev machine's
# `C:\Users\...\python.exe` in the runbook all parse as assignments; measured,
# that was three of the four false positives on a clean tree.
_BACKTICKED = re.compile(r"`([^`\n]+)`")

_DOC_ENV = re.compile(r"^(?P<ident>[A-Z_][A-Z0-9_]*)=(?=\S)")
_DOC_PY = re.compile(
    r"^(?P<ident>[A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=,;\n)]*?)?\s*=(?!=)\s*")
_DOC_JSON = re.compile(r'^"(?P<ident>[A-Za-z_][A-Za-z0-9_]*)"\s*:\s*')

_OPENERS = {"(": ")", "[": "]", "{": "}"}
_QUOTES = "\"'`"


def _take_value(s: str, i: int) -> tuple[str, int] | None:
    """Consume one literal starting at `s[i]`, and say where it ended.

    A grammar rather than "the rest of the line", because the code writes
    assignments inside larger statements: `SET status = 'approved', started_at =
    NULL` must yield `'approved'` and not everything up to the newline. It also
    has to survive `frozenset({"gaps", "package_macros"})`, which is the claim
    this check exists to resolve, so bracket nesting is balanced rather than
    matched by a regex.
    """
    n = len(s)
    while i < n and s[i].isspace():
        i += 1
    if i >= n:
        return None
    start = i
    if s[i] in _QUOTES:
        q = s[i]
        i += 1
        while i < n:
            if s[i] == "\\":
                i += 2
                continue
            if s[i] == q:
                return s[start:i + 1], i + 1
            i += 1
        return None  # unterminated on this line; not a literal we can compare
    if s[i] in _OPENERS or s[i].isalnum() or s[i] in "_-.+":
        while i < n and (s[i].isalnum() or s[i] in "_.$"):
            i += 1
        if i == start and s[i] in "-+":  # a signed number
            i += 1
            while i < n and (s[i].isdigit() or s[i] == "."):
                i += 1
        while i < n and s[i] in _OPENERS:
            depth, j = 0, i
            while j < n:
                if s[j] in _OPENERS:
                    depth += 1
                elif s[j] in _OPENERS.values():
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                elif s[j] in _QUOTES:
                    inner = _take_value(s, j)
                    if inner is None:
                        return None
                    j = inner[1]
                    continue
                j += 1
            else:
                return None
            i = j
        if i > start:
            return s[start:i], i
    return None


def _normalise_literal(value: str) -> str:
    """Whitespace and one layer of surrounding quotes.

    Numbers are deliberately not normalised. `0.20` and `0.2` are the same value
    and different claims, and the extraction digest already treats them as
    different; a checker that quietly equated them would be the first threshold
    in this file.
    """
    v = " ".join(value.split())
    if len(v) >= 2 and v[0] in _QUOTES and v[-1] == v[0]:
        v = v[1:-1]
    return v.strip()


def _parse_doc_claim(span: str) -> tuple[str, str] | None:
    """A backticked span is a claim only if the whole of it is the assignment.

    Requiring full consumption is what keeps prose out: `quality !== "clean"` and
    `x = a + b` both start like an assignment and neither is a claim about a
    single stored literal.
    """
    span = span.strip()
    for rx in (_DOC_ENV, _DOC_PY, _DOC_JSON):
        m = rx.match(span)
        if not m:
            continue
        taken = _take_value(span, m.end())
        if taken is None:
            continue
        literal, end = taken
        if span[end:].strip():
            continue
        value = _normalise_literal(literal)
        if value:
            return m.group("ident"), value
    return None


def _code_values(ident: str, code: dict[str, str]) -> list[tuple[str, str, int]]:
    """Every place the code assigns `ident`, as (literal, path, line).

    Every occurrence and not the first, because an identifier is legitimately
    assigned in more than one place: `status = 'approved'` appears twice in the
    worker and once in the app, and the claim is satisfied by any of them.
    """
    assign = re.compile(
        r"(?<![A-Za-z0-9_.$])" + re.escape(ident) +
        r"\s*(?::[^=,;\n)]*?)?\s*=(?!=)")
    colon = re.compile(r'(?<![A-Za-z0-9_.$])"?' + re.escape(ident) + r'"?\s*:\s*')
    out: list[tuple[str, str, int]] = []
    for path, text in sorted(code.items()):
        if ident not in text:
            continue
        structured = path.endswith((".json", ".yaml", ".yml"))
        for n, line in enumerate(text.splitlines(), start=1):
            for rx in ((assign, colon) if structured else (assign,)):
                for m in rx.finditer(line):
                    taken = _take_value(line, m.end())
                    if taken is None:
                        continue
                    value = _normalise_literal(taken[0])
                    if value:
                        out.append((value, path, n))
    return out


def check_assignments(record: list[RecordFile], code: dict[str, str]) -> CheckResult:
    """For each `` `IDENT = literal` `` in a law or derived file, find IDENT in
    the code and compare.

    Not run in `history` files. A dated entry recording that the threshold *was*
    0.16 is correct forever, and editing it would violate append-only.

    This is also how the one-fact-one-file rule gets enforced without a
    similarity threshold: `PROPOSED_NOTE_SIGNALS` is asserted in two documents,
    and resolving each independently against `pipeline/check_extraction.py` says
    which copy is wrong. Contradiction is a special case of staleness the moment
    both copies are resolved against the thing they were derived from.
    """
    res = CheckResult("check_assignments")
    cache: dict[str, list[tuple[str, str, int]]] = {}
    for rf in record:
        if rf.klass not in ("law", "derived"):
            continue
        level = FAIL if rf.tracked else WARN
        for n, line in enumerate(rf.lines, start=1):
            if _suppressed(line):
                res.suppressed += 1
                continue
            for span in _BACKTICKED.findall(line):
                parsed = _parse_doc_claim(span)
                if parsed is None:
                    continue
                ident, claimed = parsed
                res.resolved += 1
                if ident not in cache:
                    cache[ident] = _code_values(ident, code)
                found = cache[ident]
                if not found:
                    res.findings.append(Finding(
                        level, rf.path, n,
                        f"{ident} is claimed as {claimed!r} but is assigned "
                        f"nowhere in the code this check reads"))
                    continue
                if any(value == claimed for value, _, _ in found):
                    continue
                where = "; ".join(f"{p}:{ln} has {v!r}" for v, p, ln in found[:3])
                res.findings.append(Finding(
                    level, rf.path, n,
                    f"{ident}: the record says {claimed!r}, the code says "
                    f"otherwise ({where})"))
    return res


# --------------------------------------------------------------------------
# check_citations
# --------------------------------------------------------------------------

_CITATION = re.compile(
    r"(?P<path>[A-Za-z0-9_./-]+\.(?:" + "|".join(CITED_SUFFIXES) + r"))"
    r":(?P<line>\d+)"
    r"(?P<pin>\s*@\s*[0-9a-zA-Z][0-9a-zA-Z._/-]*)?")


def check_citations(record: list[RecordFile]) -> CheckResult:
    """A line number is not an identifier and must not be used as one.

    CLAUDE.md keeps item numbers unreused precisely so a commit can cite them
    years later: assigned once, never reused, not derived from position. Line
    numbers fail all three clauses. Section numbers pass, because this record has
    already promoted them from positions to ids: as-built sections 8 to 11
    survived being split into other files as pointer stubs that kept their
    numbers. Measured, all 44 "section N" citations and all 29 markdown link
    targets still resolve across three restructures in two days, while
    `dashboard.md` cites line 1849 of a 559-line file.

    So a line citation must carry a commit-ish. Pinned, the check does not verify
    the line: that would need a `git show` per citation and is not worth the cost
    in a pre-commit hook. It only requires that the citation be falsifiable by
    hand, which is the whole difference between permanently true and true for one
    edit.
    """
    res = CheckResult("check_citations")
    for rf in record:
        level = FAIL if rf.tracked else WARN
        for n, line in enumerate(rf.lines, start=1):
            if _suppressed(line):
                res.suppressed += 1
                continue
            for m in _CITATION.finditer(line):
                cited, lineno = m.group("path"), int(m.group("line"))
                res.resolved += 1
                if m.group("pin"):
                    continue
                target = ROOT / cited
                if not target.is_file():
                    res.findings.append(Finding(
                        level, rf.path, n,
                        f"cites {cited}:{lineno}, which names no file in this "
                        f"repository and carries no commit-ish"))
                    continue
                length = len(_read(target).splitlines())
                if lineno > length:
                    res.findings.append(Finding(
                        level, rf.path, n,
                        f"cites {cited}:{lineno}, but {cited} is {length} "
                        f"lines long"))
                    continue
                res.findings.append(Finding(
                    level, rf.path, n,
                    f"cites {cited}:{lineno} with no commit-ish; a line number "
                    f"is false by the next edit above it. Pin it as "
                    f"'{cited}:{lineno} @ <sha>' or cite a section number"))
    return res


# --------------------------------------------------------------------------
# check_coverage
# --------------------------------------------------------------------------

_MIGRATION_RANGE = re.compile(r"\b(\d{3})\s*(?:\.\.|through|to)\s*(\d{3})\b")
_MIGRATION_ONE = re.compile(r"\b0*(\d{1,3})\b")
_STAGE_TOKEN = re.compile(r"\bstage_[a-h]_[a-z_]+\b")


def _migration_covered(number: str, texts: list[str]) -> bool:
    n = int(number)
    for text in texts:
        for m in _MIGRATION_RANGE.finditer(text):
            if int(m.group(1)) <= n <= int(m.group(2)):
                return True
        # A bare number only counts when it is spelled as a migration. `014`
        # alone appears in dates and counts; "migration 014" does not.
        if re.search(rf"[Mm]igrations?\s+0*{n}\b", text):
            return True
        if re.search(rf"\b0*{n:03d}_[a-z0-9_]+\.sql\b", text):
            return True
    return False


def check_coverage(record: list[RecordFile], code: dict[str, str]) -> CheckResult:
    """The only check that runs code to docs, and the one that catches the code
    growing something no document noticed.

    When stages F, G and H landed with no documented invocation, this would have
    been the only thing in the repository that knew.

    Coverage counts only *tracked* derived documents. `.claude/memory/` is
    gitignored and the dashboard is rewritten wholesale on every Manager run, so
    an artefact named only there is undocumented to anyone who clones the repo.
    """
    res = CheckResult("check_coverage")
    texts = [
        "\n".join(rf.lines) for rf in record
        if rf.klass == "derived" and rf.tracked
    ]
    if not texts:
        res.findings.append(Finding(FAIL, "docs/", 1,
                                    "no tracked derived document to check coverage against"))
        return res

    for p in sorted((ROOT / "pipeline").glob("*.py")):
        name = p.name
        res.resolved += 1
        if not any(name in t for t in texts):
            res.findings.append(Finding(
                FAIL, f"pipeline/{name}", 1,
                f"{name} is named by no tracked derived document"))

    migrations = sorted((ROOT / "pipeline" / "db" / "migrations").glob("*.sql"))
    for p in migrations:
        number = p.name.split("_", 1)[0]
        res.resolved += 1
        if not _migration_covered(number, texts):
            res.findings.append(Finding(
                FAIL, f"pipeline/db/migrations/{p.name}", 1,
                f"migration {number} is named by no tracked derived document"))

    worker = code.get("worker/run.py", "")
    for token in sorted(set(_STAGE_TOKEN.findall(worker))):
        res.resolved += 1
        if not any(token in t for t in texts):
            res.findings.append(Finding(
                FAIL, "worker/run.py", 1,
                f"the worker runs {token}, which is named by no tracked "
                f"derived document"))
    return res


# --------------------------------------------------------------------------
# check_attestations
# --------------------------------------------------------------------------

_ATTEST_ANY = re.compile(r"\(attested:[^)]*\)", re.IGNORECASE)
_ATTEST_OK = re.compile(r"\(attested:\s*(?P<who>[^,)]+?)\s*,\s*"
                        r"(?P<date>\d{4}-\d{2}-\d{2})\s*\)")


def check_attestations(record: list[RecordFile], today: _dt.date) -> CheckResult:
    """A fact about the world outside this repository that no code can settle.

    `RECOMPUTED BY: the Developer, in the same commit as any behaviour change`
    can never fire for a setting in a vendor console, because there is no commit.
    An attested claim lives in exactly one derived file, names who looked and
    when, and is then honest in the only way it can be: it says "nobody has
    looked since this date" rather than asserting a state of the world it cannot
    see.

    **The age is printed and never failed on.** A staleness threshold here would
    be guessed, because the convention is days old and there is no corpus of
    attested facts to measure decay against. If the ages later cluster somewhere
    that suggests a cutoff, that is a measurement and a separate ticket.
    """
    res = CheckResult("check_attestations", guarded=False,
                      note="not guarded: a convention introduced with this "
                           "check has no instances by construction")
    for rf in record:
        level = FAIL if rf.tracked else WARN
        for n, line in enumerate(rf.lines, start=1):
            if _suppressed(line):
                res.suppressed += 1
                continue
            for raw in _ATTEST_ANY.findall(line):
                m = _ATTEST_OK.fullmatch(raw)
                if not m:
                    res.findings.append(Finding(
                        level, rf.path, n,
                        f"{raw} does not parse; the form is "
                        f"(attested: <who>, <YYYY-MM-DD>)"))
                    continue
                res.resolved += 1
                when = _dt.date.fromisoformat(m.group("date"))
                res.findings.append(Finding(
                    "INFO", rf.path, n,
                    f"attested by {m.group('who')} {(today - when).days} days "
                    f"ago ({m.group('date')})"))
    return res


# --------------------------------------------------------------------------
# check_symbols (warn-only)
# --------------------------------------------------------------------------

_SYMBOLISH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def check_symbols(record: list[RecordFile], code: dict[str, str]) -> CheckResult:
    """A rename detector on probation.

    Measured 7.8% unresolved and every one of them legitimate: env vars set
    outside the repo, a Postgres role, agent-prompt vocabulary, a git
    subcommand. Zero true positives today, so it warns and reports a count
    rather than a list. Making it fail is the change to resist.
    """
    res = CheckResult("check_symbols", guarded=False,
                      note="warn-only: 0 true positives measured, so it "
                           "reports a count rather than a list")
    haystack = "\n".join(code.values())
    unresolved: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for rf in record:
        if rf.klass not in ("law", "derived"):
            continue
        for n, line in enumerate(rf.lines, start=1):
            if _suppressed(line):
                res.suppressed += 1
                continue
            for span in _BACKTICKED.findall(line):
                tok = span.strip()
                if not _SYMBOLISH.match(tok) or len(tok) < 3:
                    continue
                if "_" not in tok and tok.lower() == tok:
                    continue  # a plain English word in backticks, not a symbol
                if tok in seen:
                    continue
                seen.add(tok)
                res.resolved += 1
                if tok not in haystack:
                    unresolved.append((tok, rf.path, n))
    if unresolved:
        names = ", ".join(t for t, _, _ in unresolved[:12])
        res.findings.append(Finding(
            WARN, "record", 1,
            f"{len(unresolved)} of {res.resolved} backticked symbols resolve to "
            f"nothing in the code: {names}"))
    return res


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def zero_guard(res: CheckResult) -> Finding | None:
    """The most important line in this design.

    The sharper version of "a check that agrees with itself" is an instrument
    that passes because it checked nothing. If a restructure changes how
    constants are written and no line matches the assignment form any more, every
    check returns green while resolving zero claims: a per-item pass rate of 100%
    over an empty set, which is "every failure is neutral" wearing a result's
    clothes.

    The guard is `> 0` and not a stored count. A stored count would itself be a
    derived value left to age, and would go wrong the first time a script is
    legitimately deleted. Zero is the only threshold-free signal that says the
    instrument is broken rather than the record.
    """
    if not res.guarded or res.resolved > 0:
        return None
    return Finding(FAIL, "pipeline/check_record.py", 1,
                   f"{res.name} resolved nothing; the instrument is broken, "
                   f"not the record")


def _suppression_lines(record: list[RecordFile]) -> int:
    """Distinct record lines carrying a suppression, for the dashboard. The
    per-check counts double-count a line four checks skipped."""
    return sum(1 for rf in record for line in rf.lines if _suppressed(line))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Resolve the record's claims against the code (ticket #54).")
    ap.add_argument("--all", action="store_true",
                    help="raise findings in the untracked .claude/memory/ tier "
                         "from WARN to FAIL")
    ap.add_argument("--counts", action="store_true",
                    help="print resolution counts and exit 0, for the dashboard")
    ap.add_argument("--today", default=None,
                    help="date to age attestations against (YYYY-MM-DD), for tests")
    args = ap.parse_args(argv)

    today = (_dt.date.fromisoformat(args.today) if args.today
             else _dt.date.today())

    record = load_record()
    code = load_code()

    results = [
        check_classes(record),
        check_assignments(record, code),
        check_citations(record),
        check_coverage(record, code),
        check_attestations(record, today),
        check_symbols(record, code),
    ]

    if args.counts:
        for res in results:
            print(f"{res.name}: {res.resolved}")
        print(f"suppressions: {_suppression_lines(record)}")
        return 0

    failed = False
    for res in results:
        promoted = [
            Finding(FAIL if (args.all and f.level == WARN) else f.level,
                    f.path, f.line, f.message)
            for f in res.findings
        ]
        loud = [f for f in promoted if f.level != "INFO"]
        suffix = f"  ({res.note})" if res.note else ""
        print(f"{res.name}: {res.resolved} claims, {len(loud)} findings{suffix}")
        if res.suppressed:
            plural = "" if res.suppressed == 1 else "s"
            print(f"  ({res.suppressed} suppressed line{plural} skipped)")
        for f in promoted:
            print(f"  {f.level} {f.path}:{f.line}: {f.message}")
            if f.level == FAIL:
                failed = True
        guard = zero_guard(res)
        if guard is not None:
            print(f"  {guard.level} {guard.path}:{guard.line}: {guard.message}")
            failed = True

    print()
    print("record check: FAILED" if failed else "record check: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

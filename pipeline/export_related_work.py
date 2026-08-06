"""Export: related-work skeleton (Markdown) + BibTeX from a curated genealogy.

A *skeleton*, deliberately: it supplies the real structure, real citations and
real verified quotes, and leaves the argument to the author. Nothing is invented
— CLAUDE.md rule 4 forbids fabricating metadata, quotes or citations in any
output, including this one. Papers whose authors are unknown are reported and
omitted from BibTeX rather than guessed, and unverified quotes are labelled
inferred rather than presented as evidence. Since migration 015 a quote whose
stamp names text the paper no longer has is labelled "not re-checked" and is
exported with that caveat rather than dropped: it is real text a real paper
contains, and omitting it would narrow the account in silence.

Usage:
  python pipeline/export_related_work.py "attention"
  python pipeline/export_related_work.py "attention" --out-dir ./export
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (actor_tally, curatorial_edits, data_dir,  # noqa: E402
                    edge_stamp_state, edit_op, env, stamp_state)

STOP = {"a", "an", "the", "on", "of", "in", "for", "and", "with", "is", "are", "to", "by"}


def ascii_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def surname_of(name: str) -> str:
    """Sources mix "Surname, Given" and "Given Surname" — sometimes within one
    author list — so a naive last-token split yields keys like `alex2013…`."""
    if "," in name:
        return name.split(",", 1)[0].strip()
    parts = name.split()
    if not parts:
        return name
    # keep von/van/de particles with the surname: "Aaron van den Oord" -> "van den Oord"
    i = len(parts) - 1
    while i > 0 and parts[i - 1][:1].islower():
        i -= 1
    return " ".join(parts[i:])


def cite_key(authors: list[str], year: int | None, title: str, taken: set[str]) -> str:
    surname = ascii_key(surname_of(authors[0])) if authors else "anon"
    word = next((ascii_key(w) for w in re.findall(r"[A-Za-z]+", title or "")
                 if w.lower() not in STOP and len(w) > 2), "paper")
    base = f"{surname}{year or ''}{word}"
    key, i = base, 0
    while key in taken:
        i += 1
        key = base + chr(ord("a") + i - 1)
    taken.add(key)
    return key


def tex_escape(s: str) -> str:
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_")]:
        s = s.replace(a, b)
    return s


def clean_quote(q: str) -> str:
    return re.sub(r"\s+", " ", q).strip()


def edge_cite(arxiv: str | None, keys: dict) -> str:
    r"""A `\cite` only where there is a paper this document can cite (rule 4).

    Two ways an edge endpoint has no key. Its paper row can be gone, which the
    LEFT JOIN now surfaces instead of hiding (issue #79), and then there is not
    even an arXiv id. Or it can name a paper outside this map's concept-states,
    which mints no key, because keys are minted from the corpus and BibTeX is
    written from the same list.

    Neither may be given one. `keys[None]` used to be a KeyError waiting for the
    join to change, and inventing a key would be worse than the crash: a
    `\cite{}` with no entry in the .bib compiles to a bare [?] in somebody's
    paper, which is this product printing a citation it cannot support.
    """
    if arxiv and arxiv in keys:
        return f"\\cite{{{keys[arxiv]}}}"
    if arxiv:
        return f"arXiv:{arxiv} *(not among this map's papers, so not cited)*"
    return "*(this paper is no longer in our records, so it cannot be cited)*"


def curation_note(user_edits: list) -> str:
    """One line about who curated this map, for a document going into a paper.
    Empty string when nobody curated it, and the caller writes nothing.

    This used to read "Curated by hand: N workbench edit(s) applied", which
    claims human agency from a count that cannot support it — the same claim the
    as-built had to retract about the embedding map, travelling into somebody
    else's manuscript. Two things carry the honesty now. The count is of
    curatorial ops only, so a restore after an incident is not reported as
    somebody's editorial work. And the claim is carried by the actors, each with
    the basis on which its name is known, with the entries that name nobody
    counted as naming nobody.
    """
    edits = curatorial_edits(user_edits)
    if not edits:
        return ""
    ops = ", ".join(sorted({edit_op(e) for e in edits}))
    head = f"> {len(edits)} workbench edit(s) applied ({ops})"
    parts, any_known = actor_tally(edits)
    if not any_known:
        return head + ". No actor is recorded for any of them.\n"
    return head + ": " + ", ".join(parts) + ".\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Export related-work skeleton + BibTeX.")
    ap.add_argument("concept")
    ap.add_argument("--out-dir", help="default: DATA_DIR")
    args = ap.parse_args()

    pv = env("PROMPT_VERSION", "v1")
    conn = psycopg.connect(env("DATABASE_URL"))
    gen = conn.execute("SELECT id, nodes, user_edits FROM genealogies "
                       "WHERE concept=%s AND prompt_version=%s", (args.concept, pv)).fetchone()
    if not gen:
        sys.exit(f'No genealogy for "{args.concept}" at prompt {pv}.')
    gen_id, nodes, user_edits = gen
    nodes = sorted(nodes, key=lambda n: n["year_start"])

    # real paper metadata — never invented
    papers = {r[0]: {"title": r[1], "year": r[2], "authors": r[3] or []}
              for r in conn.execute("SELECT arxiv_id, title, year, authors FROM papers").fetchall()}
    # The stamp, not the boolean (migration 015). A quote checked against text
    # that has since been replaced is not verified now, and this document goes
    # into somebody's paper.
    defs = {r[0]: {"definition": r[1], "quote": r[2], "verified": r[3],
                   "stamp": stamp_state(r[3], r[4], r[5])}
            for r in conn.execute("""
                SELECT p.arxiv_id, d.definition, d.verbatim_quote, d.quote_verified,
                       d.quote_text_digest, p.extracted_text_digest
                FROM definitions d JOIN papers p ON p.id=d.paper_id
                WHERE d.concept=%s AND d.prompt_version=%s AND d.defines_concept=true
            """, (args.concept, pv)).fetchall()}
    # LEFT JOIN on both papers (issue #79, after #60). `source_paper_id` and
    # `target_paper_id` are nullable and may name a row that is gone; an INNER
    # JOIN dropped such an edge from this document while the app counted it, so
    # the export and the page disagreed about the same map, silently and in the
    # direction of claiming fewer relationships than the site shows. The row now
    # arrives with NULL digests, which `edge_stamp_state` resolves stale exactly
    # as every other surface does, and with a NULL arxiv_id, which `edge_cite`
    # below refuses to turn into a citation.
    edges = conn.execute("""
        SELECT e.source_node, e.target_node, e.edge_type, e.confidence, e.verified,
               sp.arxiv_id, tp.arxiv_id,
               e.source_text_digest, e.target_text_digest,
               sp.extracted_text_digest, tp.extracted_text_digest
        FROM edges e LEFT JOIN papers sp ON sp.id=e.source_paper_id
                     LEFT JOIN papers tp ON tp.id=e.target_paper_id
        WHERE e.genealogy_id=%s
    """, (gen_id,)).fetchall()
    conn.close()

    # citation keys, chronological
    corpus = [m["arxiv_id"] for n in nodes for m in sorted(n["members"], key=lambda m: m["year"])]
    taken: set[str] = set()
    keys: dict[str, str] = {}
    missing_authors = []
    for aid in corpus:
        p = papers.get(aid, {})
        if not p.get("authors"):
            missing_authors.append(aid)
        keys[aid] = cite_key(p.get("authors", []), p.get("year"), p.get("title", ""), taken)

    # ── BibTeX ────────────────────────────────────────────────────────────
    bib = ["% Generated by Lineage — every entry below is real metadata from OpenAlex/arXiv.",
           "% Nothing here is invented; papers with unknown authors are omitted, not guessed.", ""]
    written = 0
    for aid in corpus:
        p = papers.get(aid)
        if not p or not p.get("authors"):
            continue
        bib.append(f"@misc{{{keys[aid]},")
        bib.append(f"  title         = {{{{{tex_escape(p['title'])}}}}},")
        bib.append(f"  author        = {{{' and '.join(tex_escape(a) for a in p['authors'])}}},")
        if p.get("year"):
            bib.append(f"  year          = {{{p['year']}}},")
        bib.append(f"  eprint        = {{{aid}}},")
        bib.append("  archivePrefix = {arXiv},")
        bib.append("}\n")
        written += 1

    # ── Markdown skeleton ─────────────────────────────────────────────────
    md: list[str] = []
    md.append(f"# Related Work — *{args.concept}*\n")
    md.append(f"> Skeleton generated by **Lineage** from {len(corpus)} papers across "
              f"{len(nodes)} concept-states, with {len(edges)} traced relationships.\n>\n"
              "> Every quotation below was copied verbatim from the paper's own source text and\n"
              "> string-verified against it. Quotes marked *inferred* failed that check and must\n"
              "> be re-checked before use; quotes marked *not re-checked* have not been matched\n"
              "> against the paper's extracted text as it now stands, so they carry no current\n"
              "> verification either. **This is a scaffold, not prose** — the citations,\n"
              "> quotes and structure are real; the argument is yours to write.\n")
    note = curation_note(user_edits)
    if note:
        md.append(note)
    md.append("\n## How the concept developed\n")
    md.append(f"Across this corpus, *{args.concept}* is used in {len(nodes)} distinct senses:\n")
    for i, n in enumerate(nodes, 1):
        span = n["year_start"] if n["year_start"] == n["year_end"] else f"{n['year_start']}–{n['year_end']}"
        md.append(f"{i}. **{n['label']}** ({span}) — {len(n['members'])} paper(s)")
    md.append("\n_[Write your framing paragraph here: which of these senses matters for your work, and why.]_\n")

    for i, n in enumerate(nodes, 1):
        span = n["year_start"] if n["year_start"] == n["year_end"] else f"{n['year_start']}–{n['year_end']}"
        md.append(f"\n### {i}. {n['label']} ({span})\n")
        cites = ", ".join(f"\\cite{{{keys[m['arxiv_id']]}}}" for m in n["members"])
        md.append(f"This formulation appears in {cites}.\n")
        for m in sorted(n["members"], key=lambda m: m["year"]):
            aid = m["arxiv_id"]
            d = defs.get(aid)
            if not d:
                continue
            md.append(f"\n**{m['title']}** ({m['year']}) — \\cite{{{keys[aid]}}}\n")
            md.append(f"{d['definition']}\n")
            # A stale quote is exported with its caveat rather than dropped: it is
            # real text a real paper contains, and omitting it would narrow the
            # account in silence. It never goes out under the verified wording.
            mark = {"verified": "",
                    "inferred": "  *(inferred — quote could not be verified)*",
                    "stale": "  *(not re-checked — not matched against the paper's "
                             "extracted text as it now stands)*"}[d["stamp"]]
            md.append(f"\n> “{clean_quote(d['quote'])}”{mark}\n")
        md.append(f"\n_[Your synthesis of this sense: what it enabled, what it left unsolved.]_\n")

    if edges:
        md.append("\n## How the senses relate\n")
        md.append("Each relationship below was classified from the citation context between the two "
                  "papers and is backed by a quotation from each.\n")
        by_type: dict[str, list] = {}
        for e in edges:
            by_type.setdefault(e[2], []).append(e)
        for etype, group in sorted(by_type.items()):
            md.append(f"\n### {etype}\n")
            for (sn, tn, et, conf, ver, sa, ta,
                 sd, td, spd, tpd) in sorted(group, key=lambda e: papers.get(e[5], {}).get("year") or 0):
                s_label = next(n["label"] for n in nodes if n["node_id"] == sn)
                t_label = next(n["label"] for n in nodes if n["node_id"] == tn)
                stamp = {"verified": "verified",
                         "inferred": "**inferred — verify before citing**",
                         "stale": "**not re-checked against the text as it now stands "
                                  "— verify before citing**"
                         }[edge_stamp_state(ver, sd, spd, td, tpd)]
                md.append(f"- {edge_cite(sa, keys)} → {edge_cite(ta, keys)}: "
                          f"*{s_label}* **{et}** into *{t_label}* "
                          f"(confidence {conf:.2f}, {stamp}).")
        md.append("\n_[Your paragraph tying these transitions into a narrative.]_\n")

    isolated = [n for n in nodes if not any(n["node_id"] in (e[0], e[1]) for e in edges)]
    if isolated:
        md.append("\n## Unconnected senses\n")
        md.append("These uses of the term appear in the corpus but no citation link to the rest of "
                  "the genealogy was traced, so no relationship is claimed:\n")
        for n in isolated:
            md.append(f"- **{n['label']}** ({n['year_start']}) — "
                      + ", ".join(f"\\cite{{{keys[m['arxiv_id']]}}}" for m in n["members"]))

    out = Path(args.out_dir) if args.out_dir else data_dir()
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"related_work_{args.concept}_{pv}.md"
    bib_path = out / f"references_{args.concept}_{pv}.bib"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    bib_path.write_text("\n".join(bib), encoding="utf-8")

    print(f"Related-work skeleton -> {md_path}")
    print(f"BibTeX ({written} entries) -> {bib_path}")
    if missing_authors:
        print(f"\n⚠ {len(missing_authors)} paper(s) had no author metadata and were omitted from "
              f"BibTeX rather than guessed: {', '.join(missing_authors)}")
        print("  Run: python pipeline/enrich_authors.py")


if __name__ == "__main__":
    main()

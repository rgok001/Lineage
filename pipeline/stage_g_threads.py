"""Stage G: the threads — the parallel lines of development a term followed.

Writes `genealogies.streams` (migration 012), which is what `/g/[id]` opens on.
Read from the corpus's CONTENT (definitions and novelty claims), not its citation
topology: nodes are senses and edges are pairwise links, but a reader wants the
lines of work and the points where one fed another. That is a different question
from "who cites whom", so it is generated and stored rather than derived at
render time.

Two phases. Phase 1 detects the threads, assigns every paper to exactly one, and
writes the through-line and the crossings. Phase 2 composes each thread's
account: for each paper, what it did and how it moved the thread on.

The column and this file still say "streams" because that is the schema; the
interface calls them threads.

**No quote is generated here.** An earlier version asked for a verbatim fragment
per paper and stored it, and the model returned paraphrase instead, which the
thread page then rendered under a verified stamp (AS-BUILT section 10, incident
8). Evidence is not something to regenerate: the app reads the paper's own
`definitions.verbatim_quote`, the span Stage E actually string-matched.

Usage:
  python pipeline/stage_g_threads.py "embedding"
  python pipeline/stage_g_threads.py "embedding" --prompt-version v2 --model claude-haiku-4-5
"""

import argparse
import json
import re
import sys
from pathlib import Path

import psycopg
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env  # noqa: E402
from stage_b_extract import cost_usd  # noqa: E402

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
          "#008a3e", "#4a3aa7", "#e34948", "#d55199"]


class Passage(BaseModel):
    idx: int
    move: str
    prose: str


class Dive(BaseModel):
    passages: list[Passage]


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the threads for a traced concept.")
    ap.add_argument("concept")
    ap.add_argument("--prompt-version", default=env("PROMPT_VERSION", "v1"))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--threads", type=int, default=None,
                    help="roughly how many threads to look for; default scales with corpus size")
    args = ap.parse_args()
    concept, pv = args.concept, args.prompt_version

    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    gen = conn.execute("SELECT id FROM genealogies WHERE concept = %s AND prompt_version = %s",
                       (concept, pv)).fetchone()
    if not gen:
        sys.exit(f'No map for "{concept}" at prompt {pv}. Run Stage C and E first.')
    gen_id = gen[0]

    rows = conn.execute("""
        SELECT p.arxiv_id, p.year, p.title, d.definition, d.novelty_claims
        FROM definitions d JOIN papers p ON p.id = d.paper_id
        WHERE d.concept = %s AND d.prompt_version = %s AND d.defines_concept = true
        ORDER BY p.year, p.arxiv_id
    """, (concept, pv)).fetchall()
    if not rows:
        sys.exit(f'No definitions for "{concept}" at prompt {pv}.')
    P = [{"arxiv": r[0], "year": r[1], "title": r[2], "def": r[3] or "",
          "nov": (r[4][0] if r[4] else "")} for r in rows]

    edge = {}
    for s, t, et, rat in conn.execute("""
        SELECT sp.arxiv_id, tp.arxiv_id, e.edge_type, e.rationale FROM edges e
        JOIN papers sp ON sp.id = e.source_paper_id
        JOIN papers tp ON tp.id = e.target_paper_id
        WHERE e.genealogy_id = %s
    """, (gen_id,)):
        edge[(s, t)] = (et, rat or "")

    import anthropic
    client = anthropic.Anthropic()
    spend = 0.0

    def call(system: str, user: str, max_tokens: int) -> dict:
        """Free-form JSON rather than a parsed schema: phase 1's shape is nested
        and variable-length, and a truncated parse would cost the whole stage."""
        nonlocal spend
        r = client.messages.create(model=args.model, max_tokens=max_tokens, system=system,
                                   messages=[{"role": "user", "content": user}])
        spend += cost_usd(args.model, r.usage.input_tokens, r.usage.output_tokens)
        raw = "".join(b.text for b in r.content if getattr(b, "text", None))
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError(f"no JSON in response: {raw[:300]}")
        return json.loads(m.group(0))

    # ── phase 1: detect the threads and assign every paper ───────────────────
    digest = "\n".join(f'[{i}] {p["year"]} {p["title"][:66]} | {p["def"][:110]} | {p["nov"][:110]}'
                       for i, p in enumerate(P))
    # A hardcoded "6-9" asked the model to fill a quota rather than read the
    # corpus, and it duly returned 9 every time: 9 was right for the 134-paper
    # embedding corpus this was tuned on and too many for attention's 85. The
    # target now scales with the corpus and is a guide, not a range to fill.
    target = args.threads or max(4, min(9, round(len(P) / 18)))
    sys1 = (
        f"Map how the concept '{concept}' evolved across this corpus. Identify the conceptual "
        f"STREAMS (parallel lines of how the idea itself developed, from CONTENT not citations). "
        f"Aim for about {target}, but return the number the corpus actually supports: do not split "
        "one line of work that shares a formulation, and do not create a stream for work ABOUT the "
        "concept (analysis, surveys, interpretability) rather than development OF it. "
        "Assign EVERY paper to exactly one primary stream. Return ONLY JSON: "
        '{"through_line":str, "streams":[{"name":str,"tagline":str,"arc":str(2-3 sentences),'
        '"members":[int paper indices, earliest-first]}], "cross_currents":[{"from":stream_name,'
        '"to":stream_name,"year":int,"label":str(<=4 words)}]}. '
        f"Cover all indices 0..{len(P) - 1} across streams."
    )
    print(f"[1/2] detecting threads across {len(P)} papers", flush=True)
    d1 = call(sys1, f"Corpus of {len(P)} papers:\n\n{digest}\n\nMap the streams and assign every paper.",
              max_tokens=5000)
    detected = d1.get("streams") or []
    if not detected:
        sys.exit("phase 1 returned no streams.")
    print(f"      {len(detected)} threads detected  spend ${spend:.4f}", flush=True)

    # ── phase 2: compose each thread's account ───────────────────────────────
    streams_out = []
    for si, st in enumerate(detected):
        mem = sorted({i for i in st.get("members", []) if 0 <= i < len(P)},
                     key=lambda i: P[i]["year"] or 0)
        if not mem:
            continue
        lines = [f'[{i}] {P[i]["year"]} {P[i]["title"][:64]}\n'
                 f'  DEFINES: {P[i]["def"][:200]}\n'
                 f'  CONTRIBUTED: {P[i]["nov"][:200]}' for i in mem]
        ids = {P[i]["arxiv"] for i in mem}
        et = [f"{s}->{t}: {r[1][:130]}" for (s, t), r in edge.items()
              if s in ids and t in ids][:20]
        sys2 = (
            f'You write the account of ONE line of work ("{st.get("name", "")}") in how "{concept}" '
            "evolved. For each paper, in developmental order, say how it moved this line on from the "
            "one before, USING ONLY the provided facts. Do not quote: quotations are attached "
            'separately from verified source text. Return ONLY JSON: {"passages":[{"idx":int,'
            '"move":str(<=12 words),"prose":str(1-2 sentences)}]}.'
        )
        user = ("PAPERS (earliest first):\n\n" + "\n\n".join(lines)
                + "\n\nEDGES:\n" + ("\n".join(et) or "(none)"))
        try:
            dive = Dive(**call(sys2, user, max_tokens=3500))
        except Exception as exc:
            # A thread whose account fails still exists and still lists its
            # papers; it just reads bare until the stage is re-run.
            print(f"      thread {si} account failed ({type(exc).__name__}); papers kept bare")
            dive = Dive(passages=[])
        by_idx = {ps.idx: ps for ps in dive.passages}
        papers = [{"arxiv": P[i]["arxiv"], "year": P[i]["year"], "title": P[i]["title"],
                   "move": by_idx[i].move if i in by_idx else "",
                   "prose": by_idx[i].prose if i in by_idx else ""} for i in mem]
        streams_out.append({
            "id": f"s{si}", "name": st.get("name", f"Thread {si + 1}"),
            "tagline": st.get("tagline", ""), "arc": st.get("arc", ""),
            "color": COLORS[si % len(COLORS)],
            "origin_year": min((P[i]["year"] for i in mem if P[i]["year"]), default=None),
            "papers": papers,
        })
        print(f"[2/2] thread {si + 1}/{len(detected)}: {str(st.get('name', ''))[:40]} "
              f"({len(papers)} papers)  spend ${spend:.4f}", flush=True)

    name2id = {s["name"]: s["id"] for s in streams_out}
    cross = []
    for x in d1.get("cross_currents", []):
        f, t = name2id.get(x.get("from")), name2id.get(x.get("to"))
        if f and t and f != t:
            cross.append({"from": f, "to": t, "year": x.get("year"), "label": x.get("label", "")})

    river = {"through_line": d1.get("through_line", ""),
             "streams": streams_out, "cross_currents": cross}
    conn.execute("UPDATE genealogies SET streams = %s, updated_at = now() WHERE id = %s",
                 (json.dumps(river), gen_id))
    print(f"\nStored on /g/{gen_id}: {len(streams_out)} threads, {len(cross)} crossings.")
    print(f"spend ${spend:.4f}")
    conn.close()


if __name__ == "__main__":
    main()

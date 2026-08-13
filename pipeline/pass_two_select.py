"""Pass two's selection: the map nominates, the citation graph answers.

Issue #191, designing #184. A map built in one pass can only read papers chosen
before it knew anything, and everything measurable at that moment is a proxy for
how much a field publishes — which is why /g/17 stopped in 2016. A map that has
already been built knows one thing no corpus query does: **which papers were the
turning points.** This stage asks a pass-one map what came next and writes the
answer as a corpus file.

What it is not: a second Stage A. `corpus_select.py`'s reserved partition (#181)
is untouched and still runs in pass one — this is a NEW selector over a DIFFERENT
population (papers that cite THIS map, rather than papers that cite the search
seeds), and the two are deliberately separate code paths.

**It writes nothing.** The map is read — `genealogies.nodes`, `edges`, `papers` —
and never updated, so this can be run against a live map at any point without
touching what a reader is being served. The output is a file.

**Nothing here calls an LLM, with or without --dry-run.** The cost is OpenAlex
metadata on the polite pool plus one Voyage batch over the gate-passers.

The output JSON is the same shape `fetch_papers.py` reads and
`stage_b_extract.py --corpus` / `stage_c_cluster.py --corpus` (#190) scope by,
with two extra keys — `pass: 2` and `nominators_cited` — so #192 can take the
union of the two passes' files. A corpus file with no `pass` key is a pass-one
file; nothing writes `pass: 1`, because the absence is what every existing file
already says.

Usage:
  python pipeline/pass_two_select.py "dark energy" --field fields/31 \
      --recent-since 2021 --json data/corpus_dark_energy_pass2.json
  python pipeline/pass_two_select.py "attention" --dry-run
"""

import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import build_row, env, version_note  # noqa: E402
from corpus_select import (  # noqa: E402
    FORWARD_MIN_SEEDS_CITED, FORWARD_SORTS, RECENT_TIEBREAK_PRECISION, RECENT_YEARS,
    arxiv_id_of, cites_per_year, expand_forward, relevance_scores,
)

# ── the seat count ──────────────────────────────────────────────────────────
#
# #184: `--pass-two-seats`, default `limit // 10` = 15 of pass one's 150. Half of
# #181's reservation moved here (its divisor went 5 -> 10 in the same design), so
# the two passes together hold the same total seats, better aimed. A divisor
# rather than a literal 15 for #181's reason: the seat count has to follow the
# corpus cap, or a 50-paper pass one would be handed a 15-paper pass two and be a
# different product. Nothing on the map records what pass one's cap was, so it is
# an argument here rather than something derivable.
PASS_TWO_SEATS_DIVISOR = 10
DEFAULT_PASS_ONE_LIMIT = 150

# ── the gate's second signal ────────────────────────────────────────────────
#
# Top 3R by relevance among the papers that cleared the citation signal. TOP-K,
# NOT A COSINE FLOOR: decision 3 holds here exactly as it holds in #181, and
# `--min-relevance` deliberately does not exist on this CLI — the one place this
# change could have introduced an absolute similarity number is this line.
#
# 3R rather than R because the gate and the ranking are separate things (#181's
# shape). Relevance is here to veto the ritual-citation papers a mature field
# produces — the AGN-feedback paper citing the 1998 supernova results as
# boilerplate — and then to get out of the way, because the fact pass two knows
# and pass one did not is which papers are turning points, and that is what
# orders the list.
RELEVANCE_POOL_MULTIPLE = 3

# Rows of the candidate table printed. The gate-passing set runs to hundreds.
CANDIDATE_TABLE_ROWS = 40

# The design's own failure condition, written as a number before the reading was
# taken (#184's risks): if the selected papers are dominated by descendants of
# one very large concept-state's nominators, the per-state quota is not doing its
# job and nomination needs a cap per state as well as a floor. Measured as
# COVERAGE — how many nominating states have anybody seated behind them — for
# the reason argued at the print site. This is PRINTED and never filtered on: it
# is a reading for a person, not a rule for the code.
NOMINATION_COVERAGE_WARN = 0.5


def read_map(conn, concept: str, prompt_version: str,
             genealogy_id: int | None = None) -> dict:
    """The pass-one map: its concept-states, their members, and its edges.

    Read the way Stage G reads a map and the way Stage D was corrected to read
    one in #190 — **the population is `genealogies.nodes`, not the `definitions`
    table.** Since Stage C can be scoped to a corpus, a definition of this
    concept can exist and sit outside this map, and nominating from the table
    would aim pass two at papers the map does not contain.
    """
    # The version this build owns (#207b). Pass two nominates from the map pass
    # ONE built, which is this build's own unpublished row — never the live map,
    # which is the previous version and is what a nomination from `is_current`
    # would aim the second pass at.
    gen = build_row(conn, concept, prompt_version, "id, status, nodes",
                    genealogy_id=genealogy_id)
    if not gen:
        sys.exit(f'No unpublished version of "{concept}" at prompt {prompt_version}. '
                 f"Pass two reads a map pass one has already built.\n"
                 f"  {version_note(conn, concept, prompt_version)}")
    gen_id, status, nodes = gen

    states = []
    for n in nodes if isinstance(nodes, list) else []:
        if not isinstance(n, dict):
            continue
        nid = n.get("node_id")
        if not isinstance(nid, str) or not nid.strip():
            continue
        members = [{"arxiv_id": m.get("arxiv_id"), "year": m.get("year"),
                    "title": m.get("title")}
                   for m in (n.get("members") or []) if isinstance(m, dict)
                   and isinstance(m.get("arxiv_id"), str) and m["arxiv_id"].strip()]
        states.append({"node_id": nid.strip(), "label": n.get("label") or nid.strip(),
                       "members": members})

    ids = sorted({m["arxiv_id"] for s in states for m in s["members"]})
    # `openalex_id` is the only thing here the map itself does not carry, and it
    # is what aims the forward hop: OpenAlex answers `cites:` in its own ids.
    meta = {r[0]: {"openalex_id": r[1], "year": r[2], "title": r[3]}
            for r in conn.execute(
                "SELECT arxiv_id, openalex_id, year, title FROM papers WHERE arxiv_id = ANY(%s)",
                (ids,)).fetchall()}

    degree: Counter = Counter()
    edge_count = 0
    for src, dst in conn.execute("""
        SELECT sp.arxiv_id, tp.arxiv_id FROM edges e
        JOIN papers sp ON sp.id = e.source_paper_id
        JOIN papers tp ON tp.id = e.target_paper_id
        WHERE e.genealogy_id = %s
    """, (gen_id,)):
        edge_count += 1
        # In either direction, and both ends counted: an edge is a place this
        # paper moved the term, whichever way round the movement ran.
        degree[src] += 1
        degree[dst] += 1

    return {"id": gen_id, "status": status, "states": states, "meta": meta,
            "degree": degree, "edge_count": edge_count, "arxiv_ids": ids}


def nominate(state: dict, degree: Counter, meta: dict) -> list[dict]:
    """This concept-state's two nominators: most-connected, and newest.

    **Per state, not per map**, and the reason is F5's own reason one level up
    (#184): nominating the map's globally top papers asks "what happened next"
    only where the map is already dense, which reproduces the popularity bias
    this line of work exists to remove. A strand of three papers gets the same
    two questions asked of it as a strand of forty.

    **Not Stage F magnitude, deliberately.** F, G and H run once, after pass two,
    because H roughly doubles what a map costs (decision 17) and has no
    cross-run cache. Nomination therefore has to work from what exists at the end
    of Stage D, and edge degree plus recency does, with no model call.

    Ties break by year then arXiv id, so two runs over the same map nominate the
    same papers. A paper with no recorded year sorts last rather than newest —
    an unknown date is not a recent one.
    """
    if not state["members"]:
        return []
    year_of = {m["arxiv_id"]: (m.get("year") or meta.get(m["arxiv_id"], {}).get("year"))
               for m in state["members"]}

    def newest_key(aid: str) -> tuple:
        return (-(year_of.get(aid) or 0), aid)

    def connected_key(aid: str) -> tuple:
        return (-degree.get(aid, 0),) + newest_key(aid)

    aids = [m["arxiv_id"] for m in state["members"]]
    picks: list[dict] = []
    for why, key in (("most-connected", connected_key), ("newest", newest_key)):
        aid = sorted(aids, key=key)[0]
        existing = next((p for p in picks if p["arxiv_id"] == aid), None)
        if existing:
            # One paper can be both, and a one-paper state always is. Say so
            # rather than listing it twice: "this state nominates once" is a fact
            # about the state, and a duplicated row would inflate every count
            # downstream that divides by the number of nominators.
            existing["why"] += f" + {why}"
            continue
        picks.append({"arxiv_id": aid, "why": why, "node_id": state["node_id"],
                      "year": year_of.get(aid), "degree": degree.get(aid, 0)})
    return picks


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Pass two's selection: the recent papers a built map nominates.")
    ap.add_argument("concept", help='the concept the pass-one map was built for')
    ap.add_argument("--prompt-version", default=None,
                    help="default: PROMPT_VERSION from the environment, or v1")
    ap.add_argument("--field", default="fields/17",
                    help="OpenAlex field scoping the candidates — this must be the field "
                         "pass one used, and nothing on the map records it "
                         "(default fields/17 = Computer Science; 'all' drops the filter)")
    ap.add_argument("--gloss",
                    help="one-line sense clarification used as the relevance query "
                         "instead of the bare concept, exactly as in corpus_select.py")
    ap.add_argument("--pass-two-seats", type=int, metavar="R",
                    help=f"papers pass two may add (default --pass-one-limit // "
                         f"{PASS_TWO_SEATS_DIVISOR}, i.e. 15 of 150)")
    ap.add_argument("--pass-one-limit", type=int, default=DEFAULT_PASS_ONE_LIMIT,
                    help=f"pass one's corpus cap, which the default seat count is "
                         f"derived from (default {DEFAULT_PASS_ONE_LIMIT})")
    ap.add_argument("--recent-since", type=int, metavar="YEAR",
                    help=f"first year of the window pass two reads "
                         f"(default: this year minus {RECENT_YEARS})")
    ap.add_argument("--max-forward", type=int, default=400,
                    help="candidates fetched per batch of 50 map papers, split across "
                         "the two orderings (default 400)")
    ap.add_argument("--no-relevance-filter", action="store_true",
                    help="skip the embedding half of the gate (no Voyage call). One of "
                         "the two signals then does not run and the seats say so")
    ap.add_argument("--json", metavar="PATH",
                    help="write the pass-two corpus here, in the shape --corpus reads")
    ap.add_argument("--stats-json", metavar="PATH",
                    help="write the funnel counts here as JSON: the citation-graph "
                         "facts either side of the gate, which the build records on "
                         "the map (#192) and the report prints (#193)")
    ap.add_argument("--dry-run", action="store_true",
                    help="select and print, write no file. Nothing in this stage calls "
                         "an LLM either way; the dry run also skips writing the corpus")
    ap.add_argument("--genealogy-id", type=int, metavar="ID",
                    help="nominate from this exact version of the map instead of the "
                         "one the build in flight owns")
    args = ap.parse_args()

    prompt_version = args.prompt_version or env("PROMPT_VERSION", "v1")
    rel_query = args.gloss or args.concept
    seats = (args.pass_two_seats if args.pass_two_seats is not None
             else args.pass_one_limit // PASS_TWO_SEATS_DIVISOR)
    since = args.recent_since or (datetime.date.today().year - RECENT_YEARS)
    if seats <= 0:
        # Said before anything is read or fetched. A zero-seat run that still
        # paged OpenAlex would spend somebody's quota to produce a table nobody
        # can act on.
        print(f"Pass two is DISABLED (--pass-two-seats {seats}). No map was read and "
              f"nothing was fetched.")
        _write(args, [], seats, state="disabled", funnel={"since": since})
        return

    # The map is read BEFORE a single HTTP request goes out. A run that cannot
    # reach the map should not first spend thirty seconds of somebody else's API
    # quota finding out.
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    try:
        m = read_map(conn, args.concept, prompt_version, args.genealogy_id)
    finally:
        conn.close()

    n_members = len(m["arxiv_ids"])
    print(f'Pass one map: /g/{m["id"]} "{args.concept}" (prompt {prompt_version}, '
          f'status {m["status"]}) — {len(m["states"])} concept-state(s), '
          f'{n_members} paper(s), {m["edge_count"]} relationship(s).')
    if not m["edge_count"]:
        # Then every degree is zero, the most-connected nominator ties with the
        # newest one on the tie-break, and every state nominates once. That is
        # the right degeneration and it must not be silent, because "7 states
        # nominated 7 papers" otherwise reads as a small map rather than as a map
        # with no relationships in it.
        print("  This map has NO relationships, so no paper is more connected than "
              "another: every state's two nominators collapse onto its newest paper.")

    # ── nomination ──────────────────────────────────────────────────────────
    nominators: list[dict] = []
    print(f"\nAsking the map what came next — two nominators per concept-state:")
    for st in m["states"]:
        picks = nominate(st, m["degree"], m["meta"])
        nominators.extend(picks)
        print(f'  [{st["node_id"]}] {str(st["label"])[:56]} — {len(st["members"])} paper(s)')
        if not picks:
            print("        no members recorded, so this state nominates nothing")
        for p in picks:
            oa = m["meta"].get(p["arxiv_id"], {}).get("openalex_id")
            title = (m["meta"].get(p["arxiv_id"], {}).get("title") or "")[:44]
            print(f'        {p["why"]:<26} {p["arxiv_id"]:<16} {p["year"] or "?":<5} '
                  f'{p["degree"]:>3} edge(s)  {title}'
                  + ("" if oa else "   ⚠ no OpenAlex id"))

    # A nominator with no OpenAlex id cannot be recognised in a candidate's
    # `referenced_works`, so it silently contributes nothing to the rank. Counted
    # here rather than discovered from a ranking that looks thin.
    nom_oa = {m["meta"].get(p["arxiv_id"], {}).get("openalex_id"): p
              for p in nominators if m["meta"].get(p["arxiv_id"], {}).get("openalex_id")}
    unnamed_nominators = len(nominators) - len(nom_oa)
    print(f'\n{len(nominators)} nominator(s) across {len(m["states"])} concept-state(s)'
          + (f"; {unnamed_nominators} with no OpenAlex id, which no candidate's "
             f"reference list can be matched against" if unnamed_nominators else ""))

    # The hop is aimed at ALL the map's defining papers, not only the nominators:
    # the gate asks whether a paper is attached to this lineage (two of the map's
    # papers) and the RANK asks whether it descends from a turning point (the
    # nominators). Two questions, two populations, and collapsing them would make
    # `nominators_cited` a restatement of the gate rather than new information.
    seed_works = [{"id": v["openalex_id"]} for v in m["meta"].values() if v["openalex_id"]]
    missing_oa = n_members - len(seed_works)
    if not seed_works:
        print(f"\nNone of this map's {n_members} paper(s) carries an OpenAlex id, so the "
              f"citation graph cannot be asked what cites them. Nothing was fetched.")
        print(f"\nFilled 0 of {seats} pass-two seats.")
        _write(args, [], seats, state="map_has_no_openalex_ids",
               funnel={"since": since, "nominators": len(nominators),
                       "nominating_states": 0})
        return
    print(f'{len(seed_works)} of the map\'s {n_members} paper(s) carry an OpenAlex id '
          f'and aim the hop'
          + (f"; {missing_oa} do not and are invisible to it" if missing_oa else ""))

    # ── fetch: #180's forward hop, re-aimed at the map ──────────────────────
    print(f"\nForward citation hop: arXiv works from {since} citing this map "
          f"({len(FORWARD_SORTS)} orderings per batch)…")
    forward, cited_map_papers, stats = expand_forward(
        seed_works, since, args.field, args.max_forward)

    # ── gate, signal 1: attached to this lineage ────────────────────────────
    in_map = set(m["arxiv_ids"])
    cands: dict[str, dict] = {}
    for w in forward:
        aid = arxiv_id_of(w)
        if aid is None or aid in in_map:
            continue
        if (w.get("publication_year") or 0) < since:
            continue
        prev = cands.get(aid)
        if prev is None or cited_map_papers[w["id"]] > cited_map_papers[prev["id"]]:
            cands[aid] = w      # OpenAlex keeps preprint and published records apart
    for aid, w in cands.items():
        w["_arxiv_id"] = aid
        refs = set(w.get("referenced_works") or [])
        w["_nominators"] = sorted({nom_oa[o]["arxiv_id"] for o in refs & set(nom_oa)})
        w["_states"] = sorted({nom_oa[o]["node_id"] for o in refs & set(nom_oa)})
    eligible = list(cands.values())

    per_sort = ", ".join(f"{k.split(':')[0]} {v:,}" for k, v in stats.get("per_sort", {}).items())
    print(f'\n  {stats["fetched"]:,} distinct work(s) fetched over {stats["batches"]} '
          f'batch(es) x {len(FORWARD_SORTS)} orderings ({per_sort})')
    print(f'  {len(forward):,} cite >= {FORWARD_MIN_SEEDS_CITED} of the map\'s papers '
          f'(signal 1)')
    print(f"  {len(eligible):,} of those are from {since} or later, carry an arXiv id, "
          f"and are not already in the map")

    if not eligible:
        # NOT a failure, and never reported as one. #184: for a mature term this
        # is worth knowing and for a young one it is expected. The honest
        # sentence names the citation graph and stops — it does not say the field
        # went quiet, which is a claim about the literature this tool cannot make
        # from a citation count.
        print(f"\nPass two nominates nothing: no arXiv work from {since} or later cites "
              f"{FORWARD_MIN_SEEDS_CITED} or more of this map's {len(seed_works)} "
              f"paper(s) within {args.field}.")
        print(f"  That is a fact about the citation graph, not about the field. Pass one's "
              f"map stands as it is.")
        print(f"\nFilled 0 of {seats} pass-two seats.")
        _write(args, [], seats, state="none_found",
               funnel={"since": since, "fetched": stats["fetched"],
                       "cite_min_seeds": len(forward),
                       "eligible": 0, "cleared": 0,
                       "nominators": len(nominators),
                       "nominating_states": len({p["node_id"] for p in nom_oa.values()})})
        return

    # ── gate, signal 2: top 3R by relevance, never a cosine floor ───────────
    rel_by_id: dict[str, float] = {}
    pool_size = seats * RELEVANCE_POOL_MULTIPLE
    if args.no_relevance_filter:
        qualified = sorted(eligible, key=lambda w: (-cited_map_papers[w["id"]], w["_arxiv_id"]))
        print(f"\n  ⚠ --no-relevance-filter: the embedding half of the gate did not run. "
              f"The seats below were chosen on the citation graph alone and may be this "
              f"field's general recent traffic.")
    else:
        print(f"\nScoring {len(eligible):,} gate-passer(s) against \"{rel_query}\" "
              f"(Voyage embeddings)…")
        rel_by_id = {w["id"]: s for w, s in zip(eligible, relevance_scores(rel_query, eligible))}
        by_rel = sorted(eligible, key=lambda w: (-rel_by_id[w["id"]], w["_arxiv_id"]))
        qualified = by_rel[:pool_size]
        cut = rel_by_id[qualified[-1]["id"]]
        print(f"  kept the top {len(qualified)} of {len(eligible):,} by relevance "
              f"(>= {cut:.3f} — a rank, not a threshold: the next run's number will differ)")

    now_year = datetime.date.today().year

    def rank_key(w: dict) -> tuple:
        # Nominator count leads because it is the new information pass two has
        # and pass one did not. Relevance has already done gate-adjacent work at
        # signal 2 — it is what removes the ritual-citation papers — and ranking
        # on it again would build a slightly better #181 rather than a two-stage
        # method. It is rounded for the same reason #181 rounds it: two cosines
        # are never exactly equal, so an unrounded sort never reaches the
        # tiebreak below it.
        rel = rel_by_id.get(w["id"])
        return (-len(w["_nominators"]),
                -(round(rel, RECENT_TIEBREAK_PRECISION) if rel is not None else 0.0),
                -cites_per_year(w, now_year),
                w["_arxiv_id"])

    ranked = sorted(qualified, key=rank_key)
    selected = ranked[:seats]

    # ── the table, and the count that prints whatever happened ──────────────
    print(f"\n{'#':>3}  {'Nom':>3} {'Rel':>5} {'C/yr':>6} {'Year':<5} {'arXiv ID':<14} "
          f"{'States':<14} Title")
    print("-" * 116)
    for i, w in enumerate(ranked[:CANDIDATE_TABLE_ROWS], 1):
        rel = rel_by_id.get(w["id"])
        mark = " " if i <= len(selected) else "·"
        # A column sized for node ids is the one place the honest answer is
        # prose, so a truncation says it truncated rather than quietly dropping
        # the states that did not fit; the file carries the full list.
        states = ",".join(w["_states"]) or "-"
        states = states if len(states) <= 14 else states[:13] + "+"
        print(f"{i:>3}{mark} {len(w['_nominators']):>3} "
              f"{(f'{rel:.3f}' if rel is not None else '    -'):>5} "
              f"{cites_per_year(w, now_year):>6.1f} {w.get('publication_year') or '?':<5} "
              f"{w['_arxiv_id']:<14} {states[:14]:<14} "
              f"{(w.get('display_name') or '?')[:44]}")
    if len(ranked) > CANDIDATE_TABLE_ROWS:
        print(f"     …and {len(ranked) - CANDIDATE_TABLE_ROWS:,} more that cleared the gate")

    print(f"\nFilled {len(selected)} of {seats} pass-two seats ({since} or later).")
    # Every stage of the funnel, because an under-filled reservation and a hop
    # that returned nothing read the same in a log otherwise, and only the counts
    # say which (#181's lesson, in this population).
    second = ("(the relevance half of the gate did NOT run)"
              if args.no_relevance_filter else f"after the relevance top-{pool_size}")
    print(f"  candidates: {stats['fetched']:,} fetched -> {len(forward):,} cite >= "
          f"{FORWARD_MIN_SEEDS_CITED} map papers -> {len(eligible):,} eligible -> "
          f"{len(qualified):,} {second} -> {len(selected)} seated")
    no_nom = sum(1 for w in selected if not w["_nominators"])
    print(f"  of the {len(selected)} seated, {len(selected) - no_nom} cite at least one "
          f"nominator and {no_nom} are attached to the map elsewhere")

    # The falsifier from #184's risks, printed as a reading rather than enforced.
    #
    # The measurement is COVERAGE, not concentration, and the difference matters.
    # A paper cites several states' nominators at once, so a per-state share
    # exceeding half is the ordinary case when the seats are healthily spread —
    # counting that as concentration fires the warning exactly when things are
    # going well. What #184 is actually worried about is small strands getting no
    # descendants while one large one takes the list, and that is visible as the
    # number of nominating states with nobody seated behind them.
    tally: Counter = Counter()
    for w in selected:
        tally.update(w["_states"])
    nominating = sorted({p["node_id"] for p in nom_oa.values()})
    if tally:
        spread = ", ".join(f"{nid} {n}" for nid, n in sorted(tally.items()))
        print(f"  seated papers by the concept-state whose nominators they cite: {spread}")
        print(f"  concept-states with at least one seated descendant: {len(tally)} of "
              f"{len(nominating)} that nominated")
        if len(tally) <= NOMINATION_COVERAGE_WARN * len(nominating):
            print(f"  ⚠ fewer than half the nominating concept-states are represented. "
                  f"#184's failure condition: the per-state quota is not doing its job, "
                  f"and nomination may need a cap per state as well as a floor.")
    else:
        print(f"  no seated paper cites any nominator, so these are papers attached to "
              f"the map elsewhere rather than descendants of its turning points — which "
              f"is #181's population reached by a different route.")

    if len(selected) < seats:
        print(f"  ⚠ UNDER-FILLED by {seats - len(selected)}. The candidate counts above "
              f"say where it ran out: the hop, the citation signal, or the relevance pool.")
    if len(selected) * 2 < seats:
        print(f"  ⚠⚠ fewer than half the pass-two seats could be filled. Read the table "
              f"before trusting any figure taken from a map built on this file.")

    _write(args, selected, seats, rel_by_id, cited_map_papers,
           state=("filled" if len(selected) >= seats
                  else "under_filled" if selected else "none_seated"),
           funnel={"since": since, "fetched": stats["fetched"],
                   "cite_min_seeds": len(forward),
                   "eligible": len(eligible), "cleared": len(qualified),
                   "nominators": len(nominators), "nominating_states": len(nominating),
                   "states_with_a_seated_descendant": len(tally),
                   "relevance_filter": not args.no_relevance_filter})


def _write(args, selected: list[dict], seats: int,
           rel_by_id: dict | None = None, cited_map_papers: Counter | None = None,
           state: str = "unknown", funnel: dict | None = None) -> None:
    """The pass-two corpus file. Written even when it is empty, and here is why.

    An absent file and a run that fell over read identically to whatever calls
    this next (#192's orchestration), and "pass two nominates nothing" is a
    finding rather than an absence of one. An empty `[]` is a corpus file the
    existing readers already handle: `stage_c_cluster.py --corpus` exits naming
    the scope, which is exactly the fallback #184 wants.

    **`--stats-json` is written on every one of those exits too**, for the same
    reason one level up: #192 records the citation-graph counts either side of the
    gate on the map and the report prints them, and a caller that had to scrape
    them out of the funnel line above would be deciding what a map claims on a
    column width. `state` is the only code in it, and it stays a code: the worker
    turns it into the sentence a reader sees, so the four states the design names
    have exactly one author and nothing between here and the page translates
    anything (#193's rule that `pass_two_outcome` is words and not a code).
    """
    if args.stats_json and not args.dry_run:
        stats = {"concept": args.concept, "state": state, "seats": seats,
                 "selected": len(selected), "since": None,
                 "fetched": None, "cite_min_seeds": None, "eligible": None,
                 "cleared": None, "nominators": None, "nominating_states": None,
                 "states_with_a_seated_descendant": None, "relevance_filter": None}
        stats.update(funnel or {})
        Path(args.stats_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.stats_json).write_text(json.dumps(stats, indent=2), encoding="utf-8")
        print(f"Wrote this run's funnel counts to {args.stats_json} (state: {state}).")
    if not args.json:
        return
    rel_by_id = rel_by_id or {}
    cited_map_papers = cited_map_papers or Counter()
    out = [{
        "arxiv_id": w["_arxiv_id"],
        "openalex_id": w["id"],
        "title": w.get("display_name"),
        "year": w.get("publication_year"),
        "cited_by_count": w.get("cited_by_count"),
        # No in-corpus reference count exists for a pass-two paper: it was never
        # in the pool `score()` ranks. Null says that; 0 would say the corpus
        # references it nowhere, which is a measurement nobody took.
        "in_corpus_refs": None,
        "seed_relevance": rel_by_id.get(w["id"]),
        "seed": False,
        # Same key and same meaning as the pass-one file: how many of the papers
        # that aimed the hop this one cites. In pass one those are the search
        # seeds; here they are the map's own papers.
        "seeds_cited": cited_map_papers.get(w["id"], 0),
        "recent_seat": True,
        "pass": 2,
        "nominators_cited": len(w["_nominators"]),
        "nominator_arxiv_ids": w["_nominators"],
        "nominating_states": w["_states"],
    } for w in selected]
    if args.dry_run:
        print(f"\n[dry-run] {len(out)} paper(s) selected; {args.json} NOT written. "
              f"Nothing in this stage calls an LLM, so a dry run costs what a real "
              f"run costs: OpenAlex metadata and one Voyage batch.")
        return
    Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {len(out)} paper(s) to {args.json} "
          f"(pass 2; {seats} seat(s) were available).")


if __name__ == "__main__":
    main()

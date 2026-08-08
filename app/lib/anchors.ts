/**
 * The strings that name a place on the evidence page, formatted here and nowhere
 * else (issue #146).
 *
 * **The key is the paper pair, never `edges.id`.** `pipeline/stage_d_edges.py`
 * rebuilds a map with `DELETE FROM edges WHERE genealogy_id = …` followed by
 * fresh INSERTs, and `edges.id` is BIGSERIAL, while the `genealogies` row
 * survives and the URL stays `/g/13/evidence`. So `#e-4711` in a link somebody
 * shared points at a *different relationship in the same map* after the next
 * rebuild. That is not a dead link, which a reader notices; it is a wrong answer
 * delivered silently, on the page whose whole purpose is that a reader can check
 * one claim. The pair `(source arXiv, target arXiv)` is what Stage D keys a
 * candidate on, so it survives a rebuild, and the edge type is deliberately not
 * part of the key: a link that dies when the owner reclassifies a relationship
 * is worse than no link.
 *
 * The second payoff is that every page that wants to link here can already write
 * the string. `InfluenceMap` holds `MapEdge {from, to, …}`, the thread page and
 * the dossier work in arXiv ids, and none of them knows an edge id; with a
 * database id each would need a new query to learn one.
 */

/** Old-style arXiv ids carry a slash (`cs/0301001`). It is legal in a fragment,
 *  and it is replaced anyway so the fragment reads as one token rather than as a
 *  path, and so nothing downstream is tempted to split on it. Everything else in
 *  an arXiv id is already `[0-9a-z.-]`, so nothing else needs touching, and an
 *  anchor a person can recognise on sight is one they can debug. */
const slug = (arxiv: string) => arxiv.replace(/\//g, "_");

/** Where a paper's own passage and its relationships sit: `p-1706.03762`. */
export const paperAnchor = (arxiv: string) => `p-${slug(arxiv)}`;

/** The jump index itself, the one place on the page not derived from content
 *  (issue #155). It is here rather than inline because this file is where the
 *  evidence page's place-names are written, and because the standfirst that
 *  points at the index and the `<nav>` that answers to it are 200 lines apart:
 *  two literals that must agree is how a fragment link quietly stops resolving.
 *  It cannot collide with `p-`/`r-` — those prefixes are reserved by shape. */
export const JUMP_INDEX_ANCHOR = "the-index";

/**
 * One relationship: `r-1409.0473-1706.03762`.
 *
 * `dup` is the edge's ordinal among the edges sharing this pair, 0 for the
 * first. Nothing in the schema stops two edges naming the same two papers, so
 * the second and later ones take a `-2`, `-3` suffix and the first stays
 * unsuffixed, which keeps the common case stable. Within a duplicated pair the
 * suffix rides on insert order and can therefore move across a rebuild; that is
 * the residue of the problem and not the problem, because the pair itself does
 * not move.
 */
export function edgeAnchor(source: string, target: string, dup = 0): string {
  return `r-${slug(source)}-${slug(target)}${dup > 0 ? `-${dup + 1}` : ""}`;
}

/** The shape `edgeAnchors` needs, structural on purpose so a caller holding
 *  something other than a `lib/genealogy` `Edge` can still ask. */
export type AnchorableEdge = {
  id: number;
  source_paper: string | null;
  target_paper: string | null;
};

/**
 * Every anchor on one page, keyed by edge id, with the duplicate rule applied
 * once for the whole set.
 *
 * **An edge whose paper row is gone (#79) is absent from the map, and that is
 * the answer, not a gap to fill.** No `r-e<id>` fallback: one fallback here
 * manufactures exactly the silently-retargeting link this scheme exists to
 * prevent, and it would pass any test that only checks the link resolves. A
 * caller that gets `undefined` renders no link and says why in words.
 */
export function edgeAnchors(edges: readonly AnchorableEdge[]): Map<number, string> {
  const byPair = new Map<string, AnchorableEdge[]>();
  for (const e of edges) {
    if (!e.source_paper || !e.target_paper) continue;
    // NUL as the separator, because an arXiv id cannot contain one and any
    // printable separator could in principle be part of an id.
    const key = `${e.source_paper}\u0000${e.target_paper}`;
    const bucket = byPair.get(key);
    if (bucket) bucket.push(e);
    else byPair.set(key, [e]);
  }
  const out = new Map<number, string>();
  for (const bucket of byPair.values()) {
    bucket.sort((a, b) => a.id - b.id);
    bucket.forEach((e, i) => {
      out.set(e.id, edgeAnchor(e.source_paper!, e.target_paper!, i));
    });
  }
  return out;
}

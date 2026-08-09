/**
 * An arXiv id out of what a person typed, or null when that string was never
 * one (issue #198).
 *
 * **The canonical form here is the one the pipeline already stores**, because
 * the whole value of a named paper is that it joins to a row: `papers.arxiv_id`
 * is written by `fetch_papers.py` from what `corpus_select.arxiv_id_of` pulls
 * out of an OpenAlex record, and that function's own regex is
 * `([a-z\-]+/\d{7}|\d{4}\.\d{4,5})`. Anything this file emits that that regex
 * would not is an id nothing in the system will ever match, and the requester
 * would be told their paper is in a map that does not contain it. So the accepted
 * shapes are deliberately narrower than what a person may paste, and the widening
 * is all on the input side.
 *
 * What is accepted and folded away:
 *   2404.03002 · 2404.03002v3 · arXiv:2404.03002 · arxiv.org/abs/2404.03002
 *   arxiv.org/pdf/2404.03002v1 · hep-th/9711200 · math.GT/0309136
 *
 * **The subject class is dropped from an old-style id on purpose.**
 * `math.GT/0309136` and `math/0309136` are one paper; arXiv's own `abs` URL uses
 * the archive alone, so that is what an OpenAlex location or DOI yields and what
 * this system stores.
 *
 * **The month is checked and the number is not.** `2413.00001` is not an id
 * anybody can hold, so refusing it at the door costs a requester nothing and
 * catches a transposed pair of digits. Beyond that this is shape and shape only:
 * whether the id names a paper that exists is settled by `corpus_select.py`,
 * which resolves every named id against OpenAlex before the build spends
 * anything and refuses the whole run by name if one does not resolve. Two
 * existence checks would be two answers to one question, and the later one is
 * the one that has to hold anyway.
 */

/** Three, and the cap is the point (issue #198, condition 5): a larger
 *  allowance turns this field into "bring your own corpus", which is F9 (#37)
 *  with its own ticket and its own questions. */
export const MAX_ANCHORS = 3;

const NEW_STYLE = String.raw`\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}`;
const OLD_STYLE = String.raw`[a-z][a-z-]*\/\d{2}(?:0[1-9]|1[0-2])\d{3}`;
const ARXIV_ID_RE = new RegExp(`^(?:${OLD_STYLE}|${NEW_STYLE})$`);

/** One id, normalised, or null. */
export function parseArxivId(raw: string): string | null {
  let s = raw.trim().toLowerCase();
  // A pasted link or a citation prefix, in that order: strip the URL down to its
  // last two path segments' worth of id, then the prefix, then a version suffix.
  s = s.replace(/^https?:\/\//, "").replace(/^(?:www\.|export\.)?arxiv\.org\/(?:abs|pdf)\//, "");
  s = s.replace(/^arxiv:/, "");
  s = s.replace(/\.pdf$/, "");
  s = s.replace(/v\d+$/, "");
  // The subject class, which is optional in the identifier and absent from every
  // form this system stores.
  s = s.replace(/^([a-z][a-z-]*)\.[a-z-]+\//, "$1/");
  return ARXIV_ID_RE.test(s) ? s : null;
}

export type AnchorParse =
  | { ok: true; ids: string[] }
  | { ok: false; bad: string; reason: "shape" }
  | { ok: false; bad: null; reason: "too many" };

/**
 * A whole field of them, separated by whitespace, commas or semicolons.
 *
 * **A bad id is named back, never dropped** (issue #198, condition 4): a
 * silently discarded id is a requester believing their paper is in a map that
 * does not contain it, which is the one failure this feature cannot have.
 * Duplicates fold rather than refuse, because naming one paper twice is naming
 * one paper, and the cap is applied after the fold so a fat-fingered paste
 * cannot cost somebody a slot.
 */
export function parseAnchors(raw: string, max: number = MAX_ANCHORS): AnchorParse {
  const tokens = raw.split(/[\s,;]+/).filter(Boolean);
  const ids: string[] = [];
  for (const t of tokens) {
    const id = parseArxivId(t);
    if (id === null) return { ok: false, bad: t.slice(0, 40), reason: "shape" };
    if (!ids.includes(id)) ids.push(id);
  }
  if (ids.length > max) return { ok: false, bad: null, reason: "too many" };
  return { ok: true, ids };
}

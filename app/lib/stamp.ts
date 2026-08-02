/**
 * What a verification stamp may be displayed as, given the text as it is now.
 *
 * Ticket #29, migration 015. Twin of `stamp_state` / `edge_stamp_state` in
 * pipeline/common.py. Two languages means two copies, and the mitigation is that
 * both are three lines with no threshold and both are pinned by the same truth
 * table (docs/design/recheckable-stamp.md, section 7, falsifier 5).
 *
 * A stamp digest is written by the code that performed the match; a paper's
 * digest is written by the code that wrote the file. Neither is ever copied from
 * the other, which is what lets this comparison return false. Everything here is
 * exact equality of a digest: there is no threshold in this file and there must
 * never be one.
 */

export type StampState = "verified" | "inferred" | "stale";

export const STAMP_LABEL: Record<StampState, string> = {
  verified: "✓ verified",
  inferred: "○ inferred",
  stale: "◌ stale",
};

/** The colour each state renders in. No new palette token: the UI tokens are
 *  owner-approved law in CLAUDE.md, and stale needs no colour of its own. It is
 *  drawn like inferred, dotted and quiet, because it claims less than either. */
export const STAMP_COLOR: Record<StampState, string> = {
  verified: "var(--verified)",
  inferred: "var(--inferred)",
  stale: "var(--ink-soft)",
};

/** The sentence each state is entitled to. Never "verified" for anything but a
 *  stamp whose digest still matches the paper's own.
 *
 *  The stale wording says "as it now stands" rather than "since the text
 *  changed", because stale has two causes and only one of them is a change we
 *  can point to: the stamp's digest differs from the paper's, or no digest was
 *  ever recorded. Naming the first as though it were both would be a claim about
 *  the corpus that the data does not support, which is the habit this ticket is
 *  about. */
export const STAMP_MEANING: Record<StampState, string> = {
  verified: "string-matched against this paper's own extracted text",
  inferred: "could not be string-matched against the extracted text",
  stale: "not checked against the extracted text as it now stands",
};

/**
 * **Stale dominates the boolean, in both directions.** A failed check against
 * text that has since changed is no more about today's text than a passing one
 * is. One rule with no exceptions is the only version of this that survives
 * being copied into a second language, which is what this file is.
 */
export function stampOf(
  verified: boolean | null | undefined,
  stampDigest: string | null | undefined,
  currentDigest: string | null | undefined,
): StampState {
  if (!stampDigest || !currentDigest || stampDigest !== currentDigest) return "stale";
  return verified ? "verified" : "inferred";
}

/**
 * The same rule for a unit carrying two stamps. An edge's boolean is one verdict
 * over both quotes, so there is no per-side boolean to resolve; what there is
 * per side is whether that side's text has moved. Either side stale makes the
 * edge stale, because half a re-checkable edge is not a re-checkable edge.
 */
export function edgeStampOf(
  verified: boolean | null | undefined,
  sourceDigest: string | null | undefined,
  sourceCurrent: string | null | undefined,
  targetDigest: string | null | undefined,
  targetCurrent: string | null | undefined,
): StampState {
  if (
    stampOf(true, sourceDigest, sourceCurrent) === "stale" ||
    stampOf(true, targetDigest, targetCurrent) === "stale"
  ) {
    return "stale";
  }
  return verified ? "verified" : "inferred";
}

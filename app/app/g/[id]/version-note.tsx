import Link from "next/link";
import type { MapVersions } from "../../../lib/genealogy";

/**
 * What a reader is told about which version of a map they are looking at
 * (issue #208, F4).
 *
 * **The rule it serves: a link always shows what it showed.** `/g/17` is version
 * 1 of dark energy permanently, and it renders in full — map, evidence, threads,
 * report, export — whether or not a later run has replaced it, because a reader
 * who cited it cited a set of claims and a citation that quietly becomes a
 * different set has broken the check this whole product is for. What a
 * superseded version owes its reader is therefore not a refusal and not a
 * redirect: it is a sentence saying so, and a way to the current one.
 *
 * **A line, not a banner.** The superseded version is not wrong and this copy
 * does not apologise for it: it states a fact, in the page's own quiet caption
 * voice, above the map rather than across it. Nothing is coloured — the stamp
 * colours mean verified and inferred and may not be spent on chrome — and the
 * only accent is the site's ordinary link colour on the link.
 *
 * **Both lines are absent on every map in this database today**, which is the
 * point: one published version per concept, current, so `published.length` is 1
 * and `is_current` is true, and this component renders nothing at all. The four
 * live maps are byte-identical after this ticket.
 *
 * Mounted per page rather than in `layout.tsx`, because that layout may not
 * fetch anything (see its own comment) and these facts come off the map row.
 * The report page carries the same facts as figures in its run section instead
 * (#209), where every other fact about the build already lives.
 */

/**
 * The date this version was replaced, or null if there is not one we can print.
 *
 * Takes `unknown` deliberately. The column is `timestamptz` and a driver may
 * hand back a `Date` or a string depending on its type parsers, and the page
 * must print neither "Invalid Date" nor a guess: an unreadable value degrades to
 * the wording that claims no date, exactly as `editWhen` degrades to "date not
 * recorded" rather than inventing one.
 *
 * The locale is pinned rather than the reader's. This is server-rendered and
 * shared, so a floating locale would make the same page read differently for
 * two people and could differ between the server render and a hydration; and the
 * long form ("12 August 2026") is unambiguous in a way that a numeric one is
 * not, which matters on a sentence about when something stopped being true.
 * The day is the server's, which is UTC on Vercel.
 */
export function supersededOn(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const d = v instanceof Date ? v : new Date(String(v));
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

export default function VersionNote({
  id, concept, versions,
}: { id: number; concept: string; versions: MapVersions | null }) {
  // Null is "this deployment's schema has no versions" (the minutes between the
  // Vercel deploy and Render's pre-deploy), not "one version": nothing is said,
  // which is what these pages said before this ticket.
  if (!versions) return null;
  const { version, is_current, published } = versions;
  const current = published.find((v) => v.is_current) ?? null;
  const others = published.filter((v) => v.id !== id);
  const when = supersededOn(versions.superseded_at);
  // A version that is current and alone says nothing. The strip earns its line
  // only when there is somewhere else to go, and the note only when this is not
  // the live reading.
  if (is_current && others.length === 0) return null;

  return (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", lineHeight: 1.75,
      color: "var(--ink-soft)", margin: "0 0 .9rem" }}>
      {!is_current && (
        <div>
          This is version {version} of the “{concept}” map.{" "}
          {/* Two wordings, because two facts. A version the swap demoted carries
              the date it was demoted; a published version that is simply not the
              current one carries no date and gets no invented one, and "replaced
              on" would be a claim nothing in the row supports. */}
          {when ? `It was replaced on ${when}.` : "It is not the current one."}{" "}
          {current ? (
            <>
              See{" "}
              <Link href={`/g/${current.id}`} style={{ color: "var(--edge-extends)" }}>
                the current version
              </Link>
              .
            </>
          ) : (
            // Reachable only if nothing is current for this concept, which the
            // swap in #207 does not produce. Said rather than left silent: a
            // reader told this is not the current version and given nowhere to
            // go reads the page as broken.
            <>No version of it is current at the moment.</>
          )}
        </div>
      )}
      {published.length > 1 && (
        <div style={{ color: "var(--ink-faint)" }}>
          Version {version} of {published.length}
          {is_current && ", the current one"}
          {others.length > 0 && (
            <>
              {" · other versions: "}
              {others.map((v, i) => (
                <span key={v.id}>
                  {i > 0 && ", "}
                  <Link href={`/g/${v.id}`} style={{ color: "var(--edge-extends)" }}>{v.version}</Link>
                  {v.is_current && " (current)"}
                </span>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

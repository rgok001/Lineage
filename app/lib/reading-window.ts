/**
 * Where a map's reading stops, said once (issue #44, `[Q7]`).
 *
 * The Product Owner read the first physics map on 2026-08-08, saw the timeline
 * finish in 2011, and asked whether the tool was claiming nothing had been added
 * to the topic since. It was not, and it had no way of saying so: the right-hand
 * end of a timeline reads as the end of the story unless the page says
 * otherwise. Corpus selection under-samples recent years (`[F5]`, issue #33) and
 * that is the actual fix; until it ships, every map states where its own reading
 * ran out. The claim is always about the map and never about the field, which is
 * the line the whole product draws between what it checked and what it read.
 *
 * **Its own module, not `lib/genealogy.ts`, because a client component imports
 * it.** `InfluenceMap` is `"use client"` and had only `import type` from
 * `lib/genealogy`, which erases; a value import from there instead put
 * `lib/db.ts` in the browser bundle, where `process.env.DATABASE_URL` is
 * undefined and its module-level `throw` runs on load. Measured on the build
 * before this file existed: `.next/static/chunks/app/g/[id]/page-*.js` contained
 * "DATABASE_URL is not set". Same reason `lib/anchors.ts` and `lib/stamp.ts` are
 * separate, and the reason to keep this file free of imports.
 *
 * The two numbers themselves come from `map_report` (see `InfluenceMapData`), so
 * this page and the report page's "earliest year"/"latest year" are one
 * expression and cannot disagree about one map.
 */

/** A year the canvas rules off, and which end of the reading it is. `side`
 *  places the label inward from that end, so the newest-paper label cannot run
 *  off the right edge of the canvas. */
export type ReadingMark = { year: number; label: string; side: "start" | "end" };

/** The years the canvas marks, from the same two numbers the sentence below is
 *  built from, so the picture and the prose cannot mark different years. A map
 *  whose reading is one year wide gets one rule rather than two on one x. */
export function readingMarks(from: number | null, to: number | null): ReadingMark[] {
  if (from === null || to === null) return [];
  if (from === to) return [{ year: to, label: `this map's reading · ${to}`, side: "end" }];
  return [
    { year: from, label: `this map's reading starts · ${from}`, side: "start" },
    { year: to, label: `this map's reading stops · ${to}`, side: "end" },
  ];
}

/**
 * The caption under the canvas, or null when the map cannot say.
 *
 * Null rather than a hedge: a map with no years recorded gets no marks and no
 * sentence, because a horizon nobody can place is worse than no horizon, and
 * "from null to null" is the fabrication rule (CLAUDE.md rule 4) in small.
 *
 * "the oldest and the newest paper in this map that defines the term" names the
 * population rather than saying "papers", which is #123's rule: four other
 * surfaces of this product print a count under that bare word and all four count
 * different sets. These two years are over the map's DEFINING papers, which is
 * wider than the papers the canvas draws and wider than the badge's "papers this
 * map ranked".
 */
export function readingWindowSentence(from: number | null, to: number | null): string | null {
  if (from === null || to === null) return null;
  if (from === to)
    return `Marked on the timeline: the oldest and the newest paper in this map that defines the term are both from ${to}. That is where this map's reading stops, not where the term's story does. Work outside that year may exist, and this map has not read it.`;
  return `Marked at both ends of the timeline: the oldest and the newest paper in this map that defines the term, ${from} and ${to}. That is where this map's reading stops, not where the term's story does. Work outside those years may exist, and this map has not read it.`;
}

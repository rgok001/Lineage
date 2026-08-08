"use client";
import type { MouseEvent } from "react";

/** What a click on the tab for the page you are already on does (issue #151).
 *
 *  It was one behaviour in two files: `nav.tsx` since it shipped and
 *  `g/[id]/tabs.tsx` inheriting the pattern faithfully for #143. Both rendered
 *  the current section as a link to itself, so the click threw the page away and
 *  fetched it again — 2.8 s on the map, 3.7 s on the evidence page, 1.5 s on the
 *  report, measured on the live deploy — and every one of those waits returned
 *  exactly what was already on screen, with the reader's open relationships
 *  closed and their scroll position gone. It lives here rather than in either
 *  strip so the third strip cannot inherit it again.
 *
 *  The click scrolls to the top and fetches nothing. Going back to the top is
 *  the one part of the old behaviour that was worth having, and on a reader who
 *  is already at the top it does nothing at all, which is most of them: neither
 *  strip is sticky (a fixed bar on a 39-screen evidence page was refused in
 *  #143), so the tab has to be on screen to be clicked. Doing literally nothing
 *  was the alternative; this is the same thing wherever the reader can see the
 *  tab today, and the right thing if a strip is ever made sticky.
 */
export function currentTabClick(href: string, path: string) {
  // "Threads" is `/g/{id}#threads`, so on `/g/{id}` it points at this very route
  // plus a hash — and it must keep navigating: it is how a reader on the map
  // reaches the thread list, and the hashchange it fires is what #150's arrival
  // handling hangs on. A href carrying a hash is never suppressed. The string
  // comparison below would already spare it; the guard is here so that a later
  // hand comparing `href.split("#")[0]` has to argue with a comment first.
  if (href.includes("#")) return undefined;
  // Which tab is *lit* is a different question from which tab points at this
  // route, and suppressing on the lit one would break real navigation:
  // "Concepts" is lit on `/g/13` and goes to `/`, "Threads" is lit on a thread
  // page and goes to the map. Compare hrefs, never active states.
  if (href !== path) return undefined;

  return (e: MouseEvent<HTMLAnchorElement>) => {
    // Mirrors next/link's own isModifiedEvent: a modifier or middle click asks
    // for a second copy in a new tab, which is a real request, not this click.
    if (e.defaultPrevented || e.button !== 0
      || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    // A query string is state that this bare href would clear, so that click
    // means something and must navigate. Read it off the location rather than
    // with useSearchParams(), which from the root layout's nav would opt every
    // route out of static rendering and undo the two pages #145 prerendered.
    if (window.location.search) return;
    e.preventDefault();
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: still ? "auto" : "smooth" });
  };
}

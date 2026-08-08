"use client";
import { useEffect } from "react";

/**
 * Scrolls to the element the URL fragment names (issue #150).
 *
 * MOUNT THIS FROM THE PAGE THAT RENDERS THE TARGETS, NEVER FROM A LAYOUT.
 *
 * A fragment is applied at a moment the *document* defines — parse, load, or
 * the router's navigation commit. On a route with a `loading.tsx` the target's
 * existence is defined by the *stream* instead. Those two clocks are unrelated
 * and nothing reconciles them, so the browser's own hash scroll has no way of
 * being right here: `/g/13#threads` landed at scrollY 150 with no `#threads`
 * element in the document at 200ms, 500ms, 1s or 2s, and the content arriving
 * at 4s re-scrolled nothing. A hard load, with no router involved at all,
 * failed identically — which is what says this belongs to the streaming
 * boundary and not to the anchor or the tab strip.
 *
 * This component's own mount IS the event "the targets now exist", exactly.
 * That is why there is no MutationObserver, no poll, no timeout and no retry
 * count: every one of those infers an event we can observe directly, and none
 * of them works without a deadline, which is a number nobody can measure on a
 * page whose arrival time is a network variable. Mounted above the streaming
 * boundary — in a layout, or in any wrapper that is already on screen while the
 * reader waits — it would fire early by construction, which is the bug as
 * filed. If a page ever renders its targets inside a nested `<Suspense>`, this
 * goes inside that boundary with them: a sibling of the content, never an
 * ancestor of the wait.
 *
 * Not found means do nothing. The page that mounts this is the page that
 * renders the targets, so "absent" means the id genuinely is not here, and
 * scrolling nowhere is the honest answer.
 *
 * `instant` rather than the default, so that a stylesheet later setting
 * `scroll-behavior: smooth` cannot turn this into a 30,000px glide down the
 * evidence page, which would be nauseating and would fight the reduced-motion
 * work in issue #147.
 */
export default function HashTarget() {
  useEffect(() => {
    const jump = () => {
      const raw = location.hash.slice(1);
      if (!raw) return;
      let id = raw;
      // A malformed % escape is not an id, but it is also not a reason to throw
      // on a page the reader asked for; fall back to the fragment as written.
      try { id = decodeURIComponent(raw); } catch { /* keep raw */ }
      const target = document.getElementById(id);
      if (!target) return;
      // An anchor that lands on a collapsed row has not answered the reader.
      for (let n: HTMLElement | null = target; n; n = n.parentElement) {
        if (n instanceof HTMLDetailsElement) n.open = true;
      }
      target.scrollIntoView({ behavior: "instant" });
    };
    jump();
    window.addEventListener("hashchange", jump);
    return () => window.removeEventListener("hashchange", jump);
  }, []);
  return null;
}

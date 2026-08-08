"use client";

/**
 * The one error boundary in the app (issue #159).
 *
 * Until now there was none anywhere under `app/`, so anything that threw during
 * a render reached Next's global-error shell: an unstyled black page reading
 * "Application error: a server-side exception has occurred" with a digest under
 * it. Two comments in this codebase already noted the gap while working around
 * it (`evidence/page.tsx` on issue #79's missing paper row, and B33 itself).
 *
 * **It says something failed. It never says the map is missing.** That
 * distinction is the whole point of shipping this alongside the id parser: a
 * bad id is now a 404 before any query runs, so what is left to reach this page
 * is a genuine failure, usually the database being unreachable. Telling that
 * reader "no such map" would be the tool lying about its own state on behalf of
 * a map that exists, which is worse than the raw shell it replaces.
 *
 * The digest is shown because it is the only handle a reader has when reporting
 * this, and it is already in the response either way. It is an opaque hash of
 * the message, not the message: nothing about the failure leaks by printing it.
 *
 * Sits at the root of `app/` rather than under `g/[id]/`, because a runtime
 * error is not a map's problem and the trace page and the front door deserve
 * the same courtesy. It cannot catch a throw in the root layout; nothing there
 * does I/O, and catching that needs `global-error.tsx`, which would have to
 * carry its own `<html>` and duplicate the shell.
 */
export default function Error({
  error, reset,
}: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem 6rem" }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: ".68rem", letterSpacing: ".14em",
        textTransform: "uppercase", color: "var(--ink-faint)",
      }}>
        Something went wrong
      </div>
      <h1 style={{
        fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.9rem",
        margin: ".35rem 0 0", letterSpacing: "-.01em",
      }}>
        This page could not be loaded
      </h1>
      <p style={{
        fontFamily: "var(--font-display)", fontSize: "1rem", lineHeight: 1.65,
        color: "var(--ink-soft)", margin: "1rem 0 0",
      }}>
        The failure is on our side, not in what you asked for. Nothing has been
        changed or lost. Loading it again often works, because the most common
        cause is a request to our database timing out.
      </p>
      <div style={{ display: "flex", gap: ".7rem", alignItems: "center", marginTop: "1.6rem",
        flexWrap: "wrap" }}>
        <button onClick={reset} style={{
          fontFamily: "var(--font-ui)", fontSize: ".9rem", color: "var(--ink)",
          background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8,
          padding: ".55rem 1rem", cursor: "pointer",
        }}>
          Try again
        </button>
        <a href="/" style={{
          fontFamily: "var(--font-mono)", fontSize: ".75rem", color: "var(--edge-extends)",
          textDecoration: "none", padding: ".55rem 0",
        }}>
          the maps
        </a>
      </div>
      {error.digest && (
        <p style={{
          fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--ink-faint)",
          lineHeight: 1.8, marginTop: "2.4rem", paddingTop: "1rem",
          borderTop: "1px solid var(--line-soft)",
        }}>
          If you report this, quote {error.digest}. It is the reference for this
          one failure in our logs.
        </p>
      )}
    </main>
  );
}

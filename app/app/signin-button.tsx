"use client";

import { useEffect, useState } from "react";
import { startSignIn, endSignOut } from "../lib/auth-actions";

/**
 * Shows who you are and lets you sign in/out. Purely informational: the edit
 * controls it gates are cosmetic — the actual authorisation happens inside every
 * Server Action (lib/authz.ts requireOwner), which is the only thing a caller
 * with curl cannot bypass.
 *
 * It reads the session from /api/viewer after paint rather than on the server
 * (issue #145). As an async server component in the root layout it used a
 * dynamic API above every route in the app, so nothing was statically
 * prerenderable and /about and /roadmap — fixed prose, no data — cost a server
 * round trip each. Suspense would not have helped: it changes when a fallback
 * shows, not whether the route is static.
 *
 * Because that made it informational-after-paint, the slot must never guess.
 * It renders NOTHING until the answer arrives — not a spinner, and above all
 * not "Sign in with GitHub" as a default, which would flash the wrong state at
 * the one reader who is signed in. If the request fails it stays empty for the
 * same reason; /api/auth/signin is still reachable directly.
 */

type Viewer = { login: string | null; owner: boolean };

export default function SignInButton() {
  const [viewer, setViewer] = useState<Viewer | null>(null);

  useEffect(() => {
    let live = true;
    fetch("/api/viewer", { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Viewer>) : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((v) => { if (live) setViewer(v); })
      .catch((exc: unknown) => {
        console.warn("sign-in state unavailable:", exc instanceof Error ? exc.message : String(exc));
      });
    return () => { live = false; };
  }, []);

  return (
    <div style={slot}>
      <noscript>
        {/* The control was a server-rendered form and worked without JavaScript;
            after #145 it does not exist until JS runs. Auth.js's own page is the
            honest answer for the readers that costs. */}
        <a href="/api/auth/signin" style={{ ...btn, display: "inline-block", textDecoration: "none" }}>
          Sign in
        </a>
      </noscript>
      {viewer === null ? null : viewer.login ? (
        <>
          <span style={{ color: "var(--ink-soft)" }}>
            {viewer.login}
            {viewer.owner ? (
              <span style={{ marginLeft: ".4rem", color: "var(--verified)", fontFamily: "var(--font-mono)", fontSize: ".68rem" }}>
                curator
              </span>
            ) : (
              <span style={{ marginLeft: ".4rem", color: "var(--ink-soft)", fontFamily: "var(--font-mono)", fontSize: ".68rem" }}>
                read-only
              </span>
            )}
          </span>
          <form action={endSignOut}>
            <button type="submit" style={btn}>Sign out</button>
          </form>
        </>
      ) : (
        <form action={startSignIn}>
          <button type="submit" style={btn}>Sign in with GitHub</button>
        </form>
      )}
    </div>
  );
}

/**
 * The reserved slot. `minHeight` is what stops the nav moving when the answer
 * lands, and it is measured rather than chosen: both states of this control
 * render 27.59 px tall on the shipped page at a 16 px root, and the header row's
 * height is exactly the control's, so any reservation short of it moves the nav
 * down on arrival. 1.77rem is that height at the smallest root size worth
 * covering — the button's 1 px borders do not scale with the root font, so the
 * requirement in rem grows as the root shrinks (1.70rem at 20 px, 1.72 at 16,
 * 1.77 at 12). It costs the header 0.7 px of permanent height, which is not a
 * shift.
 *
 * No `min-width`: it would reserve nothing useful. The signed-in width is a
 * function of the login (measured 141 px to 260 px across 2 to 19 characters),
 * so no constant covers it, and the row above is `space-between` with this slot
 * flush right, so the slot's width moves nothing on the page either way.
 */
const slot: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "flex-end",
  gap: ".7rem", fontSize: ".78rem", minHeight: "1.77rem",
};

const btn: React.CSSProperties = {
  font: "inherit", fontSize: ".76rem", padding: ".3rem .65rem", cursor: "pointer",
  border: "1px solid var(--ink-soft)", borderRadius: 4,
  background: "var(--card)", color: "var(--ink)",
};

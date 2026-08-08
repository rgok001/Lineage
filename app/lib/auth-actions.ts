"use server";

import { signIn, signOut } from "../auth";

/**
 * The two Server Actions the header's sign-in control submits (issue #145).
 *
 * They live here rather than inline in the component because the component is
 * now a client component, and a client component cannot declare a Server Action
 * inside itself. Nothing about the mechanism moved: these are the bodies that
 * were inline in signin-button.tsx, still POSTed as Server Actions with Auth.js's
 * own CSRF handling. Deliberately not next-auth/react's signIn/signOut, which is
 * a different code path with different CSRF handling — this ticket changed WHEN
 * the session is read, never HOW anyone signs in.
 *
 * Neither takes an argument, and the redirect target is hard-coded. The old
 * component had a `redirectTo` prop defaulting to "/" that no call site ever
 * set; accepting one from the client would be an open redirect introduced by a
 * performance fix. Returning a reader to the page they were on is a separate
 * ticket, and the target would be validated server-side against the app's own
 * routes. (`lib/trace-actions.ts` keeps its own sign-in to "/trace"; that one is
 * server-side and unaffected.)
 */
export async function startSignIn(): Promise<void> {
  await signIn("github", { redirectTo: "/" });
}

export async function endSignOut(): Promise<void> {
  await signOut({ redirectTo: "/" });
}

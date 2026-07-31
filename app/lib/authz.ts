import { auth } from "../auth";

/**
 * Authorisation. Authentication (GitHub, via auth.ts) only establishes WHO
 * someone is — it will vouch for any of GitHub's users. Deciding what they may
 * do is ours alone, and it lives here.
 */

/**
 * A Viewer is NOMINAL, not structural, and the brand is what makes it so.
 *
 * TypeScript compares object types by shape, so while this was a plain
 * `{ login: string; ... }` alias, `recordEdit(…, { login: "anyone" })` compiled
 * clean under --strict with no cast: the "only a session can supply this"
 * guarantee was a comment wearing a compiler's clothes, and it had already been
 * copied into the as-built as an enforced invariant. `SESSION_BACKED` is a
 * unique symbol nothing outside this module can name or construct, so the only
 * way to hold a Viewer is to have been handed one by the three functions below.
 * The single cast that mints one lives here and must live nowhere else.
 */
declare const SESSION_BACKED: unique symbol;

export type Viewer = {
  readonly [SESSION_BACKED]: true;
  readonly login: string;
  readonly name?: string | null;
  readonly image?: string | null;
};

export async function getViewer(): Promise<Viewer | null> {
  const session = await auth();
  const login = (session?.user as { login?: string } | undefined)?.login;
  if (!login) return null;
  // The one place a Viewer is minted, and the only cast that may do it: the
  // login came from a GitHub session, which is the whole content of the brand.
  return { login, name: session?.user?.name, image: session?.user?.image } as Viewer;
}

export function isOwner(viewer: Viewer | null): boolean {
  const owner = process.env.OWNER_GITHUB_LOGIN;
  if (!owner) return false; // unset => nobody is owner. Fail closed, never open.
  return viewer?.login?.toLowerCase() === owner.toLowerCase();
}

/**
 * Call this as the FIRST line of every mutating Server Action.
 *
 * A Server Action compiles to a public HTTP endpoint: hiding a button in the UI
 * removes it from the page, not from the internet. The button-hiding is
 * courtesy; this is the lock. Throws rather than returning a flag so a forgotten
 * check cannot silently fall through to the mutation.
 */
export async function requireOwner(): Promise<Viewer> {
  const viewer = await getViewer();
  if (!isOwner(viewer)) {
    throw new Error("Not authorised: only the owner may modify this genealogy.");
  }
  return viewer!;
}

/** Signed in at all — enough to REQUEST a trace, never to run one. */
export async function requireViewer(): Promise<Viewer> {
  const viewer = await getViewer();
  if (!viewer) throw new Error("Not authorised: sign in first.");
  return viewer;
}

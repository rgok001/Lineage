import { getViewer, isOwner } from "../../../lib/authz";

/** Who the caller is, for the header's sign-in control (issue #145). The root
 *  layout used to read the session while rendering, which opted every route in
 *  the app out of static generation, including /about and /roadmap — two pages
 *  of fixed prose. The control now asks this after paint instead.
 *
 *  It takes no input of any kind, so there is nothing to ask it about anyone
 *  else, and it answers only about the session its own caller presented. It
 *  returns `owner` as a boolean and never echoes OWNER_GITHUB_LOGIN: the client
 *  learns whether it is the curator, not who the curator is. isOwner stays
 *  server-side, and this endpoint grants nothing — requireOwner() inside every
 *  mutating Server Action is still the only lock (lib/authz.ts).
 *
 *  The response is one reader's identity, so it must never be shared: no-store
 *  and private on the response, and force-dynamic so the edge has nothing to
 *  hand to the next caller. */
export const dynamic = "force-dynamic";

export async function GET() {
  const viewer = await getViewer();
  return Response.json(
    { login: viewer?.login ?? null, owner: isOwner(viewer) },
    { headers: { "Cache-Control": "no-store, private" } },
  );
}

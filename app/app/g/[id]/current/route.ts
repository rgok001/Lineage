import { currentVersionId } from "../../../../lib/genealogy";
import { parseMapId } from "../../../../lib/map-id";

export const dynamic = "force-dynamic";

/**
 * `/g/<id>/current` — the concept's address, as opposed to the version's
 * (issue #208, F4).
 *
 * `/g/<id>` names a version permanently: a reader who cites a map is citing a
 * set of claims, and an id that quietly came to mean a different set would break
 * the one check this product exists to offer. Anything that wants to follow the
 * *concept* instead — a bookmark, a link from outside, a reading list that
 * should track the newest reading — points here and is sent on to whichever
 * version is current now.
 *
 * **Not `/c/<slug>`.** A slug is a new identifier with escaping and collision
 * problems, and this needs no new id space, no new table and no new column. The
 * id in the URL is one this system already minted.
 *
 * **A route handler rather than a page, and that is not a style choice.** Every
 * route under `/g/[id]` sits behind a `loading.tsx`, which flushes a 200 shell
 * before the page runs, so a page's HTTP status cannot testify about a redirect
 * or a 404 (#159): the verdict would be legible only in the RSC stream. A route
 * handler streams nothing, so its status line is its verdict, which is what a
 * link-follower, a crawler and a `curl -I` all read.
 *
 * **307 and never 308.** Which version is current is exactly the thing that
 * changes, so a permanent redirect would be cached by browsers and proxies
 * against the day it stops being true — the reader would be pinned to version 1
 * for ever by the one request they made before version 2 existed. `no-store` for
 * the same reason.
 *
 * **404 for an unpublished id, exactly as the map itself 404s** (#168): the
 * refusal is inside `currentVersionId`'s own statement rather than in a
 * conditional here, so a build that is still running is as invisible through
 * this door as through every other one.
 */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Parsed rather than caught, like the export route beside it: a string that
  // was never a map id is a 404, while a genuine database failure still raises
  // and is still a 500 (#159).
  const gid = parseMapId(id);
  if (gid === null) return new Response("No map with that id.", { status: 404 });

  const currentId = await currentVersionId(gid);
  if (currentId === null)
    // Two states answer the same way: no such published map, and a published map
    // whose concept has nothing current. The second is not something the publish
    // swap can produce (#207 demotes and promotes in one transaction), and a
    // reader cannot act on the difference.
    return new Response("No map with that id, or no current version of it.", { status: 404 });

  return new Response(null, {
    status: 307,
    headers: {
      // Relative on purpose: the app is reached at more than one hostname
      // (the Vercel domain and any alias), and an absolute Location would send
      // a reader off the host they arrived on.
      Location: `/g/${currentId}`,
      "Cache-Control": "no-store",
    },
  });
}

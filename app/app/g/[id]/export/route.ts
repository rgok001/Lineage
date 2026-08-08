import { buildExport } from "../../../../lib/export";
import { parseMapId } from "../../../../lib/map-id";

export const dynamic = "force-dynamic";

/**
 * Download the writing scaffold. `?thread=<id>` scopes it to one thread,
 * `?format=bib` returns the BibTeX instead of the Markdown. Two formats rather
 * than one archive: no zip dependency, and a .bib wants to land in a reference
 * manager while the .md wants to land in a draft.
 */
export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const url = new URL(req.url);
  const thread = url.searchParams.get("thread") ?? undefined;
  const bib = url.searchParams.get("format") === "bib";

  // A route handler has no `notFound()` boundary above it, so `/g/abc/export`
  // answered a reader's download with a bare 500 and an empty body: the browser
  // saves that as a broken file with no clue what went wrong (issue #159). The
  // id is parsed rather than caught, so a genuine database failure still raises
  // and is still a 500 — only a string that was never a map id becomes a 404.
  const gid = parseMapId(id);
  if (gid === null) return new Response("No map with that id.", { status: 404 });

  const out = await buildExport(gid, thread);
  if (!out) return new Response("No map, or no threads generated for it yet.", { status: 404 });

  const name = bib ? `${out.basename}.bib` : `${out.basename}.md`;
  return new Response(bib ? out.bibtex : out.markdown, {
    headers: {
      "Content-Type": `${bib ? "application/x-bibtex" : "text/markdown"}; charset=utf-8`,
      "Content-Disposition": `attachment; filename="${name}"`,
      "Cache-Control": "no-store",
    },
  });
}

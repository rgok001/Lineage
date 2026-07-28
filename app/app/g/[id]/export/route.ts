import { buildExport } from "../../../../lib/export";

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

  const out = await buildExport(Number(id), thread);
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

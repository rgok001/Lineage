/** OpenAlex fields that actually contain arXiv papers, for the trace-request
 *  subject picker. One group_by call returns every field with its arXiv work
 *  count, so the dropdown is populated from the live source and sorted by how
 *  much arXiv actually holds. The list is near-static, so it is cached a day. */

export type ArxivField = { id: string; name: string; count: number };

// Degraded-mode list if OpenAlex is unreachable: the arXiv-heavy fields, so a
// request can still be made (Computer Science first, matching the default).
const FALLBACK: ArxivField[] = [
  { id: "fields/17", name: "Computer Science", count: 0 },
  { id: "fields/31", name: "Physics and Astronomy", count: 0 },
  { id: "fields/26", name: "Mathematics", count: 0 },
  { id: "fields/22", name: "Engineering", count: 0 },
  { id: "fields/20", name: "Economics, Econometrics and Finance", count: 0 },
  { id: "fields/28", name: "Neuroscience", count: 0 },
];

export const DEFAULT_FIELD_ID = "fields/17"; // Computer Science

export async function getArxivFields(): Promise<ArxivField[]> {
  const mailto = process.env.OPENALEX_MAILTO || "lineage@example.com";
  const url =
    "https://api.openalex.org/works?filter=indexed_in:arxiv" +
    "&group_by=primary_topic.field.id&mailto=" + encodeURIComponent(mailto);
  try {
    const res = await fetch(url, { next: { revalidate: 86400 } });
    if (!res.ok) return FALLBACK;
    const data = (await res.json()) as {
      group_by?: { key: string; key_display_name: string; count: number }[];
    };
    const fields = (data.group_by ?? [])
      .filter((g) => g.count > 0 && g.key_display_name)
      .map((g) => ({
        id: `fields/${String(g.key).split("/").pop()}`,
        name: g.key_display_name,
        count: g.count,
      }))
      .sort((a, b) => b.count - a.count);
    return fields.length ? fields : FALLBACK;
  } catch {
    return FALLBACK;
  }
}

/** The set of valid field ids, for server-side validation of a request. */
export function isKnownField(fields: ArxivField[], id: string): boolean {
  return fields.some((f) => f.id === id);
}

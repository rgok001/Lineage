/**
 * The map id out of a URL, or null when that string was never one (issue #159,
 * `[B33]`).
 *
 * Every route under `/g/[id]` used to hand `Number(id)` straight to a query and
 * guard only the RESULT: `if (!g) notFound()`. That covers a map that is absent
 * and nothing else. `Number("abc")` is NaN, `Number("13.5")` is a float,
 * `Number("1e999")` is Infinity and `Number("9999999999999999999999")` is past
 * what the driver can bind to a bigint column — each of those makes the query
 * THROW, so no null ever exists for the guard to catch, and the reader gets the
 * unstyled "Application error … Digest: 574562160" screen where a 404 belongs.
 * `/g/abc/export` was worse: a route handler with no boundary at all returned a
 * bare 500 with an empty body, which downloads as a broken file.
 *
 * So the check happens ONCE, here, before the id can reach a query, rather than
 * as a try/catch per route. Two reasons that shape was chosen. A try/catch
 * cannot tell a malformed id from Postgres being unreachable, and it would
 * report a real outage as "no such map" — a silent 404 on a working map is a
 * worse defect than the one being fixed. And the export handler is not a page,
 * so it has no `notFound()` boundary to fall into; a value it can test is the
 * only fix that reaches it.
 *
 * What it accepts is what `genealogies.id` can hold and JavaScript can carry
 * without rounding: BIGSERIAL, so positive, and inside `Number.MAX_SAFE_INTEGER`,
 * because past that two different ids parse to the same number and the map you
 * get is not the map you asked for. Digits and nothing else — no sign, no
 * exponent, no `0x`, no separator, no surrounding space — because every one of
 * those is a second URL for a map that already has one, and `Number()` accepting
 * them is what made `/g/1_3` reach the database in the first place.
 *
 * Nothing here says what a caller does with the null. Pages call `notFound()`;
 * the export handler returns its own 404 response.
 */
export function parseMapId(raw: string): number | null {
  if (!/^[0-9]+$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 1 ? n : null;
}

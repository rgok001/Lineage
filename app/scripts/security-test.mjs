/**
 * Adversarial auth test — behave like a stranger with curl and no session.
 *
 * The naive version of this test only replays Server Action ids found in the
 * anonymous HTML. That is a FALSE PASS: the edit controls are hidden from
 * strangers, so the only id in the page is sign-in, and the rejection you see is
 * sign-in failing on bad input — not the mutation being blocked.
 *
 * A real attacker harvests action ids from the build (server-reference-manifest
 * / client chunks), which are public artifacts. So we do the same, and fire a
 * mutation payload at EVERY id, then check whether the database moved.
 *
 * Run from app/ with the dev server up:  node scripts/security-test.mjs
 */
import { existsSync, readFileSync } from "node:fs";
import { neon } from "@neondatabase/serverless";

const env = readFileSync(new URL("../.env.local", import.meta.url), "utf8");
const sql = neon(env.match(/^DATABASE_URL=(.+)$/m)[1].trim());
const BASE = process.env.BASE ?? "http://localhost:3000";
const GENEALOGY = 2;

const snapshot = async () => {
  const [g] = await sql`SELECT nodes, user_edits FROM genealogies WHERE id = ${GENEALOGY}`;
  const edges = await sql`SELECT id, edge_type FROM edges WHERE genealogy_id = ${GENEALOGY} ORDER BY id`;
  return JSON.stringify({
    labels: g.nodes.map((n) => n.label).sort(),
    edits: (g.user_edits ?? []).length,
    edges: edges.map((e) => `${e.id}:${e.edge_type}`),
  });
};

const before = await snapshot();
console.log("DB snapshot taken.\n");

// 1. public read must still work
const page = await fetch(`${BASE}/g/${GENEALOGY}`);
const html = await page.text();
console.log(`1. anonymous READ /g/${GENEALOGY}          -> HTTP ${page.status}`);
console.log(`   map renders:                ${/evolved/.test(html) ? "YES (public read works)" : "NO  <-- FAIL"}`);
console.log(`   edit controls leaked:       ${html.includes("edit this meaning") ? "YES <-- LEAK" : "no"}`);

// 2. harvest action ids the way an attacker would: from public build output
const ids = new Set();
const mPath = new URL("../.next/server/server-reference-manifest.json", import.meta.url);
if (existsSync(mPath)) {
  const m = JSON.parse(readFileSync(mPath, "utf8"));
  Object.keys(m.node ?? {}).forEach((id) => ids.add(id));
  Object.keys(m.edge ?? {}).forEach((id) => ids.add(id));
}
[...html.matchAll(/\b([a-f0-9]{40,})\b/g)].forEach((m) => ids.add(m[1]));
console.log(`\n2. action ids harvested:       ${ids.size} (from build manifest + page)`);

// 3. fire destructive payloads at every one, unauthenticated
const payloads = [
  { genealogyId: GENEALOGY, nodeId: "n1", label: "PWNED BY ANONYMOUS" }, // rename
  { genealogyId: GENEALOGY, nodeId: "n1", intoId: "n2" },                // merge
  { genealogyId: GENEALOGY, nodeId: "n1" },                              // delete node
  { genealogyId: GENEALOGY, edgeId: "2", edgeType: "contests" },         // reclassify
  { genealogyId: GENEALOGY, edgeId: "2" },                               // delete edge
];

const codes = {};
for (const id of ids) {
  for (const p of payloads) {
    const body = new FormData();
    for (const [k, v] of Object.entries(p)) body.set(k, String(v));
    try {
      const res = await fetch(`${BASE}/g/${GENEALOGY}`, {
        method: "POST", headers: { "Next-Action": id }, body,
      });
      codes[res.status] = (codes[res.status] ?? 0) + 1;
    } catch {
      codes.network = (codes.network ?? 0) + 1;
    }
  }
}
console.log(`   ${ids.size * payloads.length} unauthenticated mutation attempts sent`);
console.log(`   response codes:             ${JSON.stringify(codes)}`);

// 4. the only question that matters
const after = await snapshot();
const moved = before !== after;
console.log(`\n3. database changed:           ${moved ? "YES  <-- FAIL" : "NO"}`);
console.log(`   'PWNED' written:            ${after.includes("PWNED") ? "YES <-- FAIL" : "NO"}`);
console.log(`\n${!moved ? "PASS — strangers can read, but no mutation got through." : "FAIL — the lock did not hold."}`);
process.exit(moved ? 1 : 0);

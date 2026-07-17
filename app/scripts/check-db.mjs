/**
 * Verifies the app can reach Neon over the pooled endpoint and that its queries
 * return real rows. Run from app/:  node scripts/check-db.mjs
 * Next loads .env.local automatically; a bare node script does not, so read it here.
 */
import { readFileSync } from "node:fs";
import { neon } from "@neondatabase/serverless";

const env = readFileSync(new URL("../.env.local", import.meta.url), "utf8");
const url = env.match(/^DATABASE_URL=(.+)$/m)?.[1]?.trim();
if (!url) throw new Error("No DATABASE_URL in app/.env.local");

console.log("host:", new URL(url.replace(/^postgres(ql)?:/, "http:")).host);
console.log("pooled endpoint:", url.includes("-pooler."));

const sql = neon(url);

const gens = await sql`
  SELECT g.id, g.concept, g.status,
         jsonb_array_length(g.nodes) AS node_count,
         (SELECT count(*) FROM edges e WHERE e.genealogy_id = g.id) AS edge_count
  FROM genealogies g ORDER BY g.updated_at DESC`;
console.log(`\ngenealogies: ${gens.length}`);
for (const g of gens) {
  console.log(`  [${g.id}] ${g.concept}  ${g.node_count} states, ${g.edge_count} edges (${g.status})`);
}

if (gens.length) {
  const edges = await sql`
    SELECT e.edge_type, e.verified, sp.arxiv_id AS src, tp.arxiv_id AS tgt
    FROM edges e
    JOIN papers sp ON sp.id = e.source_paper_id
    JOIN papers tp ON tp.id = e.target_paper_id
    WHERE e.genealogy_id = ${gens[0].id} ORDER BY e.id`;
  console.log(`\nedges of [${gens[0].id}] (the join the page uses):`);
  for (const e of edges) {
    console.log(`  ${e.edge_type.padEnd(9)} ${e.src} -> ${e.tgt}  ${e.verified ? "verified" : "inferred"}`);
  }
}
console.log("\nOK — the app's queries work against the live database.");

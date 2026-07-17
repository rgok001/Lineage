/**
 * Checks app/.env.local has what auth needs, without printing any secret.
 * Run from app/:  node scripts/check-auth-env.mjs
 */
import { existsSync, readFileSync } from "node:fs";

const path = new URL("../.env.local", import.meta.url);
if (!existsSync(path)) {
  console.error("MISSING app/.env.local");
  process.exit(1);
}
const text = readFileSync(path, "utf8");

const need = [
  ["DATABASE_URL", "database (pooled endpoint)"],
  ["AUTH_SECRET", "signs the session cookie"],
  ["AUTH_GITHUB_ID", "GitHub OAuth client id"],
  ["AUTH_GITHUB_SECRET", "GitHub OAuth client secret"],
  ["OWNER_GITHUB_LOGIN", "who may edit — unset means NOBODY can"],
];

let bad = 0;
for (const [key, why] of need) {
  const m = text.match(new RegExp(`^${key}=(.*)$`, "m"));
  const commented = new RegExp(`^\\s*#\\s*${key}=`, "m").test(text);
  const val = m?.[1]?.trim() ?? "";

  if (!m || !val) {
    console.log(`  MISSING  ${key.padEnd(19)} ${commented ? "(present but COMMENTED OUT — remove the #)" : `— ${why}`}`);
    bad++;
  } else if (/^["'].*["']$/.test(val)) {
    console.log(`  QUOTED   ${key.padEnd(19)} remove the surrounding quotes`);
    bad++;
  } else {
    // never print values; describe them
    const shape =
      key === "OWNER_GITHUB_LOGIN" ? val                       // not a secret
      : key === "DATABASE_URL" ? (val.includes("-pooler.") ? "pooled ✓" : "NOT pooled ✗")
      : `set (${val.length} chars)`;
    console.log(`  OK       ${key.padEnd(19)} ${shape}`);
  }
}

console.log(bad ? `\n${bad} problem(s) — auth will not work yet.` : "\nAll auth env vars present.");
process.exit(bad ? 1 : 0);

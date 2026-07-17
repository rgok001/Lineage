/**
 * Adds AUTH_SECRET to app/.env.local if absent. This signs the session cookie —
 * without it, anyone could forge a cookie claiming to be the owner. It is
 * generated locally (not a third-party credential), so it is safe to create here.
 * Run from app/:  node scripts/gen-auth-secret.mjs
 */
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const path = new URL("../.env.local", import.meta.url);
const text = existsSync(path) ? readFileSync(path, "utf8") : "";

if (/^AUTH_SECRET=.+$/m.test(text)) {
  console.log("AUTH_SECRET already present — leaving it alone.");
} else {
  const secret = randomBytes(32).toString("base64");
  writeFileSync(path, text.replace(/\s*$/, "\n") + `AUTH_SECRET=${secret}\n`);
  console.log("AUTH_SECRET generated and written to app/.env.local (value not printed).");
}

import { neon } from "@neondatabase/serverless";

if (!process.env.DATABASE_URL) {
  throw new Error(
    "DATABASE_URL is not set. Create app/.env.local with the POOLED Neon " +
      "connection string (the host containing -pooler). The pipeline uses the " +
      "direct endpoint; serverless needs the pooled one.",
  );
}

/** HTTP driver: each query is a fetch, which is what serverless wants — no
 *  connection to hold open between invocations. */
export const sql = neon(process.env.DATABASE_URL);

import { signIn, signOut } from "../auth";
import { getViewer, isOwner } from "../lib/authz";

/**
 * Shows who you are and lets you sign in/out. Purely informational: the edit
 * controls it gates are cosmetic — the actual authorisation happens inside every
 * Server Action (lib/authz.ts requireOwner), which is the only thing a caller
 * with curl cannot bypass.
 */
export default async function SignInButton() {
  const viewer = await getViewer();
  const owner = isOwner(viewer);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: ".7rem", fontSize: ".78rem" }}>
      {viewer ? (
        <>
          <span style={{ color: "var(--ink-soft)" }}>
            {viewer.login}
            {owner ? (
              <span style={{ marginLeft: ".4rem", color: "var(--verified)", fontFamily: "var(--font-mono)", fontSize: ".68rem" }}>
                owner — can edit
              </span>
            ) : (
              <span style={{ marginLeft: ".4rem", color: "var(--ink-soft)", fontFamily: "var(--font-mono)", fontSize: ".68rem" }}>
                read-only
              </span>
            )}
          </span>
          <form action={async () => { "use server"; await signOut({ redirectTo: "/" }); }}>
            <button type="submit" style={btn}>Sign out</button>
          </form>
        </>
      ) : (
        <form action={async () => { "use server"; await signIn("github", { redirectTo: "/" }); }}>
          <button type="submit" style={btn}>Sign in with GitHub</button>
        </form>
      )}
    </div>
  );
}

const btn: React.CSSProperties = {
  font: "inherit", fontSize: ".76rem", padding: ".3rem .65rem", cursor: "pointer",
  border: "1px solid var(--ink-soft)", borderRadius: 4,
  background: "var(--card)", color: "var(--ink)",
};

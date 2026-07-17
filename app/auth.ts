import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";

/**
 * GitHub answers "who are you?" (authentication). It does NOT answer "what may
 * you do?" — GitHub will happily vouch for any of its users. Authorisation is
 * ours: see lib/authz.ts, which checks the login against OWNER_GITHUB_LOGIN.
 *
 * Reads AUTH_GITHUB_ID / AUTH_GITHUB_SECRET / AUTH_SECRET from the environment.
 */
export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [GitHub],
  callbacks: {
    // The default session carries name/email/image but not the GitHub login,
    // which is the stable handle we authorise against. Carry it through the JWT.
    async jwt({ token, profile }) {
      if (profile?.login) token.login = profile.login as string;
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as { login?: string }).login = token.login as string | undefined;
      }
      return session;
    },
  },
});

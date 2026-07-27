import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import Nav from "./nav";
import SignInButton from "./signin-button";

export const metadata: Metadata = {
  title: "Lineage",
  description: "Read how an academic concept evolved through its papers, with a verified quote behind every claim.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header style={{ padding: "1.1rem 1.5rem 0" }}>
          <div style={{ maxWidth: 1400, margin: "0 auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
              gap: "1rem", marginBottom: ".7rem" }}>
              <Link href="/" style={{ textDecoration: "none", fontFamily: "var(--font-display)",
                fontWeight: 600, fontSize: "1.15rem", color: "var(--ink)", letterSpacing: "-.01em" }}>
                Lineage
              </Link>
              <SignInButton />
            </div>
            <Nav />
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}

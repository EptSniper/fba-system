import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Honest Deal Guides",
  description:
    "Practical, honest guides for smarter online shopping: reading price history, real fee changes, cashback stacking, seasonal timing, and spotting fake deals.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="wrap">
            <Link href="/" className="brand">
              Honest Deal Guides
            </Link>
            <span className="tagline">Real math, no hype</span>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Instrument_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { MobileNav } from "@/components/mobile-nav";
import { StatusBar } from "@/components/status-bar";

// Design system (operator-console prototype, 2026-07-02): Instrument Sans body + IBM Plex Mono figures.
const sans = Instrument_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "FBA Center",
  description: "Command center for the Amazon online-arbitrage business — one source of truth.",
};

// Runs before hydration so a saved theme/accent (Settings page, localStorage) applies without
// a flash of the default dark/orange values. Reads localStorage directly — no framework needed
// for two attribute writes on <html>.
const NO_FLASH_THEME_SCRIPT = `(function(){try{
  var t=localStorage.getItem("fba-theme");
  var a=localStorage.getItem("fba-accent");
  if(t==="light")document.documentElement.setAttribute("data-theme",t);
  if(a&&a!=="orange")document.documentElement.setAttribute("data-accent",a);
}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body>
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <div className="bg-grid" aria-hidden />
        <div className="relative flex min-h-screen">
          <aside className="sticky top-0 hidden h-screen w-[210px] shrink-0 overflow-y-auto border-r border-line bg-side md:block">
            <Sidebar />
          </aside>
          <div className="min-w-0 flex-1">
            <MobileNav />
            <StatusBar />
            <main id="main-content" className="px-3 py-3.5 sm:px-4 md:px-5">
              <div className="mx-auto max-w-[1600px]">{children}</div>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}

"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

const THEME_KEY = "fba-theme";
const ACCENT_KEY = "fba-accent";

const ACCENTS: { id: string; value: string; name: string }[] = [
  { id: "orange", value: "#ff4d00", name: "Safety orange" },
  { id: "green", value: "#4ade80", name: "Signal green" },
  { id: "sky", value: "#7db8e8", name: "Sky" },
  { id: "amber", value: "#e8a200", name: "Amber" },
];

// Real, working theme + accent switch — persisted to localStorage, applied as data-attributes
// on <html> (see globals.css's [data-theme="light"]/[data-accent="..."] overrides and
// layout.tsx's inline no-flash script, which sets these same attributes before hydration).
export function ThemeControls() {
  const [theme, setTheme] = React.useState<"dark" | "light">("dark");
  const [accent, setAccent] = React.useState("orange");

  React.useEffect(() => {
    setTheme((localStorage.getItem(THEME_KEY) as "dark" | "light") || "dark");
    setAccent(localStorage.getItem(ACCENT_KEY) || "orange");
  }, []);

  const applyTheme = (t: "dark" | "light") => {
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem(THEME_KEY, t);
    setTheme(t);
  };

  const applyAccent = (id: string) => {
    document.documentElement.setAttribute("data-accent", id);
    localStorage.setItem(ACCENT_KEY, id);
    setAccent(id);
  };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="mb-2 text-[11px] text-muted">Theme</div>
        <div className="flex gap-1.5">
          {(["dark", "light"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => applyTheme(t)}
              className={cn(
                "flex-1 cursor-pointer border px-3 py-2 text-[11px] font-bold uppercase tracking-[0.06em] transition-colors",
                theme === t ? "border-accent bg-accent text-white" : "border-line text-muted hover:border-line2 hover:text-ink",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-2 text-[11px] text-muted">Accent</div>
        <div className="flex gap-2">
          {ACCENTS.map((a) => (
            <button
              key={a.id}
              type="button"
              title={a.name}
              aria-label={a.name}
              onClick={() => applyAccent(a.id)}
              className={cn(
                "h-8 w-8 cursor-pointer border-2 transition-transform hover:scale-105",
                accent === a.id ? "border-ink" : "border-transparent",
              )}
              style={{ background: a.value }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

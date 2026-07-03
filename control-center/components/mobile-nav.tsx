"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { NAV } from "@/lib/nav";

export function MobileNav() {
  const path = usePathname();
  return (
    <div className="sticky top-0 z-40 border-b border-line bg-side md:hidden">
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="grid h-6 w-6 place-items-center rounded bg-accent text-[10px] font-bold text-slate-950">FBA</span>
        <span className="text-[13px] font-semibold tracking-tight">FBA Center</span>
      </div>
      <nav className="no-scrollbar flex gap-1 overflow-x-auto px-2 pb-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded border px-2.5 py-1 text-[12px] transition-colors",
                active ? "border-line2 bg-panel2 text-ink" : "border-transparent text-muted hover:text-ink",
              )}
            >
              <Icon size={14} className={active ? "text-accent" : ""} aria-hidden />
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

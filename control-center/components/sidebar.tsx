"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/cn";
import { NAV, NAV_GROUPS } from "@/lib/nav";

export function Sidebar() {
  const path = usePathname();

  return (
    <nav aria-label="Primary" className="flex h-full flex-col gap-3 p-2.5">
      <div className="flex items-center gap-2 px-1.5 py-1">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-[11px] font-bold text-slate-950">FBA</span>
        <span className="text-[13px] font-semibold tracking-tight text-ink">FBA Center</span>
      </div>

      <div className="rule-grad" />

      {NAV_GROUPS.map((group) => (
        <div key={group} className="flex flex-col gap-0.5">
          <div className="px-2 pb-0.5 pt-1 text-[9px] font-semibold uppercase tracking-[0.16em] text-faint">{group}</div>
          {NAV.filter((n) => n.group === group).map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] transition-colors",
                  active ? "bg-panel2 text-ink" : "text-muted hover:bg-panel2/60 hover:text-ink",
                )}
              >
                {active && <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent" aria-hidden />}
                <Icon size={15} className={cn("shrink-0", active ? "text-accent" : "text-faint")} aria-hidden />
                <span className="truncate">{label}</span>
              </Link>
            );
          })}
        </div>
      ))}

      <div className="mt-auto flex items-center gap-1.5 rounded-md border border-line px-2 py-1.5 text-[10px] text-faint">
        <ShieldCheck size={12} className="shrink-0 text-warn" aria-hidden />
        Human approval before every buy.
      </div>
    </nav>
  );
}

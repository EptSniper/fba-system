import * as React from "react";
import Link from "next/link";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/cn";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("surface p-3", className)} {...props} />;
}

export function ActionLink({
  href,
  children,
  external = false,
  tone = "secondary",
}: {
  href: string;
  children: React.ReactNode;
  external?: boolean;
  tone?: "primary" | "secondary";
}) {
  const className = cn(
    "inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md px-2.5 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
    tone === "primary"
      ? "bg-accent text-slate-950 hover:brightness-110"
      : "border border-line2 bg-panel2/50 text-muted hover:border-line2 hover:bg-panel2 hover:text-ink",
  );
  if (external) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
        {children}<ArrowUpRight size={13} aria-hidden />
      </a>
    );
  }
  return (
    <Link href={href} className={className}>
      {children}<ArrowRight size={13} aria-hidden />
    </Link>
  );
}

export function Panel({
  title,
  icon,
  right,
  children,
  className,
}: {
  title: string;
  icon?: React.ReactNode;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("surface overflow-hidden", className)}>
      <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-faint">
          {icon ? <span className="text-faint">{icon}</span> : null}
          {title}
        </div>
        {right ? <div className="num text-[11px] text-faint">{right}</div> : null}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

// Outlined tag style — border does the work, no filled background (operator-console prototype).
const badgeTone: Record<string, string> = {
  success: "border-profit/40 text-profit",
  loss: "border-loss/40 text-loss",
  warn: "border-warn/40 text-warn",
  info: "border-info/40 text-info",
  accent: "border-accent/40 text-accent",
  muted: "border-line2 text-muted",
};

export function Badge({
  tone = "muted",
  children,
}: {
  tone?: keyof typeof badgeTone | string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em]",
        badgeTone[tone] ?? badgeTone.muted,
      )}
    >
      {children}
    </span>
  );
}

export function Pill({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-line bg-panel2/60 px-2 py-1 text-[11px] text-muted">
      {label} <span className="num font-medium text-ink">{value}</span>
    </span>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
}: {
  icon?: React.ReactNode;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex min-h-24 flex-col items-center justify-center gap-1 rounded border border-dashed border-line2 px-4 py-6 text-center">
      {icon ? <div className="mb-0.5 text-faint">{icon}</div> : null}
      <p className="text-[13px] font-medium text-ink">{title}</p>
      {hint ? <p className="max-w-sm text-[11px] leading-relaxed text-muted">{hint}</p> : null}
    </div>
  );
}

export function DataNote({ source, updated }: { source: string; updated: string }) {
  return (
    <span className="num text-[11px] text-faint">
      {source} · {updated}
    </span>
  );
}

export function ConnBadge({ connected }: { connected: boolean }) {
  // "connected" in the data files means "real data exists" (which may be a manual capture, not
  // a live API sync) — say "connected", never "live", so this never overclaims an automatic feed.
  return connected ? <Badge tone="success">connected</Badge> : <Badge tone="warn">not connected</Badge>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  meta,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  meta?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-line pb-2.5">
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
        <h1 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h1>
        {eyebrow ? <span className="num text-[10px] uppercase tracking-[0.18em] text-faint">{eyebrow}</span> : null}
        {description ? <span className="hidden text-xs text-muted md:inline">· {description}</span> : null}
      </div>
      {meta ? <div className="shrink-0">{meta}</div> : null}
    </header>
  );
}

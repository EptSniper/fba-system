"use client";

// Static UI primitives. This is a personal, dense operator tool — motion was causing lag and
// a "marketing site" feel, so these render instantly with no framer-motion runtime. The exports
// are kept (Reveal/Counter/Pressable/HoverLift/PageTransition/Stagger/StaggerItem/Skeleton) so
// pages don't need to change; they're now plain passthroughs. CSS handles subtle hover only.
import * as React from "react";
import { money, num, pct, bsr } from "@/lib/format";

const FMT = { money, num, pct, bsr } as const;

export function Reveal({ children, className }: { children: React.ReactNode; delay?: number; y?: number; className?: string }) {
  return <div className={className}>{children}</div>;
}

// Figure, formatted once. No count-up — instant and honest.
export function Counter({
  value,
  kind = "num",
  className,
}: {
  value: number | null | undefined;
  kind?: keyof typeof FMT;
  className?: string;
}) {
  const fmt = FMT[kind] as (n: number | null | undefined) => string;
  return <span className={className}>{value == null ? "—" : fmt(value)}</span>;
}

export function Pressable({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={className}>{children}</div>;
}

export function HoverLift({ children, className }: { children: React.ReactNode; className?: string; y?: number }) {
  return <div className={className}>{children}</div>;
}

export function PageTransition({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function Stagger({ children, className }: { children: React.ReactNode; className?: string; gap?: number }) {
  return <div className={className}>{children}</div>;
}

export function StaggerItem({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={className}>{children}</div>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={`rounded bg-panel2 ${className ?? ""}`} aria-hidden />;
}

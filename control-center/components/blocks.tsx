import * as React from "react";
import { FileText, Image as ImageIcon, Youtube, Settings2, Target } from "lucide-react";
import { Badge, EmptyState } from "./ui";
import { cn } from "@/lib/cn";
import { bsr, money, num, pct } from "@/lib/format";
import type { Pick } from "@/lib/types";

const toneText: Record<string, string> = {
  profit: "text-profit",
  loss: "text-loss",
  ink: "text-ink",
  accent: "text-accent",
};

// Static readout — NOT interactive (no hover/dot), per the honest-status design rule.
export function KpiCard({
  label,
  value,
  delta,
  tone = "ink",
}: {
  label: string;
  value: React.ReactNode;
  delta?: string;
  tone?: keyof typeof toneText;
}) {
  return (
    <div className="surface px-2.5 py-2">
      <div className="text-[9px] font-bold uppercase tracking-[0.12em] text-faint">{label}</div>
      <div className={cn("num mt-1 text-[17px] font-semibold leading-none tracking-tight", toneText[tone])}>{value}</div>
      {delta ? <div className="num mt-1 text-[10px] text-faint">{delta}</div> : null}
    </div>
  );
}

export function PickCard({ pick }: { pick: Pick }) {
  const verdict = (pick.verdict ?? "review").toLowerCase();
  const tone = verdict === "buy" ? "success" : verdict === "reject" ? "loss" : "warn";
  return (
    <div className="surface p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="truncate text-[13px] font-medium text-ink">{pick.title ?? pick.asin}</span>
        <Badge tone={tone}>{verdict}</Badge>
      </div>
      <div className="num mb-1.5 text-[11px] text-faint">{pick.asin}</div>
      <div className="num flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
        <span><span className="text-muted">bsr</span> {bsr(pick.salesRank)}</span>
        <span><span className="text-muted">sales</span> {num(pick.estSales)}/mo</span>
        <span><span className="text-muted">offers</span> {num(pick.offers)}</span>
        <span className="text-profit">roi {pct(pick.roi)}</span>
        <span className="text-profit">{money(pick.profit)}/u</span>
      </div>
      {pick.reason ? <p className="mt-1.5 text-[12px] leading-snug text-muted">{pick.reason}</p> : null}
    </div>
  );
}

const ingestIcon: Record<string, React.ReactNode> = {
  transcript: <Youtube size={13} />,
  transcripts: <Youtube size={13} />,
  screenshot: <ImageIcon size={13} />,
  document: <FileText size={13} />,
  criteria: <Settings2 size={13} />,
  item: <Target size={13} />,
};

export function IngestionFeed({
  items,
}: {
  items: { date: string; type: string; item: string; effect: string }[];
}) {
  if (!items.length) {
    return <EmptyState title="Nothing ingested yet" />;
  }
  return (
    <ul className="flex flex-col divide-y divide-line text-[12px]">
      {items
        .slice()
        .reverse()
        .map((e, i) => (
          <li key={i} className="flex gap-2.5 py-2">
            <span className="mt-0.5 text-faint">{ingestIcon[e.type] ?? <FileText size={13} />}</span>
            <span className="min-w-0 flex-1">
              <span className="text-ink">{e.item}</span>
              <span className="block text-muted">{e.effect}</span>
            </span>
            <span className="num shrink-0 text-[11px] text-faint">{e.date.slice(5)}</span>
          </li>
        ))}
    </ul>
  );
}

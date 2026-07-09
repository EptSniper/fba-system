"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/ui";
import { num, pct } from "@/lib/format";
import type { BacktestGrowthPoint, RankerHistoryPoint, RunHistoryPoint } from "@/lib/intelligence-server";

// Charts for the /intelligence page's "Training & collection" section (Session 57, 2026-07-09):
// backtest_rows growth, per-run token/tier breakdown, ranker champion/challenger accuracy, and
// two lightweight composition bars. Same recharts + CSS-custom-property convention as
// components/profit-chart.tsx — colors follow the app's existing dark/light theme automatically,
// no separate chart palette to keep in sync.

const tooltipStyle = {
  background: "var(--panel)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  fontSize: 12,
  color: "var(--text)",
} as const;

const axisTick = { fontSize: 10, fill: "var(--text-faint)" } as const;
const legendStyle = { fontSize: 11, color: "var(--text-muted)" } as const;

function formatDay(iso: string): string {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function formatHour(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", timeZone: "UTC" });
}

export function BacktestGrowthChart({ data }: { data: BacktestGrowthPoint[] }) {
  if (!data.length) {
    return (
      <EmptyState
        title="No backtest rows collected yet"
        hint="Fills in once the hourly collector (keepa-collect.yml) writes its first rows."
      />
    );
  }
  return (
    <div style={{ width: "100%", height: 170 }} role="img" aria-label="Backtest rows collected, cumulative, by day">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="btg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.25} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDay}
            tick={axisTick}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <YAxis tick={axisTick} axisLine={false} tickLine={false} width={36} allowDecimals={false} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(v: string) => formatDay(v)}
            formatter={(v: number, name: string) => [num(v), name === "cumulative" ? "total rows" : name]}
          />
          <Area type="monotone" dataKey="cumulative" name="cumulative" stroke="var(--accent)" strokeWidth={2} fill="url(#btg)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RunTokensChart({
  data,
  tierBreakdownAvailableSince,
}: {
  data: RunHistoryPoint[];
  tierBreakdownAvailableSince: string | null;
}) {
  if (!data.length) {
    return (
      <EmptyState
        title="No hourly collector runs recorded yet"
        hint="Fills in once keepa-collect.yml's hourly cron fires (github-actions-hourly)."
      />
    );
  }
  const chartData = data.map((r) => ({
    label: formatHour(r.startedAt),
    tier1: r.tier1Tokens ?? 0,
    tier2: r.tier2Tokens ?? 0,
    tier3: r.tier3Tokens ?? 0,
    legacy: r.tier1Tokens === null ? r.tokensConsumed ?? 0 : 0,
  }));
  return (
    <>
      <div style={{ width: "100%", height: 190 }} role="img" aria-label="Tokens spent per collector run, by tier">
        <ResponsiveContainer>
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={axisTick}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={30} allowDecimals={false} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={legendStyle} />
            <Bar dataKey="legacy" name="total (pre-breakdown)" stackId="t" fill="var(--text-faint)" radius={[2, 2, 0, 0]} />
            <Bar dataKey="tier1" name="tier 1 · shadow" stackId="t" fill="var(--info)" />
            <Bar dataKey="tier2" name="tier 2 · scan" stackId="t" fill="var(--accent)" />
            <Bar dataKey="tier3" name="tier 3 · backtest" stackId="t" fill="var(--profit)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {!tierBreakdownAvailableSince ? (
        <p className="mt-1.5 text-[11px] text-faint">
          Per-tier split starts with the next collector run (migration 013, 2026-07-09) — every run so far
          shows as one undivided bar.
        </p>
      ) : null}
    </>
  );
}

export function RankerAccuracyChart({ data }: { data: RankerHistoryPoint[] }) {
  const trained = data.filter((d) => !d.refused && d.championAuc !== null);
  if (!trained.length) {
    return (
      <EmptyState
        title="No training runs recorded yet"
        hint="Populates starting with the next hourly training cycle (train-ranker.yml) — champion vs.
challenger AUC will show here as a trend (migration 013, 2026-07-09)."
      />
    );
  }
  const chartData = trained.map((d) => ({
    label: formatHour(d.trainedAt),
    champion: d.championAuc,
    challenger: d.challengerAuc,
  }));
  return (
    <div style={{ width: "100%", height: 170 }} role="img" aria-label="Champion vs challenger AUC over time">
      <ResponsiveContainer>
        <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="label" tick={axisTick} axisLine={{ stroke: "var(--border)" }} tickLine={false} />
          <YAxis
            domain={[0, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            tick={axisTick}
            axisLine={false}
            tickLine={false}
            width={34}
          />
          <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => `${Math.round(v * 100)}%`} />
          <Legend wrapperStyle={legendStyle} />
          <Line type="monotone" dataKey="champion" name="champion (triage formula)" stroke="var(--info)" strokeWidth={2} dot={{ r: 3 }} />
          <Line type="monotone" dataKey="challenger" name="challenger (model)" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CompositionBar({
  segments,
  emptyHint,
}: {
  segments: { label: string; value: number; color: string }[];
  emptyHint?: string;
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) {
    return <EmptyState title="No data yet" hint={emptyHint} />;
  }
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded-sm">
        {segments
          .filter((s) => s.value > 0)
          .map((s) => (
            <div
              key={s.label}
              style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
              title={`${s.label}: ${num(s.value)} (${pct(s.value / total)})`}
            />
          ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {segments.map((s) => (
          <span key={s.label} className="flex items-center gap-1.5 text-[11px] text-muted">
            <span className="inline-block h-2 w-2 shrink-0 rounded-sm" style={{ background: s.color }} aria-hidden />
            {s.label}
            <span className="num text-ink">{num(s.value)}</span>
            <span className="text-faint">({pct(total ? s.value / total : 0)})</span>
          </span>
        ))}
      </div>
    </div>
  );
}

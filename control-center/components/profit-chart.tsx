"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function ProfitChart({ data }: { data: { date: string; profit: number }[] }) {
  if (!data.length) {
    return (
      <div className="flex h-[120px] items-center justify-center text-sm text-faint">
        No profit yet — this fills in once you make sales.
      </div>
    );
  }
  return (
    <div style={{ width: "100%", height: 120 }} role="img" aria-label="Profit over time">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="p" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--profit)" stopOpacity={0.22} />
              <stop offset="100%" stopColor="var(--profit)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" hide />
          <YAxis hide />
          <Tooltip
            contentStyle={{
              background: "var(--panel)",
              border: "1px solid var(--border-strong)",
              borderRadius: 8,
              fontSize: 12,
              color: "var(--text)",
              boxShadow: "0 8px 24px rgba(15,23,42,0.10)",
            }}
            formatter={(v: number) => [`$${Math.round(v)}`, "profit"]}
          />
          <Area type="monotone" dataKey="profit" stroke="var(--profit)" strokeWidth={2} fill="url(#p)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

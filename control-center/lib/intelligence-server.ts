// lib/intelligence-server.ts — SERVER-ONLY. The /intelligence page's training + collection
// chart data (backtest_rows growth + sample-source composition, recent collector runs' per-tier
// token/row breakdown, ranker champion/challenger AUC history), shared by app/intelligence/
// page.tsx (initial server-rendered load) and app/api/ops/intelligence/route.ts (same data as
// JSON) — a single source so the two can never drift apart, same pattern as lib/queue-server.ts.
import {
  getBacktestRowsForChart,
  getCollectorRuns,
  getRankerRuns,
  supabaseConfigured,
} from "./supabase-server";

const SOURCES = ["dealfeed", "explore", "onpolicy"] as const;
type Source = (typeof SOURCES)[number];
type SourceBucket = Record<Source | "unknown", number>;

export type BacktestGrowthPoint = { date: string; new: number; cumulative: number } & SourceBucket;

export type RunHistoryPoint = {
  startedAt: string;
  status: string;
  host: string | null;
  tokensConsumed: number | null;
  tier1Tokens: number | null;
  tier2Tokens: number | null;
  tier3Tokens: number | null;
  tokensLeftEnd: number | null;
  backtestRowsWritten: number | null;
  backtestAsinsSampled: number | null;
};

export type RankerHistoryPoint = {
  trainedAt: string;
  refused: boolean;
  refusalReason: string | null;
  rowCount: number | null;
  championAuc: number | null;
  challengerAuc: number | null;
  verdict: string | null;
  trainRows: number | null;
  valRows: number | null;
};

export type IntelligenceData = {
  connected: true;
  totalBacktestRows: number;
  backtestGrowth: BacktestGrowthPoint[];
  labelComposition: { profitable: number; notProfitable: number; unknown: number };
  sampleComposition: SourceBucket;
  sampleSourceAvailableSince: string | null;
  runHistory: RunHistoryPoint[];
  tierBreakdownAvailableSince: string | null;
  rankerHistory: RankerHistoryPoint[];
};

function dayKey(iso: string): string {
  return iso.slice(0, 10); // YYYY-MM-DD, UTC (created_at is timestamptz, ISO-formatted)
}

export async function buildIntelligenceData(): Promise<{ connected: false; error?: string } | IntelligenceData> {
  if (!supabaseConfigured()) return { connected: false };

  const [rows, runs, rankerRuns] = await Promise.all([
    getBacktestRowsForChart(),
    getCollectorRuns(60),
    getRankerRuns(60),
  ]);
  if (rows === null || runs === null || rankerRuns === null) {
    return { connected: false, error: "Could not reach Supabase." };
  }

  // Bucket backtest_rows by UTC day, tracking a running cumulative total plus that day's
  // sample-source composition. `rows` is already ordered oldest-first (see the query's own
  // order=created_at.asc), so a single forward pass computes the cumulative curve correctly.
  const byDay = new Map<string, { new: number; bySource: SourceBucket }>();
  for (const row of rows) {
    const key = dayKey(row.created_at);
    const bucket = byDay.get(key) ?? { new: 0, bySource: { dealfeed: 0, explore: 0, onpolicy: 0, unknown: 0 } };
    bucket.new += 1;
    const src = (row.sample_source ?? "unknown") as Source | "unknown";
    bucket.bySource[src in bucket.bySource ? src : "unknown"] += 1;
    byDay.set(key, bucket);
  }
  let cumulative = 0;
  const backtestGrowth: BacktestGrowthPoint[] = [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, bucket]) => {
      cumulative += bucket.new;
      return { date, new: bucket.new, cumulative, ...bucket.bySource };
    });

  const labelComposition = rows.reduce(
    (acc, row) => {
      if (row.would_have_profited === true) acc.profitable += 1;
      else if (row.would_have_profited === false) acc.notProfitable += 1;
      else acc.unknown += 1;
      return acc;
    },
    { profitable: 0, notProfitable: 0, unknown: 0 },
  );

  const sampleComposition = rows.reduce(
    (acc, row) => {
      const src = (row.sample_source ?? "unknown") as Source | "unknown";
      acc[src in acc ? src : "unknown"] += 1;
      return acc;
    },
    { dealfeed: 0, explore: 0, onpolicy: 0, unknown: 0 } as SourceBucket,
  );

  // Chronological (oldest first) for the token/rows-per-run chart — getCollectorRuns() itself
  // returns newest-first (for the runs-health panel's "last run" use), so reverse here rather
  // than adding a second query variant for one caller.
  const runHistory: RunHistoryPoint[] = [...runs].reverse().map((r) => ({
    startedAt: r.started_at,
    status: r.status,
    host: r.host,
    tokensConsumed: r.tokens_consumed,
    tier1Tokens: r.tier1_tokens,
    tier2Tokens: r.tier2_tokens,
    tier3Tokens: r.tier3_tokens,
    tokensLeftEnd: r.tokens_left_end,
    backtestRowsWritten: r.backtest_rows_written,
    backtestAsinsSampled: r.backtest_asins_sampled,
  }));
  // Tier columns are only ever non-null on a run recorded AFTER migration 013 landed — an honest
  // signal for the UI to show "tier breakdown starts with the next run" instead of a chart that
  // looks broken (all-zero) for the pre-migration history.
  const tierBreakdownAvailableSince = runHistory.find((r) => r.tier1Tokens !== null)?.startedAt ?? null;

  const rankerHistory: RankerHistoryPoint[] = [...rankerRuns].reverse().map((r) => ({
    trainedAt: r.trained_at,
    refused: r.refused,
    refusalReason: r.refusal_reason,
    rowCount: r.row_count,
    championAuc: r.champion_auc,
    challengerAuc: r.challenger_auc,
    verdict: r.verdict,
    trainRows: r.train_rows,
    valRows: r.val_rows,
  }));

  // sample_source is only ever non-null on a row written AFTER migration 011 landed — same
  // honesty concern as tierBreakdownAvailableSince above (every existing row predates it).
  const sampleSourceAvailableSince = rows.find((r) => r.sample_source !== null)?.created_at ?? null;

  return {
    connected: true,
    totalBacktestRows: rows.length,
    backtestGrowth,
    labelComposition,
    sampleComposition,
    sampleSourceAvailableSince,
    runHistory,
    tierBreakdownAvailableSince,
    rankerHistory,
  };
}

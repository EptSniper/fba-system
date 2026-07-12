// lib/intelligence-server.ts — SERVER-ONLY. Aggregates Scout collection/training telemetry for
// both app/intelligence/page.tsx and app/api/ops/intelligence/route.ts. Raw ASIN-level rows and
// the persisted sampler state stay on the server; only compact summaries reach the browser.
import { getBrain } from "./data";
import {
  getBacktestCollectionStateSummary,
  getBacktestRowsForChart,
  getCollectorRuns,
  getRankerRuns,
  type SupabaseRun,
  supabaseConfigured,
} from "./supabase-server";

const SOURCES = ["dealfeed", "explore", "onpolicy"] as const;
type Source = (typeof SOURCES)[number];
type SourceBucket = Record<Source | "unknown", number>;

const DAY_MS = 86_400_000;
const ROLLING_WINDOW_MS = DAY_MS;

export type BacktestGrowthPoint = { date: string; new: number; cumulative: number } & SourceBucket;

export type DailyAsinPoint = {
  date: string;
  newAsins: number;
  rolling7Average: number;
};

export type RunHistoryPoint = {
  startedAt: string;
  finishedAt: string | null;
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

export type DiversityBucket = {
  label: string;
  count: number;
  share: number;
};

export type DiversitySummary = {
  distinctKnown: number;
  knownAsins: number;
  unknownAsins: number;
  buckets: DiversityBucket[];
  top: DiversityBucket | null;
};

export type IntelligenceData = {
  connected: true;
  asOf: string;
  totalBacktestRows: number;
  totalUniqueAsins: number;
  averageRowsPerAsin: number | null;
  newAsinsToday: number;
  newAsinsLast24h: number;
  newAsins7DayAverage: number;
  previous7DayAverage: number;
  sevenDayTrend: number | null;
  dailyAsinTrend: DailyAsinPoint[];
  tier3Efficiency24h: {
    newAsins: number;
    tier3Tokens: number | null;
    asinsPerToken: number | null;
    telemetryComplete: boolean;
    reason: string | null;
  };
  tokenCapture24h: {
    completedRuns: number;
    spentTokens: number | null;
    generatedTokens: number | null;
    refillRatePerMinute: number | null;
    utilization: number | null;
    telemetryComplete: boolean;
    reason: string | null;
  };
  pendingBacklog: {
    available: boolean;
    pendingAsins: number | null;
    byCategory: { label: string; count: number }[];
    unknownCategoryAsins: number | null;
  };
  categoryDiversity: DiversitySummary;
  sourceDiversity: DiversitySummary;
  backtestGrowth: BacktestGrowthPoint[];
  labelComposition: { profitable: number; notProfitable: number; unknown: number };
  sampleComposition: SourceBucket;
  sampleSourceAvailableSince: string | null;
  runHistory: RunHistoryPoint[];
  tierBreakdownAvailableSince: string | null;
  rankerHistory: RankerHistoryPoint[];
};

export type IntelligenceBuildOptions = {
  // Test/alternate-call injection. `undefined` means read the single source in ai-brain.json;
  // explicit null means unavailable. No plan rate is hardcoded in this module.
  refillRatePerMinute?: number | null;
  now?: Date;
};

type AsinProfile = {
  firstSeen: string;
  firstSeenMs: number;
  category: string | null;
  source: string | null;
};

function dayKey(iso: string): string {
  return iso.slice(0, 10); // YYYY-MM-DD, UTC (created_at is timestamptz, ISO-formatted)
}

function utcDayStartMs(date: Date): number {
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function dayKeyFromMs(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

function normalizedDimension(value: string | null): string | null {
  const normalized = value?.trim().toLowerCase();
  return normalized && normalized !== "unknown" ? normalized : null;
}

function diversity(values: Array<string | null>, totalAsins: number): DiversitySummary {
  const counts = new Map<string, number>();
  let unknownAsins = 0;
  for (const value of values) {
    const key = normalizedDimension(value);
    if (!key) {
      unknownAsins += 1;
      continue;
    }
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const buckets = [...counts.entries()]
    .map(([label, count]) => ({ label, count, share: totalAsins ? count / totalAsins : 0 }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  return {
    distinctKnown: buckets.length,
    knownAsins: totalAsins - unknownAsins,
    unknownAsins,
    buckets,
    top: buckets[0] ?? null,
  };
}

function observedRunTokens(run: SupabaseRun): number | null {
  if (typeof run.tokens_consumed === "number" && Number.isFinite(run.tokens_consumed)) {
    return Math.max(0, run.tokens_consumed);
  }
  // Once migration 013 telemetry exists, a null later tier means that tier was skipped (zero),
  // not that the whole run is unknowable. A null tier1 marks a pre-breakdown/unknown run.
  if (run.tier1_tokens === null) return null;
  return [run.tier1_tokens, run.tier2_tokens, run.tier3_tokens]
    .reduce<number>((sum, value) => sum + (typeof value === "number" ? Math.max(0, value) : 0), 0);
}

export async function buildIntelligenceData(
  options: IntelligenceBuildOptions = {},
): Promise<{ connected: false; error?: string } | IntelligenceData> {
  if (!supabaseConfigured()) return { connected: false };

  const [rows, runs, rankerRuns, collectionState] = await Promise.all([
    getBacktestRowsForChart(),
    getCollectorRuns(200),
    getRankerRuns(60),
    getBacktestCollectionStateSummary(),
  ]);
  if (rows === null || runs === null || rankerRuns === null) {
    return { connected: false, error: "Could not reach Supabase." };
  }

  const now = options.now ?? new Date();
  const nowMs = now.getTime();
  const safeNow = Number.isFinite(nowMs) ? now : new Date();
  const safeNowMs = safeNow.getTime();
  const todayStartMs = utcDayStartMs(safeNow);
  const rollingStartMs = safeNowMs - ROLLING_WINDOW_MS;

  // Bucket labeled rows by UTC day for the existing cumulative-row chart.
  const byDay = new Map<string, { new: number; bySource: SourceBucket }>();
  for (const row of rows) {
    const key = dayKey(row.created_at);
    const bucket = byDay.get(key) ?? {
      new: 0,
      bySource: { dealfeed: 0, explore: 0, onpolicy: 0, unknown: 0 },
    };
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

  // One independent sample for this dashboard means one distinct ASIN. Repeated historical
  // windows remain useful labels, but they do not increment the independent-product count.
  const profiles = new Map<string, AsinProfile>();
  for (const row of rows) {
    const asin = row.asin?.trim().toUpperCase();
    if (!asin) continue;
    const firstSeenMs = Date.parse(row.created_at);
    if (!Number.isFinite(firstSeenMs)) continue;
    const existing = profiles.get(asin);
    if (!existing) {
      profiles.set(asin, {
        firstSeen: row.created_at,
        firstSeenMs,
        category: normalizedDimension(row.category),
        source: normalizedDimension(row.sample_source),
      });
      continue;
    }
    if (firstSeenMs < existing.firstSeenMs) {
      existing.firstSeen = row.created_at;
      existing.firstSeenMs = firstSeenMs;
    }
    // Old pre-migration rows can be null while a newer row for the same ASIN carries the real
    // dimension. Fill the missing profile, but never count the ASIN twice.
    if (!existing.category) existing.category = normalizedDimension(row.category);
    if (!existing.source) existing.source = normalizedDimension(row.sample_source);
  }

  const firstSeenByDay = new Map<string, number>();
  let newAsinsToday = 0;
  let newAsinsLast24h = 0;
  for (const profile of profiles.values()) {
    const key = dayKey(profile.firstSeen);
    firstSeenByDay.set(key, (firstSeenByDay.get(key) ?? 0) + 1);
    if (profile.firstSeenMs >= todayStartMs && profile.firstSeenMs <= safeNowMs) newAsinsToday += 1;
    if (profile.firstSeenMs >= rollingStartMs && profile.firstSeenMs <= safeNowMs) newAsinsLast24h += 1;
  }

  // The headline seven-day average uses seven COMPLETE UTC days, excluding today's partial
  // day. Trend compares that window to the seven complete days immediately before it.
  const sumDays = (startMs: number, count: number) => {
    let total = 0;
    for (let i = 0; i < count; i += 1) {
      total += firstSeenByDay.get(dayKeyFromMs(startMs + i * DAY_MS)) ?? 0;
    }
    return total;
  };
  const last7Total = sumDays(todayStartMs - 7 * DAY_MS, 7);
  const previous7Total = sumDays(todayStartMs - 14 * DAY_MS, 7);
  const newAsins7DayAverage = last7Total / 7;
  const previous7DayAverage = previous7Total / 7;
  const sevenDayTrend = previous7Total > 0
    ? (last7Total - previous7Total) / previous7Total
    : null;

  const dailyAsinTrend: DailyAsinPoint[] = [];
  for (let offset = 14; offset >= 0; offset -= 1) {
    const dayStart = todayStartMs - offset * DAY_MS;
    let rollingTotal = 0;
    for (let trailing = 0; trailing < 7; trailing += 1) {
      rollingTotal += firstSeenByDay.get(dayKeyFromMs(dayStart - trailing * DAY_MS)) ?? 0;
    }
    dailyAsinTrend.push({
      date: dayKeyFromMs(dayStart),
      newAsins: firstSeenByDay.get(dayKeyFromMs(dayStart)) ?? 0,
      rolling7Average: rollingTotal / 7,
    });
  }

  const completedRuns24h = runs.filter((run) => {
    const startedMs = Date.parse(run.started_at);
    return Boolean(run.finished_at)
      && Number.isFinite(startedMs)
      && startedMs >= rollingStartMs
      && startedMs <= safeNowMs;
  });

  const observedTokens = completedRuns24h.map(observedRunTokens);
  const totalTelemetryComplete = observedTokens.every((value) => value !== null);
  const spentTokens24h = totalTelemetryComplete
    ? observedTokens.reduce<number>((sum, value) => sum + (value ?? 0), 0)
    : null;

  const brainRate = getBrain().learning?.tokenBudget?.refillRatePerMinute;
  const requestedRate = options.refillRatePerMinute === undefined ? brainRate : options.refillRatePerMinute;
  const refillRatePerMinute = typeof requestedRate === "number"
    && Number.isFinite(requestedRate)
    && requestedRate > 0
    ? requestedRate
    : null;
  const generatedTokens24h = refillRatePerMinute === null ? null : refillRatePerMinute * 60 * 24;
  const tokenUtilization = spentTokens24h !== null && generatedTokens24h
    ? spentTokens24h / generatedTokens24h
    : null;
  const tokenCaptureReason = refillRatePerMinute === null
    ? "Keepa refill rate is unavailable in ai-brain.json."
    : !totalTelemetryComplete
      ? "At least one completed collector run lacks token telemetry."
      : null;

  const tier3TelemetryComplete = completedRuns24h.every((run) => run.tier1_tokens !== null);
  const tier3Tokens24h = tier3TelemetryComplete
    ? completedRuns24h.reduce((sum, run) => sum + Math.max(0, run.tier3_tokens ?? 0), 0)
    : null;
  const asinsPerTier3Token = tier3Tokens24h !== null && tier3Tokens24h > 0
    ? newAsinsLast24h / tier3Tokens24h
    : null;
  const tier3EfficiencyReason = !tier3TelemetryComplete
    ? "Per-tier token telemetry is incomplete in the rolling window."
    : tier3Tokens24h === 0
      ? "No tier-3 history tokens were recorded in the last 24 hours."
      : null;

  const totalUniqueAsins = profiles.size;
  const categoryDiversity = diversity([...profiles.values()].map((profile) => profile.category), totalUniqueAsins);
  const sourceDiversity = diversity([...profiles.values()].map((profile) => profile.source), totalUniqueAsins);

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

  const runHistory: RunHistoryPoint[] = [...runs].reverse().map((run) => ({
    startedAt: run.started_at,
    finishedAt: run.finished_at,
    status: run.status,
    host: run.host,
    tokensConsumed: run.tokens_consumed,
    tier1Tokens: run.tier1_tokens,
    tier2Tokens: run.tier2_tokens,
    tier3Tokens: run.tier3_tokens,
    tokensLeftEnd: run.tokens_left_end,
    backtestRowsWritten: run.backtest_rows_written,
    backtestAsinsSampled: run.backtest_asins_sampled,
  }));
  const tierBreakdownAvailableSince = runHistory.find((run) => run.tier1Tokens !== null)?.startedAt ?? null;

  const rankerHistory: RankerHistoryPoint[] = [...rankerRuns].reverse().map((run) => ({
    trainedAt: run.trained_at,
    refused: run.refused,
    refusalReason: run.refusal_reason,
    rowCount: run.row_count,
    championAuc: run.champion_auc,
    challengerAuc: run.challenger_auc,
    verdict: run.verdict,
    trainRows: run.train_rows,
    valRows: run.val_rows,
  }));

  const sampleSourceAvailableSince = rows.find((row) => row.sample_source !== null)?.created_at ?? null;

  return {
    connected: true,
    asOf: safeNow.toISOString(),
    totalBacktestRows: rows.length,
    totalUniqueAsins,
    averageRowsPerAsin: totalUniqueAsins ? rows.length / totalUniqueAsins : null,
    newAsinsToday,
    newAsinsLast24h,
    newAsins7DayAverage,
    previous7DayAverage,
    sevenDayTrend,
    dailyAsinTrend,
    tier3Efficiency24h: {
      newAsins: newAsinsLast24h,
      tier3Tokens: tier3Tokens24h,
      asinsPerToken: asinsPerTier3Token,
      telemetryComplete: tier3TelemetryComplete,
      reason: tier3EfficiencyReason,
    },
    tokenCapture24h: {
      completedRuns: completedRuns24h.length,
      spentTokens: spentTokens24h,
      generatedTokens: generatedTokens24h,
      refillRatePerMinute,
      utilization: tokenUtilization,
      telemetryComplete: totalTelemetryComplete,
      reason: tokenCaptureReason,
    },
    pendingBacklog: {
      available: collectionState !== null,
      pendingAsins: collectionState?.pendingAsins ?? null,
      byCategory: collectionState?.pendingByCategory ?? [],
      unknownCategoryAsins: collectionState?.unknownCategoryAsins ?? null,
    },
    categoryDiversity,
    sourceDiversity,
    backtestGrowth,
    labelComposition,
    sampleComposition,
    sampleSourceAvailableSince,
    runHistory,
    tierBreakdownAvailableSince,
    rankerHistory,
  };
}

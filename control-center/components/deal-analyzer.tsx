"use client";

import * as React from "react";
import { AlertTriangle, CheckCircle2, Circle, Loader2, RotateCcw, Save, ShieldAlert, Star } from "lucide-react";
import { Badge } from "@/components/ui";
import { cn } from "@/lib/cn";
import { money, pct } from "@/lib/format";

type Criteria = {
  bsrMax: number;
  minMonthlySales: number;
  minOffers: number;
  maxOffers: number;
  minRoi: number;
  minProfitPerUnit: number;
};

type Guards = {
  priceSpikeRatio: number;
  offersRiseRatio: number;
  amazonBuyBoxShareMax: number;
};

type DealAnalyzerProps = {
  criteria: Criteria;
  guards: Guards;
  groceryMinRoi: number;
  referralRates: Record<string, number>;
  friendlyBrands: string[];
  avoidBrands: string[];
  restrictionKeywords: Record<string, string[]>;
};

const DEFAULTS = {
  productName: "",
  asin: "",
  sellPrice: 30,
  buyCost: 14,
  fbaFee: 4.9,
  inbound: 0.6,
  bsr: 25000,
  sales: 200,
  offers: 6,
  amazonBuyBox: false,
  category: "",
  // Optional Keepa-history fields — kept as strings so "" reliably means "not checked"
  // rather than 0, which is a valid (if unlikely) real value.
  avgPrice90: "",
  avgOffers90: "",
  amazonBBSharePct: "",
  priceLow90: "",
  brandText: "",
  titleText: "",
};
type FormState = typeof DEFAULTS;

const FUEL_RATE = 0.035;
const PREP = 0.5;

function numOrNull(s: string): number | null {
  if (s.trim() === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function categoryLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Mirrors scout/scoring.py's _fba_restriction_hint: case-insensitive, word-boundary match so
// "jelly" doesn't hit "Jellycat" and "tire" doesn't hit "entire". A hint only — never a verdict.
function restrictionHints(text: string, keywords: Record<string, string[]>): string[] {
  const hay = text.toLowerCase();
  const hits: string[] = [];
  for (const [label, words] of Object.entries(keywords)) {
    for (const raw of words) {
      const w = raw.trim().toLowerCase();
      if (!w) continue;
      const escaped = w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (new RegExp(`\\b${escaped}\\b`).test(hay)) {
        hits.push(label);
        break;
      }
    }
  }
  return hits;
}

// Mirrors scout/brands.py's is_friendly/is_avoided matching (normalized exact/prefix/token match).
function matchesBrandList(brandText: string, list: string[], mode: "avoid" | "friendly"): boolean {
  const b = brandText.trim().toLowerCase();
  if (!b) return false;
  if (mode === "avoid") {
    const tokens = b.split(/\s+/);
    return list.some((a) => {
      const an = a.trim().toLowerCase();
      return b === an || tokens.includes(an);
    });
  }
  return list.some((f) => {
    const fn = f.trim().toLowerCase();
    return b === fn || b.startsWith(fn + " ");
  });
}

type CheckStatus = "pass" | "fail" | "skip" | "info";
type Check = {
  key: string;
  label: string;
  status: CheckStatus;
  detail: string;
  countable: boolean; // does this contribute to the failed-gate count?
  hard?: boolean; // does failing this force a PASS (reject) verdict?
};

export function DealAnalyzer({ criteria, guards, groceryMinRoi, referralRates, friendlyBrands, avoidBrands, restrictionKeywords }: DealAnalyzerProps) {
  const [v, setV] = React.useState<FormState>(DEFAULTS);
  const [saving, setSaving] = React.useState(false);
  const [saveMsg, setSaveMsg] = React.useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const set = (key: keyof FormState, value: string | number | boolean) =>
    setV((cur) => ({ ...cur, [key]: value }));

  const isGrocery = v.category === "grocery";
  const roiTarget = isGrocery ? groceryMinRoi : criteria.minRoi;
  const referralRate = v.category ? referralRates[v.category] ?? referralRates.default ?? 0.15 : referralRates.default ?? 0.15;

  // Mirrors amazon-fba-oa/skills/fba-deal-calculator/scripts/fba_calc.py and
  // scout/scoring.py's estimate_oa_profit_roi for referral/fulfillment/fuel/prep — category-aware
  // referral rate + the $0.30 floor ONLY when a category is known, exactly like scout's
  // estimate_oa_profit_roi (no floor on the uncategorized path). "Inbound / unit" is a
  // DELIBERATE control-center-only addition (real shipping-to-Amazon cost scout's simplified
  // estimate doesn't model) — this makes the two tools diverge on purpose for that one line
  // item; everything else stays formula-identical to scout.
  const referral = v.category ? Math.max(v.sellPrice * referralRate, 0.3) : v.sellPrice * referralRate;
  const fuel = v.fbaFee * FUEL_RATE;
  const nonCostFees = referral + v.fbaFee + fuel + PREP + v.inbound;
  const profit = v.sellPrice - v.buyCost - nonCostFees;
  const roi = v.buyCost > 0 ? profit / v.buyCost : 0;
  const margin = v.sellPrice > 0 ? profit / v.sellPrice : 0;
  const breakeven = (v.buyCost + v.fbaFee + fuel + PREP + v.inbound) / (1 - referralRate);
  const maxCost = (v.sellPrice - nonCostFees) / (1 + roiTarget);

  // ---- Optional Keepa-history guards (skipped, not failed, when the field is empty) --------
  const avgPrice90 = numOrNull(v.avgPrice90);
  const isPriceSpike = avgPrice90 !== null && v.sellPrice > avgPrice90 * guards.priceSpikeRatio;

  const avgOffers90 = numOrNull(v.avgOffers90);
  const isOffersRising = avgOffers90 !== null && v.offers > avgOffers90 * guards.offersRiseRatio;

  const bbSharePct = numOrNull(v.amazonBBSharePct);
  const bbShareFrac = bbSharePct !== null ? bbSharePct / 100 : null;
  const isBBShareReject = bbShareFrac !== null && bbShareFrac >= guards.amazonBuyBoxShareMax;

  const priceLow90 = numOrNull(v.priceLow90);
  let worstCaseLoss = 0;
  if (priceLow90 !== null) {
    const referralLow = v.category ? Math.max(priceLow90 * referralRate, 0.3) : priceLow90 * referralRate;
    const nonCostFeesLow = referralLow + v.fbaFee + fuel + PREP + v.inbound;
    worstCaseLoss = Math.max(0, -(priceLow90 - v.buyCost - nonCostFeesLow));
  }
  const isWorstCaseFail = priceLow90 !== null && worstCaseLoss > 2;

  const isAvoidBrand = matchesBrandList(v.brandText, avoidBrands, "avoid");
  const isFriendlyBrand = !isAvoidBrand && matchesBrandList(v.brandText, friendlyBrands, "friendly");

  const restrictionText = `${v.titleText} ${v.brandText}`.trim();
  const restrictionHitList = restrictionText ? restrictionHints(restrictionText, restrictionKeywords) : [];

  // ---- All checks, gates first (always active) then optional guards/signals ----------------
  const checks: Check[] = [
    { key: "eligibility", label: "Eligibility", countable: true, hard: v.amazonBuyBox,
      status: v.amazonBuyBox ? "fail" : "pass",
      detail: v.amazonBuyBox ? "Amazon owns the Buy Box" : "manual gating check still required" },
    { key: "demand", label: "Demand", countable: true,
      status: v.bsr <= criteria.bsrMax && v.sales >= criteria.minMonthlySales ? "pass" : "fail",
      detail: `BSR ${v.bsr.toLocaleString()} · ${v.sales}/mo` },
    { key: "competition", label: "Competition", countable: true,
      status: v.offers >= criteria.minOffers && v.offers <= criteria.maxOffers ? "pass" : "fail",
      detail: `${v.offers} offers` },
    { key: "profit", label: "Profit floor", countable: true,
      status: profit >= criteria.minProfitPerUnit ? "pass" : "fail",
      detail: `${money(profit)}/u` },
    { key: "roi", label: "ROI floor", countable: true,
      status: roi >= roiTarget ? "pass" : "fail",
      detail: `${pct(roi)}${isGrocery ? ` (grocery ${Math.round(groceryMinRoi * 100)}% bar)` : ""}` },
    { key: "price-spike", label: "Price spike (90d)", countable: true, hard: false,
      status: avgPrice90 === null ? "skip" : isPriceSpike ? "fail" : "pass",
      detail: avgPrice90 === null ? "not checked" : `$${v.sellPrice} vs $${avgPrice90} avg (max ${guards.priceSpikeRatio}×)` },
    { key: "offers-rising", label: "Offers rising (90d)", countable: true,
      status: avgOffers90 === null ? "skip" : isOffersRising ? "fail" : "pass",
      detail: avgOffers90 === null ? "not checked" : `${v.offers} vs ${avgOffers90} avg (max ${guards.offersRiseRatio}×)` },
    { key: "amazon-bb-share", label: "Amazon Buy-Box share", countable: true, hard: isBBShareReject,
      status: bbShareFrac === null ? "skip" : isBBShareReject ? "fail" : "pass",
      detail: bbShareFrac === null ? "not checked" : `${bbSharePct}% (max ${Math.round(guards.amazonBuyBoxShareMax * 100)}%)` },
    { key: "worst-case", label: "Worst-case (90d low)", countable: true,
      status: priceLow90 === null ? "skip" : isWorstCaseFail ? "fail" : "pass",
      detail: priceLow90 === null ? "not checked" : `~${money(worstCaseLoss)} loss at $${priceLow90} low` },
    { key: "brand", label: "Brand signal", countable: false, hard: isAvoidBrand,
      status: !v.brandText ? "skip" : isAvoidBrand ? "fail" : isFriendlyBrand ? "pass" : "info",
      detail: !v.brandText ? "not checked" : isAvoidBrand ? "avoid-list — IP/hard-gate risk" : isFriendlyBrand ? "known-good OA brand" : "not on either list" },
    { key: "restriction-hint", label: "Restriction hint", countable: false,
      status: !restrictionText ? "skip" : restrictionHitList.length ? "info" : "pass",
      detail: !restrictionText ? "not checked" : restrictionHitList.length
        ? `possible: ${restrictionHitList.join(", ")} — verify in Seller Central`
        : "no keyword hits (not proof of eligibility)" },
  ];

  const hardRejected = v.amazonBuyBox || isBBShareReject || isAvoidBrand;
  const countable = checks.filter((c) => c.countable && c.status !== "skip");
  // price-spike / offers-rising / worst-case are SOFT signals in scout's real scoring.py — small
  // point penalties (-15/-12/-10 of 100), never gates on their own. Letting enough of them
  // accumulate force a PASS (as a flat failed-check count used to) rejected candidates scout's
  // real weighted score would still send to review; letting even one slip through un-penalized
  // (as "BUY" used to when <=2 had failed) showed false confidence on a candidate with a real red
  // flag. Now: any CORE criteria failure (demand/competition/profit/roi/eligibility) rejects, same
  // as before; soft-signal failures alone can only ever demote BUY to REVIEW, never force PASS,
  // and never get silently absorbed into a BUY.
  const SOFT_KEYS = new Set(["price-spike", "offers-rising", "worst-case"]);
  const coreFailed = countable.filter((c) => c.status === "fail" && !SOFT_KEYS.has(c.key));
  const softFailed = countable.filter((c) => c.status === "fail" && SOFT_KEYS.has(c.key));
  const verdict = hardRejected || coreFailed.length > 0 ? "PASS" : softFailed.length === 0 ? "BUY" : "REVIEW";
  const failed = [...coreFailed, ...softFailed]; // combined, for display counts only — verdict logic never uses this blend
  const verdictTone = verdict === "BUY" ? "text-profit" : verdict === "REVIEW" ? "text-warn" : "text-loss";
  const rejectReason = v.amazonBuyBox
    ? "Amazon owns the Buy Box"
    : isBBShareReject
      ? `Amazon wins the Buy Box ~${bbSharePct}% of the time (rotation)`
      : isAvoidBrand
        ? "Brand is hard-gated / IP-risky for beginners"
        : null;

  const field = (label: string, key: keyof FormState, prefix?: string) => (
    <label className="block">
      <span className="mb-1 block text-[11px] text-muted">{label}</span>
      <span className="relative block">
        {prefix ? <span className="num absolute left-2.5 top-1/2 -translate-y-1/2 text-[11px] text-faint">{prefix}</span> : null}
        <input
          className={cn("field", prefix && "pl-6")}
          type="number"
          min="0"
          step="0.01"
          value={v[key] as number}
          onChange={(e) => set(key, Number(e.target.value))}
        />
      </span>
    </label>
  );

  const optField = (label: string, key: keyof FormState, prefix?: string, placeholder?: string) => (
    <label className="block">
      <span className="mb-1 block text-[11px] text-muted">{label}</span>
      <span className="relative block">
        {prefix ? <span className="num absolute left-2.5 top-1/2 -translate-y-1/2 text-[11px] text-faint">{prefix}</span> : null}
        <input
          className={cn("field", prefix && "pl-6")}
          type="number"
          step="0.01"
          placeholder={placeholder ?? "not checked"}
          value={v[key] as string}
          onChange={(e) => set(key, e.target.value)}
        />
      </span>
    </label>
  );

  const stat = (label: string, value: string, good: boolean, neutral = false) => (
    <div className="surface px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-[0.06em] text-faint">{label}</div>
      <div className={cn("num mt-0.5 text-[15px] font-semibold", neutral ? "text-ink" : good ? "text-profit" : "text-loss")}>{value}</div>
    </div>
  );

  const statusIcon = (status: CheckStatus) => {
    if (status === "pass") return <CheckCircle2 size={14} className="shrink-0 text-profit" />;
    if (status === "fail") return <AlertTriangle size={14} className="shrink-0 text-loss" />;
    if (status === "info") return <Star size={14} className="shrink-0 text-accent2" />;
    return <Circle size={10} className="ml-0.5 mr-0.5 shrink-0 text-faint" />;
  };

  async function saveLead() {
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await fetch("/api/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "lead",
          product: v.productName || v.titleText || (v.asin ? `ASIN ${v.asin}` : "Untitled deal"),
          asin: v.asin || undefined,
          roi,
          status: "researching",
          notes: `${verdict} — ${money(profit)}/u, ${pct(roi)} ROI, ${failed.length}/${countable.length} checks failed`
            + (rejectReason ? `. Hard reject: ${rejectReason}` : "")
            + (v.category ? `. Category: ${categoryLabel(v.category)}` : ""),
        }),
      });
      const data = await res.json();
      if (!res.ok) setSaveMsg({ tone: "err", text: data.error ?? "Could not save." });
      else setSaveMsg({ tone: "ok", text: "Saved to the leads pipeline." });
    } catch {
      setSaveMsg({ tone: "err", text: "Network error — is the dev server running locally?" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 xl:grid-cols-2">
        {/* Inputs */}
        <div className="flex flex-col gap-3">
          <div className="surface p-3">
            <div className="mb-2.5 flex items-center justify-between">
              <span className="text-[12px] font-semibold uppercase tracking-[0.06em] text-muted">Deal inputs</span>
              <button
                type="button"
                onClick={() => { setV(DEFAULTS); setSaveMsg(null); }}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded border border-line px-2 py-1 text-[11px] text-muted transition-colors hover:border-line2 hover:text-ink"
              >
                <RotateCcw size={12} /> reset
              </button>
            </div>
            <div className="grid gap-2.5 sm:grid-cols-2">
              <label className="block sm:col-span-2">
                <span className="mb-1 block text-[11px] text-muted">Product name (for Save as lead)</span>
                <input className="field" value={v.productName} onChange={(e) => set("productName", e.target.value)} placeholder="e.g. Crayola 64-ct crayons" maxLength={120} />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11px] text-muted">ASIN</span>
                <input className="field" value={v.asin} onChange={(e) => set("asin", e.target.value.toUpperCase())} placeholder="B0XXXXXXXX" maxLength={20} />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11px] text-muted">Category</span>
                <select className="field" value={v.category} onChange={(e) => set("category", e.target.value)}>
                  <option value="">— unspecified ({Math.round((referralRates.default ?? 0.15) * 100)}% default) —</option>
                  {Object.keys(referralRates).filter((k) => k !== "default").sort().map((k) => (
                    <option key={k} value={k}>{categoryLabel(k)} ({Math.round(referralRates[k] * 100)}%)</option>
                  ))}
                </select>
              </label>
              {field("Sell price", "sellPrice", "$")}
              {field("Landed buy cost", "buyCost", "$")}
              {field("FBA fee", "fbaFee", "$")}
              {field("Inbound / unit", "inbound", "$")}
              {field("BSR", "bsr")}
              {field("Sales / mo", "sales")}
              {field("Offers", "offers")}
              <label className="flex cursor-pointer items-center gap-2 self-end rounded border border-line px-2.5 py-2 text-[12px] text-muted transition-colors hover:border-line2">
                <input type="checkbox" checked={v.amazonBuyBox} onChange={(e) => set("amazonBuyBox", e.target.checked)} className="h-3.5 w-3.5 accent-[var(--accent)]" />
                Amazon owns Buy Box
              </label>
            </div>
            <p className="mt-2.5 text-[11px] leading-snug text-faint">
              {Math.round(referralRate * 100)}% referral ($0.30 min){v.category ? ` (${categoryLabel(v.category)})` : ""}, 3.5% fuel on FBA fee, $0.50 prep.
              Estimate only — confirm the exact fee in SellerAmp / Revenue Calculator.
            </p>
          </div>

          <div className="surface p-3">
            <div className="mb-1 text-[12px] font-semibold uppercase tracking-[0.06em] text-muted">
              Keepa history — optional, sharpens the verdict
            </div>
            <p className="mb-2.5 text-[11px] text-faint">Leave any field blank to skip that check — skipped checks never count as a pass.</p>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {optField("90-day avg price", "avgPrice90", "$")}
              {optField("90-day avg offers", "avgOffers90")}
              {optField("Amazon Buy-Box share", "amazonBBSharePct", undefined, "%")}
              {optField("90-day low price", "priceLow90", "$")}
              <label className="block">
                <span className="mb-1 block text-[11px] text-muted">Brand</span>
                <input className="field" value={v.brandText} onChange={(e) => set("brandText", e.target.value)} placeholder="not checked" maxLength={80} />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11px] text-muted">Product title</span>
                <input className="field" value={v.titleText} onChange={(e) => set("titleText", e.target.value)} placeholder="not checked" maxLength={200} />
              </label>
            </div>
          </div>
        </div>

        {/* Result */}
        <div className="surface flex flex-col p-3">
          <div className="mb-2.5 flex items-center justify-between">
            <div className="flex items-baseline gap-2">
              <span className="text-[12px] font-semibold uppercase tracking-[0.06em] text-muted">Verdict</span>
              <span className={cn("num text-[17px] font-bold", verdictTone)}>{verdict}</span>
            </div>
            <Badge tone={hardRejected ? "loss" : failed.length ? (verdict === "REVIEW" ? "warn" : "loss") : "success"}>
              {hardRejected ? "hard reject" : failed.length ? `${failed.length}/${countable.length} checks failed` : "all checks pass"}
            </Badge>
          </div>

          {rejectReason ? (
            <div className="mb-2.5 flex items-start gap-2 rounded border border-loss/25 bg-loss/5 px-2.5 py-2 text-[11px] leading-snug text-loss">
              <ShieldAlert size={14} className="mt-0.5 shrink-0" />
              {rejectReason} — forces PASS regardless of score.
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {stat("Profit / unit", money(profit), profit >= criteria.minProfitPerUnit)}
            {stat("ROI", pct(roi), roi >= roiTarget)}
            {stat("Margin", pct(margin), margin >= 0.2)}
            {stat("Breakeven sell", money(breakeven), true, true)}
            {stat(`Max cost @${Math.round(roiTarget * 100)}%`, money(maxCost), v.buyCost <= maxCost)}
          </div>

          <ul className="mt-2.5 flex flex-1 flex-col divide-y divide-line overflow-y-auto">
            {checks.map((c) => (
              <li key={c.key} className="flex items-center gap-2 py-1.5">
                {statusIcon(c.status)}
                <span className={cn("w-36 shrink-0 text-[12px]", c.status === "skip" ? "text-faint" : "text-ink")}>{c.label}</span>
                <span className="num min-w-0 flex-1 truncate text-[11px] text-muted">{c.detail}</span>
              </li>
            ))}
          </ul>

          <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-3">
            <button
              type="button"
              onClick={saveLead}
              disabled={saving}
              className="inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 rounded bg-accent px-3 text-[12px] font-semibold text-slate-950 transition-colors hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              {saving ? "Saving…" : "Save as lead"}
            </button>
            {saveMsg ? (
              <span className={cn("text-[11px] font-medium", saveMsg.tone === "ok" ? "text-profit" : "text-loss")}>{saveMsg.text}</span>
            ) : (
              <span className="text-[11px] text-faint">Local dev only — writes to the leads pipeline, not on Vercel.</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

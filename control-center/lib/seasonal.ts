// lib/seasonal.ts — pure date math for the Morning Brief's seasonal-awareness chips (CC2
// item 1). Takes `now` as a parameter (never reads the clock itself) so it's exercisable with
// fixture dates, including year-boundary cases, without a JS test runner in this project.
//
// ai-brain.json's operations.seasonal2026 block is YEAR-SPECIFIC (its absolute dates are for
// calendar year 2026). Rather than special-case "what year is it", the date-comparison chips
// (Prime Day window, Q4 arrival deadline) naturally go silent once `now` is past them — running
// this in 2027 just means those two chips never fire (correct: stale advice, not wrong advice).
// The month/day-of-year pattern chips (back-to-school, toy windows, January returns, Q4 bias)
// recompute their anchor dates against `now`'s own year, so they stay correct every year.

export type SeasonalOps = {
  primeDayWindow?: { start: string; end: string; role: string };
  backToSchoolBuyWindow?: string;
  q4ArrivalDeadline?: string;
  q4StopSpeculativeBuysAfterWeek?: number;
  toysBuyWindows?: string[];
  januaryReturnsWave?: boolean;
  biasQ4TowardLowReturnCategories?: boolean;
};

export type SeasonalChip = { key: string; label: string; tone: "info" | "warn" | "danger" };

const DAY_MS = 86_400_000;

function daysUntil(now: Date, target: Date): number {
  return Math.ceil((target.getTime() - now.getTime()) / DAY_MS);
}

// ISO-8601 week number (Thursday-of-the-week rule) — used for q4StopSpeculativeBuysAfterWeek.
export function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = date.getUTCDay() || 7; // Sunday (0) -> 7
  date.setUTCDate(date.getUTCDate() + 4 - day); // move to this week's Thursday
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / DAY_MS + 1) / 7);
}

function dateInYear(year: number, monthIdx0: number, day: number): Date {
  return new Date(Date.UTC(year, monthIdx0, day));
}

export function computeSeasonalChips(seasonal: SeasonalOps, now: Date): SeasonalChip[] {
  const chips: SeasonalChip[] = [];
  const year = now.getUTCFullYear();
  const month = now.getUTCMonth(); // 0-indexed

  if (seasonal.primeDayWindow) {
    const start = new Date(seasonal.primeDayWindow.start);
    // Bare "YYYY-MM-DD" parses as 00:00:00 UTC — the window must include the WHOLE end day,
    // not expire at its first instant (caught by a fixture test at 2026-06-26T23:00 UTC).
    const end = new Date(`${seasonal.primeDayWindow.end}T23:59:59.999Z`);
    if (now >= start && now <= end) {
      chips.push({ key: "primeday-open", label: `Prime Day sourcing window open (through ${seasonal.primeDayWindow.end})`, tone: "info" });
    } else if (now < start) {
      const d = daysUntil(now, start);
      if (d <= 30) chips.push({ key: "primeday-soon", label: `Prime Day sourcing window opens in ${d}d`, tone: "info" });
    }
  }

  if (seasonal.q4ArrivalDeadline) {
    const deadline = new Date(seasonal.q4ArrivalDeadline);
    if (now < deadline) {
      const weeks = Math.ceil(daysUntil(now, deadline) / 7);
      chips.push({
        key: "q4-deadline",
        label: `Q4 FBA arrival deadline in ${weeks} week${weeks === 1 ? "" : "s"}`,
        tone: weeks <= 4 ? "danger" : weeks <= 8 ? "warn" : "info",
      });
    }
  }

  if (typeof seasonal.q4StopSpeculativeBuysAfterWeek === "number") {
    // Independent of q4ArrivalDeadline on purpose: coupling the two (an earlier version of
    // this function silenced the chip once `now > deadline`) broke a real case — this brain's
    // deadline (2026-10-30, ISO week 44) falls BEFORE week 46, so "deadline passed" was true
    // by the time week 46 arrived and the warning never fired exactly when it mattered most.
    // ISO week resets every January, so `week >= N` alone self-bounds to roughly Nov-Dec each
    // year without needing an expiry condition.
    const week = isoWeek(now);
    if (week >= seasonal.q4StopSpeculativeBuysAfterWeek) {
      chips.push({
        key: "q4-stop-speculative",
        label: `Past week ${seasonal.q4StopSpeculativeBuysAfterWeek} — stop speculative Q4 buys (arrival risk)`,
        tone: "warn",
      });
    }
  }

  // "late June - mid August", parsed loosely against this year's calendar.
  if (seasonal.backToSchoolBuyWindow) {
    const start = dateInYear(year, 5, 20); // late June
    const end = dateInYear(year, 7, 15); // mid August
    if (now >= start && now <= end) {
      chips.push({ key: "back-to-school", label: "Back-to-school buy window open", tone: "info" });
    }
  }

  if (seasonal.toysBuyWindows?.length) {
    if (month === 1 || month === 2) chips.push({ key: "toys-clearance", label: "Toy clearance buying window (Feb-Mar)", tone: "info" });
    if (month === 9) chips.push({ key: "toys-october", label: "Toy buying window (October)", tone: "info" });
  }

  if (seasonal.januaryReturnsWave && month === 0) {
    chips.push({ key: "january-returns", label: "January returns wave — expect return-driven listings and price drops", tone: "info" });
  }

  if (seasonal.biasQ4TowardLowReturnCategories && month >= 9) {
    chips.push({ key: "q4-low-return-bias", label: "Q4: bias sourcing toward low-return categories", tone: "info" });
  }

  return chips;
}

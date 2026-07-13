# Decision note — approve the reliable collector dispatcher

**For:** Mehmet. **Prepared by:** Cowork, 2026-07-13. **Decision needed:** yes/no to install the local scheduled dispatcher for `keepa-collect`.

## What you're approving
Installing a local scheduled task (`scripts/install_keepa_dispatch_task.ps1` → `scripts/dispatch_keepa_collect.ps1`) that triggers the hourly Keepa collector on a reliable ~45-minute cadence, instead of relying on GitHub Actions cron alone. GitHub cron is best-effort and drops runs under load.

## Why it matters (quantified)
- Collector **token capture is ~69%** (992 of 1,440 daily tokens spent; only 17 of 24 hourly runs completing).
- Measured inter-run gap: **median 83.3 min, and 47% of gaps exceed 90 min** — so tokens generated in the missed windows overflow the 60-token bank and are **lost forever**.
- On 2026-07-06/07 this cost **11 full runs with no alert** (that alert gap is now fixed; the reliability gap is not).
- Lifting capture from ~69% → ~95% is roughly a **1.4× throughput gain** — the single biggest remaining lever toward 10k unique ASINs, at **zero token cost**. It shortens the timeline by roughly a third.

## What it does NOT do (guardrails intact)
- No new Keepa spend — it only makes you capture the tokens you already generate.
- Touches no hard gate, no model promotion (`scoring.rankingChampion` stays `rule`), and never buys anything.
- Fully reversible — uninstall the scheduled task to revert to cron-only.

## One tradeoff to acknowledge
While a backlog exists, `corpusAcceleration` (already approved) pauses **Tier 2 — the live buy-discovery scan** — to route the bank to data collection. More reliable dispatch means Tier 2 stays paused more consistently until the ~600-item backlog drains. You're in a data-collection sprint, not buying, so this is the right trade for now — but it's a conscious one. Flip `corpusAcceleration.skipTier2WhilePending` off (via `fba-brain-updater`) the moment you want buy-discovery back.

## Recommendation
**Approve.** It's the highest-value, lowest-risk throughput action left, and it's the fix for the 69% capture number on your dashboard. If yes, hand to Claude Code: *"Install the keepa-collect dispatcher per DISPATCHER_APPROVAL_NOTE.md; verify two full days with no >90-min gaps and report the new capture %."*

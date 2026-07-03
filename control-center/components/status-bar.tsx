import { getBrain, getPicks } from "@/lib/data";

export function StatusBar() {
  const brain = getBrain();
  const picks = getPicks();
  const c = brain.criteria as Record<string, number>;
  const chunks = brain.knowledge.ragCorpus?.chunks ?? 0;

  return (
    <div className="sticky top-0 z-30 hidden h-9 items-center justify-between border-b border-line bg-bg px-4 md:flex">
      <div className="num flex min-w-0 items-center gap-3 overflow-hidden text-[10px] uppercase tracking-[0.11em] text-faint">
        {/* This dot means "the console UI is rendering" (trivially true whenever this
            component runs) — NOT a backend health signal. Keep it labeled "console", never
            "live"/"online", so it can't be misread as a claim about Scout/Supabase/Keepa
            health the way its neighbors in this bar (which DO check real state) are. */}
        <span className="flex shrink-0 items-center gap-1.5 text-ink">
          <span className="h-1.5 w-1.5 rounded-full bg-profit" aria-hidden /> console
        </span>
        <span className="text-line2">|</span>
        <span>KB <b className="text-muted">{brain.knowledge.transcripts}v · {chunks.toLocaleString()} notes</b></span>
        <span>Scout <b className={picks.connected ? "text-profit" : "text-warn"}>{picks.connected ? "online" : "offline"}</b></span>
        <span>Gates <b className="text-muted">BSR&lt;{Math.round(c.bsrMax / 1000)}k · ROI≥{Math.round(c.minRoi * 100)}% · ${c.minProfitPerUnit}+</b></span>
      </div>
      <div className="num shrink-0 text-[10px] uppercase tracking-[0.1em] text-faint">human-approved buys</div>
    </div>
  );
}

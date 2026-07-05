import { ArrowUpRight, Wrench } from "lucide-react";
import { getBrain } from "@/lib/data";
import { Panel, Badge, DataNote } from "@/components/ui";
import { Reveal, Pressable } from "@/components/motion";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

type Tool = { name: string; url?: string; what: string };
type Group = { title: string; note: string; tools: Tool[] };

// Curated catalog. URLs are only attached where the canonical site is known; tools that
// live as browser extensions (no clean domain) are shown without a link rather than guessed.
const GROUPS: Group[] = [
  {
    title: "Research & analysis",
    note: "Decide if a product can profit.",
    tools: [
      { name: "Keepa", url: "https://keepa.com", what: "Price & sales-rank history — the chart every check starts from (BSR, Buy-Box, offers over time)." },
      { name: "SellerAmp SAS", url: "https://selleramp.com", what: "Profit/ROI calculator + buy decision on the listing. Confirm every buy here." },
      { name: "Amazon Revenue Calculator", url: "https://sellercentral.amazon.com/revcal", what: "Official FBA fee estimate by real dimensions/size tier." },
      { name: "BuyBotPro", url: "https://www.buybotpro.com", what: "Automated 1-click deal analysis + eligibility/IP signals." },
      { name: "RevROI", what: "Quick ROI math extension (browser)." },
    ],
  },
  {
    title: "Sourcing & deals",
    note: "Find the products in the first place.",
    tools: [
      { name: "Tactical Arbitrage", url: "https://tacticalarbitrage.com", what: "Scans 1,400+ retail sites against Amazon for flips." },
      { name: "ProfitPath", url: "https://profitpath.io", what: "OA sourcing suite + Dealwatch deal feed." },
      { name: "BrickSeek", url: "https://brickseek.com", what: "Local/retail stock + clearance price lookups." },
      { name: "Slickdeals", url: "https://slickdeals.net", what: "Community-surfaced deals; watch for replens." },
      { name: "IP Alert", what: "Flags brands that file IP complaints — avoid-list input (browser extension)." },
      { name: "Boxem", what: "Bulk ungating / eligibility checker across a list of ASINs." },
    ],
  },
  {
    title: "Cashback & gift cards",
    note: "Stack hidden margin on every buy.",
    tools: [
      { name: "cardbear.com", url: "https://www.cardbear.com", what: "Compares discounted gift-card marketplaces." },
      { name: "raise.com", url: "https://www.raise.com", what: "Buy discounted gift cards (instant margin)." },
      { name: "Rakuten", url: "https://www.rakuten.com", what: "Cashback portal — click through before you buy." },
      { name: "TopCashback", url: "https://www.topcashback.com", what: "Cashback portal, often higher rates than Rakuten." },
      { name: "Capital One Shopping", url: "https://capitaloneshopping.com", what: "Auto-coupons + cashback at checkout." },
      { name: "Coupert", url: "https://www.coupert.com", what: "Coupon finder + cashback (browser extension)." },
    ],
  },
  {
    title: "Account & compliance",
    note: "Run the store and stay allowed.",
    tools: [
      { name: "Amazon Seller Central", url: "https://sellercentral.amazon.com", what: "Your store: listings, shipments, performance, account health." },
      { name: "Seller University", url: "https://sell.amazon.com/learn", what: "Official training — listing, pricing, fulfilling, advertising." },
    ],
  },
];

export default function ToolsPage() {
  const brain = getBrain();
  const stack = new Set(brain.tools.map((t) => t.toLowerCase()));
  const inStack = (name: string) =>
    [...stack].some((t) => t.includes(name.toLowerCase()) || name.toLowerCase().includes(t));

  return (
    <div className="flex flex-col gap-6">
      <Reveal>
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="text-accent"><Wrench size={18} /></span>
            <h1 className="text-xl font-semibold tracking-tight">Tools</h1>
          </div>
          <DataNote source="tool stack" updated={`${brain.tools.length} in ai-brain.json`} />
        </header>
      </Reveal>

      {GROUPS.map((g, gi) => (
        <Reveal key={g.title} delay={gi * 0.04}>
          <Panel title={g.title} right={g.note}>
            <div className="grid gap-3 sm:grid-cols-2">
              {g.tools.map((t) => {
                const card = (
                  <div className="flex h-full flex-col gap-1 rounded-md border border-line bg-panel2/50 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2 text-sm font-medium text-ink">
                        {t.name}
                        {t.url ? <ArrowUpRight size={14} className="text-faint" aria-hidden /> : null}
                      </span>
                      {inStack(t.name) ? <Badge tone="accent">in stack</Badge> : <Badge tone="muted">suggested</Badge>}
                    </div>
                    <p className="text-[13px] text-muted">{t.what}</p>
                  </div>
                );
                return (
                  <Pressable key={t.name}>
                    {t.url ? (
                      <a href={t.url} target="_blank" rel="noopener noreferrer" className="block h-full">
                        {card}
                      </a>
                    ) : (
                      card
                    )}
                  </Pressable>
                );
              })}
            </div>
          </Panel>
        </Reveal>
      ))}
    </div>
  );
}

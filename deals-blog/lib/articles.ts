export type Article = {
  slug: string;
  title: string;
  dek: string;
  minutes: number;
  body: string[]; // paragraphs; a leading "## " marks a subheading, "- " marks a bullet
};

export const ARTICLES: Article[] = [
  {
    slug: "how-to-read-a-price-history-chart",
    title: "How to Read a Price-History Chart Before You Buy Anything on Sale",
    dek: "A \"70% off\" banner means nothing on its own. Here's what actually tells you whether a deal is real.",
    minutes: 6,
    body: [
      "Every big shopping site now shows some version of a price history graph, and almost nobody reads it correctly. The single most useful habit you can build as a deal shopper is checking the last 90 days of price movement before you check the discount percentage.",
      "## Start with the 90-day average, not today's price",
      "A single day's price is easy to manipulate: a retailer can mark an item up for a week and then \"discount\" it back to its normal price and call it 40% off. The 90-day average price is much harder to fake, because it's built from many separate days. If the current sale price is close to or above the 90-day average, the discount is mostly marketing.",
      "- If sale price < 90-day average by a meaningful margin (think 15-20%+), that's a real price drop.",
      "- If sale price ≈ 90-day average, you're paying a normal price with a discount sticker on it.",
      "- If sale price > 90-day average, walk away — you're paying more than usual.",
      "## Look at the shape of the line, not just the low point",
      "A price chart that saws up and down every few weeks between two levels tells you the \"sale\" price is really just the regular low end of a predictable cycle — worth buying at that price, but not worth rushing for. A chart that spikes rarely and briefly touches a low is a genuinely unusual opportunity, and those are the ones worth acting on quickly.",
      "## Watch stock/offer count alongside price",
      "When a price crashes at the same time the number of sellers or the in-stock availability also drops sharply, that's often a clearance or discontinuation event — good for a one-time buy, bad for assuming the price will ever return. When price drops but availability stays steady, that's usually a recurring promotional cycle you can catch again later.",
      "## The one-line rule",
      "Before buying anything because of a percentage-off banner, spend fifteen seconds looking at where today's price sits relative to the last 90 days. That single check filters out the large majority of fake or exaggerated \"deals\" before you ever compare it to a competitor's price.",
    ],
  },
  {
    slug: "amazon-2026-fee-changes-explained",
    title: "Amazon's 2026 Fee Changes, Explained for Shoppers and Resellers",
    dek: "Three separate 2026 fee changes quietly moved the economics of buying and reselling. Here's what changed and when.",
    minutes: 5,
    body: [
      "Marketplace fee schedules rarely make headlines, but they move real money, and 2026 brought three separate changes worth knowing about — whether you're a shopper watching prices creep up or someone reselling items you find on sale.",
      "## The January fulfillment fee increase",
      "Effective mid-January 2026, per-unit fulfillment fees rose by roughly $0.08 on average across standard-size items. It sounds small, but on thin-margin items that $0.08 can be the difference between a worthwhile flip and a break-even one. If you're evaluating whether an item is worth reselling, always price fees using the current schedule, not a number you remember from last year.",
      "## The April fuel surcharge",
      "Starting mid-April 2026, a separate fuel surcharge of roughly 3.5% was added on top of standard fulfillment fees. This one matters because it's a percentage, not a flat per-unit amount — it hits higher-priced items harder in absolute dollars than the flat January increase did. Anyone running margin math on a spreadsheet from before April is now underestimating true cost.",
      "## Aged-inventory surcharges start earlier",
      "Storage surcharges for slow-moving inventory used to kick in much later in an item's shelf life. That threshold moved earlier in 2026, meaning inventory that sits for roughly six months now starts accumulating extra storage costs sooner than it used to. If you're holding stock waiting for a price to recover, factor in that the carrying cost clock now starts earlier.",
      "## Why this matters even if you're just shopping",
      "Fee increases upstream tend to show up downstream as slightly higher \"regular\" prices over time, since sellers price in their real costs. Understanding that the floor has moved helps you judge whether a price is actually a good deal or just a return to a new, quietly higher normal.",
    ],
  },
  {
    slug: "how-cashback-and-gift-card-stacking-works",
    title: "How Cashback and Gift-Card Stacking Actually Works",
    dek: "The real math behind combining coupons, cashback portals, and discounted gift cards — and where people get it wrong.",
    minutes: 7,
    body: [
      "\"Stacking\" gets thrown around a lot, but the actual mechanics are simple once you see the order operations happen in. Here's the real math, not the hype.",
      "## Do the discount math first, cashback second",
      "A coupon or promo code reduces the price you pay at checkout — that's step one. A 15% off coupon means your cost becomes purchase price × 0.85. Cashback portals and browser extensions (the well-known ones: Rakuten, TopCashback, BeFrugal) then return a percentage of whatever you actually paid, not the pre-discount price. So the two effects multiply together rather than simply adding — always calculate the coupon first, then apply the cashback rate to the discounted number.",
      "## Discounted gift cards are a separate lever",
      "Buying store gift cards at a discount (a common one is around 3-10% off face value from gift-card resale marketplaces) effectively lowers your cost basis on anything you buy with that card, independent of whatever coupon or cashback you also use. This is the piece people miss — a discounted gift card isn't a substitute for cashback, it's a third, independent discount that stacks on top.",
      "## Compare cashback portals before you shop, not after",
      "Cashback rates for the same store vary between portals and change often — sometimes based on temporary promotions, sometimes long-term. It's worth a 30-second check across two or three portals before starting a big purchase, since the difference between a low and high rate on a large order is real money.",
      "## Read the exclusions",
      "Every one of these programs has fine print: certain categories are often excluded from cashback (gift cards themselves, sometimes electronics), and combining a manufacturer coupon with a store coupon isn't always allowed. Nothing kills a stacking plan faster than finding out at checkout that one of your three discounts doesn't apply — check the terms before you build a whole shopping list around a stack.",
      "## A worked example",
      "Item priced at $50. A 15% coupon brings it to $42.50. A gift card bought at 5% off face value effectively makes that $42.50 cost $40.38 in real money. A 4% cashback portal on top returns roughly $1.70. Net cost: about $38.68 on a $50 item — a genuine 22.6% total discount, built from three small, real levers rather than one big misleading banner.",
    ],
  },
  {
    slug: "seasonal-buying-calendar",
    title: "A Seasonal Buying Calendar: When Deals Are Actually Deals",
    dek: "Prices move on a predictable yearly rhythm. Knowing the calendar beats chasing every banner ad.",
    minutes: 6,
    body: [
      "Retail pricing follows a calendar almost as reliably as the seasons themselves. Knowing roughly when categories go on real sale — and when a \"sale\" is really just marketing around a slow period — saves both money and time.",
      "## Q4 concentrates the year's real discounting",
      "Across most general merchandise categories, the fourth quarter (October through December) is where the deepest, most genuine price drops of the year happen, concentrated around a handful of known events. If you're patient enough to wait for this window on a non-perishable item, you'll almost always beat the price available the rest of the year.",
      "## Category-specific windows exist too",
      "Some categories have their own calendar entirely separate from the big Q4 events — garden and outdoor gear discounts late in its usable season, holiday-specific items discount hard the week immediately after their holiday, and back-to-school categories move on a July-August rhythm. Learning your specific category's calendar is more useful than a generic \"wait for Black Friday\" rule.",
      "## Perishable and meltable products have real physical constraints",
      "It's easy to forget that some categories are shaped by physical logistics, not just marketing. Chocolate, gummies, and other heat-sensitive items have a real seasonal shipping window (roughly mid-October through mid-April in most of the US) tied to when it's cold enough to ship them safely — outside that window, availability and pricing on those items shift for genuinely physical reasons, not promotional ones. If you're stocking up on a heat-sensitive item, buying right as that window opens is usually smarter than waiting.",
      "## The takeaway",
      "A seasonal calendar mindset beats reactive banner-chasing: know which quarter your category actually discounts in, watch the post-holiday week for holiday-specific items, and remember that a few categories are constrained by real physical logistics rather than pure marketing timing.",
    ],
  },
  {
    slug: "how-to-spot-a-fake-deal",
    title: "How to Spot a Fake \"Deal\" (Before You Click Buy)",
    dek: "Five quick checks that catch most inflated \"was\" prices and manufactured urgency before you fall for them.",
    minutes: 5,
    body: [
      "Not every discount banner is lying, but a meaningful share of them are built on an inflated \"original\" price that was rarely, if ever, the item's real selling price. Here are five checks that catch most of it in under a minute.",
      "## 1. Check the actual price history, not the claimed one",
      "The single best defense is looking at a genuine price history chart (see our guide on reading one) rather than trusting the \"was $X\" text on the page. If the \"original\" price only appears for a day or two right before the sale started, it was very likely set specifically to make the discount look bigger.",
      "## 2. Compare the 90-day average, not the highest price ever charted",
      "A deal that beats the highest price the item has ever been listed at isn't necessarily a good deal — it just beats a number that may have only existed briefly. Compare against the 90-day average instead; that's a much more honest baseline for \"normal price.\"",
      "## 3. Be suspicious of manufactured urgency",
      "Countdown timers, \"only 2 left,\" and \"1,000 people are viewing this\" banners are frequently generic UI elements that reset or reappear regardless of real inventory. They're designed to rush a purchase decision — if you find yourself buying because of the timer rather than the actual price, slow down and check the chart first.",
      "## 4. Watch for a price that moves back up right after \"selling out\"",
      "If a \"limited time\" deal reliably reappears at the same or a very similar price every few weeks, it isn't limited — it's a recurring promotional price, and there's no need to panic-buy the first time you see it.",
      "## 5. Do the stacking math before, not after",
      "A deal that only looks good once you've added an uncertain coupon, an unconfirmed cashback rate, and a hoped-for rebate is not a confirmed deal yet — it's a plan. Confirm each piece actually applies at checkout before treating the stacked total as real.",
      "## The bottom line",
      "None of these checks take more than a few seconds once they're a habit. The goal isn't to distrust every discount — most retailers run real, honest promotions — it's to spend fifteen seconds verifying before a big purchase, the same way you'd glance at a price-per-unit label at the grocery store.",
    ],
  },
];

export function getArticle(slug: string): Article | undefined {
  return ARTICLES.find((a) => a.slug === slug);
}

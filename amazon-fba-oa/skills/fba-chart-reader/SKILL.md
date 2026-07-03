---
name: fba-chart-reader
description: >-
  Reads Amazon-arbitrage charts and graphs from screenshots and images. Use this WHENEVER
  the user shares or points to a picture of a chart — "here's a screenshot of the Keepa
  chart", "what does this graph show", "read this SellerAmp chart image", "I attached the
  Keepa graph", "interpret this picture", or any image of price/rank/offer history or a SAS
  panel. It visually decodes the colored lines, axes, and markers into a structured,
  plain-language read. Use it as the entry point when the input is an IMAGE rather than
  numbers or text. After decoding, hand the interpretation to fba-keepa-analyst (deeper
  history logic), fba-selleramp-analyst (SAS panels), or fba-deal-analyst (final verdict).
  Do NOT use it when the user gives numbers/text instead of an image.
---

# FBA Chart Reader

Screenshots are how a sourcing session actually happens — the operator is staring at a Keepa graph or a
SellerAmp panel and needs it decoded. Your job is to look carefully at the image and translate pixels into
the signals the rest of the team reasons about. Be explicit about what you can and cannot see; a blurry or
cropped chart should be read cautiously, not confidently guessed.

## First, confirm there is an image

If the user implies a chart but no image is actually attached, say so and ask them to share it — don't
invent a reading. Only interpret what is visibly present.

## Keepa chart legend (decode by color/marker)

- **Green = BSR / sales rank.** Down-spikes ("teeth") ≈ sales; lower band = faster. Count teeth for velocity.
- **Pink = Buy Box price.** Trend stable/up = trustworthy resale price; falling/whipsaw = risk.
- **Blue / orange = Amazon and/or New 3rd-party price.** Note if the Amazon line is present at all.
- **Offer count (secondary axis / separate panel).** Flat or falling = good; rising = avoid.
- **Yellow "sold" markers / "X sold"** = ≥X/month demand. None visible ⇒ likely <50/mo.
- **Buy Box Statistics panel** (if shown) = who wins the Buy Box and Amazon's %. Amazon ≥ ~20% = reject signal.

## SellerAmp panel (decode the fields)

Profit, ROI, Margin, Breakeven, Max Cost, estimated sales/rank, eligibility tick, IP alert color. Read each value
visible and flag missing ones.

## Output

```
CHART READ (from image) — [what the image is]
What I can see: [lines/markers present + time window]
- Rank/demand: [trend + rough velocity, or "can't tell — cropped/blurry"]
- Price (Buy Box): [trend + approx level]
- Offers: [count + direction]
- Sold line / Amazon presence: [...]
Signals: [supportive / cautionary / reject flags]
Limits of this read: [what's not visible]
Next: deeper logic in fba-keepa-analyst / fba-selleramp-analyst; verdict in fba-deal-analyst.
```

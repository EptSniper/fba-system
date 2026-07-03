# Answer flow — how a question becomes a cited answer

The retrieval + decision pipeline the assistant follows. Example question:
**"Can I sell this Target clearance deal on Amazon FBA?"**

```
                ┌─────────────────────────────────────────────┐
   question ──► │ 1. Embed query → search vector DB (chunks)   │
                │    hybrid: dense + keyword, then rerank       │
                └───────────────┬─────────────────────────────┘
                                │ top-k policy + rule chunks (with citations)
        ┌───────────────────────┴───────────────────────┐
        ▼                                                 ▼
┌─────────────────────┐                      ┌──────────────────────────┐
│  AM I ALLOWED?       │                      │  CAN I PROFIT?            │
│  • Listings          │                      │  • Keepa: BSR, price,     │
│    Restrictions      │                      │    offers, Buy-Box, 90d   │
│    (SP-API)          │                      │  • SellerAmp / scout ROI  │
│  • restricted/IP/    │                      │  • Revenue Calculator fee │
│    authenticity      │                      │  • buy cost + cashback    │
│  • condition +       │                      └─────────────┬────────────┘
│    invoice rules     │                                    │
│  • FBA eligibility   │                                    │
└──────────┬──────────┘                                     │
           └───────────────┬────────────────────────────────┘
                           ▼
            ┌───────────────────────────────────────────┐
            │ 8. Compose answer: verdict + WHY, each      │
            │    claim cited, confidence score, and the   │
            │    manual checks still required.            │
            └───────────────────────────────────────────┘
```

## The 8 steps
1. **Search** the Amazon knowledge base (RAG corpus) with the user's question.
2. **Pull** the most relevant policy / rule chunks (keep citations + collected date).
3. **Pull product data** from Keepa, SellerAmp, SP-API, or the scout's score.
4. **Check listing restrictions** (SP-API Listings Restrictions for the ASIN + account).
5. **Check FBA eligibility** (size/weight tier, hazmat, prep requirements).
6. **Check IP / authenticity risk** (brand on avoid-list, IP-Alert flag, invoices).
7. **Calculate fees + ROI** (Revenue Calculator assumptions; confirm in SellerAmp).
8. **Answer with citations + a confidence score**, always separating *can I profit*
   from *am I allowed*, and listing what the human must still verify by hand.

## Retrieval settings (starting point)
- Chunk size ~800 tokens, 100-token overlap (see `ingest.py`).
- Top-k = 8 for the policy leg, 5 for decision-rule leg; rerank to 4–6 final.
- Filter by `category` when the intent is clear (e.g. Policy vs Arbitrage decision rules).
- Always attach `citation` + `last_crawled_at` so the answer can date its sources.

## This connects to the rest of the system
- The **scout** (`../scout/`) already answers "can I profit?" (BSR/ROI/offers/Buy-Box +
  price-spike, offers-rising, Amazon-Buy-Box-share guards).
- This RAG corpus answers **"am I allowed?"** — the half the scout can't see from Keepa.
- The **control center** is where both surface for the user.

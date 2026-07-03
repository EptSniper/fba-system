"""
competitors.py — turn a competitor's catalog into seed product ideas.

Given a list of competitor ASINs (or a seller ID), surface their best performers
using Keepa velocity proxies. These become research seeds: niches/products worth
investigating yourself.

HONEST CONSTRAINT (stated plainly): exact private sales for another seller are NOT
available from Keepa or any sanctioned source. What we CAN see legitimately are
velocity proxies — Keepa 'Sales Rank Drops' (each drop approximates a sale) and
Buy Box stability / out-of-stock %. Everything below ranks on those proxies, not
on real sales figures. Treat the output as directional, not exact.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import keepa_client


def best_performers(asins: List[str], top_n: int = 10,
                    api=None) -> List[Dict[str, Any]]:
    """Rank competitor ASINs by velocity proxy and return the top N."""
    ranked = keepa_client.seller_catalog_signals(asins, api=api)
    return ranked[:top_n]


def best_performers_for_seller(seller_id: str, top_n: int = 10,
                               api=None) -> List[Dict[str, Any]]:
    """Pull a seller's catalog from Keepa, then rank it by velocity proxy."""
    asins = keepa_client.seller_asins(seller_id, api=api)
    return best_performers(asins, top_n=top_n, api=api)


def seed_ideas(asins: Optional[List[str]] = None, seller_id: Optional[str] = None,
               top_n: int = 10, api=None) -> List[Dict[str, Any]]:
    """
    Convenience entry point. Provide either a list of competitor ASINs or a
    seller_id. Returns ranked seed ideas with a short rationale per item.
    """
    if seller_id:
        ranked = best_performers_for_seller(seller_id, top_n=top_n, api=api)
    elif asins:
        ranked = best_performers(asins, top_n=top_n, api=api)
    else:
        raise ValueError("Provide either `asins` or `seller_id`.")

    for r in ranked:
        r["why"] = (
            f"velocity proxy {r.get('velocity_proxy', 0)} "
            f"(~{r.get('est_sales', '?')} est. units/mo from sales-rank drops; "
            f"OOS90 {r.get('oos_90', '?')}%). Proxy only — not exact sales."
        )
    return ranked


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python competitors.py <ASIN1,ASIN2,...>  |  seller:<SELLER_ID>")
        raise SystemExit(1)
    arg = sys.argv[1]
    if arg.startswith("seller:"):
        ideas = seed_ideas(seller_id=arg.split(":", 1)[1])
    else:
        ideas = seed_ideas(asins=arg.split(","))
    for i, x in enumerate(ideas, 1):
        print(f"{i:>2}. {x.get('asin')}  {x.get('title','')[:60]!r}  -> {x['why']}")

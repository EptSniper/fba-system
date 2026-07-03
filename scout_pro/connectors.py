"""
connectors.py — owned-account truth sources (SP-API, Ads API).

These are the source of STRONG realized labels (your own margins, units, returns,
PPC efficiency) per the paper. They require Amazon's OAuth (LWA refresh token,
client id/secret, role-based access) which can't be wired without your credentials,
so they ship as DOCUMENTED STUBS: correct method surface, clear guidance, and
graceful empty results so the rest of the system runs on Keepa + weak labels alone.

Wire these by implementing the marked TODOs with the official SDKs:
  - SP-API: Sales & Traffic report, Catalog Items, Product Pricing, FBA fees,
            returns, inventory; prefer Notifications over constant polling.
  - Ads API: Sponsored Products campaign/keyword reports (impressions, clicks,
            spend, attributed sales, ACOS, ROAS).
Respect token-bucket rate limits: batch, back off, prefer event-driven.
"""
from __future__ import annotations

from typing import Any, Dict, List

import config


class SPAPISource:
    """Amazon Selling Partner API — owned-account truth. STUB."""

    def __init__(self) -> None:
        self.ready = bool(config.SP_API_REFRESH_TOKEN and config.SP_API_CLIENT_ID
                          and config.SP_API_CLIENT_SECRET)

    def sales_and_traffic(self, start, end) -> List[Dict[str, Any]]:
        # TODO: call SP-API Sales & Traffic report; return per-ASIN units, sessions,
        # conversion, ordered product sales for the window.
        if not self.ready:
            return []
        raise NotImplementedError("Wire SP-API Sales & Traffic report here.")

    def returns(self, start, end) -> List[Dict[str, Any]]:
        # TODO: SP-API FBA returns report -> per-ASIN return counts/rates.
        return []

    def fees_and_inventory(self, asins: List[str]) -> Dict[str, Any]:
        # TODO: SP-API Product Fees + FBA Inventory -> realized fees, days of cover.
        return {}


class AdsSource:
    """Amazon Ads API — Sponsored Products PPC truth. STUB."""

    def __init__(self) -> None:
        self.ready = bool(config.ADS_API_REFRESH_TOKEN)

    def keyword_report(self, start, end) -> List[Dict[str, Any]]:
        # TODO: Ads API SP keyword report -> impressions/clicks/spend/attributed
        # sales/ACOS/ROAS per asin x keyword x day, write to ads_keyword_daily.
        if not self.ready:
            return []
        raise NotImplementedError("Wire Amazon Ads API keyword report here.")


def owned_account_available() -> bool:
    return SPAPISource().ready or AdsSource().ready

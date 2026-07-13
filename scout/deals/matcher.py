"""
scout/deals/matcher.py — the deal-to-ASIN matcher (Deal Finder Build Plan Prompt D2; Sourcing
& Review-Queue Plan Phase 2.2, 2026-07-13). The bridge `run_watch.py`'s own digest footer has
said was missing since it was written: "matching not yet built — these feed the scout as hints,
not buys." This is what turns a collected `deals` row into a candidate ASIN with a real,
verified buy price, instead of leaving every lead's cost at the OA_COGS_FRACTION 50%-of-price
guess (Finding A of SOURCING_AND_QUEUE_PLAN.md).

HONEST SCOPING NOTE — this is a real, working v1, but deliberately narrower than the Build
Plan's full Prompt D2 cascade, because two of the cascade's five steps aren't usable with what
actually exists in this environment today. Both are built as PLUGGABLE, self-activating seams —
neither is stubbed out or faked:

  - Step 2 (UPC path): Keepa's `code=` lookup (keepa_client.upc_lookup) is implemented and
    token-guarded, but UNVERIFIED against a live response — as of this writing zero collected
    `deals` rows carry a UPC (every currently-active source is UPC-less RSS/aggregate; only the
    not-yet-keyed Best Buy connector or best-effort clearance-page JSON-LD parsing can ever
    populate one). It activates automatically the moment a real UPC shows up.
  - Step 4 (LLM verification): Claude Haiku pairwise verification is implemented
    (_llm_verify below), gated on a real-looking ANTHROPIC_API_KEY — the one in scout/.env
    today is a 9-character placeholder, so this step degrades honestly (one log line per run,
    never a fabricated "yes") until a real key is added.
  - Step 3 (title path, the one currently live): candidates come from a Keepa product-term
    search (keepa_client.search_by_term), ranked by attribute agreement (brand/pack/size, via
    the D1 normalizer) + a plain difflib string-similarity score on the normalized core_title —
    NOT the Build Plan's bge-base-en-v1.5 embedding + cosine step. Reason: that model lives only
    in knowledge-rag's environment (sentence-transformers/torch), which scout does not depend on
    today, and adding a heavy new ML dependency to scout's tiny-footprint environment for a
    ranking signal this module doesn't yet have live data to justify is not a call to make
    silently. Flagged as a named follow-up, not a silent downgrade.

Because of the above, composite_confidence()'s algorithmic-only branch (no UPC, no LLM) is
capped BELOW the brain's current confidenceBands.autoAccept, always — see its own docstring.
Concretely, under the confidenceBands shipped with this change (autoAccept=0.90), every match
this module produces today lands in the human review band or is dropped, never auto-accepted —
neither the UPC path (no real UPC exists in any collected deal yet) nor the LLM path (no real
ANTHROPIC_API_KEY configured yet) is actually reachable with live data right now. That is the
CORRECT, honest behavior given the actual evidence available. Note this is a property of the
CURRENT brain config plus the current absence of live UPC/LLM data, not a hardcoded invariant of
the code: the two real anchors (UPC-verified ~=0.95, LLM-yes ~=0.85) are fixed real-world
confidence estimates from the Build Plan's own research, not values that track autoAccept — if
autoAccept is ever tuned below 0.85 via fba-brain-updater, an LLM-confirmed match could legitimately
clear it. That would be the config behaving as configured, not a bug.

SP-API WIRING (added this change, 2026-07-13): candidate generation now tries the FREE SP-API
Catalog Items API first (spapi.catalog_lookup_upc for the UPC path, the new
spapi.catalog_search_keywords for the title path) whenever spapi.configured() is true, with the
existing Keepa paths (upc_lookup / search_by_term) kept as the fallback when SP-API is
unconfigured, unavailable, or resolves zero ASINs. Whichever path finds candidate ASINs, they are
run through a new free eligibility pre-filter (_eligible_for_matching /
spapi.get_listings_restrictions) BEFORE any Keepa token is spent enriching them — a NOT_ELIGIBLE
ASIN is dropped before it ever reaches keepa_client.enrich(), and an APPROVAL_REQUIRED one is kept
but flagged ("needs-ungating" in the match's reason string), mirroring pipeline.py's own
"keep but tag" convention for that status. apply_verified_matches() re-checks eligibility
directly (via _eligible_for_matching, which reuses get_listings_restrictions' own 7-day cache,
so this is cheap) immediately before writing anything — rather than trusting the free-text
"needs-ungating" flag from match time, which could be stale by the time a human approves the
match — and skips a NOT_ELIGIBLE ASIN entirely (never backfills real-looking economics for
something that can't be sold at all), while an APPROVAL_REQUIRED one still gets its real
numbers backfilled but is tagged via leads.gated_status="approval_required" so it isn't
indistinguishable from a plain ALLOWED lead. apply_verified_matches() also now tries a real
spapi.get_fees_estimate() before falling back to the rule-based scoring.estimate_oa_profit_roi,
recording which source won via the fee_source_spapi/fee_source_estimate counters.

HONEST STATUS of that wiring: implemented and unit-tested with mocked spapi responses, but NOT
yet live-verified — spapi.configured() reflects only whether SP_API_LWA_CLIENT_ID/SECRET/
REFRESH_TOKEN are non-empty strings, and as of this writing scout/.env's copies of all three are
still short placeholder values (confirmed by length, never by printing the actual values), so any
real call made through this path today would hit Amazon's LWA endpoint with fake credentials and
fail — every call site here catches that and degrades to the pre-existing Keepa-only /
rule-based-fee behavior, exactly the same honesty convention this file already uses for the
UPC/LLM paths above.

OUT OF SCOPE this session (named, not silently skipped):
  - Prompt D3's runner integration — wiring deal-first candidates into scout/run_daily.py so a
    verified match with NO pre-existing lead can become a brand-new gate-checked lead. Building
    that now, in a rush, risks the one thing every hard-gate rule in this project exists to
    prevent: a candidate reaching `leads` without passing eligibility/compliance/AVOID-brand
    checks. apply_verified_matches() below only ever enriches a lead that ALREADY exists (found
    via scout's normal Keepa discovery, already gate-checked) — never creates one.
  - A genuine 30-pair hand-verified gold set (the Build Plan's own Prompt D2 step 7 explicitly
    frames this as Mehmet's task, alongside the other "no code" actions in sec 5) — goldset.py
    ships with a small SYNTHETIC fixture for exercising the scoring math in tests, honestly
    labeled as such, not as verified real-world pairs.
"""
from __future__ import annotations

import difflib
import json
import os
from typing import Any, Dict, List, Optional

import config
import db
import discord_router
import keepa_client
import redact
import scoring
import spapi

from . import brain_config, normalize

try:
    import anthropic
except Exception:  # pragma: no cover - package optional at import time
    anthropic = None

# Haiku, not Sonnet (analyst.py's ANALYST_MODEL) — the Build Plan's own cost rationale (sec 3
# step 4: "~$1.50-4 per 1,000 deals all-in" only holds at the cheap tier).
DEAL_MATCHER_MODEL = os.getenv("DEAL_MATCHER_MODEL", "claude-haiku-4-5-20251001")
LLM_MAX_TOKENS = 400
# Only escalate candidates whose algorithmic similarity already clears this floor to the LLM —
# Build Plan sec 3 step 3's own "cosine floor ~0.75 to prune" instruction, adapted to the
# string-similarity substitute (cost + noise control: don't spend an LLM call on a candidate
# that's obviously not the same product).
LLM_ESCALATION_FLOOR = 0.75
CANDIDATES_PER_DEAL = 5
MATCHES_WRITTEN_PER_DEAL = 3  # cap deal_matches rows per deal (avoid queue clutter from one item)

SYSTEM_PROMPT = (
    "You are verifying whether a retail-store deal listing and an Amazon product listing are "
    "the EXACT SAME sellable unit. Brand, core item, SIZE, and PACK COUNT must ALL match — a "
    "different pack count (e.g. a 1-pack retail deal vs. a 2-pack Amazon listing), a different "
    "size/volume (16oz vs 24oz), a different color/variant, or a bundle with extra items are "
    "NOT a match even when the brand and core item name look identical. When genuinely "
    "uncertain, answer 'unsure' rather than guessing 'yes' — a false 'yes' here can cause a "
    "real purchase against the wrong item. Call submit_match_verdict with your answer."
)

MATCH_TOOL = {
    "name": "submit_match_verdict",
    "description": "Submit whether the deal and the Amazon candidate are the same sellable unit.",
    "input_schema": {
        "type": "object",
        "properties": {
            "match": {"type": "string", "enum": ["yes", "no", "unsure"]},
            "pack_match": {"type": "boolean"},
            "confidence": {"type": "number", "description": "0-1, this model's own confidence."},
            "reason": {"type": "string", "description": "<=40 words."},
        },
        "required": ["match", "pack_match", "confidence", "reason"],
    },
}

_llm_warned = False
_llm_calls_this_run = 0

# Discovery telemetry (free SP-API vs paid Keepa candidate generation, + how many candidates the
# free eligibility pre-filter dropped before a Keepa token was ever spent on them) — reset at the
# top of each run() call, same module-global convention as _llm_calls_this_run above.
_discovery_stats_this_run = {"spapi": 0, "keepa": 0, "dropped_ineligible": 0}


def _llm_configured() -> bool:
    """Same real-vs-placeholder gate every other keyed module in this project uses (analyst.py,
    spapi.py) — a bare `bool(env var)` would treat scout/.env's 9-character placeholder as
    configured and attempt (and fail) a real API call every run."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return bool(key) and len(key) > 40 and anthropic is not None


def _llm_verify(deal: Dict[str, Any], candidate: Dict[str, Any],
                client: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """One Claude Haiku pairwise same-product check, or None (unavailable/failed — NEVER a
    fabricated verdict). Logs the unavailable case exactly once per process, not once per
    candidate, so a whole run's worth of skips doesn't spam the log."""
    global _llm_warned, _llm_calls_this_run
    if not _llm_configured():
        if not _llm_warned:
            print("[deals.matcher] ANTHROPIC_API_KEY not set (or looks like a placeholder) — "
                 "LLM verification skipped this run; title-path matches stay capped below "
                 "auto-accept (see composite_confidence's docstring).")
            _llm_warned = True
        return None
    payload = {
        "deal": {"retailer": deal.get("retailer"), "title": deal.get("title_raw"),
                 "brand": deal.get("brand"), "price": deal.get("price_current")},
        "candidate": {"asin": candidate.get("asin"), "title": candidate.get("title"),
                      "brand": candidate.get("brand"), "price": candidate.get("price")},
    }
    try:
        cl = client or anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = cl.messages.create(
            model=DEAL_MATCHER_MODEL, max_tokens=LLM_MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            tools=[MATCH_TOOL], tool_choice={"type": "tool", "name": "submit_match_verdict"},
        )
    except Exception as e:
        print(f"[deals.matcher] LLM verification call failed: {redact.redact(str(e))}")
        return None
    _llm_calls_this_run += 1
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_match_verdict":
            return block.input
    return None


def _eligible_for_matching(asin: str) -> "tuple":
    """(is_eligible, needs_ungating). True/False unless spapi is unconfigured, in which case
    always (True, False) — an unconfigured SP-API must never block matching (honest no-op, not
    a false rejection). NOT_ELIGIBLE -> (False, False), meaning drop this ASIN before spending a
    Keepa token on it (the free pre-filter the token-economy directive asks for).
    APPROVAL_REQUIRED -> (True, True) — still worth matching/pricing, just flagged for a human;
    matches pipeline.py's own "keep but tag" philosophy for this exact status. Never raises —
    an SP-API hiccup must never break candidate generation, matching pipeline._check_eligibility's
    own try/except-and-continue convention."""
    if not spapi.configured():
        return True, False
    try:
        elig = spapi.get_listings_restrictions(asin)
    except Exception as e:
        print(f"[deals.matcher] SP-API eligibility check failed for {asin} "
             f"({redact.redact(str(e))}) — treating as eligible (never block matching on an "
             "SP-API hiccup)")
        return True, False
    status = elig.get("status")
    if status == "NOT_ELIGIBLE":
        return False, False
    if status == "APPROVAL_REQUIRED":
        return True, True
    return True, False


def _filter_eligible(asins: List[str]) -> "tuple[List[str], Dict[str, bool]]":
    """Runs _eligible_for_matching over every ASIN, dropping NOT_ELIGIBLE ones BEFORE any Keepa
    token is spent enriching them (the free pre-filter the token-economy directive asks for) and
    tallying the drops into this module's discovery telemetry so run() can report them. Applies
    regardless of which path (SP-API catalog search or Keepa fallback) found the ASINs in the
    first place — eligibility is an independent capability, gated only on spapi.configured().
    Returns (surviving_asins, needs_ungating_by_asin)."""
    survivors: List[str] = []
    needs_ungating: Dict[str, bool] = {}
    for asin in asins:
        ok, ungating = _eligible_for_matching(asin)
        if not ok:
            _discovery_stats_this_run["dropped_ineligible"] += 1
            continue
        survivors.append(asin)
        if ungating:
            needs_ungating[asin] = True
    return survivors, needs_ungating


def _tag_and_count(products: List[Dict[str, Any]], method: str, discovery_source: str,
                   needs_ungating: Dict[str, bool]) -> List[Dict[str, Any]]:
    """Shared tagging step for both candidate paths below: stamps `_method` (as before),
    `_discovery_source` ("spapi"/"keepa", for run()'s free-vs-paid telemetry), and
    `_needs_ungating` (from the eligibility pre-filter) onto each enriched product, and tallies
    the discovery-source count."""
    for p in products:
        p["_method"] = method
        p["_discovery_source"] = discovery_source
        if needs_ungating.get(p.get("asin")):
            p["_needs_ungating"] = True
        _discovery_stats_this_run[discovery_source] = _discovery_stats_this_run.get(discovery_source, 0) + 1
    return products


def _resolve_candidates(method: str, spapi_call, spapi_parse, keepa_fn,
                        api=None) -> List[Dict[str, Any]]:
    """Shared try-SP-API/fallback-to-Keepa/filter-eligible/enrich/tag scaffold for
    _upc_candidates and _title_candidates below. Code review finding (2026-07-13): the two
    functions used to duplicate this five-step shape almost verbatim, differing only in which
    lookup functions and result-shape parsing (`asins` list for the UPC path vs `results` list of
    dicts for the title path) they used — exactly the two things this helper now takes as
    arguments instead of re-deriving.

    spapi_call() -> the raw SP-API result dict, or raises (only this call is wrapped in
    try/except, same as before: an SP-API network/auth failure falls back to Keepa, but a bug in
    parsing that result is a real bug, not something to silently swallow).
    spapi_parse(raw) -> List[str] of ASINs extracted from a successful (`available`) raw result.
    keepa_fn() -> List[str] of ASINs from the Keepa fallback path.

    The eligibility pre-filter below is now unconditional (previously wrapped in its own
    `if spapi.configured():` guard at each call site) — that outer guard was redundant with the
    check _eligible_for_matching already performs per ASIN (returns (True, False), an honest
    no-op, for every ASIN when SP-API is unconfigured), a second 2026-07-13 code review finding.
    Removing it changes nothing observable: unconfigured, _filter_eligible now degrades to a
    same-list pass-through instead of being skipped outright."""
    asins: List[str] = []
    discovery_source = "keepa"
    if spapi.configured():
        try:
            raw = spapi_call()
        except Exception as e:
            print(f"[deals.matcher] SP-API {method} discovery failed ({redact.redact(str(e))}) — "
                 "falling back to Keepa")
            raw = {"available": False}
        if raw.get("available"):
            parsed = spapi_parse(raw)
            if parsed:
                asins = parsed
                discovery_source = "spapi"

    if not asins:
        asins = keepa_fn()
        discovery_source = "keepa"

    if not asins:
        return []

    asins, needs_ungating = _filter_eligible(asins)
    if not asins:
        return []

    products = keepa_client.enrich(asins, api=api)
    return _tag_and_count(products, method, discovery_source, needs_ungating)


def _upc_candidates(deal: Dict[str, Any], api=None) -> List[Dict[str, Any]]:
    """UPC -> candidate ASIN(s). Tries the free SP-API Catalog Items lookup
    (spapi.catalog_lookup_upc) first when spapi.configured() is true; falls back to Keepa's paid
    code lookup (keepa_client.upc_lookup) when SP-API is unconfigured, unavailable, or resolves
    zero ASINs. Either way, candidate ASINs pass through the eligibility pre-filter before
    keepa_client.enrich() is ever called — Keepa's job here is pricing only, never discovery,
    once a candidate ASIN exists. See _resolve_candidates for the shared scaffold."""
    upc = deal.get("upc")
    if not upc:
        return []

    def _parse(raw: Dict[str, Any]) -> List[str]:
        return [a for a in (raw.get("asins") or []) if a][:CANDIDATES_PER_DEAL]

    return _resolve_candidates(
        "upc",
        spapi_call=lambda: spapi.catalog_lookup_upc(upc),
        spapi_parse=_parse,
        keepa_fn=lambda: (keepa_client.upc_lookup([upc], api=api).get(upc) or [])[:CANDIDATES_PER_DEAL],
        api=api,
    )


def _title_candidates(deal: Dict[str, Any], attrs: Dict[str, Any], api=None) -> List[Dict[str, Any]]:
    """Title/brand -> candidate ASIN(s). Tries the free SP-API Catalog Items keyword search
    (spapi.catalog_search_keywords) first when spapi.configured() is true; falls back to Keepa's
    paid product-search (keepa_client.search_by_term, 10 tokens/term) when SP-API is unconfigured,
    unavailable, or resolves zero ASINs. Same eligibility pre-filter + enrich()-for-pricing-only
    flow as _upc_candidates above. See _resolve_candidates for the shared scaffold."""
    term = " ".join(x for x in (attrs.get("brand"), attrs.get("core_title")) if x).strip()
    term = term or (deal.get("title_raw") or "").strip()
    if not term:
        return []

    def _parse(raw: Dict[str, Any]) -> List[str]:
        return [r.get("asin") for r in (raw.get("results") or []) if r.get("asin")]

    return _resolve_candidates(
        "title",
        spapi_call=lambda: spapi.catalog_search_keywords(term, brand=attrs.get("brand"),
                                                         limit=CANDIDATES_PER_DEAL),
        spapi_parse=_parse,
        keepa_fn=lambda: keepa_client.search_by_term(term, limit=CANDIDATES_PER_DEAL, api=api),
        api=api,
    )


def _attr_agreement(deal_attrs: Dict[str, Any], cand_attrs: Dict[str, Any]) -> "tuple":
    """(brand_match, pack_match, size_match). brand_match/size_match are None when either side
    doesn't state one (unknown, not a disagreement) — pack_match is always a definite True/False
    since normalize.extract_attributes() already defaults an unstated pack_count to 1 (most
    listings are single units; see that module's own docstring)."""
    d_brand = (deal_attrs.get("brand") or "").strip().lower()
    c_brand = (cand_attrs.get("brand") or "").strip().lower()
    brand_match = None if (not d_brand or not c_brand) else (d_brand == c_brand)
    pack_match = deal_attrs.get("pack_count") == cand_attrs.get("pack_count")
    d_size, c_size = deal_attrs.get("size_value"), cand_attrs.get("size_value")
    if d_size is None or c_size is None:
        size_match = None
    else:
        size_match = (deal_attrs.get("size_unit") == cand_attrs.get("size_unit")
                      and abs(d_size - c_size) < 1e-6)
    return brand_match, pack_match, size_match


def _title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _price_sane(deal_price: Optional[float], candidate_price: Optional[float]) -> bool:
    """False only when both prices are known AND the ratio suggests a pack/size mismatch
    (ai-brain.json dealFinder.priceSanity.maxAmazonToRetailRatio). Unknown price on either side
    -> True (can't flag what you can't compare — never a false alarm from missing data)."""
    if not deal_price or not candidate_price or deal_price <= 0:
        return True
    ratio = candidate_price / deal_price
    return ratio <= brain_config.price_sanity_ratio()


def composite_confidence(method: str, brand_match: Optional[bool], pack_match: bool,
                         size_match: Optional[bool], similarity: float, price_sane: bool,
                         llm_result: Optional[Dict[str, Any]]) -> float:
    """Deal Finder Build Plan sec 3 step 5's composite model, honestly adapted to what's
    actually verifiable today (see the module docstring). The two ways the original design
    reaches its auto-accept anchor are preserved exactly:

      - UPC-verified + attributes agree ~= 0.95 (method == "upc" and every attribute agrees)
      - LLM-yes + pack-match + sane price ~= 0.85 (a real LLM verdict, not assumed)

    Anything else — including a strong ALGORITHMIC-ONLY signal (high string similarity, brand +
    pack agreement, no LLM) — is capped at auto_accept - 0.05: it can land in the review band,
    never above it. Fabricating auto-accept-level confidence from a weaker signal than the two
    anchors above would be exactly the "no fabricated confidence" violation this project's
    guardrails exist to prevent, no matter how good the string match looks.

    KNOWN-MISMATCH VETO (added after the gold-set harness caught it live, 2026-07-13): a
    same-name product with a DIFFERENT stated brand, pack count, or size is the Build Plan's own
    documented #1 matching failure mode — and core_title() deliberately STRIPS pack/size phrases
    before the string-similarity comparison (so it can compare the item name alone), which means
    similarity alone is structurally blind to exactly the signal that should veto these. A known
    (not merely unknown/None) disagreement on any of the three therefore hard-caps confidence
    below the review floor, full stop — no similarity score, however high, overrides it."""
    bands = brain_config.confidence_bands()
    auto = bands["auto_accept"]

    known_mismatch = (brand_match is False) or (pack_match is False) or (size_match is False)
    if known_mismatch:
        return round(min(0.1, bands["review"] * 0.5), 3)

    if method == "upc" and brand_match and pack_match and size_match is not False:
        conf = 0.95
    elif llm_result and llm_result.get("match") == "yes" and llm_result.get("pack_match"):
        conf = 0.85
    else:
        agreement = ((0.40 if brand_match else 0.15)
                     + (0.35 if pack_match else 0.15)
                     + (0.25 if size_match else 0.12))
        conf = min(0.55 * similarity + 0.45 * agreement, auto - 0.05)

    if not price_sane:
        # A flag, not a discard — a genuinely deep, sane flip can still look "too good" on a
        # naive ratio; this lowers confidence (and the reason string says why) rather than
        # silently dropping a real candidate.
        conf = conf * 0.7

    return round(max(0.0, min(conf, 0.99)), 3)


def route(confidence: float) -> str:
    bands = brain_config.confidence_bands()
    if confidence >= bands["auto_accept"]:
        return "auto"
    if confidence >= bands["review"]:
        return "review"
    return "discard"


def match_deal(deal: Dict[str, Any], api=None) -> List[Dict[str, Any]]:
    """Score every candidate for one deal row. Returns a list of
    {asin, confidence, route, method, pack_match, llm_reason, similarity} dicts, highest
    confidence first — [] if no candidates were found at all (nothing to write)."""
    attrs = normalize.extract_attributes(deal.get("title_raw") or "", deal.get("brand"))

    candidates = _upc_candidates(deal, api=api)
    if not candidates:
        candidates = _title_candidates(deal, attrs, api=api)
    if not candidates:
        return []

    scored = []
    for cand in candidates:
        if not cand.get("asin"):
            continue
        cand_attrs = normalize.extract_attributes(cand.get("title") or "", cand.get("brand"))
        brand_match, pack_match, size_match = _attr_agreement(attrs, cand_attrs)
        similarity = _title_similarity(attrs.get("core_title"), cand_attrs.get("core_title"))
        price_sane = _price_sane(deal.get("price_current"), cand.get("price"))
        method = cand.get("_method", "title")

        llm_result = None
        if method == "title" and similarity >= LLM_ESCALATION_FLOOR:
            llm_result = _llm_verify(deal, cand)

        confidence = composite_confidence(method, brand_match, pack_match, size_match,
                                          similarity, price_sane, llm_result)
        reason_bits = [f"{method} match", f"similarity={similarity:.2f}",
                      f"brand={'y' if brand_match else 'n'}", f"pack={'y' if pack_match else 'n'}"]
        if not price_sane:
            reason_bits.append("price-sanity flag")
        if cand.get("_needs_ungating"):
            reason_bits.append("needs-ungating")
        if llm_result:
            reason_bits.append(f"llm={llm_result.get('match')}: {llm_result.get('reason', '')}")
        scored.append({
            "asin": cand["asin"], "confidence": confidence, "route": route(confidence),
            "method": method, "pack_match": pack_match,
            "llm_reason": "; ".join(reason_bits)[:500],
        })

    scored.sort(key=lambda s: s["confidence"], reverse=True)
    return scored


def run(limit: int = 50, dry_run: bool = False, notify: bool = True, api=None) -> Dict[str, Any]:
    """Batch-process `deals` rows with status='new'. Writes deal_matches rows for every
    candidate that clears the review floor (route != "discard"), up to
    MATCHES_WRITTEN_PER_DEAL per deal. A discard-band candidate is counted in telemetry but NOT
    written — migration 003's deal_matches table has no status column to keep a "discarded, kept
    for negative-example learning" row out of the live human review queue (getPendingDealMatches
    has no confidence filter), and adding one is a schema change outside this session's scope.
    Named follow-up, not a silent gap.

    Marks each processed deal 'matched' (>=1 row written) or 'discarded' (no candidates, or
    every candidate fell below the review floor) so a re-run of run() doesn't re-attempt it
    forever — see db.update_deal_status()."""
    global _llm_calls_this_run
    _llm_calls_this_run = 0
    for k in _discovery_stats_this_run:
        _discovery_stats_this_run[k] = 0
    deals_to_match = db.get_deals_by_status("new", limit=limit)
    counts = {"processed": 0, "auto": 0, "review": 0, "discard": 0, "no_candidates": 0,
             "matches_written": 0, "llm_calls": 0,
             "discovery_spapi": 0, "discovery_keepa": 0, "dropped_ineligible": 0}

    # Code review finding (2026-07-13): build ONE Keepa client for the whole batch instead of
    # letting each candidate lookup construct its own via keepa_client.get_client() (which
    # itself does a status/token-bank network call) — for `limit` deals that was up to ~2x
    # `limit` client constructions per run instead of 1. Falls back to api=None (every callee
    # already degrades to constructing its own) if Keepa isn't configured at all.
    if api is None and keepa_client._KEEPA and config.KEEPA_KEY:
        try:
            api = keepa_client.get_client()
        except Exception as e:
            print(f"[deals.matcher] Keepa client unavailable ({redact.redact(str(e))}) — "
                 "candidate generation will be skipped this run")

    for deal in deals_to_match:
        counts["processed"] += 1
        scored = match_deal(deal, api=api)
        if not scored:
            counts["no_candidates"] += 1
            if not dry_run:
                db.update_deal_status(deal["id"], "discarded")
            continue

        wrote_any = False
        for cand in scored[:MATCHES_WRITTEN_PER_DEAL]:
            counts[cand["route"]] += 1
            if cand["route"] == "discard":
                continue
            wrote_any = True
            counts["matches_written"] += 1
            if not dry_run:
                db.upsert_deal_match(deal["id"], cand["asin"], cand["confidence"], cand["method"],
                                     pack_match=cand["pack_match"], llm_reason=cand["llm_reason"])
        # Any candidates beyond the cap are simply not written this run — a re-run when the deal
        # is still 'new' would reconsider them, but a deal is marked 'matched'/'discarded' below
        # regardless, so in practice a capped-out deal's extra candidates are dropped. Acceptable
        # for v1 (MATCHES_WRITTEN_PER_DEAL=3 comfortably covers real candidate counts observed).
        if not dry_run:
            db.update_deal_status(deal["id"], "matched" if wrote_any else "discarded")

    counts["llm_calls"] = _llm_calls_this_run
    counts["discovery_spapi"] = _discovery_stats_this_run["spapi"]
    counts["discovery_keepa"] = _discovery_stats_this_run["keepa"]
    counts["dropped_ineligible"] = _discovery_stats_this_run["dropped_ineligible"]
    if notify and not dry_run:
        try:
            _notify_run(counts)
        except Exception as e:
            print(f"[deals.matcher] notify failed (non-fatal): {redact.redact(str(e))}")
    return counts


def _notify_run(counts: Dict[str, Any]) -> None:
    if not counts.get("processed"):
        return
    embed = {
        "title": "Deal matcher run",
        "description": (f"{counts['processed']} deal(s) processed — "
                        f"{counts['auto']} auto, {counts['review']} to review, "
                        f"{counts['discard']} discarded, {counts['no_candidates']} no candidates."),
        "color": 0x36D399 if counts["matches_written"] else 0x8B9BB0,
        "fields": [
            {"name": "Matches written", "value": str(counts["matches_written"]), "inline": True},
            {"name": "LLM calls", "value": str(counts["llm_calls"]), "inline": True},
        ],
    }
    discord_router.send("retail_deals", embed)


# ----------------------------------------------------------------------------
# Phase 2.3 — apply a verified match to its lead's real cost fields.
# ----------------------------------------------------------------------------
def apply_verified_matches(limit: int = 50, dry_run: bool = False) -> Dict[str, Any]:
    """For every deal_matches row a human approved OR whose algorithmic confidence already
    cleared the brain's auto-accept band (currently unreachable via the title-only path with no
    live LLM — see composite_confidence's docstring; reachable once a real UPC + full attribute
    agreement occurs), backfill the corresponding LEAD's buy_cost/source_store/source_url/
    profit/roi with the real deal economics, replacing the OA_COGS_FRACTION 50%-of-price
    assumption for that one lead.

    Only ever enriches a lead that ALREADY EXISTS (found via scout's own normal Keepa discovery,
    which already ran the hard gates) — never creates one. A verified match with no matching
    lead is skipped, not fabricated into a new ungated one (see the module docstring for why
    deal-first lead creation is Prompt D3 scope, not this).

    'First verified source wins' in v1: a lead that already has a source_store is skipped rather
    than re-evaluated against a second candidate source — a documented simplification (choosing
    the BEST of several sources is a real future improvement, not built here).

    FIXED (code review, 2026-07-13 — the finding survived an independent verify pass): the
    eligibility pre-filter's `_needs_ungating` flag used to only ever surface as free text
    buried inside a deal_matches row's llm_reason column, which this function never read —
    an APPROVAL_REQUIRED match could get its real buy_cost/source/profit/roi written onto a
    lead exactly as if it were a plain ALLOWED item, with nothing on the lead itself
    distinguishing "sourced and ready to buy" from "sourced, but Amazon hasn't approved you to
    list it yet." Now re-checks eligibility directly (via _eligible_for_matching, which uses
    get_listings_restrictions' own 7-day cache, so this is cheap) before ANY write: a
    NOT_ELIGIBLE ASIN is skipped entirely (never fabricates real-looking economics for
    something that can't be sold at all), and an APPROVAL_REQUIRED one still gets its real
    numbers backfilled — they ARE real — but tagged via leads.gated_status="approval_required"
    so a human sees it isn't immediately buyable.

    KNOWN GAP (code review, 2026-07-13): an auto-accept-band match is applied here WITHOUT
    waiting for a human — that is the Build Plan's own intended meaning of "auto-accept" (sec 3
    step 5: ">=0.90 -> straight to the scout's rater"), not an oversight. But the row still isn't
    excluded from the control-center's review queue (getPendingDealMatches has no confidence
    ceiling), so a human COULD later reject it there — and if they do, this function does not
    currently revert an already-applied lead's buy_cost/source_store. Currently unreachable with
    live data (see the module docstring: no real UPC or LLM confirmation exists yet, so nothing
    reaches the auto-accept band today) — a real follow-up once it becomes reachable, not fixed
    here."""
    bands = brain_config.confidence_bands()
    ready = db.get_deal_matches_ready_to_apply(bands["auto_accept"], limit=limit)
    counts = {"checked": 0, "applied": 0, "skipped_rejected": 0, "skipped_no_lead": 0,
             "skipped_already_sourced": 0, "skipped_incomplete_data": 0,
             "skipped_not_eligible": 0, "applied_needs_ungating": 0,
             "fee_source_spapi": 0, "fee_source_estimate": 0}

    for dm in ready:
        counts["checked"] += 1
        if dm.get("human_verdict") == "reject":
            counts["skipped_rejected"] += 1
            continue
        asin = dm.get("asin")
        deal = dm.get("deals") or {}
        price_current = deal.get("price_current")
        if not asin or not price_current or price_current <= 0:
            counts["skipped_incomplete_data"] += 1
            continue

        # Re-check eligibility right before writing (cheap — get_listings_restrictions has its
        # own 7-day cache) rather than trusting a stale _needs_ungating flag buried in this
        # deal_matches row's llm_reason text, which this function never parsed. NOT_ELIGIBLE
        # means never write real-looking economics for something that can't be sold at all.
        is_eligible, needs_ungating = _eligible_for_matching(asin)
        if not is_eligible:
            counts["skipped_not_eligible"] += 1
            continue

        lead = db.get_lead(asin)
        if not lead:
            counts["skipped_no_lead"] += 1
            continue
        if lead.get("source_store"):
            counts["skipped_already_sourced"] += 1
            continue
        sell_price = lead.get("sell_price")
        if not sell_price or sell_price <= 0:
            counts["skipped_incomplete_data"] += 1
            continue

        stack = brain_config.discount_stack(deal.get("retailer") or "")
        # Code review finding (2026-07-13): discount_stack() is a MANUALLY-maintained brain
        # table with no upstream validation (its own docstring: "no API exists for these
        # rates"). Nothing enforced cashback_pct + giftcard_pct <= 1.0 before this — a
        # data-entry slip (e.g. 0.6 typed instead of 0.06) would drive buy_cost negative,
        # which then makes cogs_fraction negative and scoring.estimate_oa_profit_roi silently
        # returns roi=None (its cogs>0 guard) while profit gets INFLATED (subtracting a
        # negative cogs) — a fabricated, artificially-high profit written straight to a real
        # lead. Clamp the combined stack to [0, 0.95] (never a 100%-or-more "discount").
        stack_fraction = max(0.0, min(stack["cashback_pct"] + stack["giftcard_pct"], 0.95))
        buy_cost = round(price_current * (1 - stack_fraction), 2)
        weight_lb = (lead.get("features_snapshot") or {}).get("weight_lb")

        # Real SP-API fees when available (spapi.get_fees_estimate) instead of the rule-based
        # estimate — never raises: an SP-API hiccup must never break this backfill, it just
        # falls back to the existing v1 estimate path exactly as before.
        fees = None
        if spapi.configured():
            try:
                fees = spapi.get_fees_estimate(asin, sell_price)
            except Exception as e:
                print(f"[deals.matcher] SP-API fee estimate failed for {asin} "
                     f"({redact.redact(str(e))}) — falling back to the rule-based estimate")
                fees = None

        if (fees and fees.get("available") and fees.get("referral_fee") is not None
                and fees.get("fba_fee") is not None):
            profit, roi = scoring.estimate_oa_profit_roi_real_fees(
                sell_price, buy_cost, fees["referral_fee"], fees["fba_fee"], weight_lb=weight_lb)
            counts["fee_source_spapi"] += 1
        else:
            cogs_fraction = buy_cost / sell_price
            profit, roi = scoring.estimate_oa_profit_roi(sell_price, weight_lb,
                                                          cogs_fraction=cogs_fraction,
                                                          category=lead.get("category"))
            counts["fee_source_estimate"] += 1
        counts["applied"] += 1
        gated_status = "approval_required" if needs_ungating else None
        if needs_ungating:
            counts["applied_needs_ungating"] += 1
        if not dry_run:
            db.update_lead_source(asin, buy_cost, deal.get("retailer"), deal.get("url"),
                                  profit, roi, gated_status=gated_status)

    return counts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the deal-to-ASIN matcher.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply-only", action="store_true",
                        help="skip matching; only apply already-verified matches to leads")
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args()
    if not args.apply_only:
        result = run(limit=args.limit, dry_run=args.dry_run, notify=not args.no_notify)
        print(json.dumps(result, indent=2))
    applied = apply_verified_matches(limit=args.limit, dry_run=args.dry_run)
    print(json.dumps(applied, indent=2))

"""
scout/signals/calendar.py — pure calendar/seasonality features (Session 55, free signal-type
features). No API calls, no I/O beyond reading ai-brain.json's operations.seasonal2026/
majorHolidays blocks — every function here is a deterministic function of a date.

Every distance function is computed relative to an EXPLICIT `as_of` date (never "today" read
internally) so the exact same code backfills historical rows (backtest simulation_date, lead
capture date, shadow checkpoint_day) as computes the live value for a fresh Keepa read — the
leakage-safety property this project already enforces for Keepa-derived features
(scout/backtest.py's strict `< as_of` boundary) extends naturally to these: a date-based feature
can only ever see its OWN as_of, never a "current" date that would leak the future into a
historical row.

APPROXIMATION, documented once here rather than at every call site: Prime Day's exact dates shift
year to year (Amazon announces them); ai-brain.json operations.seasonal2026.primeDayWindow only
encodes 2026's real window (June 23-26). days_to_prime_day() treats that window's month/day as a
RECURRING annual anchor for any other year — the best available proxy without a live lookup, and
a good enough signal for "how close are we to the summer sourcing window," not a claim that
Prime Day literally always falls on June 23-26.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")


def _brain_operations() -> Dict[str, Any]:
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            brain = json.load(f) or {}
        return brain.get("operations") or {}
    except Exception:
        return {}


def _seasonal2026() -> Dict[str, Any]:
    return _brain_operations().get("seasonal2026") or {}


def _major_holiday_rules() -> List[Dict[str, Any]]:
    ops = _brain_operations()
    rules = ops.get("majorHolidays")
    return rules if isinstance(rules, list) else []


# --- holiday date resolution (movable holidays are COMPUTED, never hardcoded) ---------------
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _dt.date:
    """The date of the nth (1-indexed) occurrence of `weekday` (Mon=0..Sun=6) in year-month —
    e.g. Thanksgiving = the 4th Thursday of November."""
    first = _dt.date(year, month, 1)
    delta = (weekday - first.weekday()) % 7
    day = 1 + delta + (n - 1) * 7
    return _dt.date(year, month, day)


def _last_weekday(year: int, month: int, weekday: int) -> _dt.date:
    """The date of the LAST occurrence of `weekday` in year-month — e.g. Memorial Day = the
    last Monday of May."""
    if month == 12:
        next_month_start = _dt.date(year + 1, 1, 1)
    else:
        next_month_start = _dt.date(year, month + 1, 1)
    d = next_month_start - _dt.timedelta(days=1)
    while d.weekday() != weekday:
        d -= _dt.timedelta(days=1)
    return d


def major_holidays(year: int) -> Dict[str, _dt.date]:
    """Every configured major holiday's ACTUAL date for `year`, from ai-brain.json
    operations.majorHolidays. {} if the brain block is missing/unreadable — never raises."""
    rules = _major_holiday_rules()
    resolved: Dict[str, _dt.date] = {}
    deferred = []
    for r in rules:
        name = r.get("name")
        kind = r.get("rule")
        if not name or not kind:
            continue
        try:
            if kind == "fixed":
                resolved[name] = _dt.date(year, int(r["month"]), int(r["day"]))
            elif kind == "nth_weekday":
                resolved[name] = _nth_weekday(year, int(r["month"]), int(r["weekday"]), int(r["n"]))
            elif kind == "last_weekday":
                resolved[name] = _last_weekday(year, int(r["month"]), int(r["weekday"]))
            elif kind == "day_after":
                deferred.append(r)  # depends on another holiday already being resolved
        except Exception:
            continue
    for r in deferred:
        base = resolved.get(r.get("of"))
        if base is not None and r.get("name"):
            resolved[r["name"]] = base + _dt.timedelta(days=1)
    return resolved


def days_to_nearest_major_holiday(as_of: _dt.date) -> Optional[Dict[str, Any]]:
    """The nearest configured major holiday to `as_of` (may be in the past — days_away is
    signed: negative = already passed). Checks year-1/year/year+1 so a late-December as_of
    correctly sees the NEXT January's New Year's Day, not just this year's — a year-boundary
    bug a naive same-year-only lookup would have. None if no holidays are configured."""
    candidates = []
    for y in (as_of.year - 1, as_of.year, as_of.year + 1):
        candidates.extend(major_holidays(y).items())
    if not candidates:
        return None
    name, date = min(candidates, key=lambda kv: abs((kv[1] - as_of).days))
    return {"holiday": name, "date": date.isoformat(), "days_away": (date - as_of).days}


# --- seasonal2026-driven windows --------------------------------------------------------------
def days_to_prime_day(as_of: _dt.date) -> Optional[int]:
    """Days until the next Prime Day sourcing window OPENS (operations.seasonal2026.
    primeDayWindow.start). 0 or negative once inside/past this year's window — recurs annually
    on the configured month/day (see module docstring's APPROXIMATION note). None if
    unconfigured."""
    win = _seasonal2026().get("primeDayWindow") or {}
    start_s, end_s = win.get("start"), win.get("end")
    if not start_s:
        return None
    start = _dt.date.fromisoformat(start_s)
    end = _dt.date.fromisoformat(end_s) if end_s else start
    this_year_start = start.replace(year=as_of.year)
    this_year_end = end.replace(year=as_of.year)
    if as_of > this_year_end:
        this_year_start = start.replace(year=as_of.year + 1)
    return (this_year_start - as_of).days


def weeks_to_q4_arrival_deadline(as_of: _dt.date) -> Optional[float]:
    """Weeks until operations.seasonal2026.q4ArrivalDeadline (the last-safe-arrival date for Q4
    inventory) — recurs annually on the configured month/day. Negative once past this year's
    deadline until it rolls to next year. None if unconfigured."""
    deadline_s = _seasonal2026().get("q4ArrivalDeadline")
    if not deadline_s:
        return None
    deadline = _dt.date.fromisoformat(deadline_s)
    this_year = deadline.replace(year=as_of.year)
    if as_of > this_year:
        this_year = deadline.replace(year=as_of.year + 1)
    return round((this_year - as_of).days / 7.0, 1)


def is_bts_window(as_of: _dt.date) -> bool:
    """True inside the back-to-school buy window (operations.seasonal2026.backToSchoolWindow —
    the structured month-day form of the backToSchoolBuyWindow text). False if unconfigured."""
    win = _seasonal2026().get("backToSchoolWindow") or {}
    start_s, end_s = win.get("startMonthDay"), win.get("endMonthDay")
    if not start_s or not end_s:
        return False
    sm, sd = (int(x) for x in start_s.split("-"))
    em, ed = (int(x) for x in end_s.split("-"))
    start = _dt.date(as_of.year, sm, sd)
    end = _dt.date(as_of.year, em, ed)
    return start <= as_of <= end


def day_of_week(as_of: _dt.date) -> int:
    """Monday=0 .. Sunday=6 (Python's date.weekday() convention)."""
    return as_of.weekday()


def calendar_features(as_of: _dt.date) -> Dict[str, Any]:
    """All calendar features for one date, in the shape PRE_DECISION_FEATURES/feature_snapshot
    expects to merge in. Never raises — any individual computation failing degrades that one key
    to None rather than losing the whole row."""
    holiday = days_to_nearest_major_holiday(as_of)
    return {
        "days_to_prime_day": days_to_prime_day(as_of),
        "weeks_to_q4_arrival_deadline": weeks_to_q4_arrival_deadline(as_of),
        "days_to_nearest_major_holiday": holiday["days_away"] if holiday else None,
        "nearest_major_holiday_name": holiday["holiday"] if holiday else None,
        "is_bts_window": is_bts_window(as_of),
        "day_of_week": day_of_week(as_of),
    }

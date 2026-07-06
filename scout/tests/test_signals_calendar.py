"""
test_signals_calendar.py — scout/signals/calendar.py's pure date functions (Session 55).

Every function is deterministic given `as_of` — no live clock, no network. Year-boundary math
(nth-weekday/last-weekday holiday resolution, window rollover across Dec->Jan) is the deliverable.
"""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals import calendar as cal  # noqa: E402  — package-qualified import (never bare
                                     # `import calendar`, which would shadow the stdlib module
                                     # in sys.modules for the rest of this test process)


FAKE_OPERATIONS = {
    "seasonal2026": {
        "primeDayWindow": {"start": "2026-06-23", "end": "2026-06-26"},
        "backToSchoolWindow": {"startMonthDay": "06-20", "endMonthDay": "08-15"},
        "q4ArrivalDeadline": "2026-10-30",
    },
    "majorHolidays": [
        {"name": "New Year's Day", "rule": "fixed", "month": 1, "day": 1},
        {"name": "Memorial Day", "rule": "last_weekday", "month": 5, "weekday": 0},
        {"name": "Thanksgiving", "rule": "nth_weekday", "month": 11, "weekday": 3, "n": 4},
        {"name": "Black Friday", "rule": "day_after", "of": "Thanksgiving"},
        {"name": "Christmas", "rule": "fixed", "month": 12, "day": 25},
    ],
}


def _patched():
    return mock.patch.object(cal, "_brain_operations", return_value=FAKE_OPERATIONS)


class HolidayResolutionTest(unittest.TestCase):
    def test_thanksgiving_2026_is_4th_thursday_of_november(self):
        with _patched():
            holidays = cal.major_holidays(2026)
        # Nov 1 2026 is a Sunday -> 1st Thu = Nov 5 -> 4th Thu = Nov 26
        self.assertEqual(holidays["Thanksgiving"], dt.date(2026, 11, 26))

    def test_black_friday_is_day_after_thanksgiving(self):
        with _patched():
            holidays = cal.major_holidays(2026)
        self.assertEqual(holidays["Black Friday"], holidays["Thanksgiving"] + dt.timedelta(days=1))

    def test_memorial_day_2026_is_last_monday_of_may(self):
        with _patched():
            holidays = cal.major_holidays(2026)
        # May 2026: May 31 is a Sunday -> last Monday is May 25
        self.assertEqual(holidays["Memorial Day"], dt.date(2026, 5, 25))

    def test_nth_weekday_math_across_multiple_years(self):
        """Thanksgiving must land on a Thursday every year, computed fresh — never hardcoded."""
        with _patched():
            for year in (2024, 2025, 2026, 2027, 2030):
                holidays = cal.major_holidays(year)
                self.assertEqual(holidays["Thanksgiving"].weekday(), 3)
                self.assertEqual(holidays["Thanksgiving"].month, 11)


class NearestHolidayYearBoundaryTest(unittest.TestCase):
    def test_late_december_sees_next_years_new_year(self):
        """The classic year-boundary bug: Dec 30 must see Jan 1 of the FOLLOWING year, not
        silently miss it because a naive lookup only checked the current year."""
        with _patched():
            result = cal.days_to_nearest_major_holiday(dt.date(2026, 12, 30))
        self.assertEqual(result["holiday"], "New Year's Day")
        self.assertEqual(result["days_away"], 2)

    def test_january_2nd_sees_past_new_year_as_negative(self):
        with _patched():
            result = cal.days_to_nearest_major_holiday(dt.date(2027, 1, 2))
        self.assertEqual(result["holiday"], "New Year's Day")
        self.assertEqual(result["days_away"], -1)

    def test_returns_none_when_unconfigured(self):
        with mock.patch.object(cal, "_brain_operations", return_value={}):
            self.assertIsNone(cal.days_to_nearest_major_holiday(dt.date(2026, 6, 1)))


class PrimeDayTest(unittest.TestCase):
    def test_days_to_prime_day_before_window(self):
        with _patched():
            self.assertEqual(cal.days_to_prime_day(dt.date(2026, 6, 1)), 22)

    def test_inside_window_is_zero_or_negative(self):
        with _patched():
            d = cal.days_to_prime_day(dt.date(2026, 6, 24))
        self.assertLessEqual(d, 0)

    def test_rolls_forward_to_next_year_once_past(self):
        with _patched():
            d = cal.days_to_prime_day(dt.date(2026, 12, 1))
        # next occurrence: June 23, 2027
        expected = (dt.date(2027, 6, 23) - dt.date(2026, 12, 1)).days
        self.assertEqual(d, expected)


class Q4DeadlineTest(unittest.TestCase):
    def test_weeks_before_deadline(self):
        with _patched():
            w = cal.weeks_to_q4_arrival_deadline(dt.date(2026, 10, 16))
        self.assertEqual(w, 2.0)

    def test_rolls_forward_past_deadline(self):
        with _patched():
            w = cal.weeks_to_q4_arrival_deadline(dt.date(2026, 11, 1))
        self.assertGreater(w, 0)  # rolled to Oct 30, 2027 — must stay positive, never negative


class BtsWindowTest(unittest.TestCase):
    def test_inside_window(self):
        with _patched():
            self.assertTrue(cal.is_bts_window(dt.date(2026, 7, 15)))

    def test_outside_window(self):
        with _patched():
            self.assertFalse(cal.is_bts_window(dt.date(2026, 1, 1)))

    def test_boundary_inclusive(self):
        with _patched():
            self.assertTrue(cal.is_bts_window(dt.date(2026, 6, 20)))
            self.assertTrue(cal.is_bts_window(dt.date(2026, 8, 15)))
            self.assertFalse(cal.is_bts_window(dt.date(2026, 8, 16)))


class DayOfWeekTest(unittest.TestCase):
    def test_known_dates(self):
        self.assertEqual(cal.day_of_week(dt.date(2026, 6, 22)), 0)  # a Monday
        self.assertEqual(cal.day_of_week(dt.date(2026, 6, 28)), 6)  # a Sunday


class CalendarFeaturesTest(unittest.TestCase):
    def test_returns_all_keys_and_never_raises_on_missing_brain(self):
        with mock.patch.object(cal, "_brain_operations", return_value={}):
            feats = cal.calendar_features(dt.date(2026, 6, 1))
        self.assertEqual(set(feats.keys()), {
            "days_to_prime_day", "weeks_to_q4_arrival_deadline",
            "days_to_nearest_major_holiday", "nearest_major_holiday_name",
            "is_bts_window", "day_of_week",
        })
        self.assertIsNone(feats["days_to_prime_day"])
        self.assertFalse(feats["is_bts_window"])
        self.assertEqual(feats["day_of_week"], dt.date(2026, 6, 1).weekday())

    def test_backfill_safe_pure_function_of_as_of(self):
        """The SAME call with the SAME as_of must be identical regardless of when it's actually
        invoked — the leakage-safety property this project requires of every backfilled feature."""
        with _patched():
            a = cal.calendar_features(dt.date(2025, 3, 1))
            b = cal.calendar_features(dt.date(2025, 3, 1))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()

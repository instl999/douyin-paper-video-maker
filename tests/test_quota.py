import unittest
from dataclasses import replace
from datetime import date
from unittest import mock

from pvm import config, quota
from pvm.util import PvmError
from tests.helpers import TempHome


class AllowanceTest(unittest.TestCase):
    def test_paces_what_is_left_of_the_month(self):
        self.assertEqual(quota.daily_allowance(20_000, 0, 0, 30, 10_000), 666)
        self.assertEqual(quota.daily_allowance(20_000, 18_000, 0, 5, 10_000), 400)
        self.assertEqual(quota.daily_allowance(20_000, 0, 0, 1, 10_000), 10_000)  # never above the daily cap
        self.assertEqual(quota.daily_allowance(20_000, 0, 500, 30, 10_000), 166)  # today's spending counts
        self.assertEqual(quota.daily_allowance(20_000, 20_000, 0, 10, 10_000), 0)
        self.assertEqual(quota.daily_allowance(20_000, 0, 0, 30, 10_000, override=2_000), 2_000)


class CycleTest(unittest.TestCase):
    def test_calendar_month_without_a_purchase_date(self):
        self.assertEqual(quota.cycle_bounds(date(2026, 10, 7)), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_the_plan_month_starts_on_the_purchase_day(self):
        start = date(2026, 10, 7)
        for today, expected in ((date(2026, 10, 7), (date(2026, 10, 7), date(2026, 11, 6))),
                                (date(2026, 11, 6), (date(2026, 10, 7), date(2026, 11, 6))),
                                (date(2026, 11, 7), (date(2026, 11, 7), date(2026, 12, 6))),
                                (date(2027, 1, 20), (date(2027, 1, 7), date(2027, 2, 6)))):  # across a year end
            self.assertEqual(quota.cycle_bounds(today, start), expected, today)

    def test_purchase_late_in_the_month_clamps_to_short_months(self):
        start = date(2026, 1, 31)
        self.assertEqual(quota.cycle_bounds(date(2026, 2, 10), start), (date(2026, 1, 31), date(2026, 2, 27)))
        self.assertEqual(quota.cycle_bounds(date(2026, 2, 28), start), (date(2026, 2, 28), date(2026, 3, 30)))

    def test_a_bad_purchase_date_is_reported(self):
        self.assertIsNone(quota.plan_start(""))
        with self.assertRaises(PvmError):
            quota.plan_start("7 Oct")


class LedgerTest(TempHome):
    def test_status_reads_the_ledger(self):
        quota.record(99, kind="image", project="demo")
        quota.record(198, kind="image", project="demo")
        st = quota.status(date.today())
        self.assertEqual((st.used_today, st.used_cycle), (297, 297))
        self.assertEqual(st.mode, "normal")

    def test_spend_per_project(self):
        quota.record(150, kind="image", project="demo")
        quota.record(45, kind="voice", project="demo")
        quota.record(3, kind="text", project="demo")
        quota.record(3, kind="text", project="demo")
        quota.record(150, kind="mascot")  # the shared mascot library belongs to no project
        self.assertEqual(quota.project_spend("demo"), {"total": 201, "by_kind": {"image": 150, "voice": 45, "text": 6},
                                                       "calls": {"image": 1, "voice": 1, "text": 2}})

    def test_status_paces_over_the_plan_month(self):
        settings = config.get_settings()
        with mock.patch.object(quota, "get_settings", return_value=replace(settings, plan_start="2026-10-07",
                                                                            afp_daily_budget=None)):
            st = quota.status(date(2026, 10, 7))
        self.assertEqual((st.cycle, st.cycle_known, st.days_left), ((date(2026, 10, 7), date(2026, 11, 6)), True, 31))
        self.assertEqual(st.allowance_today, settings.afp_monthly_budget // 31)


if __name__ == "__main__":
    unittest.main()

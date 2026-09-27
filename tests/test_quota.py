import unittest
from datetime import date

from pvm import quota
from tests.helpers import TempHome


class AllowanceTest(unittest.TestCase):
    def test_paces_what_is_left_of_the_month(self):
        self.assertEqual(quota.daily_allowance(20_000, 0, 0, 30, 10_000), 666)
        self.assertEqual(quota.daily_allowance(20_000, 18_000, 0, 5, 10_000), 400)
        self.assertEqual(quota.daily_allowance(20_000, 0, 0, 1, 10_000), 10_000)  # never above the daily cap
        self.assertEqual(quota.daily_allowance(20_000, 0, 500, 30, 10_000), 166)  # today's spending counts
        self.assertEqual(quota.daily_allowance(20_000, 20_000, 0, 10, 10_000), 0)
        self.assertEqual(quota.daily_allowance(20_000, 0, 0, 30, 10_000, override=2_000), 2_000)


class LedgerTest(TempHome):
    def test_status_reads_the_ledger(self):
        quota.record(99, kind="image", project="demo")
        quota.record(198, kind="image", project="demo")
        st = quota.status(date.today())
        self.assertEqual((st.used_today, st.used_cycle), (297, 297))
        self.assertEqual(st.mode, "normal")


if __name__ == "__main__":
    unittest.main()

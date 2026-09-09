#!/usr/bin/env python3
"""HJ 633—2026 计算工具单元测试。对照正式文本表 3、式(1)(2)、4.2.6、4.3.1、5.3.1。"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hj633 import (  # noqa: E402
    compute_aqi,
    compute_iaqi,
    iaqi_to_concentration,
    category_of,
    limits_table,
    DISPLAY,
)


class TestBreakpoints2026(unittest.TestCase):
    def test_pm25_daily_nodes(self):
        self.assertEqual(compute_iaqi("PM2.5", 0, "24h"), 0)
        self.assertEqual(compute_iaqi("PM2.5", 35, "24h"), 50)
        self.assertEqual(compute_iaqi("PM2.5", 60, "24h"), 100)
        self.assertEqual(compute_iaqi("PM2.5", 115, "24h"), 150)
        self.assertEqual(compute_iaqi("PM2.5", 150, "24h"), 200)
        self.assertEqual(compute_iaqi("PM2.5", 250, "24h"), 300)
        self.assertEqual(compute_iaqi("PM2.5", 350, "24h"), 400)
        self.assertEqual(compute_iaqi("PM2.5", 500, "24h"), 500)
        self.assertEqual(compute_iaqi("PM2.5", 800, "24h"), 500)

    def test_pm10_daily_nodes(self):
        self.assertEqual(compute_iaqi("PM10", 50, "24h"), 50)
        self.assertEqual(compute_iaqi("PM10", 120, "24h"), 100)
        self.assertEqual(compute_iaqi("PM10", 250, "24h"), 150)

    def test_so2_1h_official_not_project_bug(self):
        """旧实现常见错误：误把 24h 的 475 当成 1h 的 IAQI=100。正式表 3：1h 的 100 档是 500。"""
        self.assertEqual(compute_iaqi("SO2", 150, "1h"), 50)
        self.assertEqual(compute_iaqi("SO2", 500, "1h"), 100)
        self.assertEqual(compute_iaqi("SO2", 650, "1h"), 150)
        self.assertEqual(compute_iaqi("SO2", 800, "1h"), 200)
        self.assertEqual(compute_iaqi("SO2", 801, "1h"), 200)
        self.assertEqual(compute_iaqi("SO2", 2000, "1h"), 200)
        # 475 在 1h 表上落在 150–500 之间，IAQI 应 < 100
        iaqi_475 = compute_iaqi("SO2", 475, "1h")
        self.assertIsNotNone(iaqi_475)
        self.assertLess(iaqi_475, 100)

    def test_so2_24h(self):
        self.assertEqual(compute_iaqi("SO2", 50, "24h"), 50)
        self.assertEqual(compute_iaqi("SO2", 150, "24h"), 100)
        self.assertEqual(compute_iaqi("SO2", 475, "24h"), 150)

    def test_no2_co_o3_nodes(self):
        self.assertEqual(compute_iaqi("NO2", 40, "24h"), 50)
        self.assertEqual(compute_iaqi("NO2", 100, "1h"), 50)
        self.assertEqual(compute_iaqi("NO2", 3840, "1h"), 500)
        self.assertEqual(compute_iaqi("CO", 2, "24h"), 50)
        self.assertEqual(compute_iaqi("CO", 5, "1h"), 50)
        self.assertEqual(compute_iaqi("O3", 100, "8h"), 50)
        self.assertEqual(compute_iaqi("O3", 160, "8h"), 100)
        self.assertEqual(compute_iaqi("O3", 160, "1h"), 50)
        self.assertEqual(compute_iaqi("O3", 200, "1h"), 100)
        self.assertEqual(compute_iaqi("O3", 1000, "1h"), 400)
        self.assertEqual(compute_iaqi("O3", 1200, "1h"), 500)

    def test_o3_8h_cap(self):
        self.assertEqual(compute_iaqi("O3", 800, "8h"), 300)
        self.assertEqual(compute_iaqi("O3", 801, "8h"), 300)
        self.assertEqual(compute_iaqi("O3", 1200, "8h"), 300)


class TestCeilRounding(unittest.TestCase):
    def test_pm25_75_is_114(self):
        # 100 + (75-60)/(115-60)*50 = 113.636... → ceil 114
        self.assertEqual(compute_iaqi("PM2.5", 75, "24h"), 114)

    def test_pm10_150_is_112(self):
        # 100 + (150-120)/(250-120)*50 = 111.538... → ceil 112
        self.assertEqual(compute_iaqi("PM10", 150, "24h"), 112)

    def test_ceil_not_round_half_even(self):
        # 选一个 raw 刚好 > N 且 < N.5 的点，证明是进位不是四舍五入
        # PM2.5 60–115 / 100–150：raw = 100 + (C-60)/55*50
        # 要 raw=100.1 → C=60.11
        self.assertEqual(compute_iaqi("PM2.5", 60.11, "24h"), 101)

    def test_exact_integer_stays(self):
        self.assertEqual(compute_iaqi("PM2.5", 35, "24h"), 50)


class TestVs2012(unittest.TestCase):
    def test_pm25_75_diff(self):
        self.assertEqual(compute_iaqi("PM2.5", 75, "24h", year=2012), 100)
        self.assertEqual(compute_iaqi("PM2.5", 75, "24h", year=2026), 114)

    def test_pm10_150_diff(self):
        self.assertEqual(compute_iaqi("PM10", 150, "24h", year=2012), 100)
        self.assertEqual(compute_iaqi("PM10", 150, "24h", year=2026), 112)

    def test_so2_unchanged(self):
        self.assertEqual(
            compute_iaqi("SO2", 80, "24h", year=2012),
            compute_iaqi("SO2", 80, "24h", year=2026),
        )


class TestPrimaryPollutant(unittest.TestCase):
    def test_no_primary_when_aqi_le_50(self):
        r = compute_aqi(
            {"PM2.5": 20, "PM10": 30, "SO2": 10, "NO2": 15, "CO": 0.5, "O3": 60},
            mode="daily", incomplete=False,
        )
        self.assertLessEqual(r.aqi, 50)
        self.assertEqual(r.primary, [])

    def test_single_primary(self):
        r = compute_aqi(
            {"PM2.5": 80, "PM10": 40, "SO2": 10, "NO2": 15, "CO": 0.5, "O3": 60},
            mode="daily", incomplete=False,
        )
        self.assertGreater(r.aqi, 50)
        self.assertEqual(r.primary, ["PM2.5"])

    def test_tied_primary(self):
        # 两污染物都正好 IAQI=100
        r = compute_aqi(
            {"PM2.5": 60, "PM10": 120, "SO2": 10, "NO2": 15, "CO": 0.5, "O3": 60},
            mode="daily", incomplete=False,
        )
        self.assertEqual(r.aqi, 100)
        self.assertEqual(set(r.primary), {"PM2.5", "PM10"})

    def test_o3_daily_uses_8h(self):
        r = compute_aqi({"O3": 160, "PM2.5": 20}, mode="daily", incomplete=False)
        self.assertEqual(r.aqi, 100)
        self.assertEqual(r.primary, ["O3"])
        o3 = next(it for it in r.items if it.pollutant == "O3")
        self.assertEqual(o3.avg, "8h")

    def test_o3_realtime_uses_1h(self):
        r = compute_aqi({"O3": 160, "PM2.5": 20}, mode="realtime", incomplete=False)
        o3 = next(it for it in r.items if it.pollutant == "O3")
        self.assertEqual(o3.avg, "1h")
        self.assertEqual(o3.iaqi, 50)

    def test_pm_realtime_uses_24h_breakpoints(self):
        r = compute_aqi({"PM2.5": 60}, mode="realtime", incomplete=False)
        pm = next(it for it in r.items if it.pollutant == "PM2.5")
        self.assertEqual(pm.avg, "24h")
        self.assertEqual(pm.iaqi, 100)


class TestPublishRule53(unittest.TestCase):
    def test_incomplete_aqi_le_100_is_na(self):
        r = compute_aqi({"PM2.5": 40}, mode="daily", incomplete=True)
        self.assertEqual(r.aqi, 60)
        self.assertEqual(r.aqi_published, "NA")

    def test_incomplete_aqi_gt_100_still_published(self):
        r = compute_aqi({"PM2.5": 80}, mode="daily", incomplete=True)
        self.assertGreater(r.aqi, 100)
        self.assertEqual(r.aqi_published, r.aqi)
        self.assertEqual(r.primary, ["PM2.5"])

    def test_assume_complete_skips_na(self):
        r = compute_aqi({"PM2.5": 40}, mode="daily", incomplete=False)
        self.assertEqual(r.aqi_published, 60)


class TestReverse(unittest.TestCase):
    def test_breakpoint_inverse(self):
        r = iaqi_to_concentration("PM2.5", 100, "24h")
        self.assertEqual(r["concentration"], 60)
        r = iaqi_to_concentration("PM10", 100, "24h")
        self.assertEqual(r["concentration"], 120)
        r = iaqi_to_concentration("SO2", 100, "1h")
        self.assertEqual(r["concentration"], 500)

    def test_roundtrip_at_nodes(self):
        for p, avg, c in [
            ("PM2.5", "24h", 35), ("PM2.5", "24h", 60), ("NO2", "1h", 200),
            ("CO", "24h", 4.0), ("O3", "8h", 160),
        ]:
            iaqi = compute_iaqi(p, c, avg)
            back = iaqi_to_concentration(p, iaqi, avg)["concentration"]
            self.assertAlmostEqual(back, c, places=6)

    def test_ceil_bucket_contains_forward(self):
        # 75 → 114，反算 114 的桶应包含 75
        iaqi = compute_iaqi("PM2.5", 75, "24h")
        self.assertEqual(iaqi, 114)
        inv = iaqi_to_concentration("PM2.5", 114, "24h")
        b = inv["ceil_bucket"]
        self.assertGreater(75, b["conc_exclusive_low"])
        self.assertLessEqual(75, b["conc_inclusive_high"])


class TestCategory(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(category_of(50)["category"], "优")
        self.assertEqual(category_of(51)["category"], "良")
        self.assertEqual(category_of(100)["category"], "良")
        self.assertEqual(category_of(101)["category"], "轻度污染")
        self.assertEqual(category_of(201)["category"], "重度污染")
        self.assertEqual(category_of(301)["category"], "严重污染")
        self.assertEqual(category_of(50)["rgb_hex"], "#00E400")
        self.assertEqual(category_of(301)["rgb"], (126, 0, 35))


class TestLimitsTable(unittest.TestCase):
    def test_2026_pm_row_100(self):
        rows = {r["IAQI"]: r for r in limits_table(2026)["rows"]}
        self.assertEqual(rows[100]["PM2.5_24h"], 60)
        self.assertEqual(rows[100]["PM10_24h"], 120)
        self.assertEqual(rows[100]["SO2_1h"], 500)
        self.assertIsNone(rows[300]["SO2_1h"])
        self.assertIsNone(rows[400]["O3_8h"])

    def test_2012_pm_row_100(self):
        rows = {r["IAQI"]: r for r in limits_table(2012)["rows"]}
        self.assertEqual(rows[100]["PM2.5_24h"], 75)
        self.assertEqual(rows[100]["PM10_24h"], 150)


class TestAliasesAndInvalid(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(compute_iaqi("细颗粒物", 60, "daily"), 100)
        self.assertEqual(compute_iaqi("pm25", 60, "24"), 100)
        self.assertEqual(compute_iaqi("臭氧", 160, "8h"), 100)

    def test_invalid(self):
        self.assertIsNone(compute_iaqi("PM2.5", None, "24h"))
        self.assertIsNone(compute_iaqi("PM2.5", float("nan"), "24h"))
        self.assertIsNone(compute_iaqi("PM2.5", -1, "24h"))
        with self.assertRaises(ValueError):
            compute_iaqi("VOC", 10, "24h")
        with self.assertRaises(ValueError):
            compute_iaqi("PM2.5", 10, "1h")  # 颗粒物无独立 1h 断点

    def test_display_keys(self):
        self.assertEqual(set(DISPLAY), {"SO2", "NO2", "CO", "O3", "PM10", "PM2.5"})


class TestInterpolationFormula(unittest.TestCase):
    def test_manual_formula(self):
        # 式(1) 手工验算：NO2 1h = 350，落在 200–700 / 100–150
        raw = (150 - 100) / (700 - 200) * (350 - 200) + 100
        self.assertEqual(compute_iaqi("NO2", 350, "1h"), int(math.ceil(raw)))


if __name__ == "__main__":
    unittest.main()

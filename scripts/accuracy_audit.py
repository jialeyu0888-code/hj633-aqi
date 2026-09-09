#!/usr/bin/env python3
"""对照式(1)独立实现，扫描全表断点与插值点，统计 skill 脚本准确率。"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Windows GBK 控制台写不出 ₂/↔ 等字符，用替换避免 UnicodeEncodeError。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # 非 TextIOWrapper 或已分离
        pass
from hj633 import (  # noqa: E402
    CATEGORIES,
    IAQI_NODES,
    TABLE3,
    category_of,
    compute_aqi,
    compute_iaqi,
    iaqi_to_concentration,
)

# 独立抄表 3，不调用 compute_iaqi 内部，作为对照金标准。
GOLD: dict[str, dict[str, tuple[float | None, ...]]] = {
    "SO2": {
        "24h": (0.0, 50.0, 150.0, 475.0, 800.0, 1600.0, 2100.0, 2620.0),
        "1h": (0.0, 150.0, 500.0, 650.0, 800.0, None, None, None),
    },
    "NO2": {
        "24h": (0.0, 40.0, 80.0, 180.0, 280.0, 565.0, 750.0, 940.0),
        "1h": (0.0, 100.0, 200.0, 700.0, 1200.0, 2340.0, 3090.0, 3840.0),
    },
    "CO": {
        "24h": (0.0, 2.0, 4.0, 14.0, 24.0, 36.0, 48.0, 60.0),
        "1h": (0.0, 5.0, 10.0, 35.0, 60.0, 90.0, 120.0, 150.0),
    },
    "O3": {
        "8h": (0.0, 100.0, 160.0, 215.0, 265.0, 800.0, None, None),
        "1h": (0.0, 160.0, 200.0, 300.0, 400.0, 800.0, 1000.0, 1200.0),
    },
    "PM10": {"24h": (0.0, 50.0, 120.0, 250.0, 350.0, 420.0, 500.0, 600.0)},
    "PM2.5": {"24h": (0.0, 35.0, 60.0, 115.0, 150.0, 250.0, 350.0, 500.0)},
}


def gold_iaqi(pollutant: str, conc: float, avg: str) -> int:
    if pollutant == "SO2" and avg == "1h" and conc > 800:
        return 200
    if pollutant == "O3" and avg == "8h" and conc > 800:
        return 300
    bps = GOLD[pollutant][avg]
    defined = [(IAQI_NODES[i], bps[i]) for i in range(len(bps)) if bps[i] is not None]
    nodes, concs = zip(*defined)
    if conc <= concs[0]:
        return int(nodes[0])
    if conc >= concs[-1]:
        return int(nodes[-1])
    for i in range(len(concs) - 1):
        lo_c, hi_c = concs[i], concs[i + 1]
        if lo_c <= conc <= hi_c:
            if hi_c == lo_c:
                return int(nodes[i + 1])
            raw = (nodes[i + 1] - nodes[i]) / (hi_c - lo_c) * (conc - lo_c) + nodes[i]
            # 与 hj633.compute_iaqi 相同的整数吸附：数学上恰为整数的 raw 不被浮点顶到下一档
            if abs(raw - round(raw)) < 1e-9:
                raw = float(round(raw))
            return int(math.ceil(raw))
    return int(nodes[-1])


def sample_concentrations(pollutant: str, avg: str) -> list[float]:
    bps = GOLD[pollutant][avg]
    vals = [float(x) for x in bps if x is not None]
    out: list[float] = [0.0]
    for i, v in enumerate(vals):
        out.append(v)
        if i + 1 < len(vals) and vals[i + 1] > v:
            mid = (v + vals[i + 1]) / 2
            out.append(mid)
            span = vals[i + 1] - v
            out.append(v + span * 0.01)
            out.append(v + span * 0.99)
        if pollutant == "CO":
            out.append(round(v + 0.1, 6) if v < vals[-1] else v)
    out.append(vals[-1] + 1.0)
    out.append(vals[-1] * 1.2 + 10)
    if pollutant == "SO2" and avg == "1h":
        out.extend([800.0, 800.1, 900.0, 2000.0])
    if pollutant == "O3" and avg == "8h":
        out.extend([800.0, 800.1, 900.0, 1500.0])
    # 去重保序
    seen: set[float] = set()
    uniq: list[float] = []
    for x in out:
        if x >= 0 and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def run_forward_scan() -> tuple[int, int, list[str]]:
    ok = fail = 0
    errs: list[str] = []
    for p, avgs in GOLD.items():
        for avg in avgs:
            for c in sample_concentrations(p, avg):
                expect = gold_iaqi(p, c, avg)
                got = compute_iaqi(p, c, avg)
                if got == expect:
                    ok += 1
                else:
                    fail += 1
                    if len(errs) < 12:
                        errs.append(f"{p} {avg} C={c}: 金标准 {expect}, 脚本 {got}")
    return ok, fail, errs


def run_roundtrip() -> tuple[int, int, list[str]]:
    ok = fail = 0
    errs: list[str] = []
    for p, avgs in GOLD.items():
        for avg in avgs:
            bps = GOLD[p][avg]
            max_i = max(IAQI_NODES[i] for i in range(len(bps)) if bps[i] is not None)
            for iaqi in range(0, max_i + 1):
                inv = iaqi_to_concentration(p, iaqi, avg)
                c = inv["concentration"]
                back = compute_iaqi(p, c, avg)
                # 反算点是 raw IAQI = 整数；ceil 后应等于该整数（0 除外）
                if back == iaqi or (iaqi == 0 and back == 0):
                    ok += 1
                else:
                    fail += 1
                    if len(errs) < 12:
                        errs.append(f"反算 {p} {avg} IAQI={iaqi} → C={c} → 回算 {back}")
    return ok, fail, errs


def run_category() -> tuple[int, int]:
    ok = fail = 0
    expect = [
        (0, "优"), (50, "优"), (51, "良"), (100, "良"),
        (101, "轻度污染"), (150, "轻度污染"), (151, "中度污染"),
        (200, "中度污染"), (201, "重度污染"), (300, "重度污染"),
        (301, "严重污染"), (500, "严重污染"),
    ]
    for aqi, name in expect:
        cat = category_of(aqi)
        if cat and cat["category"] == name:
            ok += 1
        else:
            fail += 1
    rgb = [(50, (0, 228, 0)), (51, (255, 255, 0)), (101, (255, 126, 0)),
           (151, (255, 0, 0)), (201, (153, 0, 76)), (301, (126, 0, 35))]
    for aqi, rgbv in rgb:
        cat = category_of(aqi)
        if cat and tuple(cat["rgb"]) == rgbv:
            ok += 1
        else:
            fail += 1
    return ok, fail


def run_primary_and_max() -> tuple[int, int]:
    ok = fail = 0
    cases = [
        ({"PM2.5": 20, "O3": 80, "SO2": 10, "NO2": 15, "CO": 0.5, "PM10": 30}, "daily", False, []),
        ({"PM2.5": 60, "PM10": 40, "SO2": 10, "NO2": 15, "CO": 0.5, "O3": 80}, "daily", False, ["PM2.5"]),
        ({"PM2.5": 60, "PM10": 120, "SO2": 10, "NO2": 15, "CO": 0.5, "O3": 80}, "daily", False, ["PM2.5", "PM10"]),
        ({"O3": 200, "PM2.5": 20}, "realtime", False, ["O3"]),
        ({"PM2.5": 80}, "daily", True, ["PM2.5"]),
    ]
    for conc, mode, incomplete, primary in cases:
        r = compute_aqi(conc, mode=mode, incomplete=incomplete)
        items = {it.pollutant: it.iaqi for it in r.items}
        expect_aqi = max(items.values()) if items else None
        if r.aqi != expect_aqi:
            fail += 1
            continue
        if set(r.primary) != set(primary):
            fail += 1
            continue
        ok += 1
    # 5.3.1
    r = compute_aqi({"PM2.5": 40}, mode="daily", incomplete=True)
    ok += 1 if r.aqi_published == "NA" else 0
    fail += 0 if r.aqi_published == "NA" else 1
    r = compute_aqi({"PM2.5": 80}, mode="daily", incomplete=True)
    ok += 1 if r.aqi_published == r.aqi and r.aqi > 100 else 0
    fail += 0 if r.aqi_published == r.aqi and r.aqi > 100 else 1
    return ok, fail


def run_external_diff(iaqi_py: str | None) -> dict:
    """与外部 compute_iaqi(key, conc) 实现对照（key 取 PM25/PM10/SO2/NO2/CO/O3/O3_8H）。

    外部实现不是金标准；只统计它与正式表 3 的分歧点。路径来自 --compare-iaqi 或环境变量
    HJ633_COMPARE_IAQI，未提供时跳过。
    """
    if not iaqi_py:
        return {"available": False}
    iaqi_path = Path(iaqi_py).expanduser()
    if not iaqi_path.exists():
        return {"available": False, "error": f"file not found: {iaqi_path}"}
    import importlib.util

    spec = importlib.util.spec_from_file_location("external_iaqi", iaqi_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hc_iaqi = mod.compute_iaqi  # type: ignore[attr-defined]

    mapping = [
        ("PM2.5", "24h", "PM25"),
        ("PM10", "24h", "PM10"),
        ("SO2", "1h", "SO2"),
        ("NO2", "1h", "NO2"),
        ("CO", "1h", "CO"),
        ("O3", "1h", "O3"),
        ("O3", "8h", "O3_8H"),
    ]
    samples = {
        "PM2.5": [35, 60, 75, 115],
        "PM10": [50, 120, 150, 250],
        "SO2": [150, 475, 500, 650, 800, 900],
        "NO2": [100, 200, 700],
        "CO": [5, 10],
        "O3": [160, 200, 800, 1000, 1200],
    }
    diffs = []
    agree = 0
    for p, avg, key in mapping:
        for c in samples.get(p, []):
            if p == "O3" and avg == "8h" and c in (1000, 1200):
                c_use = 800 if c >= 800 else c
            else:
                c_use = c
            official = compute_iaqi(p, c, avg)
            hechuan = hc_iaqi(key, c)
            if official == hechuan:
                agree += 1
            else:
                diffs.append({"pollutant": p, "avg": avg, "C": c,
                              "official": official, "hechuan": hechuan})
    return {"available": True, "agree": agree, "diff": diffs, "n": agree + len(diffs)}


def main() -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="HJ 633—2026 本地准确率审计")
    parser.add_argument(
        "--compare-iaqi",
        default=os.environ.get("HJ633_COMPARE_IAQI"),
        help="外部 iaqi.py 路径（需暴露 compute_iaqi(key, conc)），对照统计与表 3 的分歧",
    )
    args = parser.parse_args()

    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).resolve().parent), pattern="test_hj633.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)

    f_ok, f_fail, f_err = run_forward_scan()
    r_ok, r_fail, r_err = run_roundtrip()
    c_ok, c_fail = run_category()
    p_ok, p_fail = run_primary_and_max()
    hc = run_external_diff(args.compare_iaqi)

    unit_n = result.testsRun
    unit_fail = len(result.failures) + len(result.errors)
    unit_ok = unit_n - unit_fail

    blocks = [
        ("单元测试 test_hj633.py", unit_ok, unit_fail),
        ("式(1) 全表扫描（独立金标准）", f_ok, f_fail),
        ("IAQI↔浓度反算回算", r_ok, r_fail),
        ("表1 级别/颜色边界", c_ok, c_fail),
        ("式(2)+首要污染物+5.3.1", p_ok, p_fail),
    ]
    print("\n======== HJ 633—2026 本地准确率 ========")
    total_ok = total_fail = 0
    for name, ok, fail in blocks:
        n = ok + fail
        rate = 100.0 * ok / n if n else 0
        print(f"{name}: {ok}/{n}  准确率 {rate:.1f}%")
        total_ok += ok
        total_fail += fail
        if name.startswith("式(1)") and f_err:
            for e in f_err:
                print("  -", e)
        if name.startswith("IAQI") and r_err:
            for e in r_err:
                print("  -", e)
    n = total_ok + total_fail
    print(f"合计: {total_ok}/{n}  准确率 {100.0 * total_ok / n:.2f}%")

    if hc.get("available"):
        print(f"\n外部 iaqi.py 对照正式稿: 一致 {hc['agree']}/{hc['n']}")
        if hc["diff"]:
            print("分歧（以正式表 3 为准，外部实现为偏差）:")
            for d in hc["diff"]:
                print(f"  {d['pollutant']} {d['avg']} C={d['C']}: 正式 {d['official']} vs 外部 {d['hechuan']}")
    elif hc.get("error"):
        print(f"\n外部对照跳过: {hc['error']}")
    return 0 if total_fail == 0 and unit_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

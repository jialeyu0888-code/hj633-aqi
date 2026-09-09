#!/usr/bin/env python3
"""HJ 633—2026 环境空气质量指数（AQI）计算工具。

正式文本：2026-02-14 发布，2026-03-01 实施，代替 HJ 633—2012。
任何 IAQI / AQI / 首要污染物数字必须走本脚本，禁止口算或套用 2012 断点。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from typing import Any

# Windows GBK 控制台写不出 ₂/↔/μg/m³ 等字符，用替换避免 UnicodeEncodeError。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # 非 TextIOWrapper 或已分离
        pass

IAQI_NODES: tuple[int, ...] = (0, 50, 100, 150, 200, 300, 400, 500)

# 表 3。单位：SO2/NO2/O3/PM10/PM2.5 → μg/m³；CO → mg/m³。
# None = 该档无定义（注 b / 注 c）。
TABLE3: dict[str, dict[str, tuple[float | None, ...]]] = {
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
    "PM10": {
        "24h": (0.0, 50.0, 120.0, 250.0, 350.0, 420.0, 500.0, 600.0),
    },
    "PM2.5": {
        "24h": (0.0, 35.0, 60.0, 115.0, 150.0, 250.0, 350.0, 500.0),
    },
}

# 2012 仅 PM 的 IAQI=100 档不同。
TABLE3_2012_PM = {
    "PM10": (0.0, 50.0, 150.0, 250.0, 350.0, 420.0, 500.0, 600.0),
    "PM2.5": (0.0, 35.0, 75.0, 115.0, 150.0, 250.0, 350.0, 500.0),
}

AVG_ALIASES = {
    "24h": "24h", "24": "24h", "daily": "24h", "day": "24h",
    "1h": "1h", "1": "1h", "hourly": "1h", "hour": "1h", "realtime": "1h",
    "8h": "8h", "8": "8h", "o3_8h": "8h",
}

POLLUTANT_ALIASES = {
    "so2": "SO2", "so₂": "SO2", "二氧化硫": "SO2",
    "no2": "NO2", "no₂": "NO2", "二氧化氮": "NO2",
    "co": "CO", "一氧化碳": "CO",
    "o3": "O3", "o₃": "O3", "臭氧": "O3",
    "o3_8h": "O3", "o38h": "O3", "o3-8h": "O3",
    "pm10": "PM10", "pm₁₀": "PM10", "可吸入颗粒物": "PM10",
    "pm25": "PM2.5", "pm2.5": "PM2.5", "pm2_5": "PM2.5",
    "细颗粒物": "PM2.5",
}

DISPLAY = {
    "SO2": "SO2", "NO2": "NO2", "CO": "CO", "O3": "O3",
    "PM10": "PM10", "PM2.5": "PM2.5",
}
UNIT = {
    "SO2": "ug/m3", "NO2": "ug/m3", "CO": "mg/m3", "O3": "ug/m3",
    "PM10": "ug/m3", "PM2.5": "ug/m3",
}

CATEGORIES = [
    {"lo": 0, "hi": 50, "level": "一级", "category": "优", "color": "绿色",
     "rgb": (0, 228, 0), "cmyk": (40, 0, 100, 0),
     "health": "空气质量令人满意，基本无空气污染。",
     "advice": "各类人群可正常活动。"},
    {"lo": 51, "hi": 100, "level": "二级", "category": "良", "color": "黄色",
     "rgb": (255, 255, 0), "cmyk": (0, 0, 100, 0),
     "health": "空气质量可接受，但某些污染物可能对极少数异常敏感人群健康有较弱影响。",
     "advice": "极少数异常敏感人群应减少户外活动。"},
    {"lo": 101, "hi": 150, "level": "三级", "category": "轻度污染", "color": "橙色",
     "rgb": (255, 126, 0), "cmyk": (0, 52, 100, 0),
     "health": "易感人群症状有轻度加剧，健康人群出现刺激症状。",
     "advice": "儿童、老年人及心脏病、呼吸系统疾病患者应减少长时间、高强度的户外锻炼。"},
    {"lo": 151, "hi": 200, "level": "四级", "category": "中度污染", "color": "红色",
     "rgb": (255, 0, 0), "cmyk": (0, 100, 100, 0),
     "health": "进一步加剧易感人群症状，可能对健康人群心脏、呼吸系统有影响。",
     "advice": "儿童、老年人及心脏病、呼吸系统疾病患者避免长时间、高强度的户外锻炼，一般人群适量减少户外运动。"},
    {"lo": 201, "hi": 300, "level": "五级", "category": "重度污染", "color": "紫色",
     "rgb": (153, 0, 76), "cmyk": (10, 100, 40, 30),
     "health": "心脏病和肺病患者症状显著加剧，运动耐受力降低，健康人群普遍出现症状。",
     "advice": "儿童、老年人和心脏病、肺病患者应停留在室内，停止户外运动，一般人群减少户外运动。"},
    {"lo": 301, "hi": 500, "level": "六级", "category": "严重污染", "color": "褐红色",
     "rgb": (126, 0, 35), "cmyk": (30, 100, 100, 30),
     "health": "健康人群运动耐受力降低，有明显强烈症状，提前出现某些疾病。",
     "advice": "儿童、老年人和病人应当留在室内，避免体力消耗，一般人群应避免户外活动。"},
]

SENSITIVE = {
    "SO2": "患有哮喘的人、儿童（包括青少年）以及老年人",
    "NO2": "患有呼吸系统疾病（如哮喘）的人、儿童（包括青少年）以及老年人",
    "CO": "患有心血管系统疾病的人",
    "O3": "患有呼吸系统疾病（如哮喘）的人、儿童（包括青少年）、户外活动频繁的人以及老年人",
    "PM10": "患有心血管系统疾病或呼吸系统疾病（如哮喘）的人、儿童（包括青少年）、户外活动频繁的人以及老年人",
    "PM2.5": "患有心血管系统疾病或呼吸系统疾病（如哮喘）的人、儿童（包括青少年）、户外活动频繁的人以及老年人",
}

SIX = ("SO2", "NO2", "CO", "O3", "PM10", "PM2.5")
DAILY_AVG = {"SO2": "24h", "NO2": "24h", "CO": "24h", "O3": "8h", "PM10": "24h", "PM2.5": "24h"}
# 颗粒物实时报：1 小时浓度，24 小时断点（式(1) 说明）。
REALTIME_AVG = {"SO2": "1h", "NO2": "1h", "CO": "1h", "O3": "1h", "PM10": "24h", "PM2.5": "24h"}


def normalize_pollutant(name: str) -> str:
    key = name.strip().lower().replace(" ", "").replace("－", "-")
    key = key.replace("pm₂.₅", "pm25").replace("pm2.5", "pm25").replace("pm2_5", "pm25")
    if key in POLLUTANT_ALIASES:
        return POLLUTANT_ALIASES[key]
    compact = {k.replace("_", "").replace("-", "").replace(".", ""): v
               for k, v in POLLUTANT_ALIASES.items()}
    k2 = key.replace("_", "").replace("-", "").replace(".", "")
    if k2 in compact:
        return compact[k2]
    raise ValueError(f"未知污染物: {name}。可用: SO2, NO2, CO, O3, PM10, PM2.5")


def normalize_avg(avg: str) -> str:
    key = avg.strip().lower().replace("小时", "h")
    if key in AVG_ALIASES:
        return AVG_ALIASES[key]
    raise ValueError(f"未知平均时段: {avg}。可用: 24h / 1h / 8h")


def _series(pollutant: str, avg: str, year: int = 2026) -> tuple[float | None, ...]:
    p = normalize_pollutant(pollutant)
    a = normalize_avg(avg)
    if year == 2012 and p in TABLE3_2012_PM and a == "24h":
        return TABLE3_2012_PM[p]
    if p not in TABLE3 or a not in TABLE3[p]:
        avail = ", ".join(TABLE3.get(p, {}))
        hint = " 颗粒物实时报请用 24h 断点。" if p in ("PM10", "PM2.5") else ""
        raise ValueError(f"{DISPLAY.get(p, p)} 无 {a} 断点。可用: {avail}.{hint}")
    return TABLE3[p][a]


def compute_iaqi(
    pollutant: str,
    concentration: float | None,
    avg: str,
    year: int = 2026,
) -> int | None:
    """单污染物 IAQI。4.2.6：向上进位取整。无效浓度返回 None。"""
    if concentration is None or concentration != concentration or concentration < 0:
        return None
    p = normalize_pollutant(pollutant)
    a = normalize_avg(avg)
    bps = _series(p, a, year)

    if p == "SO2" and a == "1h" and concentration > 800:
        return 200
    if p == "O3" and a == "8h" and concentration > 800:
        return 300

    defined = [(IAQI_NODES[i], bps[i]) for i in range(len(bps)) if bps[i] is not None]
    nodes, concs = zip(*defined)
    if concentration <= concs[0]:
        return int(nodes[0])
    if concentration >= concs[-1]:
        return int(nodes[-1])
    for i in range(len(concs) - 1):
        lo_c, hi_c = concs[i], concs[i + 1]
        if lo_c <= concentration <= hi_c:
            lo_i, hi_i = nodes[i], nodes[i + 1]
            if hi_c == lo_c:
                return int(hi_i)
            raw = (hi_i - lo_i) / (hi_c - lo_c) * (concentration - lo_c) + lo_i
            # 数学上 raw 恰为整数的浓度（断点、反算点）不应因浮点表示略高而被 ceil 顶到下一档
            if abs(raw - round(raw)) < 1e-9:
                raw = float(round(raw))
            return int(math.ceil(raw))
    return int(nodes[-1])


def iaqi_to_concentration(
    pollutant: str,
    iaqi: int,
    avg: str,
    year: int = 2026,
) -> dict[str, Any]:
    """由目标 IAQI 反推浓度（线性反算点 + ceil 桶）。"""
    p = normalize_pollutant(pollutant)
    a = normalize_avg(avg)
    if iaqi < 0 or iaqi > 500:
        raise ValueError("IAQI 应在 0–500")
    bps = _series(p, a, year)
    defined = [(IAQI_NODES[i], bps[i]) for i in range(len(bps)) if bps[i] is not None]
    nodes, concs = zip(*defined)
    digits = 6 if p == "CO" else 3

    def pack(c: float, note: str, bucket: dict | None = None) -> dict[str, Any]:
        # 反算点位于 ceil 桶顶端（raw IAQI 恰为整数）。半入修约会把浓度略微抬高、
        # 使回算 ceil 到 iaqi+1；向下修约保证报出的浓度回算必得目标 iaqi。
        scale = 10 ** digits
        c_disp = math.floor(float(c) * scale + 1e-6) / scale
        return {
            "pollutant": p, "avg": a, "iaqi": iaqi,
            "concentration": c_disp,
            "unit": UNIT[p], "note": note,
            "ceil_bucket": bucket,
        }

    if iaqi <= nodes[0]:
        return pack(concs[0], "位于断点下限")
    if iaqi >= nodes[-1]:
        note = "已达最高断点，更高浓度仍报该 IAQI"
        if p == "SO2" and a == "1h":
            note = "SO₂ 1h > 800 μg/m³ 时 IAQI 按 200 计，无更高档"
        if p == "O3" and a == "8h":
            note = "O₃ 8h > 800 μg/m³ 时 IAQI 按 300 计，无更高档"
        return pack(concs[-1], note)

    for i in range(len(nodes) - 1):
        lo_i, hi_i = nodes[i], nodes[i + 1]
        if lo_i <= iaqi <= hi_i:
            lo_c, hi_c = concs[i], concs[i + 1]
            span_i = hi_i - lo_i
            c = lo_c if span_i == 0 else (iaqi - lo_i) / span_i * (hi_c - lo_c) + lo_c
            if iaqi == lo_i:
                return pack(c, "落在该档下限断点")
            c_lo = (iaqi - 1 - lo_i) / span_i * (hi_c - lo_c) + lo_c
            bucket = {
                "raw_iaqi_open": iaqi - 1,
                "raw_iaqi_closed": iaqi,
                "conc_exclusive_low": round(c_lo, digits),
                "conc_inclusive_high": round(c, digits),
            }
            return pack(
                c,
                "concentration 为线性反算点；因 4.2.6 向上进位，报出该整数 IAQI 的浓度落在 ceil_bucket",
                bucket,
            )
    raise ValueError(f"{DISPLAY[p]} {a} 无法反算 IAQI={iaqi}")


def category_of(aqi: int | None) -> dict[str, Any] | None:
    if aqi is None:
        return None
    v = min(max(int(aqi), 0), 500)
    for row in CATEGORIES:
        if row["lo"] <= v <= row["hi"]:
            out = dict(row)
            out["rgb_hex"] = "#{:02X}{:02X}{:02X}".format(*row["rgb"])
            return out
    return None


@dataclass
class IaqiItem:
    pollutant: str
    display: str
    avg: str
    concentration: float
    unit: str
    iaqi: int
    sensitive_group: str | None


@dataclass
class AqiResult:
    mode: str
    aqi: int | None
    aqi_published: int | str | None
    primary: list[str]
    complete: bool
    missing: list[str]
    category: dict[str, Any] | None
    items: list[IaqiItem]
    publish_note: str


def compute_aqi(
    concentrations: dict[str, float | None],
    mode: str = "daily",
    year: int = 2026,
    incomplete: bool | None = None,
) -> AqiResult:
    """综合 AQI 与首要污染物。mode: daily | realtime。"""
    mode = mode.lower()
    if mode not in ("daily", "realtime"):
        raise ValueError("mode 必须是 daily 或 realtime")
    avg_map = DAILY_AVG if mode == "daily" else REALTIME_AVG

    items: list[IaqiItem] = []
    missing: list[str] = []
    seen: set[str] = set()
    for k, val in concentrations.items():
        try:
            p = normalize_pollutant(k)
        except ValueError:
            continue
        if p in seen:
            continue
        seen.add(p)
        if val is None or val != val or val < 0:
            missing.append(p)
            continue
        avg = avg_map[p]
        iaqi = compute_iaqi(p, float(val), avg, year)
        if iaqi is None:
            missing.append(p)
            continue
        items.append(IaqiItem(
            pollutant=p, display=DISPLAY[p], avg=avg,
            concentration=float(val), unit=UNIT[p], iaqi=iaqi,
            sensitive_group=SENSITIVE[p] if iaqi > 100 else None,
        ))

    for p in SIX:
        if p not in seen:
            missing.append(p)

    complete = len(missing) == 0
    apply_53 = incomplete if incomplete is not None else (not complete)

    if not items:
        return AqiResult(
            mode=mode, aqi=None, aqi_published="NA", primary=[],
            complete=False, missing=missing, category=None, items=[],
            publish_note="无有效污染物，无法计算 AQI。",
        )

    aqi = max(it.iaqi for it in items)
    primary: list[str] = []
    if aqi > 50:
        top = max(it.iaqi for it in items)
        primary = [it.display for it in items if it.iaqi == top]

    aqi_published: int | str | None = aqi
    if apply_53 and not complete:
        if aqi > 100:
            note = (
                f"5.3.1：缺测 {', '.join(DISPLAY[m] for m in missing)}，"
                f"但 AQI={aqi}>100，仍发布 AQI 与首要污染物。"
            )
        else:
            aqi_published = "NA"
            note = (
                f"5.3.1：缺测 {', '.join(DISPLAY[m] for m in missing)}，"
                f"且 AQI={aqi}≤100，仅发布单项浓度与分指数，AQI 以 NA 标识。"
            )
    else:
        note = ("六项齐全，按式(2) 取最大 IAQI。" if complete
                else "未启用 5.3.1 缺项规则，按已有项取最大 IAQI。")

    cat_src = aqi if isinstance(aqi_published, int) else aqi
    return AqiResult(
        mode=mode, aqi=aqi, aqi_published=aqi_published, primary=primary,
        complete=complete, missing=missing, category=category_of(cat_src),
        items=items, publish_note=note,
    )


def limits_table(year: int = 2026) -> dict[str, Any]:
    rows = []
    for i, iaqi in enumerate(IAQI_NODES):
        row: dict[str, Any] = {"IAQI": iaqi}
        for p, avgs in TABLE3.items():
            for avg, series in avgs.items():
                val: float | None = series[i]
                if year == 2012 and p in TABLE3_2012_PM and avg == "24h":
                    val = TABLE3_2012_PM[p][i]
                row[f"{p}_{avg}"] = val
        rows.append(row)
    return {
        "standard": f"HJ 633—{year}",
        "unit": "SO2/NO2/O3/PM10/PM2.5: μg/m³; CO: mg/m³",
        "notes": [
            "注 a：SO2、NO2、CO、O3 的 1 小时平均浓度限值仅用于实时报。",
            "注 b：SO2 1 小时平均浓度高于 800 μg/m³ 的，IAQI 按 200 计。",
            "注 c：O3 8 小时平均浓度高于 800 μg/m³ 的，IAQI 按 300 计。",
            "颗粒物实时报 1 小时平均使用 24 小时平均断点。",
            "2026 相对 2012：PM2.5 的 IAQI=100 档 75→60 μg/m³；PM10 的 IAQI=100 档 150→120 μg/m³。",
            "4.2.6：IAQI 与 AQI 全部向上进位取整。",
        ],
        "rows": rows,
    }


def result_to_dict(r: AqiResult) -> dict[str, Any]:
    cat = r.category
    return {
        "mode": r.mode,
        "aqi": r.aqi,
        "aqi_published": r.aqi_published,
        "primary_pollutants": r.primary,
        "complete": r.complete,
        "missing": r.missing,
        "category": None if cat is None else {
            "level": cat["level"], "category": cat["category"], "color": cat["color"],
            "rgb": list(cat["rgb"]), "rgb_hex": cat["rgb_hex"], "cmyk": list(cat["cmyk"]),
            "health": cat["health"], "advice": cat["advice"],
        },
        "items": [asdict(it) for it in r.items],
        "publish_note": r.publish_note,
        "sensitive_when_iaqi_gt_100": {
            it.display: it.sensitive_group for it in r.items if it.sensitive_group
        },
    }


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _parse_conc_kwargs(ns: argparse.Namespace) -> dict[str, float]:
    mapping = {
        "so2": "SO2", "no2": "NO2", "co": "CO", "o3": "O3",
        "pm10": "PM10", "pm25": "PM2.5",
    }
    out: dict[str, float] = {}
    for attr, canon in mapping.items():
        v = getattr(ns, attr, None)
        if v is not None:
            out[canon] = v
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="HJ 633—2026 AQI / IAQI 计算")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("iaqi", help="单污染物 IAQI")
    s.add_argument("--pollutant", required=True)
    s.add_argument("--conc", type=float, required=True)
    s.add_argument("--avg", required=True, help="24h / 1h / 8h")
    s.add_argument("--year", type=int, default=2026, choices=(2012, 2026))
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("aqi", help="综合 AQI 与首要污染物")
    s.add_argument("--mode", choices=("daily", "realtime"), default="daily")
    s.add_argument("--so2", type=float)
    s.add_argument("--no2", type=float)
    s.add_argument("--co", type=float)
    s.add_argument("--o3", type=float, help="日报=日最大 8h；实时报=1h")
    s.add_argument("--pm10", type=float)
    s.add_argument("--pm25", type=float)
    s.add_argument("--year", type=int, default=2026, choices=(2012, 2026))
    s.add_argument("--incomplete", action="store_true", help="强制启用 5.3.1")
    s.add_argument("--assume-complete", action="store_true", help="缺项仍直接出 AQI")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("reverse", help="由 IAQI 反推浓度")
    s.add_argument("--pollutant", required=True)
    s.add_argument("--iaqi", type=int, required=True)
    s.add_argument("--avg", required=True)
    s.add_argument("--year", type=int, default=2026, choices=(2012, 2026))
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("limits", help="打印表 3 全表")
    s.add_argument("--year", type=int, default=2026, choices=(2012, 2026))

    s = sub.add_parser("category", help="AQI → 级别/颜色/健康指引")
    s.add_argument("--aqi", type=int, required=True)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("sensitive", help="表 2 敏感人群")
    s.add_argument("--pollutant", required=True)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("compare-2012", help="同一浓度在 2012/2026 断点下的 IAQI")
    s.add_argument("--pollutant", required=True)
    s.add_argument("--conc", type=float, required=True)
    s.add_argument("--avg", default="24h")
    s.add_argument("--json", action="store_true")
    return p


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8()
    args = build_parser().parse_args(argv)

    if args.cmd == "iaqi":
        iaqi = compute_iaqi(args.pollutant, args.conc, args.avg, args.year)
        p = normalize_pollutant(args.pollutant)
        payload = {
            "standard": f"HJ 633—{args.year}", "pollutant": p, "display": DISPLAY[p],
            "avg": normalize_avg(args.avg), "concentration": args.conc,
            "unit": UNIT[p], "iaqi": iaqi,
        }
        if args.json:
            _print_json(payload)
        else:
            print(f"{DISPLAY[p]} {payload['avg']} {args.conc} {UNIT[p]} → IAQI {iaqi}")
        return 0

    if args.cmd == "aqi":
        conc = _parse_conc_kwargs(args)
        if not conc:
            print("请至少提供一项浓度，例如 --pm25 55 --o3 160", file=sys.stderr)
            return 2
        if args.incomplete:
            flag: bool | None = True
        elif args.assume_complete:
            flag = False
        else:
            flag = None
        r = compute_aqi(conc, args.mode, args.year, incomplete=flag)
        d = result_to_dict(r)
        d["standard"] = f"HJ 633—{args.year}"
        if args.json:
            _print_json(d)
        else:
            print(f"[{args.mode}] AQI={d['aqi_published']}  计算值={d['aqi']}")
            print("首要污染物: " + ("、".join(d["primary_pollutants"]) or "无（AQI≤50）"))
            if d["category"]:
                c = d["category"]
                print(f"{c['level']} {c['category']} {c['color']} {c['rgb_hex']}")
                print(f"健康影响: {c['health']}")
                print(f"建议措施: {c['advice']}")
            for it in d["items"]:
                print(f"  {it['display']:6} {it['avg']:3} {it['concentration']} {it['unit']} → IAQI {it['iaqi']}")
            if d["missing"]:
                print("缺测: " + ", ".join(d["missing"]))
            print(d["publish_note"])
        return 0

    if args.cmd == "reverse":
        payload = iaqi_to_concentration(args.pollutant, args.iaqi, args.avg, args.year)
        payload["standard"] = f"HJ 633—{args.year}"
        payload["display"] = DISPLAY[payload["pollutant"]]
        if args.json:
            _print_json(payload)
        else:
            print(
                f"{payload['display']} {payload['avg']} 在 IAQI={payload['iaqi']} 时浓度 = "
                f"{payload['concentration']} {payload['unit']}"
            )
            b = payload.get("ceil_bucket")
            if b:
                print(
                    f"向上进位后报出 IAQI={payload['iaqi']} 的浓度区间: "
                    f"({b['conc_exclusive_low']}, {b['conc_inclusive_high']}] {payload['unit']}"
                )
            if payload.get("note"):
                print(payload["note"])
        return 0

    if args.cmd == "limits":
        _print_json(limits_table(args.year))
        return 0

    if args.cmd == "category":
        cat = category_of(args.aqi)
        if cat is None:
            print("无效 AQI", file=sys.stderr)
            return 2
        payload = {
            "aqi": args.aqi, "level": cat["level"], "category": cat["category"],
            "color": cat["color"], "rgb": list(cat["rgb"]), "rgb_hex": cat["rgb_hex"],
            "cmyk": list(cat["cmyk"]), "health": cat["health"], "advice": cat["advice"],
        }
        if args.json:
            _print_json(payload)
        else:
            print(f"AQI {args.aqi}: {cat['level']} {cat['category']} {cat['color']} {cat['rgb_hex']}")
            print(cat["health"])
            print(cat["advice"])
        return 0

    if args.cmd == "sensitive":
        p = normalize_pollutant(args.pollutant)
        payload = {"pollutant": p, "display": DISPLAY[p], "when": "IAQI>100",
                   "sensitive_group": SENSITIVE[p]}
        if args.json:
            _print_json(payload)
        else:
            print(f"{DISPLAY[p]} 分指数 >100 时敏感人群: {SENSITIVE[p]}")
        return 0

    if args.cmd == "compare-2012":
        a26 = compute_iaqi(args.pollutant, args.conc, args.avg, 2026)
        a12 = compute_iaqi(args.pollutant, args.conc, args.avg, 2012)
        p = normalize_pollutant(args.pollutant)
        payload = {
            "pollutant": p, "avg": normalize_avg(args.avg), "concentration": args.conc,
            "unit": UNIT[p], "iaqi_2012": a12, "iaqi_2026": a26,
            "delta": None if a12 is None or a26 is None else a26 - a12,
        }
        if args.json:
            _print_json(payload)
        else:
            print(
                f"{DISPLAY[p]} {args.conc} {UNIT[p]}: "
                f"2012→IAQI {a12}  2026→IAQI {a26}  Δ={payload['delta']}"
            )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

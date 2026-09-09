#!/usr/bin/env python3
"""按 HJ 633 实时报口径批算 CSV：每项 IAQI + AQI（2026 / 2012）。"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hj633 import compute_aqi


def num(x: str | None) -> float | None:
    x = (x or "").strip()
    if x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def norm_key(k: str) -> str:
    return (
        k.replace("₂", "2")
        .replace("₅", "5")
        .replace("₃", "3")
        .replace("₁₀", "10")
        .replace(" ", "")
    )


def col(row: dict[str, str], *names: str) -> str:
    keymap = {norm_key(k): k for k in row}
    for n in names:
        raw = keymap.get(norm_key(n))
        if raw is not None:
            return row[raw] or ""
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    args = ap.parse_args()
    src, dst = Path(args.src), Path(args.dst)

    with src.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows_in = list(reader)
    if not rows_in:
        print("empty csv", file=sys.stderr)
        return 2

    out_fields = [
        "time", "AQI_csv",
        "PM25", "PM10", "SO2", "NO2", "O3", "CO",
        "IAQI_PM25", "IAQI_PM10", "IAQI_SO2", "IAQI_NO2", "IAQI_O3", "IAQI_CO",
        "AQI_2026", "primary_2026", "level_2026", "cat_2026",
        "AQI_2012", "primary_2012",
        "match_csv_2026", "match_csv_2012", "delta_csv_2026", "delta_csv_2012",
        "complete", "missing",
    ]

    n_cmp = n_m26 = n_m12 = 0
    abs26 = abs12 = 0.0
    before = {"n": 0, "m26": 0, "m12": 0}
    after = {"n": 0, "m26": 0, "m12": 0}

    with dst.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for row in rows_in:
            t = col(row, "Category")
            conc = {
                "PM2.5": num(col(row, "PM2.5")),
                "PM10": num(col(row, "PM10")),
                "SO2": num(col(row, "SO2")),
                "NO2": num(col(row, "NO2")),
                "O3": num(col(row, "O3")),
                "CO": num(col(row, "CO")),
            }
            aqi_csv = num(col(row, "AQI"))
            r26 = compute_aqi(conc, mode="realtime", year=2026, incomplete=False)
            r12 = compute_aqi(conc, mode="realtime", year=2012, incomplete=False)
            ia = {it.pollutant: it.iaqi for it in r26.items}
            cat = r26.category or {}
            rec = {
                "time": t,
                "AQI_csv": "" if aqi_csv is None else int(aqi_csv),
                "PM25": conc["PM2.5"],
                "PM10": conc["PM10"],
                "SO2": conc["SO2"],
                "NO2": conc["NO2"],
                "O3": conc["O3"],
                "CO": conc["CO"],
                "IAQI_PM25": ia.get("PM2.5"),
                "IAQI_PM10": ia.get("PM10"),
                "IAQI_SO2": ia.get("SO2"),
                "IAQI_NO2": ia.get("NO2"),
                "IAQI_O3": ia.get("O3"),
                "IAQI_CO": ia.get("CO"),
                "AQI_2026": r26.aqi,
                "primary_2026": "+".join(r26.primary),
                "level_2026": cat.get("level", ""),
                "cat_2026": cat.get("category", ""),
                "AQI_2012": r12.aqi,
                "primary_2012": "+".join(r12.primary),
                "complete": r26.complete,
                "missing": ",".join(r26.missing),
            }
            if aqi_csv is not None and r26.aqi is not None:
                n_cmp += 1
                csv_i = int(round(aqi_csv))
                rec["delta_csv_2026"] = r26.aqi - csv_i
                rec["match_csv_2026"] = int(r26.aqi == csv_i)
                n_m26 += rec["match_csv_2026"]
                abs26 += abs(r26.aqi - csv_i)
                if r12.aqi is not None:
                    rec["delta_csv_2012"] = r12.aqi - csv_i
                    rec["match_csv_2012"] = int(r12.aqi == csv_i)
                    n_m12 += rec["match_csv_2012"]
                    abs12 += abs(r12.aqi - csv_i)
                b = after if t >= "2026-03-01" else before
                b["n"] += 1
                b["m26"] += rec["match_csv_2026"]
                b["m12"] += rec.get("match_csv_2012") or 0
            w.writerow(rec)

    def pct(a, b):
        return 0 if b == 0 else 100.0 * a / b

    print(f"rows={len(rows_in)} compared={n_cmp}")
    print(f"match_2026={n_m26}/{n_cmp} {pct(n_m26, n_cmp):.2f}% MAE={abs26 / max(n_cmp,1):.3f}")
    print(f"match_2012={n_m12}/{n_cmp} {pct(n_m12, n_cmp):.2f}% MAE={abs12 / max(n_cmp,1):.3f}")
    print(
        f"before_2026-03-01 n={before['n']} "
        f"2026={pct(before['m26'], before['n']):.2f}% 2012={pct(before['m12'], before['n']):.2f}%"
    )
    print(
        f"from_2026-03-01 n={after['n']} "
        f"2026={pct(after['m26'], after['n']):.2f}% 2012={pct(after['m12'], after['n']):.2f}%"
    )
    print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

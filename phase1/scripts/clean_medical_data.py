"""Clean synthetic medical data into a traceable, analysis-ready CSV."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "raw" / "inspection_reports.json"
DEFAULT_OUTPUT = ROOT / "data" / "cleaned" / "inspection_reports_cleaned.csv"
DEFAULT_SUMMARY = ROOT / "data" / "cleaned" / "cleaning_summary.json"

UNIT_ALIASES = {
    "u/l": "U/L",
    "iu/l": "U/L",
    "g/l": "g/L",
    "g/dl": "g/L",
    "10^9/l": "10^9/L",
    "×10^9/l": "10^9/L",
    "x10^9/l": "10^9/L",
    "mmol/l": "mmol/L",
    "mg/dl": "mg/dL",
}

FIELDS = [
    "report_id", "synthetic", "source", "version_year", "modality",
    "indicator_code", "indicator_name", "value", "unit", "ref_low", "ref_high",
    "status", "source_id",
]


def normalize_unit(code: str, value: float, unit: str) -> tuple[float, str, bool]:
    key = unit.strip().lower().replace(" ", "")
    canonical = UNIT_ALIASES.get(key, unit.strip())
    converted = canonical != unit.strip()
    if code == "HGB" and key == "g/dl":
        value *= 10
    if code == "GLU" and key == "mg/dl":
        value *= 0.0555
        canonical = "mmol/L"
    return round(float(value), 3), canonical, converted


def status_for(value: float, low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "unknown"
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "normal"


def clean(input_path: Path, output_path: Path, summary_path: Path) -> dict:
    reports = json.loads(input_path.read_text(encoding="utf-8"))
    rows = []
    seen = set()
    duplicate_rows = 0
    unit_conversions = Counter()
    status_counts = Counter()
    input_rows = 0

    for report in reports:
        for indicator in report.get("indicators", []):
            input_rows += 1
            code = str(indicator.get("code", "")).strip().upper()
            key = (report.get("report_id"), code)
            if key in seen:
                duplicate_rows += 1
                continue
            seen.add(key)
            reference = indicator.get("reference") or {}
            low = reference.get("low")
            high = reference.get("high")
            value, unit, converted = normalize_unit(code, indicator.get("value"), indicator.get("unit", ""))
            if converted:
                unit_conversions[f"{indicator.get('unit')} -> {unit}"] += 1
            status = status_for(value, low, high)
            status_counts[status] += 1
            rows.append(
                {
                    "report_id": report.get("report_id", ""),
                    "synthetic": bool(report.get("synthetic", False)),
                    "source": report.get("source", ""),
                    "version_year": report.get("version_year", ""),
                    "modality": report.get("modality", ""),
                    "indicator_code": code,
                    "indicator_name": indicator.get("name", ""),
                    "value": value,
                    "unit": unit,
                    "ref_low": low,
                    "ref_high": high,
                    "status": status,
                    "source_id": indicator.get("source_id", ""),
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "synthetic_only": all(row["synthetic"] for row in rows),
        "reports_in": len(reports),
        "rows_in": input_rows,
        "rows_out": len(rows),
        "duplicate_rows_removed": duplicate_rows,
        "unit_conversions": dict(unit_conversions),
        "status_counts": dict(status_counts),
        "asset_fields": ["source", "version_year", "modality", "synthetic", "source_id"],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    summary = clean(args.input, args.output, args.summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

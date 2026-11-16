"""Generate deterministic synthetic inspection reports for the prototype."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "raw" / "inspection_reports.json"

INDICATORS = [
    ("ALT", "丙氨酸氨基转移酶", "U/L", 0, 40),
    ("AST", "天门冬氨酸氨基转移酶", "U/L", 0, 40),
    ("HGB", "血红蛋白", "g/L", 120, 160),
    ("WBC", "白细胞", "10^9/L", 4, 10),
    ("GLU", "空腹血糖", "mmol/L", 3.9, 6.1),
]

VALUES = [
    [(68, "IU/L"), (35, "U/L"), (11.8, "g/dL"), (6.2, "×10^9/L"), (5.4, "mmol/L")],
    [(32, "U/L"), (45, "IU/L"), (132, "g/L"), (3.7, "10^9/L"), (6.4, "mmol/L")],
    [(40, "U/L"), (38, "U/L"), (145, "g/L"), (7.1, "10^9/L"), (4.8, "mmol/L")],
    [(52, "U/L"), (61, "U/L"), (110, "g/L"), (5.5, "10^9/L"), (7.2, "mmol/L")],
    [(24, "U/L"), (29, "U/L"), (155, "g/L"), (8.4, "10^9/L"), (5.9, "mmol/L")],
    [(46, "U/L"), (42, "U/L"), (126, "g/L"), (4.1, "10^9/L"), (4.2, "mmol/L")],
    [(18, "U/L"), (21, "U/L"), (116, "g/L"), (9.6, "10^9/L"), (5.1, "mmol/L")],
    [(75, "U/L"), (34, "U/L"), (142, "g/L"), (6.8, "10^9/L"), (5.6, "mmol/L")],
    [(39, "U/L"), (39, "U/L"), (161, "g/L"), (4.9, "10^9/L"), (6.0, "mmol/L")],
    [(27, "U/L"), (47, "U/L"), (135, "g/L"), (3.5, "10^9/L"), (5.0, "mmol/L")],
]


def main() -> None:
    reports = []
    for index, values in enumerate(VALUES, start=1):
        report_id = f"R{index:03d}"
        indicators = []
        for (code, name, canonical_unit, low, high), (value, unit) in zip(INDICATORS, values):
            indicators.append(
                {
                    "code": code,
                    "name": name,
                    "value": value,
                    "unit": unit,
                    "reference": {"low": low, "high": high},
                    "source_id": f"SRC-{report_id}-{code}",
                }
            )
        reports.append(
            {
                "report_id": report_id,
                "synthetic": True,
                "source": "synthetic_demo_batch_v1",
                "version_year": 2026,
                "modality": "text_table",
                "indicators": indicators,
            }
        )

    # Keep one duplicate row to verify that the cleaning script removes it deterministically.
    reports[0]["indicators"].append(dict(reports[0]["indicators"][0]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(reports)} reports to {OUTPUT}")


if __name__ == "__main__":
    main()

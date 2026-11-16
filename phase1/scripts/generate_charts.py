"""Generate three document-ready charts from the cleaned demo data."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "cleaned" / "inspection_reports_cleaned.csv"
OUT_DIR = ROOT / "charts"
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    rows = load_rows()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = FontProperties(fname=str(FONT_PATH)) if FONT_PATH.exists() else None
    plt.rcParams["axes.unicode_minus"] = False
    if font:
        plt.rcParams["font.family"] = font.get_name()

    names = {}
    totals = Counter()
    abnormal = Counter()
    statuses = Counter()
    units = Counter()
    for row in rows:
        code = row["indicator_code"]
        names[code] = row["indicator_name"]
        totals[code] += 1
        statuses[row["status"]] += 1
        units[row["unit"]] += 1
        if row["status"] in {"high", "low"}:
            abnormal[code] += 1

    codes = list(names)
    labels = [f"{code}\n{names[code]}" for code in codes]
    rates = [abnormal[code] / totals[code] * 100 for code in codes]

    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=160)
    bars = ax.bar(labels, rates, color="#1f5eff")
    ax.set_title("各指标异常标记率（合成样本）", fontsize=16, fontweight="bold")
    ax.set_ylabel("异常标记率（%）")
    ax.set_ylim(0, max(rates + [10]) * 1.25)
    ax.grid(axis="y", alpha=.22)
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{rate:.0f}%", ha="center", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "abnormal_rate.png", bbox_inches="tight")
    plt.close(fig)

    status_labels = ["normal", "high", "low"]
    status_names = {"normal": "正常范围", "high": "高于范围", "low": "低于范围"}
    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=160)
    values = [statuses[label] for label in status_labels]
    bars = ax.bar([status_names[label] for label in status_labels], values, color=["#157347", "#b42318", "#9a6700"])
    ax.set_title("清洗后指标状态分布", fontsize=16, fontweight="bold")
    ax.set_ylabel("记录数")
    ax.grid(axis="y", alpha=.22)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + .25, str(value), ha="center", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "status_distribution.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=160)
    unit_labels = list(units)
    unit_values = [units[label] for label in unit_labels]
    bars = ax.bar(unit_labels, unit_values, color="#5b7cfa")
    ax.set_title("规范化单位分布", fontsize=16, fontweight="bold")
    ax.set_ylabel("记录数")
    ax.grid(axis="y", alpha=.22)
    for bar, value in zip(bars, unit_values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + .25, str(value), ha="center", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "normalized_units.png", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote charts to {OUT_DIR}")


if __name__ == "__main__":
    main()

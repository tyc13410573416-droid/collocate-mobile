"""Generate five final charts for the stage-two document and demo package."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "phase1" / "data" / "cleaned" / "inspection_reports_cleaned.csv"
OUT_DIR = ROOT / "phase2" / "charts"
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def style(font: FontProperties | None) -> None:
    plt.rcParams["axes.unicode_minus"] = False
    if font:
        plt.rcParams["font.family"] = font.get_name()


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT_DIR / name, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    rows = load_rows()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = FontProperties(fname=str(FONT_PATH)) if FONT_PATH.exists() else None
    style(font)

    names: dict[str, str] = {}
    totals = Counter()
    abnormal = Counter()
    statuses = Counter()
    units = Counter()
    reports = Counter()
    values: dict[str, list[float]] = {}
    for row in rows:
        code = row["indicator_code"]
        names[code] = row["indicator_name"]
        totals[code] += 1
        reports[row["report_id"]] += 1
        statuses[row["status"]] += 1
        units[row["unit"]] += 1
        values.setdefault(code, []).append(float(row["value"]))
        if row["status"] in {"high", "low"}:
            abnormal[code] += 1

    codes = list(names)
    labels = [f"{code}\n{names[code]}" for code in codes]

    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=160)
    rates = [abnormal[code] / totals[code] * 100 for code in codes]
    bars = ax.bar(labels, rates, color="#1f5eff")
    ax.set_title("各指标异常标记率（合成样本）", fontsize=16, fontweight="bold")
    ax.set_ylabel("异常标记率（%）")
    ax.set_ylim(0, max(rates + [10]) * 1.25)
    ax.grid(axis="y", alpha=.22)
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{rate:.0f}%", ha="center", fontsize=10)
    save(fig, "01_abnormal_rate_final.png")

    status_labels = ["normal", "high", "low"]
    status_names = {"normal": "正常范围", "high": "高于范围", "low": "低于范围"}
    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=160)
    status_values = [statuses[label] for label in status_labels]
    bars = ax.bar([status_names[label] for label in status_labels], status_values, color=["#157347", "#b42318", "#9a6700"])
    ax.set_title("清洗后指标状态分布", fontsize=16, fontweight="bold")
    ax.set_ylabel("记录数")
    ax.grid(axis="y", alpha=.22)
    for bar, value in zip(bars, status_values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + .25, str(value), ha="center", fontsize=11)
    save(fig, "02_status_distribution_final.png")

    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=160)
    unit_labels = list(units)
    unit_values = [units[label] for label in unit_labels]
    bars = ax.bar(unit_labels, unit_values, color="#5b7cfa")
    ax.set_title("规范化单位分布", fontsize=16, fontweight="bold")
    ax.set_ylabel("记录数")
    ax.grid(axis="y", alpha=.22)
    for bar, value in zip(bars, unit_values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + .25, str(value), ha="center", fontsize=11)
    save(fig, "03_normalized_units_final.png")

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=160)
    report_ids = list(reports)
    completeness = [reports[report_id] for report_id in report_ids]
    bars = ax.bar(report_ids, completeness, color="#2f7fba")
    ax.axhline(5, color="#157347", linestyle="--", linewidth=1.5, label="完整样本应有 5 项")
    ax.set_title("样本结构完整度", fontsize=16, fontweight="bold")
    ax.set_ylabel("指标记录数")
    ax.set_ylim(0, 6)
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=.22)
    for bar, value in zip(bars, completeness):
        ax.text(bar.get_x() + bar.get_width() / 2, value + .08, str(value), ha="center", fontsize=10)
    save(fig, "04_report_completeness_final.png")

    fig, ax = plt.subplots(figsize=(11, 6), dpi=160)
    box_values = [values[code] for code in codes]
    bp = ax.boxplot(box_values, labels=codes, patch_artist=True, showmeans=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("#dbe5ff")
        patch.set_edgecolor("#1f5eff")
    ax.set_title("各指标单位统一后数值分布", fontsize=16, fontweight="bold")
    ax.set_ylabel("单位统一后数值")
    ax.grid(axis="y", alpha=.22)
    save(fig, "05_indicator_value_distribution_final.png")
    print(f"wrote 5 final charts to {OUT_DIR}")


if __name__ == "__main__":
    main()

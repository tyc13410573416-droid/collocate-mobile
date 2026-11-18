# -*- coding: utf-8 -*-
"""evidence_gate 门控规则引擎 v1 —— 赛题3主打创新「证据冲突感知门控」的核心。

设计原则（冲刺表 v3 明确要求）：
  **规则先行，模型只做说明** —— 三态判定由本文件纯 Python 确定性完成，
  大模型只负责把结果翻译成人话，规避「工具调用不稳定」。

门控三态（decision_gate）：
  pass    证据一致 且 置信度 >= 0.8          → 直接给结论
  review  来源/版本参考区间冲突               → 只给说明、不给结论，需人工复核
  abstain 证据缺失 或 置信度 < 0.8            → 拒答或追问关键字段

门控 6 字段（11.17 已冻结，改动需三人同意）：
  decision_gate / confidence / evidence_status / conflicts / next_action / source_versions
"""
from range_parser import parse_range, has_gender_specific, range_to_display

CONFIDENCE_THRESHOLD = 0.8


def _compute_confidence(value, gender, range_map) -> float:
    """置信度：字段齐全度。分性别指标缺性别时降到阈值以下 → 触发 abstain。"""
    if value is None:
        return 0.4
    conf = 0.95
    if has_gender_specific(range_map) and not gender:
        conf -= 0.25  # 0.70，低于 0.8 → abstain，追问性别
    return conf


def _judge_value(value: float, r: dict) -> str:
    """判断检测值相对区间的方位：within / below / above"""
    low, high = r.get("low"), r.get("high")
    if low is not None and value < low:
        return "below"
    if high is not None and value > high:
        return "above"
    return "within"


def _select_range(range_map: dict, gender):
    """按性别选择区间：优先精确性别，其次通用区间。"""
    if gender and gender in range_map:
        return range_map[gender], gender
    if "default" in range_map:
        return range_map["default"], "default"
    # 分性别但没给 gender：取男性区间做展示，但置信度已在 _compute_confidence 里扣减
    if "male" in range_map:
        return range_map["male"], "male"
    return None, None


def _detect_conflicts(references) -> list:
    """检测多来源同一指标参考区间是否冲突。

    两两比较同一性别维度的区间上下限，任一不同即视为冲突（参考区间应是精确值）。
    返回冲突列表，每项：{field, source_a, source_b, detail}
    """
    conflicts = []
    n = len(references)
    for i in range(n):
        for j in range(i + 1, n):
            ra = references[i]
            rb = references[j]
            range_a = ra.get("gender_range") or parse_range(ra.get("reference_range", ""))
            range_b = rb.get("gender_range") or parse_range(rb.get("reference_range", ""))
            # 比较公共维度
            for dim in set(range_a.keys()) & set(range_b.keys()):
                low_a, high_a = range_a[dim]["low"], range_a[dim]["high"]
                low_b, high_b = range_b[dim]["low"], range_b[dim]["high"]
                if low_a != low_b or high_a != high_b:
                    conflicts.append({
                        "field": "reference_range",
                        "dimension": dim,
                        "source_a": ra.get("source_id"),
                        "source_b": rb.get("source_id"),
                        "detail": (
                            f"{ra.get('source_id')} {range_to_display({dim: range_a[dim]})} "
                            f"vs {rb.get('source_id')} {range_to_display({dim: range_b[dim]})}"
                        ),
                    })
    return conflicts


def evaluate(indicator, value, gender=None, age=None, references=None) -> dict:
    """门控主入口。

    Args:
        indicator:   指标名（展示用，不参与判定）
        value:       检测值（float 或 None）
        gender:      性别 'male' / 'female' / None
        age:         年龄（预留，v1 不参与判定）
        references:  该指标的多来源数据列表。每项至少含 source_id / source_version /
                     effective_date / reference_range（或已解析好的 gender_range）。

    Returns:
        6 字段门控 JSON（dict）。
    """
    references = references or []
    source_versions = [
        {
            "source_id": r.get("source_id") or r.get("source"),
            "version": r.get("source_version") or "v1",
            "effective_date": r.get("effective_date") or str(r.get("source_year", "")),
        }
        for r in references
    ]

    # 1. 证据缺失：无来源或无数值
    if not references:
        return {
            "decision_gate": "abstain",
            "confidence": 0.0,
            "evidence_status": "missing",
            "conflicts": [],
            "next_action": "无法定位该指标的参考区间，请补充标准数据",
            "source_versions": source_versions,
        }
    if value is None:
        return {
            "decision_gate": "abstain",
            "confidence": 0.4,
            "evidence_status": "missing",
            "conflicts": [],
            "next_action": "缺少检测值，请补充后重新解读",
            "source_versions": source_versions,
        }

    # 2. 解析各来源区间 + 检测冲突（冲突优先，一旦冲突即 review）
    range_map = references[0].get("gender_range") or parse_range(references[0].get("reference_range", ""))
    conflicts = _detect_conflicts(references)
    if conflicts:
        return {
            "decision_gate": "review",
            "confidence": _compute_confidence(value, gender, range_map),
            "evidence_status": "conflict",
            "conflicts": conflicts,
            "next_action": "来源参考区间不一致，需人工复核后再给结论",
            "source_versions": source_versions,
        }

    # 3. 置信度/关键字段判定（阈值 0.8）。缺性别是可澄清的 review，
    # 只有没有任何指标或参考依据时才 abstain。
    confidence = _compute_confidence(value, gender, range_map)
    if confidence < CONFIDENCE_THRESHOLD:
        if has_gender_specific(range_map) and not gender:
            return {
                "decision_gate": "review",
                "confidence": confidence,
                "evidence_status": "missing",
                "conflicts": [],
                "next_action": "该指标参考区间区分男女，请补充性别后重新解读",
                "clarification": {"field": "gender", "prompt": "请提供患者性别，以便准确选择参考区间"},
                "source_versions": source_versions,
            }
        return {
            "decision_gate": "review",
            "confidence": confidence,
            "evidence_status": "low_confidence",
            "conflicts": [],
            "next_action": "证据不完整，置信度不足，请补充关键字段",
            "clarification": {"field": "report_value", "prompt": "请核对报告中的指标数值"},
            "source_versions": source_versions,
        }

    # 4. 通过：判断值方位，给结论
    r, dim = _select_range(range_map, gender)
    position = _judge_value(value, r) if r else "within"
    item = references[0]
    direction = item.get("abnormal_direction", "")
    if position == "within":
        hint = "该检测值处于参考区间内，结论为大致正常"
    elif position == "below":
        hint = f"该检测值低于参考下限，方向为「{direction}」中的偏低侧"
    else:
        hint = f"该检测值高于参考上限，方向为「{direction}」中的偏高侧"

    return {
        "decision_gate": "pass",
        "confidence": confidence,
        "evidence_status": "found",
        "conflicts": [],
        "next_action": hint,
        "source_versions": source_versions,
    }

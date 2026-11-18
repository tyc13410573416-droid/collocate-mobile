# -*- coding: utf-8 -*-
"""参考区间文本解析器：把 references.json 里的 reference_range 字符串
解析成结构化数值区间，供 query_reference 返回、evidence_gate 做数值比较。

支持的格式（34 条数据里出现的全部变体）：
  - 分性别：「男 9–50；女 7–40」
  - 带年龄备注：「男 57–97；女 41–73（20–59岁）」
  - 无性别区间：「3.9–6.1」「11–14.5」
  - 单侧上限：「<5.2」「<10（常规CRP）」
  - 单侧下限：「≥1.0」
"""
import re

NUM = r"(\d+(?:\.\d+)?)"
# 区间连接符：en-dash / em-dash / 连字符 / 波浪号 / 全角波浪
_RANGE_RE = re.compile(NUM + r"\s*[–—\-~～]\s*" + NUM)
_LT_RE = re.compile(r"<\s*" + NUM)
_GT_RE = re.compile(r"[>≥]\s*" + NUM)


def _strip_note(text: str) -> str:
    """去掉括号备注，如「（20–59岁）」「（合适水平）」「（常规CRP）」"""
    return re.sub(r"[（(][^）)]*[）)]", "", text)


def _detect_gender(seg: str) -> str:
    if "男" in seg:
        return "male"
    if "女" in seg:
        return "female"
    return "default"


def _parse_single(seg: str) -> dict:
    """解析单段区间文本 → {"low": float|None, "high": float|None}"""
    seg = re.sub(r"^(男|女)\s*[:：]?\s*", "", seg.strip())
    seg = seg.strip()
    m = _RANGE_RE.search(seg)
    if m:
        return {"low": float(m.group(1)), "high": float(m.group(2))}
    m = _LT_RE.search(seg)
    if m:
        return {"low": None, "high": float(m.group(1))}
    m = _GT_RE.search(seg)
    if m:
        return {"low": float(m.group(1)), "high": None}
    return {"low": None, "high": None}


def parse_range(text: str) -> dict:
    """把参考区间文本解析成结构化区间。

    返回：{"male": {low, high}, "female": {low, high}} 或
          {"default": {low, high}}
    解析失败返回空 dict。
    """
    if not text:
        return {}
    text = _strip_note(text.strip())
    if not text:
        return {}

    result = {}
    segments = [s for s in re.split(r"[；;]", text) if s.strip()]
    if len(segments) == 1:
        seg = segments[0]
        gender = _detect_gender(seg)
        result[gender] = _parse_single(seg)
    else:
        for seg in segments:
            gender = _detect_gender(seg)
            result[gender] = _parse_single(seg)
    return result


def has_gender_specific(range_map: dict) -> bool:
    """该指标的参考区间是否区分男女（决定缺性别时是否降低置信度）"""
    return "male" in range_map or "female" in range_map


def range_to_display(range_map: dict) -> str:
    """把结构化区间还原成可读文本（用于返回给 Agent / 文档）"""
    parts = []
    for key, label in (("male", "男"), ("female", "女"), ("default", "通用")):
        if key in range_map:
            r = range_map[key]
            low, high = r.get("low"), r.get("high")
            if low is not None and high is not None:
                parts.append(f"{label} {low:g}–{high:g}")
            elif high is not None:
                parts.append(f"{label} <{high:g}")
            elif low is not None:
                parts.append(f"{label} ≥{low:g}")
    return "；".join(parts)

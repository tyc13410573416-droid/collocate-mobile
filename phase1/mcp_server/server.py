# -*- coding: utf-8 -*-
"""Nexent 医疗智能体 MCP Server —— 赛题3「检验报告解读与用药禁忌核查」

工具（阶段二联调版）：
  query_reference  查参考区间，返回 来源/版本/性别 结构化字段（含溯源）
  parse_report     解析检验单文本 → 指标名 + 数值 + 单位 + confidence
  normalize        统一常见医学检验单位，并返回换算证据
  check_interaction 用药与异常指标的规则化禁忌核查（仅输出复核提示）
  evidence_gate    门控三态判定（pass / review / abstain），输出冻结的 6 字段

接入 Nexent（Docker 部署）：
  资源仓库 → 添加 MCP 服务器 → 服务器 URL 填 http://host.docker.internal:3001/mcp
  先在宿主机启动：C:/Python314/python.exe D:/ict1.0/nexent-mcp/server.py --http
"""
import json
import re
from pathlib import Path
from typing import Any, List, Optional

try:
    from fastmcp import FastMCP
    FASTMCP_AVAILABLE = True
except ImportError:  # pragma: no cover - allows pure-Python rule tests on the demo host
    FASTMCP_AVAILABLE = False

    class FastMCP:  # type: ignore[no-redef]
        """Compatibility shim so rule tests run without the optional transport."""

        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self, fn=None, **_kwargs):
            if fn is None:
                return lambda wrapped: wrapped
            return fn

        def run(self, *_args, **_kwargs):
            raise RuntimeError(
                "MCP transport requires fastmcp; install dependencies from "
                "phase1/mcp_server/requirements.txt."
            )


from range_parser import parse_range
from gate_engine import evaluate as gate_evaluate

DATA_DIR = Path(__file__).parent / "data"
REFERENCES_FILE = DATA_DIR / "references.json"

mcp = FastMCP("medical-report-agent")


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def _load_references() -> dict:
    """把 data/references.json 加载成「别名 -> 条目」索引。"""
    if not REFERENCES_FILE.exists():
        return {}
    with open(REFERENCES_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)
    index = {}
    for it in items:
        keys = [it.get("key"), it.get("name"), it.get("name_en")]
        aliases = it.get("alias") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in keys + aliases:
            if alias:
                index[str(alias).strip().lower()] = it
    return index


_REF_INDEX = _load_references()


# ---------------------------------------------------------------------------
# 阶段二工具规则（可由真实 Nexent Skill 替换）
# ---------------------------------------------------------------------------
_UNIT_ALIASES = {
    "iu/l": "u/l",
    "μg/l": "ug/l",
    "µg/l": "ug/l",
    "μmol/l": "umol/l",
    "µmol/l": "umol/l",
    "×10⁹/l": "10^9/l",
    "×10^9/l": "10^9/l",
    "10^3/ul": "10^9/l",
    "10^3/μl": "10^9/l",
    "10^3/µl": "10^9/l",
}

# factor 表示：目标单位 = 输入数值 × factor。仅放入确定性、常用且可解释的换算。
_UNIT_FACTORS = {
    ("g/dl", "g/l"): 10.0,
    ("mg/dl", "mmol/l"): 1 / 18.0,       # glucose-like values
    ("mmol/l", "mg/dl"): 18.0,
    ("mg/dl", "umol/l"): 88.4,            # creatinine-like values
    ("umol/l", "mg/dl"): 1 / 88.4,
    ("10^3/ul", "10^9/l"): 1.0,
    ("10^9/l", "10^3/ul"): 1.0,
    ("iu/l", "u/l"): 1.0,
    ("u/l", "iu/l"): 1.0,
}


def _unit_key(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "")
    return _UNIT_ALIASES.get(text, text)


def _canonical_unit(indicator: str, target_unit: str = "") -> str:
    if target_unit:
        return str(target_unit)
    item = _REF_INDEX.get(str(indicator or "").strip().lower())
    return str(item.get("unit") if item else "")


def _conversion_factor(indicator: str, source: str, target: str) -> Optional[float]:
    """返回仅适用于该指标的安全换算因子；不确定时返回 None。"""
    key = str(indicator or "").strip().lower()
    if (source, target) in {("mg/dl", "mmol/l"), ("mmol/l", "mg/dl")}:
        glucose_keys = {"glu", "glucose", "血糖", "空腹血糖", "葡萄糖"}
        if key not in glucose_keys:
            return None
    if (source, target) in {("mg/dl", "umol/l"), ("umol/l", "mg/dl")}:
        creatinine_keys = {"cr", "crea", "creatinine", "肌酐", "血肌酐"}
        if key not in creatinine_keys:
            return None
    return _UNIT_FACTORS.get((source, target))


@mcp.tool
def normalize(indicator: str, value: float, from_unit: str, to_unit: str = "") -> dict:
    """统一常见检验单位，返回可审计的换算信息。

    不确定的换算不会猜测，返回 ``review``，由人工或后端 Skill 选择目标单位。
    ``mg/dL ↔ mmol/L`` 适用于血糖类演示，肌酐使用 ``mg/dL ↔ μmol/L``。
    """
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return {"status": "review", "indicator": indicator, "message": "value 必须是数值"}
    source = _unit_key(from_unit)
    target_display = _canonical_unit(indicator, to_unit)
    target = _unit_key(target_display)
    if not source or not target:
        return {"status": "review", "indicator": indicator, "input": {"value": numeric, "unit": from_unit}, "message": "缺少输入或目标单位"}
    if source == target:
        return {
            "status": "pass", "indicator": indicator, "value": numeric,
            "unit": target_display or from_unit, "original_value": numeric,
            "original_unit": from_unit, "conversion": "identity", "confidence": 1.0,
        }
    factor = _conversion_factor(indicator, source, target)
    if factor is None:
        return {
            "status": "review", "indicator": indicator,
            "input": {"value": numeric, "unit": from_unit},
            "target_unit": target_display, "conversion": None, "confidence": 0.0,
            "message": f"暂不支持 {from_unit} → {target_display} 的确定性换算",
        }
    converted = numeric * factor
    return {
        "status": "pass", "indicator": indicator, "value": round(converted, 6),
        "unit": target_display, "original_value": numeric, "original_unit": from_unit,
        "conversion": f"{from_unit} → {target_display}", "factor": factor, "confidence": 0.99,
    }


_INTERACTION_RULES = [
    {
        "drug_aliases": ["阿托伐他汀", "atorvastatin"],
        "indicators": ["alt", "ast", "丙氨酸氨基转移酶", "天门冬氨酸氨基转移酶"],
        "risk": "发现肝酶相关异常，需结合药品说明书与专业人员复核用药风险",
        "source": "阿托伐他汀药品说明书（演示规则）",
        "source_id": "SRC-DRUG-ATORVASTATIN-001",
    },
    {
        "drug_aliases": ["华法林", "warfarin"],
        "indicators": ["inr", "pt", "凝血酶原标准化比值", "凝血酶原时间"],
        "risk": "发现凝血相关指标，需复核华法林相关出血风险与医嘱",
        "source": "华法林药品说明书（演示规则）",
        "source_id": "SRC-DRUG-WARFARIN-001",
    },
    {
        "drug_aliases": ["二甲双胍", "metformin"],
        "indicators": ["cr", "肌酐", "血肌酐"],
        "risk": "发现肾功能相关指标，需结合肾功能评估与药品说明书复核",
        "source": "二甲双胍药品说明书（演示规则）",
        "source_id": "SRC-DRUG-METFORMIN-001",
    },
]


def _as_names(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,，;；\n]+", value) if part.strip()]
    if isinstance(value, dict):
        value = [value]
    result = []
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                item = item.get("drug_name") or item.get("drug") or item.get("test_name") or item.get("indicator")
            if item:
                result.append(str(item).strip())
    return result


def _indicator_names(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip().lower() for part in re.split(r"[,，;；\n]+", value) if part.strip()]
    result = []
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                status = str(item.get("status") or "").lower()
                if status and status not in ("high", "low"):
                    continue
                item = item.get("indicator") or item.get("indicator_code") or item.get("abbreviation") or item.get("test_name")
            if item:
                result.append(str(item).strip().lower())
    return result


@mcp.tool
def check_interaction(medications: Any, indicators: Any = None) -> dict:
    """检查当前用药与异常指标是否命中已配置的复核规则。

    这是安全门控提示，不是诊断、停药或剂量调整建议。未命中规则时返回空
    ``warnings``；规则命中时必须带 ``source`` 和 ``source_id``。
    """
    drugs = _as_names(medications)
    names = _indicator_names(indicators)
    warnings = []
    for rule in _INTERACTION_RULES:
        drug_hit = any(alias.lower() in drug.lower() for drug in drugs for alias in rule["drug_aliases"])
        indicator_hit = any(alias.lower() in name for name in names for alias in rule["indicators"])
        if drug_hit and indicator_hit:
            warnings.append({
                "drug": next((drug for drug in drugs if any(alias.lower() in drug.lower() for alias in rule["drug_aliases"])), drugs[0] if drugs else "当前用药"),
                "risk": rule["risk"], "source": rule["source"], "source_id": rule["source_id"],
                "severity": "review", "level": "review",
            })
    return {
        "status": "review" if warnings else "pass", "checked_medications": drugs,
        "checked_indicators": names, "warnings": warnings,
        "next_action": "请由专业人员结合说明书复核" if warnings else "未命中已配置的演示规则",
    }


def _enhance(item: dict) -> dict:
    """给条目补门控所需字段。优先读真实字段，缺失时用现有数据推导占位。

    注意：source_version / effective_date 目前是占位值（v1 + 年份），
    等万嘉宜知识库 v2（含真实 version/effective_date/source_id）到位后替换。
    """
    out = dict(item)
    out["source_id"] = item.get("source_id") or item.get("source")
    out["source_version"] = item.get("source_version") or "v1"
    out["effective_date"] = item.get("effective_date") or str(item.get("source_year", ""))
    out["gender_range"] = item.get("gender_range") or parse_range(item.get("reference_range", ""))
    return out


# ---------------------------------------------------------------------------
# 工具 1：query_reference
# ---------------------------------------------------------------------------
@mcp.tool
def query_reference(indicator: str) -> dict:
    """查询检验指标的参考区间，返回 来源(source_id)/版本/性别 结构化字段。

    Args:
        indicator: 指标名。支持中文名（如「谷丙转氨酶」）或英文缩写（ALT / CREA / GLU）。
    """
    item = _REF_INDEX.get(indicator.strip().lower())
    if item is None:
        return {"found": False, "message": f"未找到指标「{indicator}」。", "source": None}
    return {"found": True, **_enhance(item)}


# ---------------------------------------------------------------------------
# 工具 2：parse_report
# ---------------------------------------------------------------------------
def _extract_value(tail: str):
    """在指标名之后的文本片段里找第一个数值（支持小数）。"""
    m = re.search(r"(\d+(?:\.\d+)?)", tail)
    return float(m.group(1)) if m else None


def _build_candidates():
    """构建 (别名, 条目) 列表，按别名长度降序，避免短别名截断长别名。"""
    candidates = []
    for it in _load_references().values():
        seen = set()
        keys = [it.get("key"), it.get("name"), it.get("name_en")]
        aliases = it.get("alias") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for a in keys + aliases:
            if a and a not in seen:
                seen.add(a)
                candidates.append((a, it))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)
    return candidates


@mcp.tool
def parse_report(text: str) -> dict:
    """解析检验单文本，抽取可识别的指标名 + 检测值 + 单位，返回 confidence。

    confidence：字段齐全度（指标名找到且数值找到 = 0.9，只有指标名 = 0.5）。

    Args:
        text: 检验单文本，如「谷丙转氨酶 68 U/L，肌酐 88 μmol/L」。
    """
    items = []
    matched_keys = set()
    for alias, it in _build_candidates():
        key = it.get("key")
        if key in matched_keys:
            continue
        # 英文缩写用词边界匹配，避免单字母（K/Na/Ca/Cl）误匹配普通单词
        if alias.isascii():
            m = re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", text)
            if not m:
                continue
            pos = m.end()
        else:
            pos = text.find(alias)
            if pos == -1:
                continue
            pos += len(alias)
        value = _extract_value(text[pos:pos + 40])
        matched_keys.add(key)
        items.append({
            "indicator": it.get("name_en") or key,
            "name": it.get("name"),
            "value": value,
            "unit": it.get("unit"),
            "confidence": 0.9 if value is not None else 0.5,
        })

    return {
        "matched_count": len(items),
        "items": items,
        "raw_text": text,
    }


# ---------------------------------------------------------------------------
# 工具 3：evidence_gate
# ---------------------------------------------------------------------------
@mcp.tool
def evidence_gate(indicator: str, value: float, gender: str = "", age: str = "") -> dict:
    """门控三态判定：pass（通过）/ review（复核）/ abstain（拒答）。

    输出冻结的 6 字段：decision_gate / confidence / evidence_status /
    conflicts / next_action / source_versions。

    Args:
        indicator: 指标名（中文名或英文缩写）
        value:     检测值（数值）
        gender:    性别 male / female（可选，缺省为空）
        age:       年龄（可选，v1 暂不参与判定）
    """
    item = _REF_INDEX.get(indicator.strip().lower())
    refs = [_enhance(item)] if item else []
    g = (gender or "").strip().lower()
    if g not in ("male", "female"):
        g = None
    return gate_evaluate(indicator, value, gender=g, age=age or None, references=refs)


if __name__ == "__main__":
    import sys

    if not FASTMCP_AVAILABLE:
        raise SystemExit(
            "fastmcp is not installed. Install phase1/mcp_server/requirements.txt "
            "with Python 3.10+ before starting the MCP transport."
        )

    if "--http" in sys.argv:
        # streamable-http 模式：Nexent 通过「添加MCP服务器 → 服务器URL」接入
        port = 3001
        for i, a in enumerate(sys.argv):
            if a == "--http" and i + 1 < len(sys.argv):
                try:
                    port = int(sys.argv[i + 1])
                except ValueError:
                    pass
        mcp.run(transport="http", host="0.0.0.0", port=port)
    else:
        # stdio 模式：本地测试用
        mcp.run()

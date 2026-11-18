# -*- coding: utf-8 -*-
"""Nexent 医疗智能体 MCP Server —— 赛题3「检验报告解读与用药禁忌核查」

工具（阶段一 v3 门控版）：
  query_reference  查参考区间，返回 来源/版本/性别 结构化字段（含溯源）
  parse_report     解析检验单文本 → 指标名 + 数值 + 单位 + confidence
  evidence_gate    门控三态判定（pass / review / abstain），输出冻结的 6 字段

接入 Nexent（Docker 部署）：
  资源仓库 → 添加 MCP 服务器 → 服务器 URL 填 http://host.docker.internal:3001/mcp
  先在宿主机启动：C:/Python314/python.exe D:/ict1.0/nexent-mcp/server.py --http
"""
import json
import re
from pathlib import Path

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

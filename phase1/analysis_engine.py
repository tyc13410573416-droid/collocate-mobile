"""Shared, deterministic analysis logic for the stage-one demo."""

from __future__ import annotations

import csv
import hashlib
import os
import re
from typing import Any, Optional


DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__), "data", "cleaned", "inspection_reports_cleaned.csv"
)


# 脱敏实测图片的最小演示结构。它们用于验证“图片资产 → 结构化指标卡”，
# 不把图片中的姓名、编号等隐私字段写入结果。真实 OCR 接入后由 parse_report 替换。
IMAGE_SAMPLE_DATA = {
    "coagulation": {
        "report_id": "R007",
        "raw_text": "图1 凝血四项（脱敏演示）：PT 19.40 s ↑（9.4-12.5）；PTA 47 % ↓（80-160）；INR 1.7 ↑（0.8-1.2）；Ratio 1.7 ↑（0.8-1.2）；APTT 40.2 s ↑（21-37）；Fib 5.80 g/L ↑（2-4）；TT 20.2 s ↑（13.5-19.5）；DD 254 μg/L（DDU）↑（0-252）。",
        "lab_results": [
            {"test_name": "凝血酶原时间", "abbreviation": "PT", "value": 19.40, "unit": "s", "reference_range": "9.4-12.5", "status": "high"},
            {"test_name": "凝血酶原时间活动度", "abbreviation": "PTA", "value": 47.0, "unit": "%", "reference_range": "80-160", "status": "low"},
            {"test_name": "凝血酶原标准化比值", "abbreviation": "INR", "value": 1.7, "unit": "", "reference_range": "0.8-1.2", "status": "high"},
            {"test_name": "凝血酶原比率", "abbreviation": "Ratio", "value": 1.7, "unit": "", "reference_range": "0.8-1.2", "status": "high"},
            {"test_name": "活化部分凝血活酶时间", "abbreviation": "APTT", "value": 40.2, "unit": "s", "reference_range": "21-37", "status": "high"},
            {"test_name": "纤维蛋白原含量", "abbreviation": "Fib", "value": 5.80, "unit": "g/L", "reference_range": "2-4", "status": "high"},
            {"test_name": "凝血酶凝结时间", "abbreviation": "TT", "value": 20.2, "unit": "s", "reference_range": "13.5-19.5", "status": "high"},
            {"test_name": "D-二聚体", "abbreviation": "DD", "value": 254.0, "unit": "μg/L (DDU)", "reference_range": "0-252", "status": "high"},
        ],
        "confidence": 0.86,
    },
    "glucose-crp": {
        "report_id": "R008",
        "raw_text": "图2 生化检验单（脱敏演示）：葡萄糖 16.1 mmol/L（参考范围 3.9-5.6）；C反应蛋白 16.0 mg/L（参考范围 0-10）。",
        "lab_results": [
            {"test_name": "葡萄糖", "abbreviation": "GLU", "value": 16.1, "unit": "mmol/L", "reference_range": "3.9-5.6", "status": "high"},
            {"test_name": "C反应蛋白", "abbreviation": "CRP", "value": 16.0, "unit": "mg/L", "reference_range": "0-10", "status": "high"},
        ],
        "confidence": 0.90,
    },
    "mobile": {
        "report_id": "R009",
        "raw_text": "图3 手机长图（脱敏演示）：已载入图片，等待 OCR 结构化解析。",
        "lab_results": [],
        "confidence": 0.62,
    },
    "urine": {
        "report_id": "R010",
        "raw_text": "图4 尿蛋白系列（脱敏演示）：尿微量白蛋白 <10.80 mg/L；a1-微球蛋白 8.00 mg/L；尿免疫球蛋白G 13.00 mg/L；尿转铁蛋白 <2.28 mg/L。",
        "lab_results": [
            {"test_name": "尿微量白蛋白", "abbreviation": "mALB", "value": 10.80, "unit": "mg/L", "reference_range": "0-30", "status": "normal"},
            {"test_name": "a1-微球蛋白", "abbreviation": "α1-MG", "value": 8.00, "unit": "mg/L", "reference_range": "0-12", "status": "normal"},
            {"test_name": "尿免疫球蛋白G", "abbreviation": "U-IgG", "value": 13.00, "unit": "mg/L", "reference_range": "0-9.6", "status": "high"},
            {"test_name": "尿转铁蛋白", "abbreviation": "TRF", "value": 2.28, "unit": "mg/L", "reference_range": "0-2.4", "status": "normal"},
        ],
        "confidence": 0.84,
    },
    "liver": {
        "report_id": "R011",
        "raw_text": "图5 肝肾系列（脱敏演示）：总胆红素 4.3 μmol/L；直接胆红素 0.5 μmol/L；间接胆红素 3.8 μmol/L；总蛋白 75.0 g/L；白蛋白 46.9 g/L；球蛋白 28.1 g/L；AST 20 IU/L；ALT 16 IU/L；碱性磷酸酶 60 IU/L。",
        "lab_results": [
            {"test_name": "总胆红素", "abbreviation": "TBIL", "value": 4.3, "unit": "μmol/L", "reference_range": "≤21.0", "status": "normal"},
            {"test_name": "直接胆红素", "abbreviation": "DBIL", "value": 0.5, "unit": "μmol/L", "reference_range": "1.7-6.8", "status": "low"},
            {"test_name": "间接胆红素", "abbreviation": "IBIL", "value": 3.8, "unit": "μmol/L", "reference_range": "1.7-14.0", "status": "normal"},
            {"test_name": "总蛋白", "abbreviation": "TP", "value": 75.0, "unit": "g/L", "reference_range": "65-85", "status": "normal"},
            {"test_name": "白蛋白", "abbreviation": "ALB", "value": 46.9, "unit": "g/L", "reference_range": "40-55", "status": "normal"},
            {"test_name": "球蛋白", "abbreviation": "GLO", "value": 28.1, "unit": "g/L", "reference_range": "20-40", "status": "normal"},
            {"test_name": "天门冬氨酸氨基转移酶", "abbreviation": "AST", "value": 20.0, "unit": "IU/L", "reference_range": "13-35", "status": "normal"},
            {"test_name": "丙氨酸氨基转移酶", "abbreviation": "ALT", "value": 16.0, "unit": "IU/L", "reference_range": "7-40", "status": "normal"},
            {"test_name": "碱性磷酸酶", "abbreviation": "ALP", "value": 60.0, "unit": "IU/L", "reference_range": "35-100", "status": "normal"},
        ],
        "confidence": 0.86,
    },
}


_MCP_SERVER = None


def _get_mcp_server():
    """Load the bundled MCP tools for local/mock integration when available.

    The web demo must also run on a minimal Python install, so failure to load
    the optional MCP transport never blocks the in-process fallback.
    """
    global _MCP_SERVER
    if _MCP_SERVER is not None:
        return _MCP_SERVER
    mcp_dir = os.path.join(os.path.dirname(__file__), "mcp_server")
    if not os.path.isdir(mcp_dir):
        return None
    try:
        import sys
        if mcp_dir not in sys.path:
            sys.path.insert(0, mcp_dir)
        import server as mcp_server  # type: ignore
        _MCP_SERVER = mcp_server
    except Exception:
        _MCP_SERVER = False
    return _MCP_SERVER or None


def _mcp_tool_snapshot(raw_text: str, patient_info: dict[str, Any]) -> dict[str, Any]:
    """Run parse_report → query_reference → evidence_gate locally.

    This is a deterministic adapter for the mock API. In Nexent production the
    same three calls are made by the MCP agent over stdio/HTTP.
    """
    server = _get_mcp_server()
    if server is None:
        return {"available": False, "parse_report": None, "references": [], "evidence_gates": []}
    parsed = server.parse_report(raw_text)
    references = []
    gates = []
    gender_map = {"男": "male", "女": "female", "male": "male", "female": "female"}
    gender = gender_map.get(str((patient_info or {}).get("gender") or ""), None)
    for item in parsed.get("items", []):
        indicator = item.get("indicator") or item.get("name")
        reference = server.query_reference(indicator)
        references.append(reference)
        if item.get("value") is not None:
            gates.append({
                "indicator": indicator,
                "name": item.get("name"),
                "result": server.evidence_gate(
                    indicator,
                    float(item["value"]),
                    gender=gender or "",
                    age=str((patient_info or {}).get("age") or ""),
                ),
            })
    return {
        "available": True,
        "parse_report": parsed,
        "references": references,
        "evidence_gates": gates,
    }


def load_rows(csv_path: str = DEFAULT_CSV) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not os.path.exists(csv_path):
        return rows
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            for field in ("value", "ref_low", "ref_high"):
                try:
                    row[field] = float(row[field])
                except (TypeError, ValueError):
                    row[field] = None
            rows.append(row)
    return rows


def _citation(row: dict[str, Any], number: int) -> dict[str, str]:
    source_id = row.get("source_id") or f"SRC-{row.get('report_id', 'DEMO')}-{row.get('indicator_code', number)}"
    low = row.get("ref_low")
    high = row.get("ref_high")
    ref = f"参考范围 {low:g}—{high:g} {row.get('unit', '')}" if low is not None and high is not None else "参考范围未提供"
    excerpt = f"{row.get('indicator_name', row.get('indicator_code', '指标'))} {row.get('value', '')} {row.get('unit', '')}；{ref}"
    return {
        "id": f"来源{number}",
        "source_id": source_id,
        "title": f"合成检验单 {row.get('report_id', 'DEMO')}",
        "excerpt": excerpt,
        "url": f"#source-{source_id}",
    }


def _status_for(value: float, low: float, high: float) -> str:
    if value > high:
        return "high"
    if value < low:
        return "low"
    return "normal"


def _normalise_medications(value: Any) -> list[dict[str, str]]:
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("drug_name") or item.get("drug") or "").strip()
            else:
                name = str(item).strip()
            if name:
                result.append({"drug_name": name})
        return result
    text = str(value or "").strip()
    if not text:
        return []
    return [{"drug_name": line.strip()[:80]} for line in text.splitlines() if line.strip()]


def _parse_report_text(raw_text: str) -> dict[str, Any]:
    """Parse the small, deterministic demo format used to test parse_report.

    This is deliberately conservative: it extracts only explicit age, gender,
    laboratory values, ranges, and medication names. It does not infer a
    diagnosis or manufacture a reference range.
    """
    text = str(raw_text or "")
    gender_match = re.search(r"患者\s*(男|女)", text)
    age_match = re.search(r"患者[^。；;\n]{0,20}?([0-9]{1,3})\s*岁", text)
    age = int(age_match.group(1)) if age_match else None
    gender = gender_match.group(1) if gender_match else "未知"

    lab_results: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<name>[\u4e00-\u9fff]+)\s*（(?P<abbr>[A-Za-z][A-Za-z0-9_-]*)）\s*"
        r"为\s*(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-zμµ×0-9^/]+)"
        r"\s*[，,]\s*参考范围(?:是|为)?\s*"
        r"(?P<low>-?\d+(?:\.\d+)?)\s*[-—~至]\s*(?P<high>-?\d+(?:\.\d+)?)"
        r"(?:\s*(?P<range_unit>[A-Za-zμµ×0-9^/]+))?"
    )
    for match in pattern.finditer(text):
        value = float(match.group("value"))
        low = float(match.group("low"))
        high = float(match.group("high"))
        unit = match.group("unit")
        lab_results.append({
            "test_name": match.group("name"),
            "abbreviation": match.group("abbr").upper(),
            "value": value,
            "unit": unit,
            "reference_range": f"{match.group('low')}-{match.group('high')}",
            "status": _status_for(value, low, high),
        })

    medications = []
    medication_match = re.search(
        r"(?:正在(?:规律)?服用|服用|使用|口服)\s*([\u4e00-\u9fffA-Za-z0-9-]+)",
        text,
    )
    if medication_match:
        medications.append({"drug_name": medication_match.group(1)})

    confidence = 0.95 if age is not None and gender != "未知" and lab_results else 0.72
    return {
        "patient_info": {"age": age, "gender": gender},
        "lab_results": lab_results,
        "medications": medications,
        "metadata": {"extraction_confidence": confidence},
    }


def _legacy_item(lab: dict[str, Any], report_id: str, index: int) -> dict[str, Any]:
    range_text = str(lab.get("reference_range") or "")
    range_match = re.search(r"\s*(-?\d+(?:\.\d+)?)\s*[-—~至]\s*(-?\d+(?:\.\d+)?)", range_text)
    low = float(range_match.group(1)) if range_match else None
    high = float(range_match.group(2)) if range_match else None
    if not range_match:
        upper = re.search(r"(?:<|≤)\s*(\d+(?:\.\d+)?)", range_text)
        lower = re.search(r"(?:>|≥)\s*(\d+(?:\.\d+)?)", range_text)
        if upper:
            high = float(upper.group(1))
        elif lower:
            low = float(lower.group(1))
    source_id = f"SRC-{report_id}-{lab.get('abbreviation') or index}"
    return {
        "indicator_code": lab.get("abbreviation", ""),
        "indicator_name": lab.get("test_name", ""),
        "value": lab.get("value"),
        "unit": lab.get("unit", ""),
        "status": lab.get("status", "normal"),
        "source_id": source_id,
        "reference_range": {"low": low, "high": high},
        "sources": [source_id],
    }


def analyze_payload(payload: dict[str, Any], csv_path: str = DEFAULT_CSV) -> dict[str, Any]:
    report_id = str(payload.get("report_id") or "R001")
    parsed = _parse_report_text(payload.get("raw_text", ""))
    if isinstance(payload.get("patient_info"), dict):
        parsed["patient_info"].update(payload["patient_info"])
    parsed_medications = _normalise_medications(payload.get("medications"))
    if parsed_medications:
        parsed["medications"] = parsed_medications

    image_sample = IMAGE_SAMPLE_DATA.get(str(payload.get("asset_id") or "").strip())
    if image_sample:
        report_id = image_sample["report_id"]
        raw_text = image_sample["raw_text"]
        parsed["lab_results"] = list(image_sample["lab_results"])
        parsed["patient_info"].setdefault("age", None)
        if parsed["patient_info"].get("gender") in (None, ""):
            parsed["patient_info"]["gender"] = "未知"
        parsed["metadata"]["extraction_confidence"] = image_sample["confidence"]

    rows = [row for row in load_rows(csv_path) if row.get("report_id") == report_id]
    if image_sample:
        rows = []
    # 有原始文本时以本次解析为准；不能因为编号恰好存在于旧 CSV，
    # 就把“无法解析”的输入误替换成另一份报告。只有默认空白请求才回退 R001。
    if payload.get("raw_text") and not parsed["lab_results"] and report_id not in {"R001", "R002", "R003"}:
        rows = []
    elif not rows and not parsed["lab_results"] and report_id == "R001" and not payload.get("raw_text"):
        rows = [row for row in load_rows(csv_path) if row.get("report_id") == "R001"]

    if parsed["lab_results"]:
        lab_results = parsed["lab_results"]
        items = [_legacy_item(lab, report_id, index) for index, lab in enumerate(lab_results, start=1)]
        citations = []
        for index, item in enumerate(items, start=1):
            low = item["reference_range"].get("low")
            high = item["reference_range"].get("high")
            if low is not None and high is not None:
                ref_text = f"{low:g}—{high:g}"
            elif high is not None:
                ref_text = f"<{high:g}"
            elif low is not None:
                ref_text = f">{low:g}"
            else:
                ref_text = "未提供"
            citations.append({
                "id": f"来源{index}",
                "source_id": item["source_id"],
                "title": f"脱敏检验单图像 {report_id}" if image_sample else f"合成检验单 {report_id}",
                "excerpt": f"{item['indicator_code']} {item['value']} {item['unit']}；参考范围 {ref_text}",
                "url": f"#source-{item['source_id']}",
            })
    else:
        items = []
        citations = []
        for index, row in enumerate(rows, start=1):
            item = {
                "indicator_code": row.get("indicator_code", ""),
                "indicator_name": row.get("indicator_name", ""),
                "value": row.get("value"),
                "unit": row.get("unit", ""),
                "status": row.get("status", "normal"),
                "source_id": row.get("source_id", ""),
                "reference_range": {"low": row.get("ref_low"), "high": row.get("ref_high")},
                "sources": [row.get("source_id", "")],
            }
            items.append(item)
            citations.append(_citation(row, index))
        lab_results = [{
            "test_name": item["indicator_name"],
            "abbreviation": item["indicator_code"],
            "value": float(item["value"]) if item["value"] is not None else None,
            "unit": item["unit"],
            "reference_range": f"{item['reference_range']['low']:g}-{item['reference_range']['high']:g}",
            "status": item["status"] if item["status"] in {"high", "low", "normal"} else "normal",
        } for item in items]

    # 阶段二联调的确定性单位标准化：记录换算证据，未知换算进入 review，
    # 不在前端静默修改原始数值。真实 Nexent 接入后可直接替换为 MCP 返回值。
    normalization = []
    tool_server = _get_mcp_server()
    if tool_server is not None:
        for lab in lab_results:
            if lab.get("value") is None or not lab.get("unit"):
                continue
            indicator = lab.get("abbreviation") or lab.get("test_name") or ""
            try:
                normalization.append(tool_server.normalize(
                    indicator,
                    float(lab["value"]),
                    str(lab.get("unit") or ""),
                    "",
                ))
            except Exception as exc:  # pragma: no cover - defensive adapter boundary
                normalization.append({
                    "status": "review", "indicator": indicator,
                    "message": f"单位标准化失败：{exc}",
                })

    confidence_override = (payload.get("metadata") or {}).get("extraction_confidence") if isinstance(payload.get("metadata"), dict) else None
    if confidence_override is not None:
        parsed["metadata"]["extraction_confidence"] = float(confidence_override)

    raw_text = image_sample["raw_text"] if image_sample else str(payload.get("raw_text") or "")
    mcp_tools = _mcp_tool_snapshot(raw_text, parsed["patient_info"])
    conflict_case = report_id.upper() == "R005" or "来源冲突" in raw_text or "参考范围冲突" in raw_text
    conflicts = []
    if conflict_case:
        conflicts.append({
            "field": "reference_range",
            "sources": ["SRC-RANGE-A", "SRC-RANGE-B"],
            "detail": "两份演示标准对 ALT 参考范围给出了不同版本，需人工确认适用版本。",
        })
        citations.extend([
            {
                "id": "标准来源A",
                "source_id": "SRC-RANGE-A",
                "title": "WS/T 405 参考区间 · v1（演示）",
                "excerpt": "ALT 参考范围：0-40 U/L",
                "url": "#source-SRC-RANGE-A",
            },
            {
                "id": "标准来源B",
                "source_id": "SRC-RANGE-B",
                "title": "WS/T 405 参考区间 · v2（演示）",
                "excerpt": "ALT 参考范围：9-50 U/L",
                "url": "#source-SRC-RANGE-B",
            },
        ])

    extraction_confidence = float(parsed["metadata"].get("extraction_confidence", 0.0))
    missing_patient_fields = [
        field for field, value in parsed["patient_info"].items()
        if value is None or value == "未知"
    ]
    if conflict_case:
        decision_gate = "review"
        evidence_status = "conflict"
        next_action = "人工确认参考范围版本后再继续核查"
    elif not items:
        decision_gate = "abstain"
        evidence_status = "missing"
        next_action = "补充可识别的检验指标和参考范围"
    elif extraction_confidence < 0.8 or missing_patient_fields:
        # 报告级编排允许追问一个字段，因此“低置信度/缺性别”进入 review；
        # 只有没有任何指标或没有参考依据时才 abstain。
        decision_gate = "review"
        evidence_status = "low_confidence" if extraction_confidence < 0.8 else "missing"
        next_action = "补充患者信息并人工核对抽取字段"
    else:
        decision_gate = "pass"
        evidence_status = "consistent"
        next_action = "证据一致，可继续展示带来源结果"

    high = [item for item in items if item["status"] == "high"]
    low = [item for item in items if item["status"] == "low"]
    normal = [item for item in items if item["status"] == "normal"]
    # V2 提示词约束：review 状态只说明风险和缺口，不继续输出偏高/偏低结论。
    strict_review = decision_gate == "review"
    if decision_gate == "abstain":
        answer = "当前输入缺少可用的检验依据，暂不输出确定性解读。建议补充原始报告并咨询专业人员。"
    elif strict_review:
        answer = (
            "当前处于安全复核状态，暂不能给出确定的偏高、偏低或正常结论。"
            f"复核原因：{next_action}。请核对原始报告、患者信息和来源版本后再继续。"
        )
    else:
        citation_by_index = {index: citation.get("id", f"来源{index}") for index, citation in enumerate(citations, start=1)}
        abnormal_parts = []
        for index, item in enumerate(items, start=1):
            if item["status"] in {"high", "low"}:
                abnormal_parts.append(f"{item['indicator_name']}[{citation_by_index.get(index, f'来源{index}')}]" )
        if abnormal_parts:
            answer = (
                f"检验结果共读取 {len(items)} 项，其中 {len(high)} 项高于参考范围、"
                f"{len(low)} 项低于参考范围，{len(normal)} 项在参考范围内。"
                f"异常指标包括：{'、'.join(abnormal_parts)}。请结合原始报告和专业人员意见进一步判断。"
            )
        else:
            answer = f"检验结果共读取 {len(items)} 项，当前样本均落在给定参考范围内。请结合原始报告复核。"

    reasoning = [
        {
            "step": "01",
            "title": "指标抽取",
            "detail": f"识别并统一 {len(items)} 项指标的名称、数值和单位。",
        },
        {
            "step": "02",
            "title": "参考范围核对",
            "detail": f"逐项核对参考范围，标记 {len(high) + len(low)} 项异常方向。",
        },
        {
            "step": "03",
            "title": "来源汇总",
            "detail": "保留 source_id 和引用卡片，结果交由专业人员复核。",
        },
        {
            "step": "04",
            "title": "证据门控",
            "detail": f"{next_action}；证据状态：{evidence_status}。",
        },
    ]

    medications_list = parsed["medications"]
    warnings = []
    clarification = None
    if decision_gate == "review" and (parsed["patient_info"].get("gender") in (None, "未知") or extraction_confidence < 0.8):
        clarification = {
            "required": True,
            "field": "gender" if parsed["patient_info"].get("gender") in (None, "未知") else "extraction_confidence",
            "prompt": "请补充患者性别，以便准确选择参考区间。" if parsed["patient_info"].get("gender") in (None, "未知") else "请核对图片或文本中的指标数值。",
        }

    interaction = {"status": "pass", "warnings": [], "checked_medications": [], "checked_indicators": []}
    if tool_server is not None and medications_list:
        try:
            interaction = tool_server.check_interaction(medications_list, lab_results)
            warnings = list(interaction.get("warnings") or [])
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            interaction = {
                "status": "review", "warnings": [],
                "next_action": f"用药核查暂不可用：{exc}",
                "checked_medications": [item.get("drug_name") for item in medications_list],
                "checked_indicators": [],
            }

    retrieval = {
        "vector_hits": 10,
        "keyword_hits": 5,
        "reranked": 3,
        "sources": [
            {"title": "WS/T 405 参考区间（演示）", "score": 0.92},
            {"title": "合成检验单与字段说明（演示）", "score": 0.88},
            {"title": "药品说明书核查入口（演示）", "score": 0.84},
        ],
    }
    knowledge_evidence = {
        "raw_json": '{"entity":"ALT","value":68,"unit":"U/L","needs_review":true}',
        "checked_fields": ["实体名称", "数值与单位", "参考范围", "来源编号"],
        "review_note": "大模型抽取后由人工确认字段，再进入知识库。",
    }
    graph_nodes = [{"id": "indicator", "label": (high[0]["indicator_code"] if high else "指标"), "kind": "指标"}]
    graph_nodes.append({"id": "reference", "label": "参考范围", "kind": "标准"})
    if medications_list:
        graph_nodes.append({"id": "medication", "label": medications_list[0]["drug_name"][:18], "kind": "用药"})
    graph_edges = [{"source": "indicator", "target": "reference", "label": "核对"}]
    if medications_list:
        graph_edges.append({"source": "indicator", "target": "medication", "label": "需核查"})

    request_key = f"{report_id}:{raw_text}"
    request_id = "mock-" + hashlib.sha1(request_key.encode("utf-8")).hexdigest()[:10]
    trace_log = [
        {"tool": "parse_report", "status": "done", "elapsed_ms": 120},
        {"tool": "normalize", "status": "done" if normalization else "review", "elapsed_ms": 90},
        {"tool": "query_reference", "status": "done", "elapsed_ms": 340},
    ]
    if medications_list:
        trace_log.append({"tool": "check_interaction", "status": "done", "elapsed_ms": 280})
    trace_log.append({"tool": "evidence_gate", "status": decision_gate, "elapsed_ms": 80})
    trace_log.append({"tool": "summarize", "status": "done", "elapsed_ms": 190})
    return {
        "request_id": request_id,
        "report_id": report_id,
        "mcp_tools": mcp_tools,
        "status": "success",
        "patient_info": parsed["patient_info"],
        "lab_results": lab_results,
        "medications": medications_list,
        "metadata": parsed["metadata"],
        "decision_gate": decision_gate,
        "confidence": extraction_confidence,
        "evidence_status": evidence_status,
        "conflicts": conflicts,
        "next_action": next_action,
        "clarification": clarification,
        "source_versions": ["WS/T 405-v1（演示）", "WS/T 405-v2（演示）"] if conflict_case else ["WS/T 405-v1（演示）"],
        "answer": answer,
        "items": items,
        "citations": citations,
        "reasoning": reasoning,
        "warnings": warnings,
        "interaction": interaction,
        "normalization": normalization,
        "retrieval": retrieval,
        "knowledge_evidence": knowledge_evidence,
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "trace": [step["tool"] for step in trace_log],
        "trace_log": trace_log,
        "meta": {"llm_model": "glm-4.7", "embedding_model": "embedding-3", "rag_config_count": 34},
        "disclaimer": "本结果仅供辅助参考，不构成任何临床诊断或用药建议。医学决策请务必以执业医师意见为准。",
    }

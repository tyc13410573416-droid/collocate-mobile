"""Shared, deterministic analysis logic for the stage-one demo."""

from __future__ import annotations

import csv
import hashlib
import os
import re
from typing import Any


DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__), "data", "cleaned", "inspection_reports_cleaned.csv"
)


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
    range_match = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*[-—~至]\s*(-?\d+(?:\.\d+)?)", range_text)
    low = float(range_match.group(1)) if range_match else None
    high = float(range_match.group(2)) if range_match else None
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

    rows = [row for row in load_rows(csv_path) if row.get("report_id") == report_id]
    if not rows and not parsed["lab_results"]:
        rows = [row for row in load_rows(csv_path) if row.get("report_id") == "R001"]
        report_id = "R001" if rows else report_id

    if parsed["lab_results"]:
        lab_results = parsed["lab_results"]
        items = [_legacy_item(lab, report_id, index) for index, lab in enumerate(lab_results, start=1)]
        citations = []
        for index, item in enumerate(items, start=1):
            citations.append({
                "id": f"来源{index}",
                "source_id": item["source_id"],
                "title": f"合成检验单 {report_id}",
                "excerpt": f"{item['indicator_code']} {item['value']} {item['unit']}；参考范围 {item['reference_range']['low']:g}—{item['reference_range']['high']:g} {item['unit']}",
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

    confidence_override = (payload.get("metadata") or {}).get("extraction_confidence") if isinstance(payload.get("metadata"), dict) else None
    if confidence_override is not None:
        parsed["metadata"]["extraction_confidence"] = float(confidence_override)

    raw_text = str(payload.get("raw_text") or "")
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
        decision_gate = "review"
        evidence_status = "missing"
        next_action = "补充患者信息并人工核对抽取字段"
    else:
        decision_gate = "pass"
        evidence_status = "consistent"
        next_action = "证据一致，可继续展示带来源结果"

    high = [item for item in items if item["status"] == "high"]
    low = [item for item in items if item["status"] == "low"]
    normal = [item for item in items if item["status"] == "normal"]
    abnormal_names = [item["indicator_name"] for item in high + low]
    if abnormal_names:
        abnormal_text = "、".join(abnormal_names)
        answer = (
            f"演示结果：共读取 {len(items)} 项指标，其中 {len(high)} 项高于参考范围、"
            f"{len(low)} 项低于参考范围，{len(normal)} 项在参考范围内。"
            f"异常标记涉及：{abnormal_text}。请结合原始报告和专业人员意见进一步判断。"
        )
    else:
        answer = f"演示结果：共读取 {len(items)} 项指标，当前样本均落在给定参考范围内。请结合原始报告复核。"
    if decision_gate != "pass":
        answer = f"{answer} 当前决策门控：{next_action}。"

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
    if medications_list:
        first_medication = medications_list[0]["drug_name"]
        warnings.append({
            "drug": first_medication,
            "risk": "需要结合异常指标、药品说明书和专业人员意见进一步核查",
            "source": "用药说明书 / 知识库引用（演示占位）",
            "level": "review",
            "severity": "review",
            "sources": ["SRC-DRUG-001"],
        })

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

    request_key = f"{report_id}:{payload.get('raw_text', '')}"
    request_id = "mock-" + hashlib.sha1(request_key.encode("utf-8")).hexdigest()[:10]
    trace_log = [
        {"tool": "parse_report", "status": "done", "elapsed_ms": 120},
        {"tool": "query_reference", "status": "done", "elapsed_ms": 340},
    ]
    if medications_list:
        trace_log.append({"tool": "check_interaction", "status": "done", "elapsed_ms": 280})
    trace_log.append({"tool": "evidence_gate", "status": decision_gate, "elapsed_ms": 80})
    trace_log.append({"tool": "summarize", "status": "done", "elapsed_ms": 190})
    return {
        "request_id": request_id,
        "report_id": report_id,
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
        "source_versions": ["WS/T 405-v1（演示）", "WS/T 405-v2（演示）"] if conflict_case else ["WS/T 405-v1（演示）"],
        "answer": answer,
        "items": items,
        "citations": citations,
        "reasoning": reasoning,
        "warnings": warnings,
        "retrieval": retrieval,
        "knowledge_evidence": knowledge_evidence,
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "trace": [step["tool"] for step in trace_log],
        "trace_log": trace_log,
        "meta": {"llm_model": "glm-4.7", "embedding_model": "embedding-3", "rag_config_count": 34},
        "disclaimer": "仅用于工程演示，不构成诊断或用药建议。",
    }

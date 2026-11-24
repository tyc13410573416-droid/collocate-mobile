"""Format actual OCR/MCP outputs; no demo engine, retrieval metrics or fake timings."""
from __future__ import annotations
import time
import uuid
import re


def patient_fields(raw_text, supplied_gender):
    # Never infer patient sex from male/female reference ranges elsewhere in a
    # report, or from a substring such as "male" within "female".
    match = re.search(r"(?:性别|gender|患者)\s*[:：]?\s*(female|male|女性|男性|女|男)(?=\s|[，,。;；\d]|$)", raw_text, re.I)
    sex = {"female": "女", "male": "男", "女性": "女", "男性": "男", "女": "女", "男": "男"}.get(match.group(1).lower(), "未知") if match else "未知"
    age_match = re.search(r"(?:年龄|age)\s*[:：]?\s*(\d{1,3})\s*(?:岁|years?)?", raw_text, re.I)
    if not age_match:
        age_match = re.search(r"患者\s*[:：]?\s*(?:男|女|男性|女性)?[，,\s]*(\d{1,3})\s*岁", raw_text)
    return {"age": int(age_match.group(1)) if age_match else None,
            "gender": supplied_gender if supplied_gender in {"男", "女"} else sex}


def build_result(readings, transcription, gender, medications, server, verified=False, report_conditions="unknown"):
    trace = []
    def call(name, *args, **kwargs):
        started = time.perf_counter()
        value = getattr(server, name)(*args, **kwargs)
        trace.append({"tool": name, "status": "done", "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "origin": "local-mcp-workflow"})
        return value
    aligned = "\n".join("{} {} {}".format(row["indicator"], row["value"], row["unit"]) for row in readings)
    parsed = call("parse_report", aligned)
    parsed_values = {item["indicator"]: item.get("value") for item in parsed.get("items", [])}
    for row in readings:
        if parsed_values.get(row["indicator"]) != row["value"]:
            transcription["uncertain_fields"].append(row["test_name"] + "：表格读数与文本解析不一致。")
    patient = patient_fields(transcription["raw_text"], gender)
    sex = patient.get("gender", "未知")
    labs, citations, versions, gates = [], [], [], []
    for row in readings:
        indicator = row["indicator"]
        ref = call("query_reference", indicator)
        gate = call("evidence_gate", indicator, row["value"], gender=sex, age=str(patient.get("age") or ""))
        gates.append(gate)
        version = gate.get("source_versions", [])
        for entry in version:
            if entry not in versions: versions.append(entry)
        source_id = ref.get("source_id") or ref.get("source")
        citation_id = None
        if source_id:
            citation_id = "来源{}".format(len(citations) + 1)
            citations.append({"id": "来源{}".format(len(citations) + 1), "source_id": source_id,
                              "indicator": indicator, "citation_key": "ref-" + indicator,
                              "title": ref.get("source") or source_id, "version": ref.get("source_version"),
                              "version_note": "版本标签来自现有知识库，原始标准版本与页码待核验。",
                              "original_text_available": False, "excerpt_kind": "knowledge-entry",
                              "excerpt": "{}；参考区间 {} {}。适用人群、采样条件与检测方法请结合原单核对。".format(ref.get("name"), ref.get("reference_range"), ref.get("unit")),
                              "reference_range": ref.get("reference_range")})
        limits = ref.get("gender_range", {})
        bounds = limits.get({"男": "male", "女": "female"}.get(sex, "default")) or limits.get("default") or {}
        status = "unknown"
        if gate["decision_gate"] == "pass" and bounds and row["unit"] == ref.get("unit"):
            low, high = bounds.get("low"), bounds.get("high")
            status = "low" if low is not None and row["value"] < low else "high" if high is not None and row["value"] > high else "normal"
        if row["unit"] != ref.get("unit"):
            transcription["uncertain_fields"].append(row["test_name"] + "：原单单位与知识库单位需要核对。")
        labs.append({"test_name": row["test_name"], "abbreviation": indicator, "value": row["value"],
                     "value_comparator": row["value_comparator"], "unit": row["unit"],
                     "reference_range": ref.get("reference_range", "待核对"), "status": status,
                     "source_id": source_id, "citation_ids": [citation_id] if citation_id else []})
    uncertainty = transcription["uncertain_fields"]
    gate = next((g for g in gates if g["decision_gate"] == "review"), None) or next((g for g in gates if g["decision_gate"] == "abstain"), None)
    gate = dict(gate or {"decision_gate": "pass", "evidence_status": "found", "confidence": min((g["confidence"] for g in gates), default=0.0), "conflicts": [], "next_action": "请对照原图核对数值和参考条件。"})
    if not labs or uncertainty:
        gate.update(decision_gate="review", evidence_status="low_confidence", next_action="部分指标的读数、单位或行列对应关系尚未确认，已触发安全拦截。请核对并提交所选项目，暂不作确定性异常方向判定。", confidence=min((r["score"] for r in readings), default=0.0))
        gate.pop("clarification", None)
    elif any(r["indicator"] == "GLU" for r in readings) and not (report_conditions == "fasting" or (not verified and re.search(r"(?<!非)(?<!不)空腹", transcription["raw_text"]))):
        gate.update(decision_gate="review", evidence_status="missing_info", next_action="已确认非空腹；当前血糖参考条目不适用于本次条件，请补充适用的参考依据。" if report_conditions == "nonfasting" else "原单未明确空腹状态，请人工核对参考区间的适用条件。")
        gate["clarification"] = {"field": "report_conditions", "prompt": gate["next_action"]}
    if gate["decision_gate"] == "review" and gate["evidence_status"] == "missing_info" and "clarification" not in gate:
        gate["clarification"] = {"field": "gender", "prompt": "请补充患者性别。"}
    score = min((r["score"] for r in readings), default=0.0)
    gate["source_versions"] = versions
    drugs = [{"drug_name": name} for name in server._as_names(medications)]
    interaction = call("check_interaction", drugs, labs if gate["decision_gate"] == "pass" else []) if drugs else {}
    return dict(gate, request_id="local-image-" + uuid.uuid4().hex[:12], patient_info=patient,
                lab_results=labs, medications=drugs, warnings=interaction.get("warnings", []), citations=citations, trace_log=trace,
                metadata={"extraction_confidence": None if verified else score, "input_origin": "human-reviewed" if verified else "ocr",
                          "workflow_engine": "local-mcp", "retrieval_mode": "reference-lookup", "report_conditions": report_conditions,
                          "medication_check_scope": "configured-demo-rules-only" if drugs else "not-requested"},
                answer="已读取 {} 项可确认指标。通过只表示证据允许显示，不代表指标正常。仅处理可匹配知识库的部分指标，未收录项目需人工核对。".format(len(labs)) if gate["decision_gate"] == "pass" else "本次报告需要人工复核，暂不作确定性解读。仅显示可匹配的部分原始读数。",
                review_issues=[{"field": "report_value", "detail": item} for item in uncertainty] +
                              ([{"field": "gender", "detail": "性别未提供，部分参考区间需要按性别选择。"}] if any(g.get("clarification", {}).get("field") == "gender" for g in gates) else []) +
                              ([{"field": "report_conditions", "detail": gate["next_action"]}] if gate.get("clarification", {}).get("field") == "report_conditions" else []),
                disclaimer="本结果仅供辅助参考，不构成任何临床诊断或用药建议。医学决策请务必以执业医师意见为准。")

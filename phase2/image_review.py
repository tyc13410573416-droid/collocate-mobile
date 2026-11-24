"""Re-evaluate explicitly confirmed image fields with the real deterministic gate."""
import copy
from datetime import datetime, timezone
import math
import time

from phase2.local_image_store import load_record, save_result, load_result
from phase2.local_result import build_result
from phase2.nexent_image_client import ImageHandoffError, validated_gate


def review_image(payload, server):
    if not isinstance(payload, dict):
        raise ImageHandoffError("INVALID_REVIEW", "请提交有效的核对信息。", 400)
    try:
        stored = load_record(payload.get("review_token"))
    except (OSError, ValueError, TypeError) as exc:
        raise ImageHandoffError("REVIEW_EXPIRED", "核对会话已过期或无效，请重新上传原图后再核对。", 410) from exc
    original = stored.get("original_result") or stored["result"]
    previous = stored["result"]
    original_rows = {row["abbreviation"]: row for row in original.get("lab_results", [])}
    items = payload.get("lab_results")
    gender = payload.get("gender", "未知")
    condition = payload.get("report_conditions", "unknown")
    if gender not in {"男", "女", "未知", ""} or condition not in {"unknown", "fasting", "nonfasting"}:
        raise ImageHandoffError("INVALID_REVIEW", "请使用提供的性别和采样条件选项。", 400)
    if payload.get("scope_confirmed") is not True or not isinstance(items, list) or not 1 <= len(items) <= len(original_rows):
        raise ImageHandoffError("CONFIRM_FIELDS_REQUIRED", "请逐项核对并勾选至少一个指标，确认本次仅核查所选项目。", 400)
    readings, changes, normalizations, seen = [], [], [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ImageHandoffError("INVALID_REVIEW", "指标核对格式无效。", 400)
        code = item.get("abbreviation")
        if not isinstance(code, str) or code not in original_rows or code in seen or item.get("confirmed") is not True:
            raise ImageHandoffError("INVALID_REVIEW", "只能提交本张图片中已列出的指标，且每项必须确认。", 400)
        seen.add(code)
        numeric, unit, comparator = item.get("value"), item.get("unit"), item.get("value_comparator", "")
        if isinstance(numeric, bool) or not isinstance(numeric, (int, float)) or not math.isfinite(numeric) or numeric < 0 or numeric > 1e12:
            raise ImageHandoffError("INVALID_REVIEW_VALUE", "{} 的数值必须是有限数字，请保留原单小数点。".format(code), 400)
        if not isinstance(unit, str) or not 1 <= len(unit.strip()) <= 32 or any(c in unit for c in "\r\n<>") or comparator not in {"", "<", ">", "≤", "≥"}:
            raise ImageHandoffError("INVALID_REVIEW_UNIT", "{} 的单位或不等号格式无效。".format(code), 400)
        before = original_rows[code]
        start = time.perf_counter()
        normalized = server.normalize(code, float(numeric), unit.strip())
        normalized["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        normalizations.append(normalized)
        value = normalized.get("value", numeric) if normalized["status"] == "pass" else numeric
        canonical_unit = normalized.get("unit", unit.strip()) if normalized["status"] == "pass" else unit.strip()
        readings.append({"indicator": code, "test_name": before["test_name"], "value": float(value),
                         "unit": canonical_unit, "value_comparator": comparator, "score": before.get("ocr_score", 0.0)})
        changes.append({"indicator": code, "before": {"value": before["value"], "unit": before["unit"], "comparator": before.get("value_comparator", "")},
                        "submitted": {"value": numeric, "unit": unit.strip(), "comparator": comparator}, "confirmed": True})
    original_transcript = copy.deepcopy(original["image_transcription"])
    transcript = {"raw_text": original_transcript["raw_text"], "readable": original_transcript["readable"], "uncertain_fields": []}
    for row in readings:
        if row["value_comparator"]:
            transcript["uncertain_fields"].append(row["indicator"] + " 含不等号，仍需专业人员核对。")
    medications = previous.get("medications", [])
    result = build_result(readings, transcript, gender or "未知", medications, server, verified=True, report_conditions=condition)
    result["metadata"].update(original_ocr_score=original.get("metadata", {}).get("extraction_confidence"),
                              image_route="human-review-mcp", human_verified=True, confidence_kind="human-confirmed-fields",
                              parent_request_id=original.get("request_id"), review_pipeline="deterministic-mcp")
    result["normalization"] = normalizations
    result["image_transcription"] = original_transcript
    result["image_transcription"]["is_original_ocr"] = True
    excluded = [code for code in original_rows if code not in seen]
    result["review_summary"] = {"selected_count": len(readings), "excluded_indicators": excluded,
                                "original_uncertain_fields": original_transcript.get("uncertain_fields", []),
                                "scope": "selected-fields-only", "reviewed_at": datetime.now(timezone.utc).isoformat(),
                                "changes": changes}
    result["next_action"] = ("已重新核查 {} 项人工确认的指标。通过只表示这些项目的证据允许输出，不代表整份报告正常。".format(len(readings)) if result["decision_gate"] == "pass" else result["next_action"])
    result["answer"] = "本次仅核查 {} 项人工确认的指标；未勾选及原图其他项目仍需核对。".format(len(readings))
    detail = "；".join("{indicator}：{before[value]} {before[unit]} → {submitted[value]} {submitted[unit]}".format(**change) for change in changes)
    human_step = {"tool": "human_review", "status": "done", "origin": "user-confirmed", "detail": detail + "；性别：" + (gender or "未知")}
    normalization_trace = [{"tool": "normalize", "status": row["status"], "elapsed_ms": row["elapsed_ms"], "origin": "local-mcp-workflow"} for row in normalizations]
    result["trace_log"] = previous.get("trace_log", []) + [human_step] + normalization_trace + result["trace_log"]
    result["transport"] = "nexent-image-http"
    validated_gate(result)
    receipt = save_result(stored["image_url"], result, original_result=original)
    return load_result(receipt, {"url": stored["image_url"]})

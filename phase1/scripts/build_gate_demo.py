"""Build exact-input, sex-specific offline fixtures from the Python demo engine."""
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "phase1"))
from analysis_engine import IMAGE_SAMPLE_DATA, analyze_payload


def build():
    source = (ROOT / "docs/static/app.js").read_text(encoding="utf-8")
    text_block = source.split("const sampleTexts = {", 1)[1].split("};", 1)[0]
    samples = {key: text.replace("\\n", "\n") for key, text in re.findall(r"(R\d+): `([^`]+)`", text_block)}
    med_block = source.split("const sampleMedications = {", 1)[1].split("};", 1)[0]
    medications = dict(re.findall(r'(R\d+): "([^"]*)"', med_block))
    catalog, variants, results = {}, {}, {}
    for report_id, raw_text in samples.items():
        catalog[report_id] = {"text": raw_text, "asset_id": "", "medications": medications.get(report_id, "")}
    for asset_id, asset in IMAGE_SAMPLE_DATA.items():
        ui_text = re.search(r'reportId: "' + asset["report_id"] + r'", text: "([^"]+)"', source)
        catalog[asset["report_id"]] = {"text": ui_text.group(1), "asset_id": asset_id, "medications": ""}
    (ROOT / "phase1/data/web_demo_inputs.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for report_id, entry in catalog.items():
        variants[report_id] = {}
        for gender in ("未知", "男", "女"):
            variants[report_id][gender] = {}
            for meds in sorted(set(("", entry["medications"]))):
                payload = {
                    "report_id": report_id, "raw_text": entry["text"],
                    "asset_id": entry["asset_id"], "patient_info": {"gender": gender},
                    "medications": meds,
                }
                # Curated CSV values have no extraction uncertainty. Sex completeness
                # remains independently evaluated by the actual gate engine.
                if report_id in {"R001", "R002", "R003"}:
                    payload["metadata"] = {"extraction_confidence": 0.95}
                result = analyze_payload(payload)
                result["transport"] = "github-pages-demo"
                result["request_id"] = "demo-{}-{}-{}".format(report_id, {"未知": "unknown", "男": "male", "女": "female"}[gender], "med" if meds else "plain")
                if result["decision_gate"] == "pass" and result["lab_results"]:
                    item = result["lab_results"][0]
                    direction = {"high": "高于参考上限，方向为偏高", "low": "低于参考下限，方向为偏低", "normal": "处于参考区间内"}.get(item["status"], "待核对")
                    result["next_action"] = "{} {} {}：{}。通过表示证据允许输出，不表示所有指标正常。".format(item["abbreviation"], item["value"], item["unit"], direction)
                gate, status = result["decision_gate"], result["evidence_status"]
                result["audit_trace"] = [
                    {"title": "提取报告读数", "status": "done", "detail": "合成/脱敏样本 {}，读取 {} 项指标。".format(report_id, len(result["lab_results"]))},
                    {"title": "核对参考依据", "status": "done", "detail": "核对本次报告的参考范围与性别（{}），不套用其他报告。".format(gender)},
                    {"title": {"conflict": "发现来源差异", "missing_info": "等待补充性别", "low_confidence": "识别置信度不足", "missing": "没有可用指标"}.get(status, "依据核对完成"), "status": gate, "detail": result["next_action"]},
                    {"title": "输出带来源解读" if gate == "pass" else "停止确定性解读", "status": gate, "detail": "门控由本地演示引擎生成；共享页回放这份样本的判定记录。"},
                ]
                variants[report_id][gender][meds] = result
                if gender == ("男" if report_id in {"R004", "R005", "R012"} else "未知") and meds == entry["medications"]:
                    results[report_id] = copy.deepcopy(result)
    data = {"samples": catalog, "variants": variants}
    (ROOT / "docs/static/gate-fixtures.js").write_text("window.MEDTRACE_GATE_FIXTURES = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (ROOT / "docs/static/demo-results.js").write_text("window.MEDTRACE_STATIC_RESULTS = " + json.dumps(results, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    template = page.replace('window.MEDTRACE_CONFIG = { mode: "demo" };', 'window.MEDTRACE_CONFIG = { mode: "api" };')
    (ROOT / "phase1/templates/index.html").write_text(template.rstrip() + "\n", encoding="utf-8")
    print("Built {} reports with separate sex/medication variants".format(len(catalog)))


if __name__ == "__main__":
    build()

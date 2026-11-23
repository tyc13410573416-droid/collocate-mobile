"""Front-end prototype and proxy for the stage-one mock integration."""

from __future__ import annotations

import os
import sys
import hashlib
import json
from datetime import datetime, timezone

import requests
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from werkzeug.exceptions import RequestEntityTooLarge

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHASE1_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if PHASE1_DIR not in sys.path:
    sys.path.insert(0, PHASE1_DIR)

from analysis_engine import analyze_payload, _get_mcp_server

from phase2.nexent_client import NexentClient, NexentClientError
from phase2.nexent_image_client import NexentImageClient, ImageHandoffError, checked_file, MAX_FILE_BYTES


# Local Flask and GitHub Pages use the same UI assets to prevent version drift.
app = Flask(__name__, static_folder=os.path.join(ROOT_DIR, "docs", "static"))
MOCK_NEXENT_URL = os.environ.get("MOCK_NEXENT_URL", "http://127.0.0.1:5051/v1/analyze")
APP_MODE = os.environ.get("APP_MODE", "demo").lower()
NEXENT_API_URL = os.environ.get("NEXENT_API_URL", MOCK_NEXENT_URL)
NEXENT_CLIENT = NexentClient(endpoint=NEXENT_API_URL)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES + 64 * 1024
ACCESS_LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "access.jsonl")
os.makedirs(os.path.dirname(ACCESS_LOG_PATH), exist_ok=True)


def visitor_hash() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    address = forwarded or request.remote_addr or "unknown"
    salt = os.environ.get("ACCESS_LOG_SALT", "phase1-demo")
    return hashlib.sha256(f"{salt}:{address}".encode("utf-8")).hexdigest()[:12]


@app.after_request
def record_access(response):
    if request.path in {"/", "/api/analyze", "/api/analyze-image", "/api/health"}:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "visitor": visitor_hash(),
        }
        with open(ACCESS_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if request.path in {"/api/analyze-image", "/api/image-status"}:
        origin = request.headers.get("Origin", "")
        allowed = os.environ.get("IMAGE_ALLOWED_ORIGINS", "").split(",")
        if origin and origin in [value.strip() for value in allowed]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Cache-Control"] = "no-store"
    return response


@app.before_request
def image_origin_check():
    if request.path not in {"/api/analyze-image", "/api/image-status"}:
        return None
    origin = request.headers.get("Origin", "")
    allowed = [value.strip() for value in os.environ.get("IMAGE_ALLOWED_ORIGINS", "").split(",")]
    if origin and origin != request.host_url.rstrip("/") and origin not in allowed:
        return jsonify({"error": "当前网页未获准使用图片接口。", "error_code": "ORIGIN_NOT_ALLOWED"}), 403


@app.errorhandler(RequestEntityTooLarge)
def file_too_large(_error):
    return jsonify({"error": "单个文件不能超过 10 MB。", "error_code": "FILE_TOO_LARGE"}), 413


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "phase1-frontend",
        "mode": APP_MODE,
        "nexent_url_configured": bool(NEXENT_API_URL),
        "mcp_tools": bool(_get_mcp_server()),
    })


@app.route("/api/image-status", methods=["GET"])
def image_status():
    client = NexentImageClient.from_env()
    try:
        client.check_config()
    except ImageHandoffError as exc:
        return jsonify({"configured": False, "error_code": exc.code, "message": str(exc)})
    # Configuration is not a claim of OCR service availability.
    return jsonify({"configured": True, "message": "接口已配置，实际识别能力以请求结果为准。"})


@app.route("/api/analyze-image", methods=["POST"])
def analyze_image():
    client = NexentImageClient.from_env()
    try:
        client.check_config()
        files = request.files.getlist("file")
        if len(files) != 1:
            raise ImageHandoffError("FILE_REQUIRED", "请选择一份检验单文件。", 400)
        content = files[0].read(MAX_FILE_BYTES + 1)
        mime, extension = checked_file(content)
        client.check_file_kind(mime)
        gender = request.form.get("gender", "")
        if gender not in {"", "未知", "男", "女"}:
            raise ImageHandoffError("INVALID_GENDER", "性别请选择男、女或未知。", 400)
        context = {"patient_info": {"gender": gender or "未知"},
                   "raw_text": request.form.get("raw_text", ""),
                   "medications": request.form.get("medications", "")}
        if sum(len(value) for value in (context["raw_text"], context["medications"])) > 16000:
            raise ImageHandoffError("CONTEXT_TOO_LARGE", "补充文本过长，请精简后重试。", 400)
    except ImageHandoffError as exc:
        return jsonify({"error": str(exc), "error_code": exc.code}), exc.status

    def stream():
        try:
            for event in client.events(content, mime, extension, context):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except ImageHandoffError as exc:
            yield json.dumps({"type": "error", "error": str(exc), "error_code": exc.code}, ensure_ascii=False) + "\n"

    return Response(stream_with_context(stream()), content_type="application/x-ndjson; charset=utf-8",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})


@app.route("/api/tools/query_reference", methods=["POST"])
def tool_query_reference():
    payload = request.get_json(silent=True) or {}
    indicator = str(payload.get("indicator") or "").strip()
    server = _get_mcp_server()
    if not indicator:
        return jsonify({"error": "indicator is required"}), 400
    if server is None:
        return jsonify({"error": "MCP tools are unavailable"}), 503
    return jsonify(server.query_reference(indicator))


@app.route("/api/tools/parse_report", methods=["POST"])
def tool_parse_report():
    payload = request.get_json(silent=True) or {}
    server = _get_mcp_server()
    if server is None:
        return jsonify({"error": "MCP tools are unavailable"}), 503
    return jsonify(server.parse_report(str(payload.get("text") or "")))


@app.route("/api/tools/evidence_gate", methods=["POST"])
def tool_evidence_gate():
    payload = request.get_json(silent=True) or {}
    server = _get_mcp_server()
    indicator = str(payload.get("indicator") or "").strip()
    if server is None:
        return jsonify({"error": "MCP tools are unavailable"}), 503
    if not indicator or payload.get("value") is None:
        return jsonify({"error": "indicator and value are required"}), 400
    try:
        value = float(payload.get("value"))
    except (TypeError, ValueError):
        return jsonify({"error": "value must be numeric"}), 400
    return jsonify(server.evidence_gate(
        indicator,
        value,
        gender=str(payload.get("gender") or ""),
        age=str(payload.get("age") or ""),
    ))


@app.route("/api/tools/normalize", methods=["POST"])
def tool_normalize():
    """本地联调入口：统一检验单位，真实 Nexent 接入时保持字段结构不变。"""
    payload = request.get_json(silent=True) or {}
    server = _get_mcp_server()
    indicator = str(payload.get("indicator") or "").strip()
    if server is None:
        return jsonify({"error": "MCP tools are unavailable"}), 503
    if not indicator or payload.get("value") is None or not payload.get("from_unit"):
        return jsonify({"error": "indicator, value and from_unit are required"}), 400
    try:
        value = float(payload.get("value"))
    except (TypeError, ValueError):
        return jsonify({"error": "value must be numeric"}), 400
    return jsonify(server.normalize(
        indicator,
        value,
        str(payload.get("from_unit") or ""),
        str(payload.get("to_unit") or ""),
    ))


@app.route("/api/tools/check_interaction", methods=["POST"])
def tool_check_interaction():
    """本地联调入口：用药与指标规则核查，只返回复核提示。"""
    payload = request.get_json(silent=True) or {}
    server = _get_mcp_server()
    if server is None:
        return jsonify({"error": "MCP tools are unavailable"}), 503
    medications = payload.get("medications") or payload.get("current_medications") or []
    indicators = payload.get("indicators") or payload.get("lab_results") or []
    return jsonify(server.check_interaction(medications, indicators))


@app.route("/api/analyze", methods=["POST"])
def proxy_analyze():
    payload = request.get_json(silent=True) or {}
    try:
        result = NEXENT_CLIENT.analyze(payload)
        if NEXENT_API_URL == MOCK_NEXENT_URL:
            result["transport"] = "mock-nexent-http"
        return jsonify(result)
    except NexentClientError as exc:
        if APP_MODE == "real":
            return jsonify({"error": str(exc), "error_code": "NEXENT_UNAVAILABLE"}), 502
        # Demo mode remains usable if the separately launched mock service is unavailable.
        result = analyze_payload(payload)
        result["transport"] = "in-process-fallback"
        return jsonify(result)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5050")),
        debug=False,
    )

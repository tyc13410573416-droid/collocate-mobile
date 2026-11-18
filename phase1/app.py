"""Front-end prototype and proxy for the stage-one mock integration."""

from __future__ import annotations

import os
import sys
import hashlib
import json
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template, request

from analysis_engine import analyze_payload, _get_mcp_server

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
from phase2.nexent_client import NexentClient, NexentClientError


app = Flask(__name__)
MOCK_NEXENT_URL = os.environ.get("MOCK_NEXENT_URL", "http://127.0.0.1:5051/v1/analyze")
APP_MODE = os.environ.get("APP_MODE", "demo").lower()
NEXENT_API_URL = os.environ.get("NEXENT_API_URL", MOCK_NEXENT_URL)
NEXENT_CLIENT = NexentClient(endpoint=NEXENT_API_URL)
ACCESS_LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "access.jsonl")
os.makedirs(os.path.dirname(ACCESS_LOG_PATH), exist_ok=True)


def visitor_hash() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    address = forwarded or request.remote_addr or "unknown"
    salt = os.environ.get("ACCESS_LOG_SALT", "phase1-demo")
    return hashlib.sha256(f"{salt}:{address}".encode("utf-8")).hexdigest()[:12]


@app.after_request
def record_access(response):
    if request.path in {"/", "/api/analyze", "/api/health"}:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "visitor": visitor_hash(),
        }
        with open(ACCESS_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return response


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

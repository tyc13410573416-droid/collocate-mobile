"""A small Flask service that emulates the Nexent endpoint used in stage one."""

from __future__ import annotations

import os

from flask import Flask, jsonify, request

from analysis_engine import analyze_payload


app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "mock-nexent"})


@app.route("/v1/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(silent=True) or {}
    return jsonify(analyze_payload(payload))


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5051")),
        debug=False,
    )

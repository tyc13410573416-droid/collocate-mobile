"""Optional CPU OCR. No cloud OCR, image-name fixtures or model API keys."""
from __future__ import annotations

import os
from pathlib import Path
import re
import statistics
import sys
import threading
import time
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "phase1", ROOT / "phase1/mcp_server"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

_ENGINE = None
_LOCK = threading.Lock()


def join_rows(lines):
    """Use detected positions, preserving table rows instead of column-major text."""
    if not lines:
        return "", []
    heights = [max(p[1] for p in box) - min(p[1] for p in box) for box, _, _ in lines]
    tolerance = max(4.0, statistics.median(heights) * 0.55)
    positioned = sorted(((sum(p[1] for p in box) / 4, min(p[0] for p in box), str(text), float(score))
                         for box, text, score in lines), key=lambda item: (item[0], item[1]))
    rows = []
    for item in positioned:
        if not rows or abs(item[0] - rows[-1][0][0]) > tolerance:
            rows.append([item])
        else:
            rows[-1].append(item)
    texts, uncertain = [], []
    for index, row in enumerate(rows, 1):
        row.sort(key=lambda item: item[1])
        texts.append("  ".join(item[2] for item in row))
        if any(item[3] < 0.8 and re.search(r"\d", item[2]) for item in row):
            uncertain.append("第{}行有低置信度读数，请对照原图核对。".format(index))
    return "\n".join(texts), uncertain


def read_image(content):
    global _ENGINE
    from phase2.nexent_image_client import checked_file
    mime, _ = checked_file(content)
    if mime == "application/pdf":
        raise ValueError("本地识图通道请先将 PDF 导出为图片。")
    from rapidocr_onnxruntime import RapidOCR
    with _LOCK:
        if _ENGINE is None:
            _ENGINE = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        lines, elapsed = _ENGINE(content)
    lines = lines or []
    text, uncertain = join_rows(lines)
    numeric_scores = [float(score) for _, word, score in lines if re.search(r"\d", str(word))]
    score = min(numeric_scores) if numeric_scores else 0.0
    return {"raw_text": text, "readable": bool(lines), "uncertain_fields": uncertain}, score, lines


def analyze_image_bytes(content, gender="未知", medications=""):
    from phase2.local_result import build_result
    import server
    started = time.perf_counter()
    transcription, score, lines = read_image(content)
    ocr_ms = (time.perf_counter() - started) * 1000
    aligned_at = time.perf_counter()
    readings, uncertainty = align_readings(lines, server)
    align_ms = (time.perf_counter() - aligned_at) * 1000
    # Only table-associated readings enter the tool workflow. Never replay a sample.
    transcription["uncertain_fields"] = uncertainty
    result = build_result(readings, transcription, gender, medications, server)
    result["trace_log"][:0] = [
        {"tool": "RapidOCR", "status": "done", "elapsed_ms": round(ocr_ms, 3), "origin": "local-cpu-ocr"},
        {"tool": "align_table", "status": "done", "elapsed_ms": round(align_ms, 3), "origin": "local-table-parser"},
    ]
    result["image_transcription"] = transcription
    result.setdefault("metadata", {}).update({
        "ocr_engine": "RapidOCR-ONNX", "image_route": "local-ocr-mcp",
        "confidence_kind": "uncalibrated-ocr-score", "cloud_model_called": False,
    })
    return result


_UNIT = r"(?:mmol/[lL]|[uμµ]mol/[lL]|mg/d[lL]|mg/[lL]|g/d[lL]|g/[lL]|IU/[lL]|U/[lL]|10\^9/[lL]|10\^12/[lL]|%|s)"
_READING = re.compile(r"^\s*([<>≤≥]?)\s*(\d+(?:\.\d+)?)[↑↓HL*]?\s*(" + _UNIT + r")?\s*$")


def align_readings(lines, server):
    """Match numeric boxes to each table's RESULT column, excluding reference values."""
    cells = [{"x": sum(p[0] for p in box) / 4, "y": sum(p[1] for p in box) / 4,
              "h": max(p[1] for p in box) - min(p[1] for p in box),
              "text": str(text), "score": float(score)} for box, text, score in lines]
    headers = sorted([cell for cell in cells if cell["text"].strip() in {"结果", "检测结果", "测定结果"}], key=lambda c: c["x"])
    if not headers:
        return [], ["未确认表格的结果列，请人工核对后粘贴报告文本。"]
    found, uncertain, seen = [], [], set()
    candidates = server._build_candidates()
    for cell in cells:
        label = cell["text"]
        matched = None
        for alias, definition in candidates:
            present = re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", label) if alias.isascii() else alias in label
            if present:
                matched = definition
                break
        if not matched or matched["key"] in seen:
            continue
        choices = [(i, header) for i, header in enumerate(headers) if header["x"] > cell["x"] and cell["y"] > header["y"] + header["h"]]
        if not choices:
            continue
        index, header = min(choices, key=lambda pair: pair[1]["x"] - cell["x"])
        span = (headers[index + 1]["x"] - header["x"]) if index + 1 < len(headers) else (header["x"] - headers[index - 1]["x"] if index else 400)
        x_tolerance = span * 0.16
        numbers = []
        for other in cells:
            match = _READING.fullmatch(other["text"])
            height = max(cell["h"], other["h"])
            delta_y = other["y"] - cell["y"]
            if match and abs(other["x"] - header["x"]) < x_tolerance and -height * 0.45 <= delta_y <= height * 1.1:
                numbers.append((abs(other["y"] - cell["y"]) + abs(other["x"] - header["x"]) * 0.1, other, match))
        if not numbers:
            uncertain.append(label + "：没有找到可确认的结果格。")
            continue
        numbers.sort(key=lambda n: n[0])
        if len(numbers) > 1 and numbers[1][0] - numbers[0][0] < cell["h"] * 0.2:
            uncertain.append(label + "：相邻两行结果无法可靠区分。")
            continue
        _, number, match = numbers[0]
        units = [other for other in cells if header["x"] - x_tolerance <= other["x"] < header["x"] + span * 0.5 and abs(other["y"] - number["y"]) < max(cell["h"], number["h"]) * 1.3 and re.search(_UNIT, other["text"])]
        unit = match.group(3)
        if not unit and units:
            source = min(units, key=lambda other: abs(other["y"] - number["y"]))
            unit = re.search(_UNIT, source["text"]).group(0)
        unit = (unit or "").replace("/l", "/L").replace("umol", "μmol").replace("µmol", "μmol")
        score = min(cell["score"], number["score"])
        if score < 0.8 or not unit or match.group(1):
            uncertain.append(label + "：字迹、单位或不等号需要人工核对。")
        found.append({"indicator": matched.get("name_en") or matched["key"], "test_name": label,
                      "value": float(match.group(2)), "value_comparator": match.group(1), "unit": unit, "score": score})
        seen.add(matched["key"])
    return found, uncertain


def storage_config():
    source = Path(os.environ.get("MEDTRACE_NEXENT_ENV", "/opt/medtrace/nexent-v2.8.1/deploy/env/.env"))
    allowed = {"MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "MINIO_DEFAULT_BUCKET"}
    config = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key in allowed:
            config[key] = value.strip().strip('"').strip("'")
    return config


def image_from_storage(url):
    from minio import Minio
    from phase2.nexent_image_client import MAX_FILE_BYTES
    config = storage_config()
    parsed = urlsplit(url)
    key = unquote(parsed.path).lstrip("/")
    bucket = config.get("MINIO_DEFAULT_BUCKET")
    if parsed.scheme != "s3" or parsed.netloc != bucket or not key or ".." in key.split("/") or "\\" in key or "\x00" in key:
        raise ValueError("只允许读取当前平台 MinIO 桶中的图片附件。")
    endpoint = os.environ.get("MEDTRACE_MINIO_ENDPOINT", "127.0.0.1:9010")
    client = Minio(endpoint, access_key=config["MINIO_ROOT_USER"], secret_key=config["MINIO_ROOT_PASSWORD"], secure=False)
    if client.stat_object(bucket, key).size > MAX_FILE_BYTES:
        raise ValueError("图片不能超过 10 MB。")
    response = client.get_object(bucket, key)
    try:
        return response.read(MAX_FILE_BYTES + 1)
    finally:
        response.close()
        response.release_conn()

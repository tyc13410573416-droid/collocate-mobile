"""Short-lived private results so a small routing model never rewrites readings."""
import json
import os
from pathlib import Path
import re
import time
import uuid
from datetime import datetime, timezone

TTL_SECONDS = 15 * 60


def result_dir():
    value = os.environ.get("NEXENT_LOCAL_RESULT_DIR", "")
    if not value:
        raise ValueError("local result store not configured")
    return Path(value)


def save_result(image_url, result, original_result=None):
    directory = result_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = time.time()
    for old in directory.glob("*.json"):
        if now - old.stat().st_mtime > TTL_SECONDS:
            try:
                old.unlink()
            except FileNotFoundError:
                pass
    key = uuid.uuid4().hex
    target = directory / (key + ".json")
    # Create with restrictive permissions before writing medical content.
    descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"image_url": image_url, "result": result, "original_result": original_result}, handle, ensure_ascii=False)
    return {"local_result_id": key}


def load_record(key):
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{32}", key):
        raise ValueError("invalid local result receipt")
    target = result_dir() / (key + ".json")
    modified = target.stat().st_mtime
    if time.time() - modified > TTL_SECONDS:
        raise ValueError("expired local result")
    stored = json.loads(target.read_text(encoding="utf-8"))
    stored["expires_at"] = datetime.fromtimestamp(modified + TTL_SECONDS, timezone.utc).isoformat()
    return stored


def load_result(receipt, attachment):
    if isinstance(receipt, str):
        receipt = json.loads(receipt)
    key = receipt.get("local_result_id") if isinstance(receipt, dict) else None
    stored = load_record(key)
    if stored.get("image_url") != attachment.get("url"):
        raise ValueError("result belongs to another attachment")
    result = stored["result"]
    result["review_context"] = {"token": key, "expires_at": stored["expires_at"]}
    original = stored.get("original_result") or result
    edited = {row.get("abbreviation"): row for row in result.get("lab_results", [])}
    result["review_candidates"] = [dict(row, **edited.get(row.get("abbreviation"), {})) for row in original.get("lab_results", [])]
    return result

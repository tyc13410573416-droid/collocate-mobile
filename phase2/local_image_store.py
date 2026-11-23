"""Short-lived private results so a small routing model never rewrites readings."""
import json
import os
from pathlib import Path
import re
import time
import uuid

TTL_SECONDS = 15 * 60


def result_dir():
    value = os.environ.get("NEXENT_LOCAL_RESULT_DIR", "")
    if not value:
        raise ValueError("local result store not configured")
    return Path(value)


def save_result(image_url, result):
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
        json.dump({"image_url": image_url, "result": result}, handle, ensure_ascii=False)
    return {"local_result_id": key}


def load_result(receipt, attachment):
    if isinstance(receipt, str):
        receipt = json.loads(receipt)
    key = receipt.get("local_result_id") if isinstance(receipt, dict) else None
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{32}", key):
        raise ValueError("invalid local result receipt")
    target = result_dir() / (key + ".json")
    if time.time() - target.stat().st_mtime > TTL_SECONDS:
        raise ValueError("expired local result")
    stored = json.loads(target.read_text(encoding="utf-8"))
    if stored.get("image_url") != attachment.get("url"):
        raise ValueError("result belongs to another attachment")
    return stored["result"]

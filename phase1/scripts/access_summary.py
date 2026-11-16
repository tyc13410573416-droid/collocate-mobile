"""Summarize the local anonymous access log without exposing raw IP addresses."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


DEFAULT_LOG = Path(__file__).resolve().parents[1] / "logs" / "access.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()
    if not args.log.exists():
        print(json.dumps({"total_requests": 0, "unique_visitors": 0, "message": "暂无访问记录"}, ensure_ascii=False, indent=2))
        return

    entries = []
    with args.log.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    by_path = Counter(entry.get("path", "") for entry in entries)
    by_status = Counter(str(entry.get("status", "")) for entry in entries)
    print(json.dumps({
        "total_requests": len(entries),
        "unique_visitors": len({entry.get("visitor") for entry in entries}),
        "requests_by_path": dict(by_path),
        "responses_by_status": dict(by_status),
        "last_requests": entries[-20:],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

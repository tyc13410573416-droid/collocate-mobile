"""Strict Nexent-compatible HTTP client used by the stage-two frontend."""

from __future__ import annotations

import os
from typing import Any

import requests


class NexentClientError(RuntimeError):
    """Raised when the configured Nexent endpoint cannot serve a valid response."""


class NexentClient:
    def __init__(self, endpoint: str | None = None, api_key: str | None = None, timeout: float = 8.0):
        self.endpoint = endpoint or os.environ.get("NEXENT_API_URL", "")
        self.api_key = api_key or os.environ.get("NEXENT_API_KEY", "")
        self.timeout = timeout

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.endpoint:
            raise NexentClientError("未配置 NEXENT_API_URL")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
        except requests.Timeout as exc:
            raise NexentClientError("Nexent 请求超时") from exc
        except requests.RequestException as exc:
            raise NexentClientError(f"Nexent 请求失败：{exc}") from exc
        except ValueError as exc:
            raise NexentClientError("Nexent 返回的不是有效 JSON") from exc
        self._validate(result)
        result["transport"] = "nexent-http"
        return result

    @staticmethod
    def _validate(result: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            raise NexentClientError("Nexent 返回格式必须是 JSON 对象")
        trace_key_present = "trace" in result or "trace_log" in result
        lab_key_present = isinstance(result.get("items"), list) or isinstance(result.get("lab_results"), list)
        missing = [key for key in ("answer", "citations") if key not in result]
        if not lab_key_present:
            missing.append("lab_results/items")
        if not trace_key_present:
            missing.append("trace_log")
        if missing:
            raise NexentClientError(f"Nexent 响应缺少字段：{', '.join(missing)}")
        if not isinstance(result["citations"], list):
            raise NexentClientError("Nexent 响应中的 citations 必须是数组")
        if "items" in result and not isinstance(result["items"], list):
            raise NexentClientError("Nexent 响应中的 items 必须是数组")
        if "lab_results" in result and not isinstance(result["lab_results"], list):
            raise NexentClientError("Nexent 响应中的 lab_results 必须是数组")


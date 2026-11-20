"""Nexent 响应契约的本地校验测试。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nexent_client import NexentClient, NexentClientError


def valid_response():
    return {
        "answer": "仅用于演示的结果",
        "citations": [{"id": "来源1", "source_id": "SRC-ALT-001"}],
        "lab_results": [{"test_name": "ALT", "value": 68.0, "status": "high"}],
        "trace_log": [{"tool": "parse_report", "status": "done"}],
        "metadata": {"extraction_confidence": 0.95},
        "decision_gate": "review",
    }


class NexentContractTest(unittest.TestCase):
    def test_accepts_stage_two_response(self):
        NexentClient._validate(valid_response())

    def test_rejects_invalid_status(self):
        payload = valid_response()
        payload["lab_results"][0]["status"] = "diagnosis"
        with self.assertRaises(NexentClientError):
            NexentClient._validate(payload)

    def test_rejects_missing_source_id(self):
        payload = valid_response()
        payload["citations"] = [{"id": "来源1"}]
        with self.assertRaises(NexentClientError):
            NexentClient._validate(payload)

    def test_rejects_invalid_confidence(self):
        payload = valid_response()
        payload["metadata"]["extraction_confidence"] = 1.2
        with self.assertRaises(NexentClientError):
            NexentClient._validate(payload)


if __name__ == "__main__":
    unittest.main()

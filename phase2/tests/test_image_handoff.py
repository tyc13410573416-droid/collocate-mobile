"""HTTP attachment integration tests; the fake service does NOT perform OCR."""
import cgi
import copy
import io
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from phase1.app import app
from phase2.nexent_image_client import ImageHandoffError, validated_gate

PNG = b"\x89PNG\r\n\x1a\n" + b"test-payload-actual-bytes"


def result():
    return {"answer": "测试服务的结构化结果（非 OCR）", "decision_gate": "pass",
            "confidence": 0.95, "evidence_status": "found", "conflicts": [],
            "next_action": "仅用于传输测试", "source_versions": [],
            "citations": [{"source_id": "TEST-REFERENCE"}],
            "lab_results": [{"test_name": "ALT", "value": 123.45, "status": "high"}],
            "trace_log": [{"tool": "parse_report", "status": "done"}],
            "metadata": {"extraction_confidence": 0.95}}


class FakeNexent(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        state = self.server.state
        state["auth"].append(self.headers.get("Authorization"))
        if self.path == "/api/file/storage":
            fields = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                      environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]})
            state["file_bytes"] = fields["files"].file.read()
            state["filename"] = fields["files"].filename
            state["folder"] = fields.getvalue("folder")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"results": [{"success": True, "object_name": "attachments/received-file.png"}]}).encode())
        elif self.path == "/api/agent/run":
            state["agent_body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            self.wfile.write(b': heartbeat\n\ndata: {"type":"model_output","content":"internal not forwarded"}\n\n')
            for event in state["events"]:
                self.wfile.write(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class ImageHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeNexent)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.env = patch.dict(os.environ, {"NEXENT_BASE_URL": "http://127.0.0.1:{}/api".format(self.server.server_port),
                                         "NEXENT_IMAGE_AGENT_ID": "42", "NEXENT_IMAGE_PROTOCOL": "v1.8",
                                         "NEXENT_API_KEY": "server-only-test-token", "IMAGE_ALLOWED_ORIGINS": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.server.state = {"auth": [], "events": [{"type": "final_answer", "content": json.dumps(result(), ensure_ascii=False)}]}
        self.client = app.test_client()

    def post(self, content=PNG, filename="sample-02-glucose-crp.png", **kw):
        data = {"file": (io.BytesIO(content), filename), "gender": "女", "medications": "测试用药", "raw_text": "用户补充"}
        return self.client.post("/api/analyze-image", data=data, content_type="multipart/form-data", **kw)

    def events(self, response):
        return [json.loads(line) for line in response.get_data(as_text=True).splitlines()]

    def test_transfers_bytes_and_returned_attachment_with_context(self):
        # A demo-like filename must still send real bytes; no fixture/MCP shortcut.
        with patch("phase1.app.analyze_payload", side_effect=AssertionError("no image fallback")):
            response = self.post()
            events = self.events(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([event.get("stage") for event in events[:-1]], ["uploading", "uploaded", "agent_submitted"])
        self.assertEqual(events[-1]["result"]["lab_results"][0]["value"], 123.45)
        self.assertEqual(events[-1]["result"]["transport"], "nexent-image-http")
        self.assertEqual(self.server.state["file_bytes"], PNG)
        self.assertEqual(self.server.state["filename"], "report.png")
        body = self.server.state["agent_body"]
        self.assertEqual(body["agent_id"], 42)
        self.assertEqual(body["minio_files"][0]["object_name"], "attachments/received-file.png")
        self.assertEqual(body["minio_files"][0]["size"], len(PNG))
        self.assertIn('"gender": "女"', body["query"])
        self.assertIn("测试用药", body["query"])
        self.assertEqual(self.server.state["auth"], ["Bearer server-only-test-token"] * 2)
        self.assertNotIn("server-only-test-token", response.get_data(as_text=True))
        self.assertNotIn("internal not forwarded", response.get_data(as_text=True))

    def test_unconfigured_is_503_even_in_demo_mode(self):
        with patch.dict(os.environ, {"NEXENT_BASE_URL": "", "NEXENT_IMAGE_AGENT_ID": ""}):
            response = self.post()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json()["error_code"], "IMAGE_NOT_CONFIGURED")
            self.assertFalse(self.client.get("/api/image-status").get_json()["configured"])

    def test_bad_file_and_size_rejected_before_nexent(self):
        self.assertEqual(self.post(b"not an image").status_code, 415)
        self.assertEqual(self.post(b"").status_code, 400)
        self.assertEqual(self.post(PNG + b"x" * (10 * 1024 * 1024)).status_code, 413)
        self.assertEqual(self.server.state["auth"], [])

    def test_plain_text_answer_never_becomes_result_cards(self):
        self.server.state["events"] = [{"type": "final_answer", "content": "ALT 123.45 偏高"}]
        events = self.events(self.post())
        self.assertEqual(events[-1]["error_code"], "INVALID_GATE_RESULT")
        self.assertFalse(any(event["type"] == "result" for event in events))

    def test_ocr_error_is_sanitized_and_not_a_success(self):
        self.server.state["events"] = [{"type": "error", "content": "sensitive server-only-test-token patient name"}]
        response = self.post()
        events = self.events(response)
        self.assertEqual(events[-1]["error_code"], "AGENT_FAILED")
        self.assertNotIn("sensitive", response.get_data(as_text=True))
        self.assertNotIn("server-only-test-token", response.get_data(as_text=True))

    def test_stream_without_final_answer_stays_error(self):
        self.server.state["events"] = []
        self.assertEqual(self.events(self.post())[-1]["error_code"], "AGENT_NO_RESULT")

    def test_explicit_cors_allowlist(self):
        response = self.post(headers={"Origin": "https://unknown.example"})
        self.assertEqual(response.status_code, 403)
        with patch.dict(os.environ, {"IMAGE_ALLOWED_ORIGINS": "https://tyc13410573416-droid.github.io"}):
            response = self.client.options("/api/analyze-image", headers={"Origin": "https://tyc13410573416-droid.github.io"})
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://tyc13410573416-droid.github.io")
            self.assertNotIn("Access-Control-Allow-Credentials", response.headers)

    def test_unreachable_nexent_stays_error(self):
        import requests
        with patch("phase2.nexent_image_client.requests.post", side_effect=requests.ConnectionError("secret")):
            events = self.events(self.post())
        self.assertEqual(events[-1]["error_code"], "NEXENT_UNAVAILABLE")
        self.assertNotIn("secret", str(events))

    def test_gate_contract_rejects_missing_inconsistent_or_nonfinite(self):
        payloads = []
        missing = result()
        del missing["confidence"]
        payloads.append(missing)
        inconsistent = result()
        inconsistent["evidence_status"] = "conflict"
        payloads.append(inconsistent)
        nonfinite = result()
        nonfinite["lab_results"][0]["value"] = float("nan")
        payloads.append(nonfinite)
        for payload in payloads:
            with self.assertRaises(ImageHandoffError):
                validated_gate(payload)
        for gate, status in [("pass", "found"), ("review", "missing_info"), ("review", "low_confidence"), ("review", "conflict"), ("abstain", "missing")]:
            payload = copy.deepcopy(result())
            payload.update(decision_gate=gate, evidence_status=status)
            self.assertEqual(validated_gate(payload)["decision_gate"], gate)


if __name__ == "__main__":
    unittest.main()

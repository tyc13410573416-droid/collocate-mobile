"""HTTP attachment integration tests; the fake service does NOT perform OCR."""
import cgi
import copy
import io
import json
import os
import threading
import tempfile
from pathlib import Path
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

    def do_GET(self):
        if self.path == "/api/agent/stop/123":
            self.server.state["stops"] = self.server.state.get("stops", 0) + 1
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        state = self.server.state
        state["auth"].append(self.headers.get("Authorization"))
        if self.path == "/api/user/signin":
            state["signins"] = state.get("signins", 0) + 1
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if body != {"email": "test@localhost", "password": "test-only-password"}:
                self.send_response(401)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Set-Cookie", "nexent_access_token=test-session-{}; HttpOnly; Path=/".format(state["signins"]))
            self.end_headers()
            self.wfile.write(b'{}')
        elif self.path == "/api/file/storage":
            fields = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                      environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]})
            state["file_bytes"] = fields["files"].file.read()
            state["filename"] = fields["files"].filename
            state["folder"] = fields.getvalue("folder")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"results": [{"success": True, "object_name": "attachments/received-file.png", "url": state.get("upload_url", "s3://nexent/attachments/received-file.png")}]}).encode())
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


class FakeNexentCase(unittest.TestCase):
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


class ImageHandoffTest(FakeNexentCase):
    def test_team_uploads_get_busy_message_and_disconnect_releases_slot(self):
        first = self.post(buffered=False)
        try:
            second = self.post()
            self.assertEqual(second.status_code, 429)
            self.assertEqual(second.get_json()["error_code"], "IMAGE_SERVICE_BUSY")
        finally:
            first.close()
        self.assertEqual(self.events(self.post())[-1]["type"], "result")

    def test_failed_identification_releases_shared_cpu_slot(self):
        self.server.state["events"] = [{"type":"error","content":"test upstream failure"}]
        self.assertEqual(self.events(self.post())[-1]["type"], "error")
        self.server.state["events"] = [{"type":"final_answer","content":json.dumps(result())}]
        self.assertEqual(self.events(self.post())[-1]["type"], "result")

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


def image_result():
    data = result()
    data["image_transcription"] = {"raw_text": "ALT 123.45 U/L，原单参考范围 9-50 U/L", "readable": True, "uncertain_fields": []}
    return data


def vision_call(url="s3://nexent/attachments/received-file.png"):
    return {"type": "tool", "tool_name": "analyze_image", "tool_arguments": {"image_urls_list": [url], "query": "逐行转录"}, "tool_call_id": "test-vision-call"}


class NativeVisionTest(FakeNexentCase):
    def setUp(self):
        super().setUp()
        os.environ["NEXENT_IMAGE_PROTOCOL"] = "v2.8.1"
        self.server.state["events"] = [vision_call(), {"type": "final_answer", "content": json.dumps(image_result()), "answer_phase": "complete"}]

    def test_native_tool_and_complete_transcript(self):
        events = self.events(self.post())
        self.assertEqual(events[-1]["type"], "result")
        data = events[-1]["result"]
        self.assertTrue(data["metadata"]["vision_tool_observed"])
        self.assertEqual(data["image_transcription"]["raw_text"], image_result()["image_transcription"]["raw_text"])
        self.assertIn({"type": "stage", "stage": "vision_reading"}, events)
        body = self.server.state["agent_body"]
        self.assertEqual(body["minio_files"][0]["url"], "s3://nexent/attachments/received-file.png")
        self.assertIn("必须先使用 analyze_image", body["query"])
        self.assertIn("用户补充", body["query"])

    def test_unicode_deltas_wait_for_complete(self):
        text = json.dumps(image_result(), ensure_ascii=False)
        self.server.state["events"] = [vision_call()] + [
            {"type": "final_answer", "content": text[index:index + 13], "answer_phase": "delta", "step_id": "root-step", "attempt_id": "good-attempt"}
            for index in range(0, len(text), 13)
        ] + [{"type": "final_answer", "content": "", "answer_phase": "complete", "step_id": "root-step", "attempt_id": "good-attempt"}]
        events = self.events(self.post())
        self.assertEqual(events[-1]["result"]["lab_results"][0]["value"], 123.45)
        self.assertEqual(sum(event["type"] == "result" for event in events), 1)

    def test_incomplete_deltas_are_not_a_result(self):
        self.server.state["events"] = [vision_call(), {"type": "final_answer", "content": '{"answer":', "answer_phase": "delta"}]
        self.assertEqual(self.events(self.post())[-1]["error_code"], "AGENT_NO_RESULT")

    def test_subagent_answer_cannot_finish_root(self):
        child = image_result()
        child["lab_results"][0]["value"] = 999
        self.server.state["events"].insert(1, {"type": "final_answer", "content": json.dumps(child), "answer_phase": "complete", "invocation_id": "child", "depth": 1})
        self.assertEqual(self.events(self.post())[-1]["result"]["lab_results"][0]["value"], 123.45)

    def test_reclassified_root_answer_uses_only_its_step(self):
        self.server.state["events"] = [vision_call(),
            {"type": "model_output_code", "content": "stale internal text", "step_id": "old", "attempt_id": "old-attempt"},
            {"type": "model_output_code", "content": json.dumps(image_result()), "step_id": "new", "attempt_id": "new-attempt"},
            {"type": "final_answer", "content": "", "answer_phase": "complete", "step_id": "new", "attempt_id": "new-attempt", "reclassify_step": True}]
        response = self.post()
        self.assertEqual(self.events(response)[-1]["type"], "result")
        self.assertNotIn("stale internal text", response.get_data(as_text=True))

    def test_no_vision_call_rejected_even_if_final_claims_it(self):
        data = image_result()
        data["metadata"]["vision_tool_observed"] = True
        self.server.state["events"] = [{"type": "final_answer", "content": json.dumps(data)}]
        self.assertEqual(self.events(self.post())[-1]["error_code"], "VISION_TOOL_NOT_CALLED")

    def test_reading_another_picture_does_not_count(self):
        self.server.state["events"][0] = vision_call("s3://nexent/attachments/another-file.png")
        self.assertEqual(self.events(self.post())[-1]["error_code"], "VISION_TOOL_NOT_CALLED")

    def test_same_key_on_unrelated_bucket_does_not_count(self):
        self.server.state["events"][0] = vision_call("s3://unrelated-bucket/attachments/received-file.png")
        self.assertEqual(self.events(self.post())[-1]["error_code"], "VISION_TOOL_NOT_CALLED")

    def test_missing_transcript_rejected(self):
        self.server.state["events"][-1]["content"] = json.dumps(result())
        self.assertEqual(self.events(self.post())[-1]["error_code"], "IMAGE_TRANSCRIPT_MISSING")

    def test_uncertain_reading_cannot_pass(self):
        data = image_result()
        data["image_transcription"]["uncertain_fields"] = ["ALT 小数点无法确认"]
        self.server.state["events"][-1]["content"] = json.dumps(data)
        self.assertEqual(self.events(self.post())[-1]["error_code"], "IMAGE_REVIEW_REQUIRED")
        data.update(decision_gate="review", evidence_status="low_confidence")
        self.server.state["events"][-1]["content"] = json.dumps(data)
        self.assertEqual(self.events(self.post())[-1]["result"]["decision_gate"], "review")

    def test_pdf_never_sent_to_image_tool(self):
        response = self.post(b"%PDF-1.4\nexample", filename="report.pdf")
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.get_json()["error_code"], "VISION_PDF_UNSUPPORTED")
        self.assertEqual(self.server.state["auth"], [])


class LocalImageTransportTest(FakeNexentCase):
    def setUp(self):
        super().setUp()
        from phase2.local_image_store import save_result
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        local_env = patch.dict(os.environ, {"NEXENT_IMAGE_PROTOCOL": "v2.8.1", "NEXENT_IMAGE_READER_TOOL": "analyze_medical_image",
                                          "NEXENT_LOCAL_RESULT_DIR": self.temp.name, "NEXENT_ATTACHMENT_BUCKET": "nexent"})
        local_env.start();self.addCleanup(local_env.stop)
        self.receipt = save_result("s3://nexent/attachments/received-file.png", image_result())
        call = vision_call();call["tool_name"] = "analyze_medical_image"
        self.server.state["events"] = [{"type":"conversation_created","content":{"conversation_id":123}},call, {"type": "execution_logs", "content": json.dumps(self.receipt)}]

    def test_local_workflow_returns_frozen_tool_result_without_model_rewriting(self):
        response = self.post()
        data = self.events(response)[-1]["result"]
        self.assertEqual(data["lab_results"][0]["value"],123.45)
        self.assertEqual(data["metadata"]["result_source"],"local-tool-receipt")
        self.assertFalse(data["metadata"]["vision_tool_observed"])
        self.assertTrue(data["metadata"]["image_tool_observed"])
        self.assertEqual(self.server.state["stops"],1)

    def test_native_relative_location_maps_only_to_configured_actual_bucket(self):
        self.server.state["upload_url"] = "/nexent/attachments/received-file.png"
        self.assertEqual(self.events(self.post())[-1]["type"],"result")
        self.assertEqual(self.server.state["agent_body"]["minio_files"][0]["url"],"s3://nexent/attachments/received-file.png")
        self.server.state["upload_url"] = "/unrelated/attachments/received-file.png"
        self.assertEqual(self.events(self.post())[-1]["error_code"],"ATTACHMENT_URL_MISSING")

    def test_tool_name_config_cannot_inject_python(self):
        with patch.dict(os.environ,{"NEXENT_IMAGE_READER_TOOL":"other(); print('bad')"}):
            self.assertEqual(self.post().status_code,503)
        self.assertEqual(self.server.state["auth"],[])

    def test_local_session_is_refreshed_for_each_image_and_never_sent_to_browser(self):
        login = Path(self.temp.name)/"login.json"
        login.write_text(json.dumps({"email":"test@localhost","password":"test-only-password"}),encoding="utf-8")
        with patch.dict(os.environ,{"NEXENT_LOCAL_LOGIN_FILE":str(login)}):
            for _ in range(2):
                response=self.post()
                self.assertEqual(self.events(response)[-1]["type"],"result")
                self.assertNotIn("test-session",response.get_data(as_text=True))
        self.assertEqual(self.server.state["signins"],2)
        self.assertEqual(self.server.state["auth"],[None,"Bearer test-session-1","Bearer test-session-1",None,"Bearer test-session-2","Bearer test-session-2"])


if __name__ == "__main__":
    unittest.main()

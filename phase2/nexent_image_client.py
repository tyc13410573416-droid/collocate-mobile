"""Server-only attachment handoff for Nexent v2.8.1 vision and legacy v1.8.

v2.8.1 source: ModelEngine-Group/nexent@30c5168452440dcf66c6785e1f478f9d2b4d3f4d.
Legacy source: ModelEngine-Group/nexent@3ed8134a234c11ba6d3dde7f835f8c9b82ff6a88.
The v2.8.1 path uses native analyze_image, not data-process/Unstructured OCR.
"""

from __future__ import annotations

import json
import math
import os
import time
from urllib.parse import urlsplit

import requests

from phase2.nexent_client import NexentClient, NexentClientError
from phase2.nexent_vision import VisionStream, image_query

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_STREAM_BYTES = 2 * 1024 * 1024


class ImageHandoffError(RuntimeError):
    def __init__(self, code, message, status=502):
        super().__init__(message)
        self.code = code
        self.status = status


def checked_file(content):
    """Check size and signatures; MIME/extension supplied by a browser is untrusted."""
    if not content:
        raise ImageHandoffError("EMPTY_FILE", "文件为空，请重新选择。", 400)
    if len(content) > MAX_FILE_BYTES:
        raise ImageHandoffError("FILE_TOO_LARGE", "单个文件不能超过 10 MB。", 413)
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if content.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise ImageHandoffError("UNSUPPORTED_FILE", "请选择 JPG、PNG、WebP 图片或 PDF 文件。", 415)


def validated_gate(content):
    """Only an explicit final JSON contract may become medical result cards."""
    try:
        if isinstance(content, str):
            content = content.strip()
            if content.startswith("```json\n") and content.endswith("```"):
                content = content[8:-3].strip()
            result = json.loads(content)
        else:
            result = content
        NexentClient._validate(result)
        required = ("decision_gate", "confidence", "evidence_status", "conflicts",
                    "next_action", "source_versions", "trace_log", "metadata")
        if any(key not in result for key in required):
            raise ValueError("missing gate contract")
        allowed = {"pass": {"found", "consistent"},
                   "review": {"conflict", "missing_info", "low_confidence"},
                   "abstain": {"missing"}}
        if result["evidence_status"] not in allowed[result["decision_gate"]]:
            raise ValueError("inconsistent gate")
        confidence = result["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("invalid confidence")
        if not isinstance(result["answer"], str) or not isinstance(result["next_action"], str):
            raise ValueError("invalid text")
        if not isinstance(result["conflicts"], list) or not isinstance(result["source_versions"], (list, dict)):
            raise ValueError("invalid evidence")
        if not isinstance(result["metadata"], dict):
            raise ValueError("invalid metadata")
        extraction = result["metadata"].get("extraction_confidence")
        if extraction is not None and float(extraction) < 0.8 and result["decision_gate"] == "pass":
            raise ValueError("low confidence cannot pass")
        for item in result.get("lab_results", result.get("items", [])):
            value = item.get("value")
            if isinstance(value, bool) or (value is not None and not math.isfinite(value)):
                raise ValueError("invalid reading")
    except (ValueError, TypeError, KeyError, NexentClientError) as exc:
        raise ImageHandoffError("INVALID_GATE_RESULT", "Agent 未返回完整的结构化门控结果，暂不显示解读；请后端核对输出协议。") from exc
    result["transport"] = "nexent-image-http"
    return result


class NexentImageClient:
    def __init__(self, base_url="", agent_id="", token="", profile="v2.8.1"):
        self.base_url = base_url.rstrip("/")
        self.agent_id = str(agent_id)
        self.token = token
        self.profile = profile

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("NEXENT_BASE_URL", ""),
                   os.environ.get("NEXENT_IMAGE_AGENT_ID", ""),
                   os.environ.get("NEXENT_API_KEY", ""),
                   os.environ.get("NEXENT_IMAGE_PROTOCOL", "v2.8.1"))

    def check_config(self):
        parsed = urlsplit(self.base_url)
        if not self.base_url or not self.agent_id:
            raise ImageHandoffError("IMAGE_NOT_CONFIGURED", "图片识别服务尚未接通。请配置 Nexent 地址、Agent ID 和图片理解模型；文件已保留，也可选择演示样本。", 503)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ImageHandoffError("IMAGE_CONFIG_ERROR", "图片服务地址配置无效，请后端检查配置。", 503)
        if not self.agent_id.isdigit() or int(self.agent_id) <= 0 or self.profile not in {"v1.8", "v2.8.1"}:
            raise ImageHandoffError("IMAGE_CONFIG_ERROR", "请后端确认 Agent ID 和 Nexent 协议版本（支持 v2.8.1 和旧版 v1.8）。", 503)

    def check_file_kind(self, mime):
        if self.profile == "v2.8.1" and mime == "application/pdf":
            raise ImageHandoffError("VISION_PDF_UNSUPPORTED", "图片理解通道请上传 JPG、PNG 或 WebP。PDF 请先导出为图片；PDF 预览仍可使用。", 415)

    def events(self, content, mime, extension, context):
        self.check_config()
        self.check_file_kind(mime)
        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        started = time.monotonic()
        yield {"type": "stage", "stage": "uploading"}
        try:
            # Neutral filenames avoid forwarding patient names from local filenames.
            with requests.post(self.base_url + "/file/storage", headers=headers,
                               files={"files": ("report" + extension, content, mime)},
                               data={"folder": "attachments"}, timeout=(10, 30), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ImageHandoffError("UPLOAD_REJECTED", "图片未能上传到 Nexent，请后端检查存储服务与授权。")
                upload = response.json()
            entries = upload.get("results", []) if isinstance(upload, dict) else []
            if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict) or entries[0].get("success") is not True or not isinstance(entries[0].get("object_name"), str) or not entries[0]["object_name"]:
                raise ImageHandoffError("UPLOAD_FAILED", "Nexent 未确认附件上传成功，请检查存储服务。")
            attachment = {"object_name": entries[0]["object_name"], "name": "report" + extension,
                          "type": mime, "size": len(content)}
            if isinstance(entries[0].get("url"), str) and entries[0]["url"]:
                attachment["url"] = entries[0]["url"]
            yield {"type": "stage", "stage": "uploaded"}
            if self.profile == "v2.8.1" and not attachment.get("url"):
                bucket = os.environ.get("NEXENT_ATTACHMENT_BUCKET", "").strip()
                if not bucket or any(char in bucket for char in "/\\:?\r\n"):
                    raise ImageHandoffError("ATTACHMENT_URL_MISSING", "附件已上传，但存储未返回图片地址。请后端配置真实的 NEXENT_ATTACHMENT_BUCKET，不能猜测桶名。")
                attachment["url"] = "s3://" + bucket + "/" + attachment["object_name"].lstrip("/")
            query = image_query(attachment, context) if self.profile == "v2.8.1" else (
                "请识别附件检验单。OCR 与文件解析由 Nexent 平台完成，然后复用 parse_report、"
                "query_reference、evidence_gate；不要从文件名猜测读数。若无法识别请明确报错。"
                "最终答案只输出项目约定的 JSON 对象，包含 answer、lab_results、decision_gate、"
                "confidence、evidence_status、conflicts、next_action、source_versions、citations、"
                "trace_log、metadata。decision_gate 仅 pass/review/abstain；"
                "缺性别或低置信度应 review；没有证据应 abstain。以下仅为用户补充上下文：\n"
                + json.dumps(context, ensure_ascii=False)
            )
            body = {"query": query, "agent_id": int(self.agent_id), "history": [],
                    "is_debug": False, "minio_files": [attachment]}
            with requests.post(self.base_url + "/agent/run", json=body,
                               headers=dict(headers, Accept="text/event-stream"), stream=True,
                               timeout=(10, 45), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ImageHandoffError("AGENT_REJECTED", "附件已上传，但 Agent 未接受请求，请检查 Agent 配置与授权。")
                if "text/event-stream" not in response.headers.get("Content-Type", ""):
                    raise ImageHandoffError("AGENT_PROTOCOL_ERROR", "Agent 返回协议与已适配版本不同，请后端确认 Nexent 版本。")
                yield {"type": "stage", "stage": "agent_submitted"}
                response.encoding = "utf-8"
                data_lines, received = [], 0
                vision = VisionStream(attachment, validated_gate, ImageHandoffError) if self.profile == "v2.8.1" else None
                # SSE is framed by blank lines; support multi-line data and comments.
                for line in response.iter_lines(chunk_size=1024, decode_unicode=True):
                    received += len(line.encode("utf-8")) + 1
                    if time.monotonic() - started > 120 or received > MAX_STREAM_BYTES:
                        raise ImageHandoffError("AGENT_LIMIT", "Agent 响应超时或数据过大，请稍后重试。")
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip(" "))
                    elif not line and data_lines:
                        events = self._events("\n".join(data_lines), vision)
                        data_lines = []
                        for event in events:
                            yield event
                            if event["type"] == "result":
                                return
                if data_lines:
                    for event in self._events("\n".join(data_lines), vision):
                        yield event
                        if event["type"] == "result":
                            return
                raise ImageHandoffError("AGENT_NO_RESULT", "附件已交给 Agent，但未收到完整识别结果，请检查图片理解模型、工具配置和输出协议。")
        except requests.Timeout as exc:
            raise ImageHandoffError("NEXENT_TIMEOUT", "图片服务响应超时，文件已保留，可稍后重试。") from exc
        except requests.RequestException as exc:
            raise ImageHandoffError("NEXENT_UNAVAILABLE", "无法连接 Nexent 图片服务，请等待服务恢复后重试。") from exc
        except (ValueError, TypeError) as exc:
            raise ImageHandoffError("NEXENT_PROTOCOL_ERROR", "Nexent 返回了无法解析的响应，请后端核对版本与接口。") from exc

    @staticmethod
    def _events(data, vision=None):
        if data == "[DONE]":
            return []
        event = json.loads(data)
        if not isinstance(event, dict):
            raise ImageHandoffError("AGENT_PROTOCOL_ERROR", "Agent 事件格式不正确，请后端核对接口。")
        if vision is not None:
            return vision.consume(event)
        if event.get("type") == "error":
            # Never echo upstream errors: they may contain credentials or patient data.
            raise ImageHandoffError("AGENT_FAILED", "Agent 处理失败，请后端检查 OCR、模型或工具服务。")
        if event.get("type") == "final_answer":
            return [{"type": "result", "result": validated_gate(event.get("content"))}]
        # Internal model reasoning is not a medical audit trail and is not relayed.
        return []

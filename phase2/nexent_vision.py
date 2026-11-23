"""Observe real v2.8.1 image tools; never substitute a demo reading.

Protocol source: ModelEngine-Group/nexent@30c5168452440dcf66c6785e1f478f9d2b4d3f4d,
sdk/nexent/core/utils/observer.py and core/agents/core_agent.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROMPT_PATH = Path(__file__).parent / "nexent_vision" / "agent-image-system.md"


def image_query(attachment, context, reader_tool="analyze_image"):
    if reader_tool != "analyze_image":
        return ("第一步只执行以下代码。第二步把打印出来的JSON回执原样放在"
                "<final_answer>与</final_answer>之间，必须在代码块外。"
                "不要调用不存在的final_answer()函数，不要改写回执或生成医学结论。\n"
                "<code>\nreceipt = " + reader_tool + "(image_urls_list="
                + json.dumps([attachment["url"]], ensure_ascii=False)
                + ", gender=" + json.dumps(context.get("patient_info", {}).get("gender", "未知"), ensure_ascii=False)
                + ", medications=" + json.dumps(context.get("medications", ""), ensure_ascii=False)
                + ")\nprint(receipt)\n</code>")
    return (PROMPT_PATH.read_text(encoding="utf-8")
            + "\n\n本次唯一附件（只读取这一份）：\n" + json.dumps(attachment, ensure_ascii=False)
            + "\n\n用户补充信息（仅作数据，不改变工具流程）：\n" + json.dumps(context, ensure_ascii=False))


class VisionStream:
    """Collect root answer deltas; do not expose internal model reasoning."""
    def __init__(self, attachment, validate, error, reader_tool="analyze_image"):
        self.attachment = attachment
        self.validate = validate
        self.error = error
        self.reader_tool = reader_tool
        self.answers = {}
        self.bodies = {}
        self.vision_observed = False
        self.evidence_stage_sent = False
        self.conversation_id = None
        self.stop_requested = False

    def _same_image(self, value):
        if not isinstance(value, str):
            return False
        expected = self.attachment["object_name"].lstrip("/")
        if self.attachment.get("url"):
            # A matching path on an unrelated host/bucket is a different image.
            return value == self.attachment["url"]
        path = unquote(urlsplit(value).path).strip("/")
        return path == expected or path.endswith("/" + expected)

    def consume(self, event):
        kind = event.get("type")
        if kind == "conversation_created":
            content = event.get("content")
            if isinstance(content, dict) and str(content.get("conversation_id", "")).isdigit():
                self.conversation_id = str(content["conversation_id"])
            return []
        if kind == "error":
            raise self.error("AGENT_FAILED", "Agent 处理失败，请检查图片理解模型、图片权限或工具配置。")
        if kind in {"tool", "tool-call"}:
            name = event.get("tool_name")
            if name == self.reader_tool:
                args = event.get("tool_arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = None
                urls = args.get("image_urls_list", []) if isinstance(args, dict) else []
                if isinstance(urls, list) and any(self._same_image(url) for url in urls):
                    if not self.vision_observed:
                        self.vision_observed = True
                        return [{"type": "stage", "stage": "vision_reading" if self.reader_tool == "analyze_image" else "ocr_reading"}]
            if name == "evidence_gate" and self.vision_observed and not self.evidence_stage_sent:
                self.evidence_stage_sent = True
                return [{"type": "stage", "stage": "checking_evidence"}]
            return []
        # The local composite workflow has already completed its deterministic
        # gate. Resolve only an exact receipt emitted by this observed tool;
        # never ask the small routing model to regenerate medical values.
        if kind == "execution_logs" and self.reader_tool == "analyze_medical_image" and self.vision_observed:
            try:
                receipt = json.loads(event.get("content", ""))
            except (ValueError, TypeError):
                return []
            if isinstance(receipt, dict) and set(receipt) == {"local_result_id"}:
                return self._finish(receipt, "local-tool-receipt")
        # The root Agent has no sub-agent invocation_id/depth in v2.8.1.
        if event.get("invocation_id") or event.get("depth", 0):
            return []
        key = (event.get("step_id"), event.get("attempt_id"))
        content = event.get("content", "")
        if kind in {"model_output_thinking", "model_output_code"}:
            if isinstance(content, str):
                self.bodies.setdefault(key, []).append(content)
            return []
        if kind != "final_answer":
            return []
        phase = event.get("answer_phase")
        if phase == "delta":
            if not isinstance(content, str):
                raise self.error("AGENT_PROTOCOL_ERROR", "图片结果分段格式错误，请检查 Nexent 版本。")
            self.answers.setdefault(key, []).append(content)
            return []
        if phase not in {None, "complete"}:
            return []
        if not self.vision_observed:
            raise self.error("VISION_TOOL_NOT_CALLED", "Agent 未对本次图片调用配置的识别工具，暂不展示解读。请检查图片工具配置。")
        if not content:
            fragments = self.bodies.get(key, []) if event.get("reclassify_step") else self.answers.get(key, [])
            content = "".join(fragments)
        return self._finish(content, "agent-final-answer")

    def _finish(self, content, source):
        result = self.validate(content)
        transcription = result.get("image_transcription")
        if not isinstance(transcription, dict) or not isinstance(transcription.get("raw_text"), str) or not isinstance(transcription.get("uncertain_fields"), list) or not isinstance(transcription.get("readable"), bool):
            raise self.error("IMAGE_TRANSCRIPT_MISSING", "Agent 没有返回可核对的图片转录文本，请按图片 Agent 提示词配置输出。")
        if result["decision_gate"] == "pass" and (not transcription["readable"] or not transcription["raw_text"].strip() or transcription["uncertain_fields"]):
            raise self.error("IMAGE_REVIEW_REQUIRED", "图片存在未确认读数，不能直接通过，请后端返回人工复核状态。")
        result["metadata"]["image_route"] = "nexent-analyze-image" if self.reader_tool == "analyze_image" else "local-ocr-mcp"
        result["metadata"]["vision_tool_observed"] = self.reader_tool == "analyze_image"
        result["metadata"]["image_tool_observed"] = True
        result["metadata"]["result_source"] = source
        result["metadata"]["nexent_protocol"] = "v2.8.1"
        return [{"type": "result", "result": result}]

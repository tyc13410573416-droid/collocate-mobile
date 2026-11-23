"""Extend the existing medical MCP server with a fully local image workflow."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "phase1", ROOT / "phase1/mcp_server"):
    sys.path.insert(0, str(folder))

from server import mcp
from phase2.local_ocr import analyze_image_bytes, image_from_storage
from phase2.local_image_store import save_result


@mcp.tool
def analyze_medical_image(image_urls_list: list[str], gender: str = "未知", medications: str = "") -> str:
    """Read ONE uploaded S3 lab-report image with free local CPU OCR, then run the
    existing parse_report/reference/evidence_gate workflow. Returns an opaque
    result receipt as a JSON string. Print the receipt, then return it unchanged
    inside <final_answer>...</final_answer> outside code. Do not call final_answer().
    Never guess or substitute the image URL. gender is 男/女/未知, only use supplied sex.
    """
    if len(image_urls_list) != 1 or gender not in {"男", "女", "未知", ""}:
        raise ValueError("请选择一张图片，并提供男、女或未知。")
    content = image_from_storage(image_urls_list[0])
    result = analyze_image_bytes(content, gender or "未知", medications)
    return json.dumps(save_result(image_urls_list[0], result), ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=3001)

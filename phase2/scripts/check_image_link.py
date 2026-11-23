"""Check configuration or explicitly submit an image to the real Nexent Agent."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from phase2.nexent_image_client import NexentImageClient, ImageHandoffError, checked_file, MAX_FILE_BYTES


def main():
    parser = argparse.ArgumentParser(description="MedTrace 图片链路检查（不使用样例回退）")
    parser.add_argument("--image", type=Path, help="指定图片后才会实际调用 Agent/视觉模型")
    parser.add_argument("--gender", choices=["男", "女", "未知"], default="未知")
    parser.add_argument("--expect", action="append", default=[], help="验收读数，例如 GLU=16.1，可重复")
    args = parser.parse_args()
    client = NexentImageClient.from_env()
    try:
        client.check_config()
        if not args.image:
            print("配置格式检查通过（{}）。尚未调用 Nexent，也不代表图片模型可用。".format(client.profile))
            return 0
        with args.image.open("rb") as handle:
            content = handle.read(MAX_FILE_BYTES + 1)
        mime, extension = checked_file(content)
        for event in client.events(content, mime, extension, {"patient_info": {"gender": args.gender}}):
            if event["type"] == "stage":
                print("阶段：" + event["stage"])
            elif event["type"] == "result":
                data = event["result"]
                print("收到门控结果：{} / {}".format(data["decision_gate"], data["evidence_status"]))
                actual = {item.get("abbreviation") or item.get("indicator") or item.get("test_name"): item.get("value") for item in data.get("lab_results", data.get("items", []))}
                for expected in args.expect:
                    name, number = expected.split("=", 1)
                    if name not in actual or actual[name] is None or abs(float(actual[name]) - float(number)) > 1e-6:
                        print("验收未通过：{}，实际读数 {}".format(expected, actual.get(name)))
                        return 1
                print(json.dumps({"readings": actual, "vision_tool_observed": data["metadata"].get("vision_tool_observed", False)}, ensure_ascii=False))
                return 0
        print("未收到完整结果。")
        return 1
    except ImageHandoffError as exc:
        print("{}：{}".format(exc.code, exc))
        return 1
    except (OSError, ValueError):
        print("图片路径或 --expect 参数无效。")
        return 1


if __name__ == "__main__":
    sys.exit(main())

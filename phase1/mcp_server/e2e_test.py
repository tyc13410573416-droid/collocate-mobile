# -*- coding: utf-8 -*-
"""端到端验证 MCP 工具。

安装 fastmcp 后走真实 stdio 协议；在只有 Python 规则环境的机器上，
自动退化为同一进程的工具调用，便于先验收业务逻辑。
"""
import asyncio
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def _direct_check():
    sys.path.insert(0, str(ROOT))
    import server

    print("fastmcp 不可用，执行离线工具链校验")
    tools = ["query_reference", "parse_report", "evidence_gate"]
    print("注册工具:", tools)
    r1 = server.query_reference("肌酐")
    print("\n[query_reference] 肌酐 ->", r1)
    r2 = server.parse_report("谷丙转氨酶 68 U/L，肌酐 88 μmol/L")
    print("\n[parse_report] ->", r2)
    r3 = server.evidence_gate("ALT", 200, gender="male")
    print("\n[evidence_gate] ALT=200 male ->", r3)
    r4 = server.evidence_gate("ALT", 30, gender="")
    print("\n[evidence_gate] ALT=30 缺性别 ->", r4)
    assert r1["found"]
    assert r2["matched_count"] == 2
    assert r3["decision_gate"] == "pass"
    assert r4["decision_gate"] == "review"
    print("\n离线端到端校验通过")


async def _stdio_check():
    from fastmcp import Client

    config = {
        "mcpServers": {
            "medical-report-agent": {
                "command": sys.executable,
                "args": [str(ROOT / "server.py")],
            }
        }
    }
    async with Client(config) as client:
        tools = await client.list_tools()
        print("通过 stdio 连接成功，注册工具:", [t.name for t in tools])

        r1 = await client.call_tool("query_reference", {"indicator": "肌酐"})
        print("\n[query_reference] 肌酐 ->", r1)

        r2 = await client.call_tool("parse_report", {"text": "谷丙转氨酶 68 U/L，肌酐 88 μmol/L"})
        print("\n[parse_report] ->", r2)

        r3 = await client.call_tool("evidence_gate", {"indicator": "ALT", "value": 200, "gender": "male"})
        print("\n[evidence_gate] ALT=200 male ->", r3)

        r4 = await client.call_tool("evidence_gate", {"indicator": "ALT", "value": 30, "gender": ""})
        print("\n[evidence_gate] ALT=30 缺性别 ->", r4)


def main():
    if importlib.util.find_spec("fastmcp") is None:
        _direct_check()
    else:
        asyncio.run(_stdio_check())


if __name__ == "__main__":
    main()

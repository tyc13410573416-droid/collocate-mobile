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
    tools = ["query_reference", "parse_report", "normalize", "check_interaction", "evidence_gate"]
    print("注册工具:", tools)
    r1 = server.query_reference("肌酐")
    print("\n[query_reference] 肌酐 ->", r1)
    r2 = server.parse_report("谷丙转氨酶 68 U/L，肌酐 88 μmol/L")
    print("\n[parse_report] ->", r2)
    r3 = server.evidence_gate("ALT", 200, gender="male")
    print("\n[evidence_gate] ALT=200 male ->", r3)
    r4 = server.evidence_gate("ALT", 30, gender="")
    print("\n[evidence_gate] ALT=30 缺性别 ->", r4)
    r5 = server.normalize("HGB", 11.8, "g/dL", "g/L")
    print("\n[normalize] HGB 11.8 g/dL ->", r5)
    r6 = server.check_interaction(
        [{"drug_name": "阿托伐他汀 10 mg"}],
        [{"abbreviation": "ALT", "status": "high"}],
    )
    print("\n[check_interaction] ->", r6)
    assert r1["found"]
    assert r2["matched_count"] == 2
    assert r3["decision_gate"] == "pass"
    assert r4["decision_gate"] == "review"
    assert r5["status"] == "pass" and r5["value"] == 118.0
    assert r6["status"] == "review" and r6["warnings"]
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

        r5 = await client.call_tool("normalize", {"indicator": "HGB", "value": 11.8, "from_unit": "g/dL", "to_unit": "g/L"})
        print("\n[normalize] ->", r5)

        r6 = await client.call_tool("check_interaction", {
            "medications": [{"drug_name": "阿托伐他汀 10 mg"}],
            "indicators": [{"abbreviation": "ALT", "status": "high"}],
        })
        print("\n[check_interaction] ->", r6)


def main():
    if importlib.util.find_spec("fastmcp") is None:
        _direct_check()
    else:
        asyncio.run(_stdio_check())


if __name__ == "__main__":
    main()

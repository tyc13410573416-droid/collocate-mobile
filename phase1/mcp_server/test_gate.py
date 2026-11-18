# -*- coding: utf-8 -*-
"""验证 v3 门控版三个工具：区间解析、门控三态、parse_report、query_reference。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from range_parser import parse_range, has_gender_specific, range_to_display
from gate_engine import evaluate as gate_evaluate
import server  # noqa: 触发 server 模块加载（构建索引）


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name} {detail}")
    return cond


print("=" * 60)
print("一、区间解析 range_parser")
print("=" * 60)
r1 = parse_range("男 9–50；女 7–40")
check("分性别区间", r1 == {"male": {"low": 9.0, "high": 50.0}, "female": {"low": 7.0, "high": 40.0}}, str(r1))

r2 = parse_range("男 57–97；女 41–73（20–59岁）")
check("带年龄备注", r2["male"]["high"] == 97.0 and r2["female"]["low"] == 41.0, str(r2))

r3 = parse_range("3.9–6.1")
check("无性别区间", r3 == {"default": {"low": 3.9, "high": 6.1}}, str(r3))

r4 = parse_range("<5.2（合适水平）")
check("单侧上限", r4 == {"default": {"low": None, "high": 5.2}}, str(r4))

r5 = parse_range("≥1.0")
check("单侧下限", r5 == {"default": {"low": 1.0, "high": None}}, str(r5))

check("分性别判断", has_gender_specific(r1) is True)
check("不分性别判断", has_gender_specific(r3) is False)
check("还原显示", range_to_display(r1) == "男 9–50；女 7–40", range_to_display(r1))

print()
print("=" * 60)
print("二、门控引擎 gate_engine（三态）")
print("=" * 60)

# 用真实数据构造单来源引用
alt_item = server._load_references()["alt"]
alt_ref = [server._enhance(alt_item)]

# ① pass：分性别指标给了性别，值在区间内
g = gate_evaluate("ALT", 30, gender="male", references=alt_ref)
check("pass 一致通过", g["decision_gate"] == "pass", f"conf={g['confidence']} -> {g['next_action']}")
check("pass 置信度>=0.8", g["confidence"] >= 0.8)

# ② abstain：分性别指标缺性别
g = gate_evaluate("ALT", 30, gender=None, references=alt_ref)
check("review 缺性别追问", g["decision_gate"] == "review", f"conf={g['confidence']} -> {g['next_action']}")
check("缺性别置信度<0.8", g["confidence"] < 0.8)

# ③ abstain：missing（无来源）
g = gate_evaluate("ALT", 30, references=[])
check("abstain 无来源", g["decision_gate"] == "abstain" and g["evidence_status"] == "missing")

# ④ review：合成双来源冲突（ALT 男 9-50 vs 7-40）
conflict_refs = [
    {**alt_ref[0], "source_id": "WS/T 404.1-2012", "source_version": "v1", "effective_date": "2012",
     "gender_range": {"male": {"low": 9, "high": 50}, "female": {"low": 7, "high": 40}}},
    {**alt_ref[0], "source_id": "WS/T 404.1-2024", "source_version": "v2", "effective_date": "2024",
     "gender_range": {"male": {"low": 7, "high": 45}, "female": {"low": 5, "high": 35}}},
]
g = gate_evaluate("ALT", 30, gender="male", references=conflict_refs)
check("review 来源冲突", g["decision_gate"] == "review", f"conflicts={len(g['conflicts'])}")
check("review 有冲突明细", len(g["conflicts"]) >= 1, str(g["conflicts"][:1]))

# ⑤ pass：值超出上限，方向正确
g = gate_evaluate("ALT", 200, gender="male", references=alt_ref)
check("pass 值偏高", g["decision_gate"] == "pass" and "高于" in g["next_action"], g["next_action"])

print()
print("=" * 60)
print("三、parse_report 工具")
print("=" * 60)
res = server.parse_report("谷丙转氨酶 68 U/L，肌酐 88 μmol/L，血清钾 4.0 mmol/L")
check("匹配到 3 项", res["matched_count"] == 3, f"matched={res['matched_count']}")
for it in res["items"]:
    print(f"    {it['indicator']}: value={it['value']} unit={it['unit']} conf={it['confidence']}")
alt = next((i for i in res["items"] if i["indicator"] == "ALT"), None)
check("ALT 数值抽取", alt and alt["value"] == 68.0, str(alt))
image2 = server.parse_report("葡萄糖 16.1 mmol/L；C反应蛋白 16.0 mg/L")
check("图2 葡萄糖/CRP 双指标", image2["matched_count"] == 2, str(image2))
check("图2 数值提取", sorted(item["value"] for item in image2["items"]) == [16.0, 16.1], str(image2["items"]))
check("图2 置信度", all(item["confidence"] >= 0.9 for item in image2["items"]), str(image2["items"]))

print()
print("=" * 60)
print("四、query_reference 工具（新字段）")
print("=" * 60)
q = server.query_reference("ALT")
check("返回 found", q["found"] is True)
check("有 source_id", bool(q.get("source_id")), q.get("source_id"))
check("有 source_version", bool(q.get("source_version")), q.get("source_version"))
check("有 gender_range", "male" in q.get("gender_range", {}), str(q.get("gender_range")))
check("有 effective_date", bool(q.get("effective_date")), q.get("effective_date"))

print()
print("=" * 60)
print("五、evidence_gate 工具（走 MCP 工具入口）")
print("=" * 60)
eg = server.evidence_gate("ALT", 200, "male")
check("工具入口 pass", eg["decision_gate"] == "pass", str(eg))
eg2 = server.evidence_gate("ALT", 200, "")
check("工具入口 review(缺性别)", eg2["decision_gate"] == "review", str(eg2))

print()
print("全部测试执行完毕。")

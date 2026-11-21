"""V2 系统提示词对应的回答安全边界测试。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_engine import analyze_payload


DISCLAIMER = "本结果仅供辅助参考，不构成任何临床诊断或用药建议。医学决策请务必以执业医师意见为准。"


class PromptContractTest(unittest.TestCase):
    def test_pass_has_source_and_disclaimer(self):
        result = analyze_payload({
            "report_id": "V2-ALT-200",
            "raw_text": "患者男，45岁。丙氨酸氨基转移酶（ALT）为 200 U/L，参考范围是 9-50 U/L。",
        })
        self.assertEqual(result["decision_gate"], "pass")
        self.assertIn("[来源1]", result["answer"])
        self.assertEqual(result["disclaimer"], DISCLAIMER)

    def test_review_does_not_output_indicator_conclusion(self):
        result = analyze_payload({
            "report_id": "V2-MISSING-GENDER",
            "raw_text": "丙氨酸氨基转移酶（ALT）为 68 U/L，参考范围是 9-50 U/L。",
        })
        self.assertEqual(result["decision_gate"], "review")
        self.assertTrue(result["answer"].startswith("当前处于安全复核状态"))
        self.assertNotIn("异常指标包括", result["answer"])
        self.assertEqual(result["disclaimer"], DISCLAIMER)

    def test_abstain_stops_when_no_indicator(self):
        result = analyze_payload({"report_id": "V2-EMPTY", "raw_text": "这是一段没有检验指标的文字。"})
        self.assertEqual(result["decision_gate"], "abstain")
        self.assertIn("暂不输出确定性解读", result["answer"])


if __name__ == "__main__":
    unittest.main()

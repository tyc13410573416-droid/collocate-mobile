"""Four UI scenarios must originate from consistent backend gate responses."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "phase1"))
from analysis_engine import analyze_payload

TEXT = "合成数据：患者45岁。丙氨酸氨基转移酶（ALT）为 68 U/L，参考范围是 9-50 U/L。"


class GateFlowTest(unittest.TestCase):
    def test_gender_correction_changes_gate_and_reference(self):
        payload = {"report_id": "R013", "raw_text": TEXT, "patient_info": {"gender": "未知"}}
        first = analyze_payload(payload)
        self.assertEqual((first["decision_gate"], first["evidence_status"]), ("review", "missing_info"))
        payload["patient_info"]["gender"] = "女"
        second = analyze_payload(payload)
        self.assertEqual((second["decision_gate"], second["evidence_status"]), ("pass", "found"))
        self.assertEqual(second["lab_results"][0]["reference_range"], "7-40")

    def test_conflict_survives_gender_correction(self):
        result = analyze_payload({"report_id": "R005", "raw_text": TEXT, "patient_info": {"gender": "男"}})
        self.assertEqual((result["decision_gate"], result["evidence_status"]), ("review", "conflict"))
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertTrue(result["conflicts"][0]["synthetic"])

    def test_low_confidence_is_not_bypassed_by_gender(self):
        result = analyze_payload({"report_id": "TEST", "raw_text": TEXT, "patient_info": {"gender": "男"}, "metadata": {"extraction_confidence": 0.65}})
        self.assertEqual((result["decision_gate"], result["evidence_status"]), ("review", "low_confidence"))

    def test_no_data_is_abstain(self):
        result = analyze_payload({"report_id": "R006", "raw_text": "非检验报告，没有数值"})
        self.assertEqual((result["decision_gate"], result["evidence_status"]), ("abstain", "missing"))

    def test_old_report_id_cannot_supply_another_reports_values(self):
        result = analyze_payload({"report_id": "R001", "raw_text": "这是一份新的未知报告，没有数值"})
        self.assertEqual(result["decision_gate"], "abstain")
        self.assertEqual(result["lab_results"], [])


if __name__ == "__main__":
    unittest.main()

"""No OCR fixture replay: test table geometry and immutable result binding."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from phase2.local_image_store import save_result, load_result, TTL_SECONDS
from phase2.local_ocr import align_readings
from phase2.local_result import build_result, patient_fields
from phase2.nexent_image_client import ImageHandoffError, validated_gate
from phase2.nexent_vision import VisionStream, image_query


def box(text, x, y, score=0.99):
    return ([[x-12,y-5],[x+12,y-5],[x+12,y+5],[x-12,y+5]], text, score)


class TableServer:
    @staticmethod
    def _build_candidates():
        return [(name, {"key": name, "name_en": name}) for name in ["ALT", "AST", "UA", "Cr"]]


class TableGeometryTest(unittest.TestCase):
    def test_reference_lower_bound_is_never_used_as_result(self):
        lines=[box("结果",200,10),box("Cr",50,50),box("63",200,52),box("44",340,50),box("μmol/L",240,52)]
        rows, uncertain=align_readings(lines,TableServer)
        self.assertEqual(rows[0]["value"],63.0)
        self.assertFalse(uncertain)

    def test_next_row_does_not_borrow_previous_result(self):
        lines=[box("结果",200,10),box("Cr",50,50),box("63",200,52),box("μmol/L",240,52),box("UA",50,62)]
        rows, uncertain=align_readings(lines,TableServer)
        self.assertEqual([r["indicator"] for r in rows],["Cr"])
        self.assertTrue(any("UA" in note for note in uncertain))

    def test_low_score_and_inequality_require_review(self):
        rows, uncertain=align_readings([box("结果",200,10),box("ALT",50,50),box(">200",200,50,.7),box("U/L",240,50)],TableServer)
        self.assertEqual(rows[0]["value_comparator"],">")
        self.assertTrue(uncertain)

    def test_two_table_result_columns_are_separate(self):
        rows, _=align_readings([box("结果",200,10),box("结果",600,10),box("ALT",50,50),box("AST",450,50),box("68",200,50),box("35",600,50),box("U/L",240,50),box("U/L",640,50)],TableServer)
        self.assertEqual({r["indicator"]:r["value"] for r in rows},{"ALT":68.,"AST":35.})


class LocalStoreTest(unittest.TestCase):
    def test_receipt_is_bound_to_exact_uploaded_image_and_expires(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{"NEXENT_LOCAL_RESULT_DIR":temp}):
            receipt=save_result("s3://real/a.png",{"answer":"original 16.1"})
            self.assertEqual(load_result(receipt,{"url":"s3://real/a.png"})["answer"],"original 16.1")
            with self.assertRaises(ValueError):load_result(receipt,{"url":"s3://other/a.png"})
            with self.assertRaises(ValueError):load_result({"local_result_id":"../anything"},{"url":"s3://real/a.png"})
            target=Path(temp)/(receipt["local_result_id"]+".json")
            os.utime(str(target),(time.time()-TTL_SECONDS-10,)*2)
            with self.assertRaises(ValueError):load_result(receipt,{"url":"s3://real/a.png"})

    def test_only_observed_local_tool_receipt_can_finish(self):
        attachment={"url":"s3://real/a.png","object_name":"a.png"}
        data={"decision_gate":"review","image_transcription":{"raw_text":"read from image","readable":True,"uncertain_fields":["unit"]},"metadata":{}}
        stream=VisionStream(attachment,lambda _receipt:copy.deepcopy(data),ImageHandoffError,"analyze_medical_image")
        receipt={"type":"execution_logs","content":json.dumps({"local_result_id":"a"*32})}
        self.assertEqual(stream.consume(receipt),[])
        stream.consume({"type":"tool","tool_name":"analyze_medical_image","tool_arguments":{"image_urls_list":["s3://real/a.png"]}})
        result=stream.consume(receipt)[0]["result"]
        self.assertEqual(result["metadata"]["result_source"],"local-tool-receipt")
        self.assertFalse(result["metadata"]["vision_tool_observed"])
        self.assertTrue(result["metadata"]["image_tool_observed"])

    def test_small_model_routes_supplied_gender_and_never_copies_full_result(self):
        query=image_query({"url":"s3://real/a.png"},{"patient_info":{"gender":"女"},"medications":"A"},"analyze_medical_image")
        self.assertIn('gender="女"',query)
        self.assertIn("print(receipt)",query)
        self.assertIn("<code>",query)


class ActualRuleFormattingTest(unittest.TestCase):
    def test_patient_sex_never_comes_from_reference_population(self):
        self.assertEqual(patient_fields("参考范围 男 9–50，女 7–40", "未知")["gender"],"未知")
        self.assertEqual(patient_fields("gender: female", "未知")["gender"],"女")
        self.assertEqual(patient_fields("性别：女 年龄：45岁", "未知"),{"gender":"女","age":45})
        self.assertEqual(patient_fields("性别：女", "男")["gender"],"男")

    def run_reading(self,indicator,value,unit,gender="男",raw=""):
        import server
        row={"indicator":indicator,"test_name":indicator,"value":value,"unit":unit,"score":.99,"value_comparator":""}
        return build_result([row],{"raw_text":raw,"readable":True,"uncertain_fields":[]},gender,"",server)

    def test_evidence_pass_does_not_mean_normal_lab_value(self):
        data=self.run_reading("ALT",200.,"U/L")
        self.assertEqual(data["decision_gate"],"pass")
        self.assertEqual(data["lab_results"][0]["status"],"high")
        self.assertTrue(data["citations"])
        self.assertNotIn("retrieval",data)

    def test_missing_sex_stays_review(self):
        data=self.run_reading("ALT",68.,"U/L",gender="未知")
        self.assertEqual(data["decision_gate"],"review")
        self.assertEqual(data["clarification"]["field"],"gender")

    def test_missing_fasting_condition_is_not_a_sex_question(self):
        data=self.run_reading("GLU",16.1,"mmol/L")
        self.assertEqual(data["decision_gate"],"review")
        self.assertEqual(data["clarification"]["field"],"report_conditions")

    def test_unconverted_unit_stays_review(self):
        data=self.run_reading("ALT",68.,"IU/L")
        self.assertEqual(data["decision_gate"],"review")
        self.assertEqual(data["evidence_status"],"low_confidence")


if __name__=="__main__":unittest.main()

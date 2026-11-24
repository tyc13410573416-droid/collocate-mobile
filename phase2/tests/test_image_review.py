"""Human review must preserve originals and re-run actual evidence rules."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from phase1.app import app, _get_mcp_server
from phase2.image_review import review_image
from phase2.local_image_store import save_result, load_result, load_record, TTL_SECONDS
from phase2.local_result import build_result
from phase2.nexent_image_client import ImageHandoffError


class ImageReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ,{"NEXENT_LOCAL_RESULT_DIR":self.temp.name,"IMAGE_ALLOWED_ORIGINS":"https://tyc13410573416-droid.github.io"})
        env.start();self.addCleanup(env.stop)
        self.server=_get_mcp_server()
        rows=[{"indicator":"ALT","test_name":"丙氨酸氨基转移酶","value":68.,"unit":"U/L","score":.65,"value_comparator":""},
              {"indicator":"AST","test_name":"天门冬氨酸氨基转移酶","value":35.,"unit":"U/L","score":.99,"value_comparator":""}]
        transcript={"raw_text":"性别未提供。ALT 68 U/L；AST 35 U/L。","readable":True,"uncertain_fields":["ALT 小数点需要核对。"]}
        result=build_result(rows,transcript,"未知","",self.server)
        result["image_transcription"]=transcript
        self.original=copy.deepcopy(result)
        self.receipt=save_result("s3://nexent/attachments/original.png",result)
        self.payload={"review_token":self.receipt["local_result_id"],"scope_confirmed":True,"gender":"男","report_conditions":"unknown",
                      "lab_results":[{"abbreviation":"ALT","value":68.,"unit":"IU/L","confirmed":True}]}

    def run_review(self,payload=None):return review_image(payload or self.payload,self.server)

    def test_selected_confirmed_fields_re_run_rules_and_preserve_original_ocr(self):
        data=self.run_review()
        self.assertEqual(data["decision_gate"],"pass")
        self.assertEqual(data["lab_results"][0]["status"],"high")
        self.assertEqual(data["lab_results"][0]["unit"],"U/L")
        self.assertEqual(data["review_summary"]["excluded_indicators"],["AST"])
        self.assertEqual([row["abbreviation"] for row in data["review_candidates"]],["ALT","AST"])
        self.assertEqual(data["image_transcription"]["raw_text"],self.original["image_transcription"]["raw_text"])
        self.assertEqual(data["image_transcription"]["uncertain_fields"],self.original["image_transcription"]["uncertain_fields"])
        self.assertIsNone(data["metadata"]["extraction_confidence"])
        self.assertEqual(data["metadata"]["original_ocr_score"],.65)
        self.assertTrue(any(step["tool"]=="human_review" for step in data["trace_log"]))
        self.assertTrue(any(step["tool"]=="evidence_gate" for step in data["trace_log"]))
        self.assertEqual(load_record(self.receipt["local_result_id"])["result"],self.original)

    def test_low_confidence_is_not_a_shortcut_around_missing_gender(self):
        self.payload["gender"]="未知"
        data=self.run_review()
        self.assertEqual(data["decision_gate"],"review")
        self.assertEqual(data["clarification"]["field"],"gender")

    def test_changed_numeric_value_is_reevaluated_and_audited(self):
        self.payload["lab_results"][0]["value"]=80.5
        data=self.run_review()
        self.assertEqual(data["lab_results"][0]["value"],80.5)
        self.assertEqual(data["review_summary"]["changes"][0]["before"]["value"],68.)
        self.assertEqual(data["review_summary"]["changes"][0]["submitted"]["value"],80.5)

    def test_frontend_cannot_force_pass_or_supply_its_own_citation(self):
        self.payload.update(decision_gate="pass",source_versions=[{"source_id":"MADE-UP"}])
        self.payload["lab_results"][0]["unit"]="bananas/L"
        data=self.run_review()
        self.assertEqual(data["decision_gate"],"review")
        self.assertNotIn("MADE-UP",json.dumps(data))

    def test_conflicting_evidence_stays_review_after_human_confirmation(self):
        conflict={"decision_gate":"review","confidence":.95,"evidence_status":"conflict","conflicts":[{"field":"reference_range","detail":"source mismatch"}],"next_action":"请核对依据","source_versions":[]}
        with patch.object(self.server,"evidence_gate",return_value=conflict):data=self.run_review()
        self.assertEqual(data["decision_gate"],"review")
        self.assertEqual(data["evidence_status"],"conflict")

    def test_no_new_unconfirmed_or_duplicate_indicators(self):
        for change in [{"abbreviation":"UNKNOWN"},{"confirmed":False},{"value":True},{"value":-1},{"value":float('nan')},{"value":None},{"unit":""}]:
            payload=copy.deepcopy(self.payload);payload["lab_results"][0].update(change)
            with self.assertRaises(ImageHandoffError):self.run_review(payload)
        payload=copy.deepcopy(self.payload);payload["lab_results"]*=2
        with self.assertRaises(ImageHandoffError):self.run_review(payload)
        payload=copy.deepcopy(self.payload);payload["scope_confirmed"]=False
        with self.assertRaises(ImageHandoffError):self.run_review(payload)

    def test_inequality_cannot_be_converted_to_an_exact_reading(self):
        self.payload["lab_results"][0]["value_comparator"]="<"
        self.assertEqual(self.run_review()["decision_gate"],"review")

    def test_expired_receipt_and_path_traversal_rejected(self):
        path=Path(self.temp.name)/(self.receipt["local_result_id"]+".json")
        os.utime(str(path),(time.time()-TTL_SECONDS-5,)*2)
        with self.assertRaises(ImageHandoffError) as context:self.run_review()
        self.assertEqual(context.exception.status,410)
        self.payload["review_token"]="../../private"
        with self.assertRaises(ImageHandoffError):self.run_review()

    def test_source_is_linked_to_each_indicator_not_just_first_standard(self):
        data=load_result(self.receipt,{"url":"s3://nexent/attachments/original.png"})
        self.assertEqual(len(data["citations"]),2)
        self.assertNotEqual(data["lab_results"][0]["citation_ids"],data["lab_results"][1]["citation_ids"])
        self.assertEqual(data["citations"][1]["indicator"],"AST")
        self.assertFalse(data["citations"][1]["original_text_available"])

    def test_http_endpoint_and_preflight_allow_only_authorized_origin(self):
        client=app.test_client()
        response=client.options('/api/review-image',headers={"Origin":"https://tyc13410573416-droid.github.io"})
        self.assertEqual(response.status_code,204)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'],'https://tyc13410573416-droid.github.io')
        self.assertEqual(client.post('/api/review-image',json=self.payload,headers={"Origin":"https://unrelated.invalid"}).status_code,403)
        response=client.post('/api/review-image',json=self.payload)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()["decision_gate"],"pass")


if __name__=='__main__':unittest.main()

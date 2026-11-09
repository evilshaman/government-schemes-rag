"""
Automated Test Suite for Phase 4: Full-Stack App & Matching API (FastAPI + Dashboard).
Validates:
1. System Health Check (/health).
2. Knowledge Base Stats API (/api/stats).
3. Scheme Browsing, Filtering & Details APIs (/api/schemes, /api/schemes/{id}).
4. Sample Profiles Loading API (/api/sample-profiles, /api/sample-profile/{id}).
5. Document Upload & Extraction API (/api/upload-document).
6. End-to-End Deliberation & Gap Analysis API (/api/schemes/deliberate).
7. Markdown Export API (/api/schemes/export-markdown).
8. Policy Copilot Chat API (/api/chat).
9. Static Dashboard Serving (GET /).
"""

from __future__ import annotations
import os
import sys
import unittest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.main import app
from schemas.business_profile import BusinessProfile


class TestPhase4API(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    # 1. Health Check
    def test_health_check(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertGreaterEqual(data["knowledge_base"]["total_schemes"], 30)

    # 2. Stats Endpoint
    def test_stats_endpoint(self):
        res = self.client.get("/api/stats")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_schemes", data)
        self.assertIn("benefit_type_breakdown", data)
        self.assertGreaterEqual(data["total_schemes"], 30)

    # 3. Scheme Browsing & Filtering
    def test_list_schemes_and_filter(self):
        # List all
        res = self.client.get("/api/schemes?limit=50")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total_count"], 30)
        self.assertGreaterEqual(len(data["schemes"]), 1)

        # Keyword Search
        res_search = self.client.get("/api/schemes?search=ZED")
        self.assertEqual(res_search.status_code, 200)
        search_data = res_search.json()
        self.assertGreaterEqual(search_data["total_count"], 1)
        self.assertTrue(any("zed" in s["scheme_short_code"].lower() for s in search_data["schemes"]))

    # 4. Scheme Details & Document Chunks
    def test_scheme_details(self):
        res = self.client.get("/api/schemes/pmegp")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["scheme"]["scheme_id"], "pmegp")
        self.assertIn("KVIC", data["scheme"]["implementing_agency"])
        self.assertIsInstance(data["guideline_chunks"], list)

    # 5. Sample Profiles
    def test_sample_profiles(self):
        res_list = self.client.get("/api/sample-profiles")
        self.assertEqual(res_list.status_code, 200)
        samples = res_list.json()
        self.assertGreaterEqual(len(samples), 3)

        # Fetch Sample 1
        res_s1 = self.client.post("/api/sample-profile/1")
        self.assertEqual(res_s1.status_code, 200)
        p1 = res_s1.json()
        self.assertEqual(p1["constitution"], "Private Limited Company")
        self.assertEqual(p1["principal_address"]["state_name"], "Maharashtra")
        self.assertTrue(p1["is_woman_owned"])
        self.assertTrue(p1["is_dpiit_recognized"])

    # 6. Document Upload & Extraction
    def test_upload_document(self):
        raw_gst_text = (
            "Government of India\nForm GST REG-06\nRegistration Number: 27AABCS1234D1Z8\n"
            "1. Legal Name: GREENLIGHT AGRO PRODUCTS PVT LTD\n"
            "3. Constitution of Business: Private Limited Company\n"
            "4. Address: Hinjewadi, Pune, Maharashtra, 411057\n"
            "Nature of Activities: Manufacturing"
        )
        files = {"file": ("test_gst_cert.txt", raw_gst_text.encode("utf-8"), "text/plain")}
        res = self.client.post("/api/upload-document", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        profile = data["profile"]
        self.assertEqual(profile["legal_name"], "GREENLIGHT AGRO PRODUCTS PVT LTD")
        self.assertEqual(profile["principal_address"]["state_name"], "Maharashtra")

    # 7. End-to-End Deliberation & Gap Analysis
    def test_deliberate_endpoint(self):
        # Fetch sample profile
        sample_res = self.client.post("/api/sample-profile/1")
        profile = sample_res.json()

        payload = {
            "profile": profile,
            "top_k": 3,
            "apply_hard_filters": True,
        }
        res = self.client.post("/api/schemes/deliberate", json=payload)
        self.assertEqual(res.status_code, 200)
        report = res.json()
        self.assertEqual(report["business_legal_name"], profile["legal_name"])
        self.assertGreaterEqual(report["top_candidates_evaluated"], 1)
        self.assertGreaterEqual(len(report["top_recommendations"]), 1)

        # Verify Document Gap Checklist is present
        top_rec = report["top_recommendations"][0]
        self.assertIn("financial_benefit", top_rec)
        self.assertIn("document_checklist", top_rec)
        self.assertGreaterEqual(len(top_rec["document_checklist"]), 1)

    # 8. Markdown Export
    def test_export_markdown(self):
        sample_res = self.client.post("/api/sample-profile/1")
        profile = sample_res.json()
        delib_res = self.client.post("/api/schemes/deliberate", json={"profile": profile, "top_k": 2})
        report = delib_res.json()

        res_export = self.client.post("/api/schemes/export-markdown", json=report)
        self.assertEqual(res_export.status_code, 200)
        data = res_export.json()
        self.assertTrue(data["file_name"].endswith(".md"))
        self.assertIn("# Government Schemes Eligibility & Document Gap Analysis Report", data["markdown_content"])

    # 9. Policy Copilot Chat
    def test_chat_copilot(self):
        payload = {
            "message": "What is the margin money subsidy under PMEGP?",
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("reply", data)
        self.assertGreaterEqual(len(data["cited_schemes"]), 1)
        self.assertIn("pmegp", [c["scheme_id"] for c in data["cited_schemes"]])

    def test_chat_copilot_out_of_domain_guardrail(self):
        payload = {
            "message": "write a hello world code in c",
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("reply", data)
        self.assertEqual(len(data["cited_schemes"]), 0)
        self.assertIn("specialized exclusively in Indian government subsidies", data["reply"])

    # 10. Serve Dashboard
    def test_dashboard_serving(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Government Schemes Discovery & RAG Platform", res.text)


if __name__ == "__main__":
    unittest.main()

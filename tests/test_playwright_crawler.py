"""
Unit tests for Playwright Application Process Crawler.
Verifies fixture integrity, schema normalization, and application step extraction.
"""

from __future__ import annotations
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawlers.playwright_application_crawler import (
    PlaywrightApplicationCrawler,
    SchemeApplicationProcessRecord,
)
from schemas.government_scheme import GovernmentScheme


class TestPlaywrightApplicationCrawler(unittest.TestCase):
    def setUp(self):
        self.crawler = PlaywrightApplicationCrawler(headless=True, offline_mode=True)

    def test_curated_fixtures_exist(self):
        fixtures = self.crawler.get_curated_application_fixtures()
        self.assertGreaterEqual(len(fixtures), 30)
        self.assertIn("pmegp", fixtures)
        self.assertIn("cgtmse", fixtures)
        self.assertIn("mudra-shishu", fixtures)
        self.assertIn("pm-vishwakarma", fixtures)

    def test_fixture_steps_and_urls(self):
        fixtures = self.crawler.get_curated_application_fixtures()
        for s_id, record in fixtures.items():
            self.assertTrue(len(record.steps) >= 3, f"Scheme '{s_id}' has fewer than 3 steps")
            self.assertTrue(record.application_portal_url.startswith("http"), f"Scheme '{s_id}' invalid URL")
            self.assertTrue(len(record.markdown_guide) > 20, f"Scheme '{s_id}' markdown guide empty")

    def test_offline_crawl_all(self):
        results = self.crawler.crawl_all(scheme_ids=["pmegp", "cgtmse"])
        self.assertEqual(len(results), 2)
        pmegp_rec = results["pmegp"]
        self.assertIn("pmegp", pmegp_rec.scheme_id)
        self.assertTrue(any("Apply Online" in step or "KVIC" in step for step in pmegp_rec.steps))

    def test_ast_text_extractor(self):
        ast_mock = {
            "type": "paragraph",
            "children": [
                {"text": "Step 1: "},
                {"bold": True, "text": "Visit Portal "},
                {
                    "type": "link",
                    "children": [{"text": "https://example.gov.in"}],
                },
            ],
        }
        extracted = self.crawler._extract_ast_text(ast_mock)
        self.assertEqual(extracted, "Step 1: Visit Portal https://example.gov.in")


if __name__ == "__main__":
    unittest.main()

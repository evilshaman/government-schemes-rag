"""
Automated Test Suite for Phase 2: Crawler Pipeline & Hybrid Knowledge Base.
Validates crawlers, schema normalizer, PDF guidelines parser, SQLite storage, and Vector Store.
"""

from __future__ import annotations
import os
import sys
import unittest
import tempfile
import shutil

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from schemas.government_scheme import GovernmentScheme, SchemeJurisdiction, BenefitType
from crawlers.base import CrawledSchemeRecord
from crawlers.msme_crawler import MSMECrawler
from crawlers.startup_india_crawler import StartupIndiaCrawler
from crawlers.jansamarth_crawler import JanSamarthCrawler
from crawlers.myscheme_crawler import MySchemeCrawler
from parsers.pdf_guidelines_parser import PDFGuidelinesParser
from knowledge_base.normalizer import SchemeNormalizer
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore


class TestPhase2Pipeline(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_schemes.db")
        self.vector_index_path = os.path.join(self.temp_dir, "test_vector_index.json")
        self.store = SchemeKnowledgeStore(db_path=self.db_path)
        self.vector_store = SchemeVectorStore(index_file_path=self.vector_index_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # 1. CRAWLER TESTS
    # -------------------------------------------------------------
    def test_msme_crawler_offline_fixture(self):
        crawler = MSMECrawler(offline_mode=True)
        results = crawler.crawl()
        self.assertGreaterEqual(len(results), 4)
        zed = next((r for r in results if "zed" in r.raw_title.lower()), None)
        self.assertIsNotNone(zed)
        self.assertEqual(zed.source_portal, "msme.gov.in")
        self.assertIn("Manufacturing", zed.raw_tags)
        self.assertGreater(len(zed.raw_eligibility), 0)

    def test_startup_india_crawler_offline_fixture(self):
        crawler = StartupIndiaCrawler(offline_mode=True)
        results = crawler.crawl()
        self.assertGreaterEqual(len(results), 4)
        sisfs = next((r for r in results if "seed fund" in r.raw_title.lower()), None)
        self.assertIsNotNone(sisfs)
        self.assertEqual(sisfs.raw_short_name, "SISFS")
        self.assertIn("DPIIT", sisfs.raw_tags)

    def test_jansamarth_crawler_offline_fixture(self):
        crawler = JanSamarthCrawler(offline_mode=True)
        results = crawler.crawl()
        self.assertGreaterEqual(len(results), 4)
        cgtmse = next((r for r in results if "cgtmse" in (r.raw_short_name or "").lower()), None)
        self.assertIsNotNone(cgtmse)
        self.assertEqual(cgtmse.raw_benefits.get("type"), "Credit Guarantee")

    def test_myscheme_crawler_offline_fixture(self):
        crawler = MySchemeCrawler(offline_mode=True)
        results = crawler.crawl()
        self.assertGreaterEqual(len(results), 3)
        cmegp = next((r for r in results if "cmegp" in (r.raw_short_name or "").lower()), None)
        self.assertIsNotNone(cmegp)
        self.assertIn("Maharashtra", cmegp.raw_tags)

    # -------------------------------------------------------------
    # 2. SCHEMA NORMALIZER & DEDUPLICATION TESTS
    # -------------------------------------------------------------
    def test_scheme_normalizer_conversion(self):
        raw = CrawledSchemeRecord(
            source_portal="msme.gov.in",
            source_url="https://zed.msme.gov.in",
            raw_title="MSME Sustainable ZED Certification Scheme",
            raw_short_name="ZED",
            raw_summary="Assistance on certification fees for Zero Defect Zero Effect manufacturing.",
            raw_ministry="Ministry of MSME",
            raw_agency="QCI",
            raw_eligibility=["Micro, Small, Medium manufacturing enterprises with Udyam."],
            raw_benefits={
                "type": "Fee / Cost Reimbursement",
                "subsidy_percentage": 80.0,
                "max_amount_inr": 500000.0,
                "description": "Up to 80% fee reimbursement."
            },
            raw_documents=["Udyam Certificate", "GSTIN"],
            raw_guidelines_url="https://zed.msme.gov.in/guidelines.pdf",
            raw_application_mode="Online",
            raw_tags=["Manufacturing", "ZED", "Quality"],
        )

        scheme = SchemeNormalizer.normalize_record(raw)
        self.assertIsInstance(scheme, GovernmentScheme)
        self.assertEqual(scheme.scheme_short_code, "ZED")
        self.assertTrue(scheme.rules.requires_manufacturing)
        self.assertEqual(scheme.benefits.subsidy_percentage, 80.0)
        self.assertEqual(scheme.benefits.max_assistance_amount_inr, 500000.0)

    def test_deduplicate_and_merge(self):
        crawler = MSMECrawler(offline_mode=True)
        records = crawler.crawl()
        schemes = [SchemeNormalizer.normalize_record(r) for r in records]

        # Duplicate one scheme with extra tag
        dup = schemes[0].model_copy(deep=True)
        dup.tags.append("NewUniqueTag")

        merged = SchemeNormalizer.deduplicate_and_merge(schemes, [dup])
        self.assertEqual(len(merged), len(schemes))
        matched = next(s for s in merged if s.scheme_id == dup.scheme_id)
        self.assertIn("NewUniqueTag", matched.tags)

    # -------------------------------------------------------------
    # 3. PDF GUIDELINES PARSER TEST
    # -------------------------------------------------------------
    def test_pdf_guidelines_parser(self):
        pdf_path = os.path.join(PROJECT_ROOT, "samples", "guidelines", "pmegp_guidelines.pdf")
        self.assertTrue(os.path.exists(pdf_path), f"Sample PDF not found at {pdf_path}")

        parser = PDFGuidelinesParser(chunk_size=300)
        parsed = parser.parse_file(pdf_path, scheme_id="pmegp")

        self.assertGreaterEqual(parsed.total_pages, 1)
        self.assertGreater(len(parsed.eligibility_points), 0)
        self.assertGreater(len(parsed.financial_benefits_text), 0)
        self.assertEqual(parsed.subsidy_percentage, 35.0)
        self.assertGreater(len(parsed.required_documents), 0)
        self.assertGreater(len(parsed.chunks), 0)

    # -------------------------------------------------------------
    # 4. KNOWLEDGE STORE SQLITE PERSISTENCE TESTS
    # -------------------------------------------------------------
    def test_sqlite_storage_crud_and_stats(self):
        crawler = MSMECrawler(offline_mode=True)
        records = crawler.crawl()
        schemes = [SchemeNormalizer.normalize_record(r) for r in records]

        for s in schemes:
            self.store.save_scheme(s)

        # Retrieve single scheme
        retrieved = self.store.get_scheme("zed")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.scheme_short_code, "ZED")

        # List schemes
        all_schemes = self.store.list_schemes()
        self.assertEqual(len(all_schemes), len(schemes))

        # Audit log
        crawl_id = self.store.log_crawl_run(
            source_portal="msme.gov.in",
            schemes_found=len(records),
            schemes_saved=len(schemes),
            status="SUCCESS"
        )
        self.assertGreater(crawl_id, 0)

        # Statistics
        stats = self.store.get_statistics()
        self.assertEqual(stats["total_schemes"], len(schemes))
        self.assertEqual(stats["total_crawls_logged"], 1)

    # -------------------------------------------------------------
    # 5. VECTOR STORE INDEXING & HYBRID RETRIEVAL TEST
    # -------------------------------------------------------------
    def test_hybrid_vector_retrieval(self):
        # Prepare schemes across sectors
        c_msme = MSMECrawler(offline_mode=True)
        c_start = StartupIndiaCrawler(offline_mode=True)
        c_jan = JanSamarthCrawler(offline_mode=True)
        c_my = MySchemeCrawler(offline_mode=True)

        all_records = c_msme.crawl() + c_start.crawl() + c_jan.crawl() + c_my.crawl()
        schemes = [SchemeNormalizer.normalize_record(r) for r in all_records]

        for s in schemes:
            self.store.save_scheme(s)

        # Build Vector Store
        count = self.vector_store.build_index(schemes)
        self.assertGreater(count, 0)
        self.assertTrue(os.path.exists(self.vector_index_path))

        # Query 1: Startup seed funding
        results = self.vector_store.hybrid_search(
            query="early stage proof of concept prototype seed funding grant",
            top_k=3
        )
        self.assertGreater(len(results), 0)
        top_slugs = [r.scheme_id for r in results]
        self.assertIn("sisfs", top_slugs)

        # Query 2: Collateral-free credit guarantee
        results_credit = self.vector_store.hybrid_search(
            query="collateral free bank credit guarantee working capital",
            top_k=3
        )
        self.assertGreater(len(results_credit), 0)
        self.assertIn("cgtmse", [r.scheme_id for r in results_credit])

        # Query 3: State-specific filter (Maharashtra)
        results_state = self.vector_store.hybrid_search(
            query="employment generation margin money subsidy",
            state="Maharashtra",
            top_k=5
        )
        self.assertGreater(len(results_state), 0)
        self.assertTrue(any("cmegp" in r.scheme_id for r in results_state))


if __name__ == "__main__":
    unittest.main()

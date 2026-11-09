"""
Automated Test Suite for Phase 3: Hybrid Retrieval & LLM Reasoner Engine.
Validates:
1. Phase 3 Pydantic Schemas (DocumentGapItem, Citations, Assessments, FullReasoningReport).
2. Hybrid Retriever with Reciprocal Rank Fusion (RRF).
3. Cross-Encoder Contextual Reranker and factor breakdowns.
4. Document Gap Analysis against official regulatory registry.
5. Financial Benefit Quantum calculations for diverse schemes (PMEGP, ZED, SISFS).
6. Official circular citation extraction.
7. End-to-end Phase 3 Reasoner Pipeline execution and Markdown rendering.
"""

from __future__ import annotations
import os
import sys
import unittest
import tempfile
import shutil
from datetime import date

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from schemas.business_profile import (
    BusinessProfile,
    BusinessAddress,
    ConstitutionType,
    MSMETier,
    SocialCategory,
    TurnoverBracket,
)
from schemas.government_scheme import (
    GovernmentScheme,
    FinancialBenefit,
    BenefitType,
    SchemeJurisdiction,
    EligibilityRuleCondition,
)
from schemas.reasoner_schema import (
    DocumentGapItem,
    ClauseCitation,
    FinancialBenefitCalculation,
    SchemeEligibilityAssessment,
    FullReasoningReport,
)
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore
from parsers.pdf_guidelines_parser import SchemeDocumentChunk
from engine.retriever import HybridRetriever, RetrievedSchemeCandidate
from engine.reranker import CrossEncoderReranker, RerankedSchemeCandidate
from engine.reasoner import LLMEligibilityReasoner, DOCUMENT_REGULATORY_REGISTRY
from engine.pipeline_phase3 import Phase3ReasonerPipeline


class TestPhase3ReasonerEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_schemes.db")
        self.vector_index_path = os.path.join(self.temp_dir, "test_vector_index.json")

        self.store = SchemeKnowledgeStore(db_path=self.db_path)
        self.vector_store = SchemeVectorStore(index_file_path=self.vector_index_path)

        # Create test schemes
        self.scheme_zed = GovernmentScheme(
            scheme_id="zed",
            scheme_name="MSME Sustainable (ZED) Certification Scheme",
            scheme_short_code="ZED",
            nodal_ministry="Ministry of Micro, Small and Medium Enterprises",
            implementing_agency="Quality Council of India (QCI)",
            jurisdiction=SchemeJurisdiction.CENTRAL,
            summary="80% financial subsidy on assessment fees to adopt Zero Defect Zero Effect manufacturing.",
            rules=EligibilityRuleCondition(
                applicable_states=["ALL"],
                eligible_msme_tiers=[MSMETier.MICRO, MSMETier.SMALL, MSMETier.MEDIUM],
                requires_manufacturing=True,
            ),
            benefits=FinancialBenefit(
                benefit_type=BenefitType.REIMBURSEMENT,
                quantum_description="80% fee subsidy up to Rs 5 Lakh for Micro units.",
                subsidy_percentage=80.0,
                max_assistance_amount_inr=500000.0,
            ),
            required_documents=["Udyam Registration", "Factory License"],
            official_portal_url="https://zed.msme.gov.in",
            tags=["zed", "manufacturing", "quality", "clean energy"],
        )

        self.scheme_pmegp = GovernmentScheme(
            scheme_id="pmegp",
            scheme_name="Prime Minister Employment Generation Programme",
            scheme_short_code="PMEGP",
            nodal_ministry="Ministry of Micro, Small and Medium Enterprises",
            implementing_agency="KVIC",
            jurisdiction=SchemeJurisdiction.CENTRAL,
            summary="Credit-linked subsidy program providing 15% to 35% margin money for micro-enterprises.",
            rules=EligibilityRuleCondition(
                applicable_states=["ALL"],
                eligible_constitutions=[
                    ConstitutionType.PROPRIETORSHIP,
                    ConstitutionType.PARTNERSHIP,
                    ConstitutionType.SOCIETY_TRUST,
                ],
                eligible_msme_tiers=[MSMETier.MICRO],
            ),
            benefits=FinancialBenefit(
                benefit_type=BenefitType.CAPITAL_SUBSIDY,
                quantum_description="15% to 35% margin money subsidy on project cost up to Rs 50 Lakh.",
                subsidy_percentage=35.0,
                max_assistance_amount_inr=1750000.0,
            ),
            required_documents=["Aadhaar", "DPR", "Class 8th Certificate", "Caste Certificate"],
            official_portal_url="https://www.kviconline.gov.in/pmegpeportal/",
            tags=["pmegp", "subsidy", "margin money", "credit", "employment"],
        )

        self.scheme_sisfs = GovernmentScheme(
            scheme_id="sisfs",
            scheme_name="Startup India Seed Fund Scheme",
            scheme_short_code="SISFS",
            nodal_ministry="Ministry of Commerce and Industry",
            implementing_agency="DPIIT",
            jurisdiction=SchemeJurisdiction.CENTRAL,
            summary="Financial assistance up to Rs 50 Lakh for proof of concept and commercialization.",
            rules=EligibilityRuleCondition(
                applicable_states=["ALL"],
                eligible_constitutions=[ConstitutionType.PRIVATE_LIMITED, ConstitutionType.LLP],
                requires_dpiit_recognition=True,
                max_business_age_years=2.0,
            ),
            benefits=FinancialBenefit(
                benefit_type=BenefitType.GRANT_EQUITY,
                quantum_description="Grant up to Rs 20 Lakh for PoC, prototype development.",
                subsidy_percentage=100.0,
                max_assistance_amount_inr=5000000.0,
            ),
            required_documents=["DPIIT Recognition Certificate", "Pitch Deck"],
            official_portal_url="https://seedfund.startupindia.gov.in/",
            tags=["startup", "seed fund", "dpiit", "prototype", "innovation"],
        )

        # Save schemes to test DB
        self.store.save_scheme(self.scheme_zed)
        self.store.save_scheme(self.scheme_pmegp)
        self.store.save_scheme(self.scheme_sisfs)

        # Ingest a sample guideline chunk
        chunk = SchemeDocumentChunk(
            chunk_id="chk_pmegp_1",
            scheme_id="pmegp",
            file_name="pmegp_guidelines.pdf",
            page_number=1,
            section_title="Financial Assistance and Subsidy",
            content="Margin money subsidy of 35 percent margin money subsidy for rural special category entrepreneurs.",
            metadata={"source": "KVIC official gazette"},
        )
        self.store.save_document_chunks([chunk])

        # Build vector index
        self.vector_store.build_index([self.scheme_zed, self.scheme_pmegp, self.scheme_sisfs], chunks=[chunk])

        # Sample Business Profile: Rural Woman Micro Food Manufacturer (Proprietorship)
        self.profile_food_proprietor = BusinessProfile(
            legal_name="MAA TARA AGRO FOODS",
            gstin="24AAAPL1234A1Z1",
            constitution=ConstitutionType.PROPRIETORSHIP,
            principal_address=BusinessAddress(
                full_address="Village Post Anand, Gujarat",
                state_name="Gujarat",
                state_code="24",
                pincode="388001",
            ),
            date_of_registration=date(2025, 6, 1),
            nature_of_activities=["Manufacturing"],
            primary_sector="Food Processing",
            turnover_bracket=TurnoverBracket.BELOW_1_CR,
            msme_tier=MSMETier.MICRO,
            is_woman_owned=True,
            social_category=SocialCategory.SC,
        )

        # Sample Business Profile: Tech Startup Private Limited
        self.profile_tech_startup = BusinessProfile(
            legal_name="CYBERCORE ROBOTICS PVT LTD",
            gstin="27AAACC5678B1Z9",
            constitution=ConstitutionType.PRIVATE_LIMITED,
            principal_address=BusinessAddress(
                full_address="Hinjewadi Phase 1, Pune, Maharashtra",
                state_name="Maharashtra",
                state_code="27",
                pincode="411057",
            ),
            date_of_registration=date(2025, 8, 1),
            nature_of_activities=["Manufacturing", "Services"],
            primary_sector="Electronics",
            turnover_bracket=TurnoverBracket.BELOW_1_CR,
            msme_tier=MSMETier.MICRO,
            is_woman_owned=True,
            is_dpiit_recognized=True,
            social_category=SocialCategory.GENERAL,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # 1. SCHEMA SERIALIZATION TESTS
    # -------------------------------------------------------------
    def test_phase3_schemas_serialization(self):
        item = DocumentGapItem(
            document_name="Detailed Project Report",
            status="Missing",
            criticality="Mandatory",
            issuing_authority="Chartered Accountant",
            how_to_obtain="Engage certified CA to compile financial projections",
            estimated_turnaround_days=7,
        )
        self.assertEqual(item.status, "Missing")
        self.assertEqual(item.criticality, "Mandatory")

        calc = FinancialBenefitCalculation(
            benefit_type="Capital Subsidy",
            quantum_description="35% margin money",
            subsidy_percentage=35.0,
            max_cap_inr=1750000.0,
        )
        self.assertEqual(calc.subsidy_percentage, 35.0)

        assessment = SchemeEligibilityAssessment(
            scheme_id="pmegp",
            scheme_name="PMEGP",
            scheme_short_code="PMEGP",
            verdict="Conditionally Eligible",
            match_score=85.0,
            confidence_score=0.92,
            executive_summary="Strong match for micro entrepreneur",
            eligibility_rationale=["Meets age criteria"],
            disqualification_or_gap_reasons=["Requires DPR"],
            financial_benefit=calc,
            document_checklist=[item],
            missing_mandatory_docs_count=1,
            application_roadmap=["Step 1"],
            application_portal_url="https://kvic.gov.in",
            nodal_agency="KVIC",
        )
        self.assertEqual(assessment.verdict, "Conditionally Eligible")
        self.assertEqual(assessment.missing_mandatory_docs_count, 1)

    # -------------------------------------------------------------
    # 2. HYBRID RETRIEVER & RRF TESTS
    # -------------------------------------------------------------
    def test_hybrid_retriever_rrf(self):
        retriever = HybridRetriever(knowledge_store=self.store, vector_store=self.vector_store)
        candidates = retriever.retrieve(
            profile=self.profile_food_proprietor,
            query="margin money subsidy credit loan agro manufacturing",
            top_k=3,
        )
        self.assertGreaterEqual(len(candidates), 1)
        top_scheme_ids = [c.scheme.scheme_id for c in candidates]
        self.assertIn("pmegp", top_scheme_ids)
        # Check that guideline chunk is associated
        pmegp_cand = next(c for c in candidates if c.scheme.scheme_id == "pmegp")
        self.assertGreaterEqual(len(pmegp_cand.guideline_chunks), 1)

    def test_hybrid_retriever_hard_filters(self):
        retriever = HybridRetriever(knowledge_store=self.store, vector_store=self.vector_store)
        # Tech startup (Pvt Ltd) should NOT be retrieved for PMEGP because PMEGP only allows Proprietorship/Partnership/SHG
        candidates = retriever.retrieve(
            profile=self.profile_tech_startup,
            query="startup funding subsidy",
            top_k=3,
            apply_hard_filters=True,
        )
        scheme_ids = [c.scheme.scheme_id for c in candidates]
        self.assertIn("sisfs", scheme_ids)
        self.assertNotIn("pmegp", scheme_ids)

    # -------------------------------------------------------------
    # 3. CROSS-ENCODER RERANKER TESTS
    # -------------------------------------------------------------
    def test_cross_encoder_reranker(self):
        retriever = HybridRetriever(knowledge_store=self.store, vector_store=self.vector_store)
        candidates = retriever.retrieve(profile=self.profile_tech_startup, query="startup seed fund prototype", top_k=3)
        reranker = CrossEncoderReranker()
        reranked = reranker.rerank(profile=self.profile_tech_startup, candidates=candidates)

        self.assertGreaterEqual(len(reranked), 1)
        # SISFS should be top ranked due to DPIIT startup alignment and Pvt Ltd constitution
        self.assertEqual(reranked[0].candidate.scheme.scheme_id, "sisfs")
        self.assertGreaterEqual(reranked[0].rerank_score, 75.0)
        self.assertTrue(
            any("DPIIT Startup recognition priority verified" in note for note in reranked[0].factors.explanation_notes)
        )

    # -------------------------------------------------------------
    # 4. DOCUMENT GAP ANALYSIS TESTS
    # -------------------------------------------------------------
    def test_document_gap_analysis(self):
        reasoner = LLMEligibilityReasoner()
        chunks = self.store.get_document_chunks_for_scheme("pmegp")
        checklist = reasoner.audit_document_gaps(self.profile_food_proprietor, self.scheme_pmegp, chunks)

        doc_names = [d.document_name for d in checklist]
        # Should detect GST as Available
        gst_doc = next(d for d in checklist if "GST Registration Certificate" in d.document_name)
        self.assertEqual(gst_doc.status, "Available")

        # Should detect DPR as Missing
        dpr_doc = next(d for d in checklist if "Detailed Project Report" in d.document_name)
        self.assertEqual(dpr_doc.status, "Missing")
        self.assertEqual(dpr_doc.issuing_authority, "Empanelled Chartered Accountant / MSME-DFO / Certified Project Consultant")

        # Should detect Udyam as Action Required
        udyam_doc = next(d for d in checklist if "Udyam" in d.document_name)
        self.assertEqual(udyam_doc.status, "Action Required")

    # -------------------------------------------------------------
    # 5. FINANCIAL BENEFIT QUANTUM CALCULATION TESTS
    # -------------------------------------------------------------
    def test_financial_benefit_calculations(self):
        reasoner = LLMEligibilityReasoner()

        # PMEGP for rural SC woman manufacturing: 35% margin money
        pmegp_calc = reasoner.calculate_financial_benefit(self.profile_food_proprietor, self.scheme_pmegp)
        self.assertEqual(pmegp_calc.subsidy_percentage, 35.0)
        self.assertEqual(pmegp_calc.max_cap_inr, 1750000.0)  # 35% of Rs 50 Lakh
        self.assertIn("Special Category / Woman Entrepreneur", pmegp_calc.special_affirmative_boost or "")

        # ZED for Micro woman unit: 80% + 10% = 90%
        zed_calc = reasoner.calculate_financial_benefit(self.profile_tech_startup, self.scheme_zed)
        self.assertEqual(zed_calc.subsidy_percentage, 90.0)
        self.assertIn("+10% affirmative boost", zed_calc.special_affirmative_boost or "")

    # -------------------------------------------------------------
    # 6. OFFICIAL CLAUSE CITATION TESTS
    # -------------------------------------------------------------
    def test_guideline_citation_extraction(self):
        reasoner = LLMEligibilityReasoner()
        chunks = self.store.get_document_chunks_for_scheme("pmegp")
        citations = reasoner.extract_official_citations(self.scheme_pmegp, chunks)
        self.assertGreaterEqual(len(citations), 1)
        self.assertEqual(citations[0].source_document, "pmegp_guidelines.pdf")
        self.assertIn("35 percent margin money subsidy", citations[0].excerpt)

    # -------------------------------------------------------------
    # 7. END-TO-END PIPELINE & MARKDOWN REPORT TESTS
    # -------------------------------------------------------------
    def test_end_to_end_phase3_pipeline(self):
        pipeline = Phase3ReasonerPipeline(knowledge_store=self.store, vector_store=self.vector_store)
        report = pipeline.run(profile=self.profile_food_proprietor, query="subsidy margin money food", top_n_rerank=2)

        self.assertEqual(report.business_legal_name, "MAA TARA AGRO FOODS")
        self.assertGreaterEqual(report.top_candidates_evaluated, 1)
        self.assertTrue(len(report.top_recommendations) > 0)

        # Render Markdown
        md = pipeline.render_markdown_report(report)
        self.assertIn("# Government Schemes Eligibility & Document Gap Analysis Report", md)
        self.assertIn("MAA TARA AGRO FOODS", md)
        self.assertIn("Mandatory Document Compliance Checklist", md)
        self.assertIn("Step-by-Step Application Roadmap", md)


if __name__ == "__main__":
    unittest.main()

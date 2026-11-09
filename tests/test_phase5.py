"""
Automated Test Suite for Phase 5: Guardrails, Evaluation & Production Launch.
Validates:
1. PII Sanitizer (Aadhaar, PAN, Phone, Email masking).
2. PII Profile Sanitization & Audit detection.
3. Hallucination Guardrail (Grounding verification, detecting fabricated subsidies and jurisdiction mismatches).
4. Golden Benchmark Evaluator (Precision@K, Recall@K, MRR, Factual Grounding).
5. Production Dockerfile & docker-compose configurations.
"""

from __future__ import annotations
import os
import sys
import unittest
from datetime import date

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from guardrails.pii_sanitizer import PIISanitizer
from guardrails.hallucination_guard import HallucinationGuard
from evaluation.evaluator import BenchmarkEvaluator, BenchmarkSummary
from schemas.business_profile import BusinessProfile, BusinessAddress, ConstitutionType, MSMETier, SocialCategory
from schemas.government_scheme import GovernmentScheme, SchemeJurisdiction, BenefitType, FinancialBenefit, EligibilityRuleCondition
from schemas.reasoner_schema import SchemeEligibilityAssessment, FinancialBenefitCalculation


class TestPhase5GuardrailsAndEvaluation(unittest.TestCase):

    # -------------------------------------------------------------
    # 1. PII SANITIZATION TESTS
    # -------------------------------------------------------------
    def test_pii_sanitization_aadhaar(self):
        text = "Promoter Aadhaar card number is 9876 5432 1098."
        masked = PIISanitizer.mask_aadhaar(text)
        self.assertNotIn("9876 5432 1098", masked)
        self.assertIn("XXXX-XXXX-1098", masked)

    def test_pii_sanitization_pan(self):
        text = "Personal PAN card: ABCDE1234F registered with IT department."
        masked = PIISanitizer.mask_pan(text)
        self.assertNotIn("ABCDE1234F", masked)
        self.assertIn("ABCXXXXX4F", masked)

    def test_pii_sanitization_phone_email(self):
        text = "Contact founder at +91 9876543210 or founder.ceo@acmetech.in for details."
        sanitized = PIISanitizer.sanitize_text(text)
        self.assertNotIn("9876543210", sanitized)
        self.assertIn("+91 XXXXX-3210", sanitized)
        self.assertNotIn("founder.ceo@acmetech.in", sanitized)
        self.assertIn("f*********o@acmetech.in", sanitized)

    def test_pii_audit_detection(self):
        clean_text = "NEXUS ROBOTICS PRIVATE LIMITED registered in Maharashtra."
        dirty_text = "Director Aadhaar: 5555 4444 3333, Email: contact@nexus.in, Phone: 9812345678."

        clean_audit = PIISanitizer.audit_pii_presence(clean_text)
        self.assertFalse(clean_audit["has_pii"])
        self.assertEqual(clean_audit["total_pii_detected"], 0)

        dirty_audit = PIISanitizer.audit_pii_presence(dirty_text)
        self.assertTrue(dirty_audit["has_pii"])
        self.assertGreaterEqual(dirty_audit["total_pii_detected"], 3)

    # -------------------------------------------------------------
    # 2. HALLUCINATION GUARD TESTS
    # -------------------------------------------------------------
    def test_hallucination_guard_verifies_clean_claim(self):
        scheme = GovernmentScheme(
            scheme_id="clcss",
            scheme_name="Credit Linked Capital Subsidy Scheme",
            scheme_short_code="CLCSS",
            nodal_ministry="MSME",
            implementing_agency="SIDBI",
            jurisdiction=SchemeJurisdiction.CENTRAL,
            summary="15% upfront capital subsidy.",
            rules=EligibilityRuleCondition(applicable_states=["ALL"]),
            benefits=FinancialBenefit(
                benefit_type=BenefitType.CAPITAL_SUBSIDY,
                quantum_description="15% capital subsidy up to ₹15 Lakh.",
                subsidy_percentage=15.0,
                max_assistance_amount_inr=1500000.0,
            ),
            official_portal_url="https://champions.gov.in/",
        )

        profile = BusinessProfile(
            legal_name="ACME MFG",
            constitution=ConstitutionType.PRIVATE_LIMITED,
            principal_address=BusinessAddress(full_address="Pune", state_name="Maharashtra", state_code="27"),
            date_of_registration=date(2025, 1, 1),
            nature_of_activities=["Manufacturing"],
        )

        clean_assessment = SchemeEligibilityAssessment(
            scheme_id="clcss",
            scheme_name="CLCSS",
            scheme_short_code="CLCSS",
            verdict="Eligible",
            match_score=85.0,
            confidence_score=0.95,
            executive_summary="Complies with scheme requirements.",
            eligibility_rationale=["Valid Central scheme"],
            financial_benefit=FinancialBenefitCalculation(
                benefit_type="Capital Subsidy",
                quantum_description="15% subsidy",
                subsidy_percentage=15.0,
                max_cap_inr=1500000.0,
            ),
            application_portal_url="https://champions.gov.in/",
            nodal_agency="SIDBI",
        )

        audit = HallucinationGuard.verify_assessment(clean_assessment, scheme, profile)
        self.assertTrue(audit.is_grounded)
        self.assertEqual(audit.violations_count, 0)
        self.assertEqual(audit.grounding_score, 1.0)

    def test_hallucination_guard_catches_fabricated_subsidy(self):
        scheme = GovernmentScheme(
            scheme_id="clcss",
            scheme_name="Credit Linked Capital Subsidy Scheme",
            scheme_short_code="CLCSS",
            nodal_ministry="MSME",
            implementing_agency="SIDBI",
            jurisdiction=SchemeJurisdiction.CENTRAL,
            summary="15% upfront capital subsidy.",
            rules=EligibilityRuleCondition(applicable_states=["ALL"]),
            benefits=FinancialBenefit(
                benefit_type=BenefitType.CAPITAL_SUBSIDY,
                quantum_description="15% subsidy.",
                subsidy_percentage=15.0,
                max_assistance_amount_inr=1500000.0,
            ),
            official_portal_url="https://champions.gov.in/",
        )

        profile = BusinessProfile(
            legal_name="ACME MFG",
            constitution=ConstitutionType.PRIVATE_LIMITED,
            principal_address=BusinessAddress(full_address="Pune", state_name="Maharashtra", state_code="27"),
            date_of_registration=date(2025, 1, 1),
            nature_of_activities=["Manufacturing"],
        )

        # Fabricated 90% subsidy for a 15% scheme
        hallucinated_assessment = SchemeEligibilityAssessment(
            scheme_id="clcss",
            scheme_name="CLCSS",
            scheme_short_code="CLCSS",
            verdict="Eligible",
            match_score=95.0,
            confidence_score=0.95,
            executive_summary="Huge subsidy.",
            eligibility_rationale=["Matches"],
            financial_benefit=FinancialBenefitCalculation(
                benefit_type="Capital Subsidy",
                quantum_description="90% subsidy",
                subsidy_percentage=90.0,  # Fabricated!
                max_cap_inr=50000000.0,   # Fabricated!
            ),
            application_portal_url="https://fake-subsidy-portal.com",  # Wrong portal!
            nodal_agency="SIDBI",
        )

        audit = HallucinationGuard.verify_assessment(hallucinated_assessment, scheme, profile)
        self.assertFalse(audit.is_grounded)
        self.assertGreaterEqual(audit.violations_count, 2)
        violation_checks = [f.check_name for f in audit.findings if f.status == "VIOLATION"]
        self.assertIn("Subsidy Percentage Bound", violation_checks)
        self.assertIn("Financial Assistance Ceiling", violation_checks)
        self.assertIn("Official Application Portal Link", violation_checks)

    # -------------------------------------------------------------
    # 3. BENCHMARK EVALUATOR TESTS
    # -------------------------------------------------------------
    def test_benchmark_evaluator_metrics(self):
        evaluator = BenchmarkEvaluator()
        summary = evaluator.run_evaluation(top_k=4)

        self.assertGreaterEqual(summary.total_test_cases, 5)
        self.assertGreaterEqual(summary.macro_precision_at_k, 0.70)
        self.assertGreaterEqual(summary.mean_reciprocal_rank, 0.80)
        self.assertGreaterEqual(summary.average_grounding_score, 0.95)
        self.assertEqual(summary.total_hallucination_violations, 0)
        self.assertTrue(summary.all_tests_passed)

    # -------------------------------------------------------------
    # 4. DOCKER & CONTAINERIZATION CONFIG TESTS
    # -------------------------------------------------------------
    def test_docker_and_compose_configs(self):
        dockerfile = os.path.join(PROJECT_ROOT, "Dockerfile")
        compose_file = os.path.join(PROJECT_ROOT, "docker-compose.yml")
        env_example = os.path.join(PROJECT_ROOT, ".env.example")

        self.assertTrue(os.path.exists(dockerfile), "Dockerfile must exist")
        self.assertTrue(os.path.exists(compose_file), "docker-compose.yml must exist")
        self.assertTrue(os.path.exists(env_example), ".env.example must exist")

        with open(dockerfile, "r", encoding="utf-8") as f:
            df_content = f.read()
            self.assertIn("FROM python", df_content)
            self.assertIn("EXPOSE 8000", df_content)
            self.assertIn("HEALTHCHECK", df_content)
            self.assertIn("appuser", df_content)

        with open(compose_file, "r", encoding="utf-8") as f:
            compose_content = f.read()
            self.assertIn("gov-schemes-rag", compose_content)
            self.assertIn("${PORT:-8000}:8000", compose_content)


if __name__ == "__main__":
    unittest.main()

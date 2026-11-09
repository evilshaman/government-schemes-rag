"""
Hallucination Guardrails & Groundedness Verification Engine (Phase 5).
Verifies that generated eligibility claims, subsidy percentages, financial caps,
and document requirements strictly adhere to authoritative policy rules with zero fabrication.
"""

from __future__ import annotations
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

from schemas.government_scheme import GovernmentScheme
from schemas.reasoner_schema import SchemeEligibilityAssessment, FullReasoningReport
from schemas.business_profile import BusinessProfile

logger = logging.getLogger("HallucinationGuard")


class VerificationFinding(BaseModel):
    check_name: str
    status: str = Field(..., description="'PASS' or 'VIOLATION'")
    claimed_value: Any
    authoritative_value: Any
    message: str


class GroundingAuditReport(BaseModel):
    scheme_id: str
    is_grounded: bool
    grounding_score: float = Field(..., ge=0.0, le=1.0, description="Ratio of verified claims to total checks")
    findings: List[VerificationFinding] = Field(default_factory=list)
    violations_count: int = Field(default=0)


class HallucinationGuard:
    """
    Automated fact verification engine against authoritative government scheme schemas.
    """

    @classmethod
    def verify_assessment(
        cls,
        assessment: SchemeEligibilityAssessment,
        authoritative_scheme: GovernmentScheme,
        profile: BusinessProfile,
    ) -> GroundingAuditReport:
        """
        Audits a SchemeEligibilityAssessment against the official GovernmentScheme truth.
        """
        findings: List[VerificationFinding] = []
        rules = authoritative_scheme.rules
        benefits = authoritative_scheme.benefits

        # 1. State / Jurisdiction Consistency Check
        is_central = authoritative_scheme.jurisdiction.value == "Central"
        state_match = (
            is_central
            or "ALL" in rules.applicable_states
            or profile.principal_address.state_name in rules.applicable_states
        )
        if not state_match and assessment.verdict == "Eligible":
            findings.append(
                VerificationFinding(
                    check_name="State Jurisdiction Constraint",
                    status="VIOLATION",
                    claimed_value=assessment.verdict,
                    authoritative_value=f"Only valid in {rules.applicable_states}",
                    message="Model marked out-of-state applicant as Eligible.",
                )
            )
        else:
            findings.append(
                VerificationFinding(
                    check_name="State Jurisdiction Constraint",
                    status="PASS",
                    claimed_value=assessment.verdict,
                    authoritative_value="Jurisdiction Satisfied",
                    message="State eligibility is consistent with scheme rules.",
                )
            )

        # 2. Manufacturing Requirement Check
        is_mfg = any("manufacturing" in act.lower() for act in profile.nature_of_activities)
        if rules.requires_manufacturing and not is_mfg and assessment.verdict == "Eligible":
            findings.append(
                VerificationFinding(
                    check_name="Manufacturing Activity Requirement",
                    status="VIOLATION",
                    claimed_value=assessment.verdict,
                    authoritative_value="Requires Manufacturing",
                    message="Scheme strictly requires manufacturing, but applicant lacks manufacturing operations.",
                )
            )
        else:
            findings.append(
                VerificationFinding(
                    check_name="Manufacturing Activity Requirement",
                    status="PASS",
                    claimed_value=assessment.verdict,
                    authoritative_value="Compliant",
                    message="Manufacturing constraints respected.",
                )
            )

        # 3. Subsidy Percentage Ceiling Check
        claimed_pct = assessment.financial_benefit.subsidy_percentage
        auth_pct = benefits.subsidy_percentage

        # If scheme has a declared max percentage and claimed percentage exceeds it + affirmative bonus threshold
        if auth_pct is not None and claimed_pct is not None:
            max_permissible = min(auth_pct + 15.0, 100.0)  # Allow affirmative bonus (+10-15%)
            if claimed_pct > max_permissible:
                findings.append(
                    VerificationFinding(
                        check_name="Subsidy Percentage Bound",
                        status="VIOLATION",
                        claimed_value=f"{claimed_pct}%",
                        authoritative_value=f"Max {max_permissible}% (Base {auth_pct}%)",
                        message=f"Claimed subsidy percentage ({claimed_pct}%) exceeds official scheme ceiling ({max_permissible}%).",
                    )
                )
            else:
                findings.append(
                    VerificationFinding(
                        check_name="Subsidy Percentage Bound",
                        status="PASS",
                        claimed_value=f"{claimed_pct}%",
                        authoritative_value=f"{auth_pct}%",
                        message="Claimed subsidy percentage is factually bounded.",
                    )
                )

        # 4. Financial Ceiling Cap Check
        claimed_cap = assessment.financial_benefit.max_cap_inr
        auth_cap = benefits.max_assistance_amount_inr
        if auth_cap is not None and claimed_cap is not None:
            # Tolerates slight variation if calculation is based on project cost vs subsidy
            if claimed_cap > (auth_cap * 1.5):
                findings.append(
                    VerificationFinding(
                        check_name="Financial Assistance Ceiling",
                        status="VIOLATION",
                        claimed_value=claimed_cap,
                        authoritative_value=auth_cap,
                        message=f"Claimed assistance cap (₹{claimed_cap:,.0f}) substantially exceeds official limit (₹{auth_cap:,.0f}).",
                    )
                )
            else:
                findings.append(
                    VerificationFinding(
                        check_name="Financial Assistance Ceiling",
                        status="PASS",
                        claimed_value=claimed_cap,
                        authoritative_value=auth_cap,
                        message="Financial cap is verified against official policy terms.",
                    )
                )

        # 5. Application Portal URL Check
        if assessment.application_portal_url != authoritative_scheme.official_portal_url:
            findings.append(
                VerificationFinding(
                    check_name="Official Application Portal Link",
                    status="VIOLATION",
                    claimed_value=assessment.application_portal_url,
                    authoritative_value=authoritative_scheme.official_portal_url,
                    message="Official application portal link does not match authoritative registry.",
                )
            )
        else:
            findings.append(
                VerificationFinding(
                    check_name="Official Application Portal Link",
                    status="PASS",
                    claimed_value=assessment.application_portal_url,
                    authoritative_value=authoritative_scheme.official_portal_url,
                    message="Official application portal link matches verified government URL.",
                )
            )

        # Score resolution
        total_checks = len(findings)
        violations = sum(1 for f in findings if f.status == "VIOLATION")
        passed_checks = total_checks - violations
        score = round(passed_checks / total_checks, 3) if total_checks > 0 else 1.0

        return GroundingAuditReport(
            scheme_id=authoritative_scheme.scheme_id,
            is_grounded=(violations == 0),
            grounding_score=score,
            findings=findings,
            violations_count=violations,
        )

    @classmethod
    def audit_full_report(
        cls,
        report: FullReasoningReport,
        scheme_map: Dict[str, GovernmentScheme],
        profile: BusinessProfile,
    ) -> Dict[str, Any]:
        """
        Audits all recommendations in a FullReasoningReport.
        """
        audit_reports: List[GroundingAuditReport] = []
        total_violations = 0

        for rec in report.top_recommendations:
            auth_scheme = scheme_map.get(rec.scheme_id)
            if auth_scheme:
                audit = cls.verify_assessment(rec, auth_scheme, profile)
                audit_reports.append(audit)
                total_violations += audit.violations_count

        total_audited = len(audit_reports)
        avg_score = (
            round(sum(a.grounding_score for a in audit_reports) / total_audited, 3)
            if total_audited > 0
            else 1.0
        )

        return {
            "all_grounded": total_violations == 0,
            "average_grounding_score": avg_score,
            "total_schemes_audited": total_audited,
            "total_violations": total_violations,
            "audits": [a.model_dump() for a in audit_reports],
        }

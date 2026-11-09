"""
Pydantic Schemas for Phase 3: Hybrid Retrieval & LLM Reasoner Engine.
Defines structured models for:
- Document Gap Analysis items
- Official Clause Citations
- Scheme Eligibility Assessments
- Full Synthesis and Actionable Roadmap Reports
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class DocumentGapItem(BaseModel):
    """
    Represents an individual document requirement, verification status,
    and actionable steps to bridge the gap if missing.
    """
    document_name: str = Field(..., description="Official title of the document or certificate")
    status: Literal["Available", "Missing", "Conditional", "Action Required"] = Field(
        ..., description="Verification status based on profile data"
    )
    criticality: Literal["Mandatory", "Recommended", "Optional"] = Field(
        default="Mandatory", description="Severity level for scheme qualification"
    )
    issuing_authority: str = Field(
        ..., description="Designated government authority, portal, or professional (e.g. Udyam Portal, CA, Tehsildar)"
    )
    how_to_obtain: str = Field(
        ..., description="Actionable step-by-step guidance on how the entrepreneur can obtain this document"
    )
    estimated_turnaround_days: int = Field(
        default=3, description="Estimated SLA in working days to procure the document"
    )
    prerequisites: List[str] = Field(
        default_factory=list, description="Underlying documents or identities required before applying"
    )


class ClauseCitation(BaseModel):
    """
    Official regulatory citation grounding an eligibility finding or benefit calculation.
    """
    source_document: str = Field(..., description="Official circular or guideline PDF name")
    section_or_page: str = Field(..., description="Section title or page reference in official documentation")
    excerpt: str = Field(..., description="Exact or summarized text excerpt from the guidelines")
    relevance_explanation: str = Field(
        ..., description="Explanation of how this clause applies directly to the applicant's profile"
    )


class FinancialBenefitCalculation(BaseModel):
    """
    Structured breakdown of the financial subsidy, grant, or credit assistance.
    """
    benefit_type: str = Field(..., description="Category (e.g., Capital Subsidy, Credit Guarantee, Seed Grant)")
    quantum_description: str = Field(..., description="Formal description of the benefit terms")
    subsidy_percentage: Optional[float] = Field(None, description="Percentage of project cost or fees subsidized")
    max_cap_inr: Optional[float] = Field(None, description="Maximum ceiling in INR")
    estimated_eligible_amount_inr: Optional[float] = Field(
        None, description="Computed monetary assistance based on profile turnover / investment"
    )
    special_affirmative_boost: Optional[str] = Field(
        None, description="Additional booster applied (e.g., +10% for women/SC-ST, rural margin money)"
    )


class SchemeEligibilityAssessment(BaseModel):
    """
    Authoritative LLM-reasoned assessment for a single scheme candidate.
    """
    scheme_id: str
    scheme_name: str
    scheme_short_code: str
    verdict: Literal["Eligible", "Conditionally Eligible", "Ineligible"] = Field(
        ..., description="Definitive eligibility verdict"
    )
    match_score: float = Field(..., ge=0.0, le=100.0, description="Composite fit score (0 to 100)")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Model confidence in verdict (0.0 to 1.0)")
    executive_summary: str = Field(
        ..., description="Concise summary explaining the match and strategic value for the business"
    )
    eligibility_rationale: List[str] = Field(
        default_factory=list, description="Bullet points verifying specific criteria against business profile"
    )
    disqualification_or_gap_reasons: List[str] = Field(
        default_factory=list, description="Specific conditions failed or prerequisites not yet fulfilled"
    )
    official_citations: List[ClauseCitation] = Field(
        default_factory=list, description="Grounding citations from scheme guidelines and circulars"
    )
    financial_benefit: FinancialBenefitCalculation
    document_checklist: List[DocumentGapItem] = Field(
        default_factory=list, description="Complete document compliance audit with gap resolution roadmap"
    )
    missing_mandatory_docs_count: int = Field(default=0)
    application_roadmap: List[str] = Field(
        default_factory=list, description="Step-by-step application guidance from preparation to disbursement"
    )
    application_portal_url: str
    nodal_agency: str


class FullReasoningReport(BaseModel):
    """
    Comprehensive synthesis report for a business profile across the policy universe.
    """
    business_legal_name: str
    trade_name: Optional[str] = None
    gstin: Optional[str] = None
    state: str
    constitution: str
    msme_tier: str
    primary_sector: str
    business_age_years: float
    query_intent: Optional[str] = None
    total_schemes_searched: int
    top_candidates_evaluated: int
    eligible_count: int
    conditional_count: int
    ineligible_count: int
    top_recommendations: List[SchemeEligibilityAssessment] = Field(default_factory=list)
    strategic_roadmap_summary: str = Field(
        ..., description="Holistic strategic advisory synthesized for the business promoter"
    )
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

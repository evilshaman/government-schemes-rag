"""
Government Scheme Schema for Discovery and Hybrid RAG Matching Engine.
Defines the authoritative structure for government schemes, subsidies, and credit facilities.
Supports deterministic rule evaluation (Stage 1) and semantic search + LLM reasoner (Stages 2-4).
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from schemas.business_profile import ConstitutionType, MSMETier


class SchemeJurisdiction(str, Enum):
    CENTRAL = "Central"
    STATE = "State"


class BenefitType(str, Enum):
    CAPITAL_SUBSIDY = "Capital Subsidy"
    CREDIT_GUARANTEE = "Credit Guarantee"
    TERM_LOAN = "Term Loan / Working Capital"
    INTEREST_SUBVENTION = "Interest Subvention"
    GRANT_EQUITY = "Grant / Seed Funding"
    TAX_EXEMPTION = "Tax Exemption / Concession"
    REIMBURSEMENT = "Fee / Cost Reimbursement"
    TRAINING_INFRASTRUCTURE = "Training & Infrastructure"


class SchemeStatus(str, Enum):
    ACTIVE = "Active"
    DISCONTINUED = "Discontinued"
    UNDER_REVISION = "Under Revision"
    PILOT = "Pilot"


class EligibilityRuleCondition(BaseModel):
    """
    Structured rule condition for deterministic pre-filtering.
    """
    allowed_jurisdictions: List[SchemeJurisdiction] = Field(
        default_factory=lambda: [SchemeJurisdiction.CENTRAL, SchemeJurisdiction.STATE]
    )
    applicable_states: List[str] = Field(
        default_factory=lambda: ["ALL"],
        description="List of states or ['ALL'] for nationwide central schemes"
    )
    eligible_constitutions: List[ConstitutionType] = Field(
        default_factory=list,
        description="Allowed legal forms. Empty list indicates open to all."
    )
    eligible_msme_tiers: List[MSMETier] = Field(
        default_factory=lambda: [MSMETier.MICRO, MSMETier.SMALL, MSMETier.MEDIUM],
        description="Applicable MSME brackets"
    )
    min_business_age_years: Optional[float] = Field(
        None,
        description="Minimum business age required (e.g. at least 3 years profitable track record)"
    )
    max_business_age_years: Optional[float] = Field(
        None,
        description="Maximum business age allowed (e.g. <= 10 years for Startup India)"
    )
    target_sectors: List[str] = Field(
        default_factory=lambda: ["ALL"],
        description="Target industry sectors or ['ALL']"
    )
    requires_manufacturing: bool = Field(
        default=False,
        description="Strictly restricted to manufacturing entities"
    )
    requires_services: bool = Field(
        default=False,
        description="Strictly restricted to service entities"
    )
    requires_women_ownership: bool = Field(
        default=False,
        description="Scheme is reserved for women-owned enterprises"
    )
    requires_sc_st_ownership: bool = Field(
        default=False,
        description="Scheme is reserved for SC/ST entrepreneurs"
    )
    requires_dpiit_recognition: bool = Field(
        default=False,
        description="Requires DPIIT startup certificate"
    )


class FinancialBenefit(BaseModel):
    benefit_type: BenefitType = Field(..., description="Primary classification of benefit")
    quantum_description: str = Field(..., description="Human-readable description of assistance")
    subsidy_percentage: Optional[float] = Field(
        None,
        description="Percentage of subsidy or concession, if applicable (e.g. 25.0 for 25%)"
    )
    max_assistance_amount_inr: Optional[float] = Field(
        None,
        description="Maximum financial benefit cap in INR"
    )
    interest_subsidy_rate: Optional[float] = Field(
        None,
        description="Interest subvention percentage (e.g. 2.0% or 3.0%)"
    )
    guarantee_coverage_percentage: Optional[float] = Field(
        None,
        description="Credit guarantee coverage percentage (e.g. 85.0% under CGTMSE)"
    )


class GovernmentScheme(BaseModel):
    """
    Standard schema for a government scheme or policy.
    """
    scheme_id: str = Field(..., description="Unique slug identifier (e.g. 'cgtmse', 'pmegp')")
    scheme_name: str = Field(..., description="Official title of the scheme")
    scheme_short_code: str = Field(..., description="Common acronym (e.g. 'CGTMSE', 'SISFS')")
    nodal_ministry: str = Field(..., description="Ministry responsible for the scheme")
    implementing_agency: str = Field(..., description="Executing agency, bank, or portal")
    jurisdiction: SchemeJurisdiction = Field(..., description="Central or State")
    summary: str = Field(..., description="Concise 2-3 sentence overview of the scheme")
    
    # Matching and eligibility constraints
    rules: EligibilityRuleCondition = Field(
        default_factory=EligibilityRuleCondition,
        description="Deterministic pre-filter criteria"
    )
    eligibility_criteria_text: List[str] = Field(
        default_factory=list,
        description="Granular eligibility points for LLM reasoning and user checklist"
    )
    
    # Financial benefits
    benefits: FinancialBenefit = Field(
        ...,
        description="Structured financial package details"
    )
    
    # Application & compliance
    required_documents: List[str] = Field(
        default_factory=list,
        description="List of mandatory documents required for application"
    )
    application_mode: str = Field(
        default="Online Portal",
        description="e.g. 'Online via Jan Samarth', 'National Single Window Portal (NSWS)'"
    )
    official_portal_url: str = Field(
        ...,
        description="Direct application or info website URL"
    )
    guidelines_doc_url: Optional[str] = Field(
        None,
        description="Direct link to official gazette notification or operational guidelines PDF"
    )
    application_process: List[str] = Field(
        default_factory=list,
        description="Authoritative step-by-step application process and instructions"
    )
    application_process_md: Optional[str] = Field(
        None,
        description="Complete markdown formatted official application workflow and guidelines"
    )
    
    tags: List[str] = Field(
        default_factory=list,
        description="Keywords for dense semantic embedding and hybrid search"
    )
    status: SchemeStatus = Field(
        default=SchemeStatus.ACTIVE,
        description="Current operational status of scheme"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra context, nodal contacts, or circular numbers"
    )

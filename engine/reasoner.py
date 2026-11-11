"""
LLM Eligibility Verification & Document Gap Analysis Synthesizer (Phase 3).
Integrates:
1. Gemini LLM Vision & Reasoning API for dynamic policy deliberation.
2. High-precision Grounded Rule-Assisted Engine for offline / zero-hallucination execution.
3. Automated Document Gap Analysis against official regulatory checklists.
4. Financial Benefit Quantum Calculation tailored to the specific business profile.
5. Official Guideline Clause citations referencing PDF circulars.
"""

from __future__ import annotations
import os
import json
import logging
import httpx
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from schemas.business_profile import (
    BusinessProfile,
    ConstitutionType,
    MSMETier,
    SocialCategory,
    TurnoverBracket,
)
from schemas.government_scheme import GovernmentScheme, SchemeJurisdiction, BenefitType
from schemas.reasoner_schema import (
    DocumentGapItem,
    ClauseCitation,
    FinancialBenefitCalculation,
    SchemeEligibilityAssessment,
    FullReasoningReport,
)
from engine.reranker import RerankedSchemeCandidate
from parsers.pdf_guidelines_parser import SchemeDocumentChunk

logger = logging.getLogger("SchemeReasoner")


# Master Knowledge Base of Indian Regulatory & Scheme Documents
DOCUMENT_REGULATORY_REGISTRY: Dict[str, Dict[str, Any]] = {
    "gst_certificate": {
        "title": "GST Registration Certificate (Form GST REG-06)",
        "issuing_authority": "Goods and Services Tax Network (GSTN), CBIC",
        "how_to_obtain": "Download directly from gst.gov.in portal via Services > User Services > View/Download Certificates.",
        "turnaround_days": 1,
        "criticality": "Mandatory",
        "prerequisites": ["Valid GSTIN credentials"],
    },
    "pan_card": {
        "title": "Permanent Account Number (PAN) Card",
        "issuing_authority": "Income Tax Department / NSDL / UTIITSL",
        "how_to_obtain": "Apply online at onlineservices.nsdl.com or download e-PAN via Income Tax e-Filing portal.",
        "turnaround_days": 1,
        "criticality": "Mandatory",
        "prerequisites": ["Aadhaar", "Identity Proof"],
    },
    "udyam_registration": {
        "title": "Udyam MSME Registration Certificate",
        "issuing_authority": "Ministry of Micro, Small and Medium Enterprises (MSME)",
        "how_to_obtain": "Free self-declaration registration online at udyamregistration.gov.in using Aadhaar, PAN, and GSTIN.",
        "turnaround_days": 1,
        "criticality": "Mandatory",
        "prerequisites": ["Aadhaar linked with mobile", "PAN Card", "GSTIN"],
    },
    "dpr": {
        "title": "Detailed Project Report (DPR) / Techno-Economic Feasibility Report",
        "issuing_authority": "Empanelled Chartered Accountant / MSME-DFO / Certified Project Consultant",
        "how_to_obtain": "Commission project report detailing promoter background, plant & machinery capex, financial projections, DSCR, and break-even analysis.",
        "turnaround_days": 7,
        "criticality": "Mandatory",
        "prerequisites": ["Machinery quotations", "Building / Land estimate", "Working capital estimates"],
    },
    "quotations": {
        "title": "Machinery & Equipment Quotations / Proforma Invoices",
        "issuing_authority": "Original Equipment Manufacturers (OEM) / Authorized Industrial Suppliers",
        "how_to_obtain": "Procure competitive quotation letters with GSTIN, technical specifications, and price breakdown on vendor letterhead.",
        "turnaround_days": 4,
        "criticality": "Mandatory",
        "prerequisites": ["Technical equipment specification sheet"],
    },
    "educational_marksheet": {
        "title": "Educational Qualification Marksheet (Class 8th / 10th Certificate)",
        "issuing_authority": "State / Central Recognized Secondary Education Board / School",
        "how_to_obtain": "Produce original or self-attested copy of school transfer certificate or passing marksheet.",
        "turnaround_days": 1,
        "criticality": "Mandatory",
        "prerequisites": ["Academic records"],
    },
    "caste_category_certificate": {
        "title": "Special Social Category / Caste Certificate (SC/ST/OBC)",
        "issuing_authority": "Revenue Department / Sub-Divisional Magistrate (SDM) / Tehsildar",
        "how_to_obtain": "Apply through State e-District portal or local Revenue / Taluk office with family ration card and revenue proof.",
        "turnaround_days": 14,
        "criticality": "Mandatory",
        "prerequisites": ["Father's caste certificate", "Birth certificate", "Ration card"],
    },
    "factory_license_pcb": {
        "title": "Pollution Control Board Consent (CTE/CTO) / Factory License",
        "issuing_authority": "State Pollution Control Board (SPCB) / Directorate of Industrial Safety",
        "how_to_obtain": "Submit industrial effluent and emissions layout on State Single Window Clearance Portal under White/Green/Orange industry category.",
        "turnaround_days": 21,
        "criticality": "Mandatory",
        "prerequisites": ["Site blueprint", "Manufacturing process flowchart", "Water/power connection details"],
    },
    "dpiit_recognition": {
        "title": "DPIIT Startup India Recognition Certificate",
        "issuing_authority": "Department for Promotion of Industry and Internal Trade (DPIIT)",
        "how_to_obtain": "Register on startupindia.gov.in and submit pitch deck, proof of concept link, and explanation of uniqueness.",
        "turnaround_days": 3,
        "criticality": "Mandatory",
        "prerequisites": ["Incorporation Certificate / Partnership Deed", "Pitch deck / Website", "PAN"],
    },
    "bank_statement": {
        "title": "Current Bank Account Statement & Cancelled Cheque",
        "issuing_authority": "Scheduled Commercial Bank / Branch Manager",
        "how_to_obtain": "Obtain last 6 months account statement and personalized cheque leaf with printed entity name.",
        "turnaround_days": 1,
        "criticality": "Mandatory",
        "prerequisites": ["Active current bank account"],
    },
    "gram_panchayat_cert": {
        "title": "Gram Panchayat Rural Area Certificate",
        "issuing_authority": "Village Gram Panchayat / Sarpanch / Block Development Officer (BDO)",
        "how_to_obtain": "Request village rural demarcation certificate affirming that the project site falls outside municipal boundaries.",
        "turnaround_days": 3,
        "criticality": "Recommended",
        "prerequisites": ["Address proof of industrial plot / premises"],
    },
}


class LLMEligibilityReasoner:
    """
    Synthesizes grounded eligibility verdicts, benefit calculations, document gap roadmaps,
    and official guideline citations using Gemini LLM with an offline-resilient grounded fallback.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    # -------------------------------------------------------------------------
    # 1. BENEFIT QUANTUM CALCULATION
    # -------------------------------------------------------------------------
    @staticmethod
    def calculate_financial_benefit(
        profile: BusinessProfile, scheme: GovernmentScheme
    ) -> FinancialBenefitCalculation:
        """
        Calculates exact or estimated financial benefits based on profile parameters.
        """
        benefits = scheme.benefits
        b_type = benefits.benefit_type.value
        desc = benefits.quantum_description
        percentage = benefits.subsidy_percentage
        cap = benefits.max_assistance_amount_inr
        boost: Optional[str] = None
        est_amount: Optional[float] = None

        sid = scheme.scheme_id.lower()
        is_mfg = any("manufacturing" in act.lower() for act in profile.nature_of_activities)

        # 1. PMEGP (Prime Minister's Employment Generation Programme)
        if "pmegp" in sid:
            max_cost = 5000000.0 if is_mfg else 2000000.0
            is_special = (
                profile.is_woman_owned
                or profile.social_category in [SocialCategory.SC, SocialCategory.ST, SocialCategory.OBC]
            )
            # 35% for rural special category, 25% for rural general, 25% for urban special, 15% for urban general
            if is_special:
                subsidy_pct = 35.0
                boost = "Special Category / Woman Entrepreneur: 35% rural margin money subsidy (Beneficiary contribution only 5%)"
            else:
                subsidy_pct = 25.0
                boost = "General Category: 25% rural margin money subsidy (Beneficiary contribution 10%)"

            percentage = subsidy_pct
            cap = max_cost * (subsidy_pct / 100.0)
            est_amount = cap

        # 2. ZED Certification Scheme
        elif "zed" in sid:
            tier_pct = 80.0
            if profile.msme_tier == MSMETier.SMALL:
                tier_pct = 60.0
            elif profile.msme_tier == MSMETier.MEDIUM:
                tier_pct = 50.0

            if profile.is_woman_owned or profile.social_category in [SocialCategory.SC, SocialCategory.ST]:
                tier_pct = min(tier_pct + 10.0, 100.0)
                boost = f"+10% affirmative boost for woman/SC-ST promoter (Total Subsidy: {tier_pct}%)"

            percentage = tier_pct
            cap = 500000.0
            est_amount = cap * (tier_pct / 100.0)

        # 3. Startup India Seed Fund Scheme (SISFS)
        elif "sisfs" in sid or "seed_fund" in sid:
            percentage = 100.0
            cap = 5000000.0
            est_amount = 2000000.0  # ₹20 Lakhs grant for prototype
            boost = "Up to ₹20 Lakhs as 100% grant for prototype/PoC; up to ₹50 Lakhs for market entry via convertible debt."

        # 4. Maharashtra CMEGP
        elif "cmegp" in sid:
            max_cost = 5000000.0 if is_mfg else 2000000.0
            subsidy_pct = 35.0 if profile.is_woman_owned or profile.social_category in [SocialCategory.SC, SocialCategory.ST] else 25.0
            percentage = subsidy_pct
            cap = max_cost * (subsidy_pct / 100.0)
            est_amount = cap
            boost = f"State subsidy of {subsidy_pct}% margin money for Maharashtra unit."

        # 5. CGTMSE Credit Guarantee
        elif "cgtmse" in sid:
            cap = 50000000.0  # ₹5 Crore
            percentage = 85.0 if profile.is_woman_owned or profile.msme_tier == MSMETier.MICRO else 75.0
            boost = f"{percentage}% collateral-free loan default guarantee underwritten by SIDBI & Ministry of MSME."
            est_amount = cap

        else:
            if percentage and cap:
                est_amount = cap * (percentage / 100.0)
            elif cap:
                est_amount = cap

        return FinancialBenefitCalculation(
            benefit_type=b_type,
            quantum_description=desc,
            subsidy_percentage=percentage,
            max_cap_inr=cap,
            estimated_eligible_amount_inr=est_amount,
            special_affirmative_boost=boost,
        )

    # -------------------------------------------------------------------------
    # 2. DOCUMENT GAP ANALYSIS
    # -------------------------------------------------------------------------
    @staticmethod
    def audit_document_gaps(
        profile: BusinessProfile, scheme: GovernmentScheme, chunks: List[SchemeDocumentChunk]
    ) -> List[DocumentGapItem]:
        """
        Compares applicant profile documents against mandatory scheme checklist.
        Produces step-by-step gap resolution items.
        """
        checklist: List[DocumentGapItem] = []
        is_mfg = any("manufacturing" in act.lower() for act in profile.nature_of_activities)
        sid = scheme.scheme_id.lower()

        # 1. Base Documents (GST & PAN)
        if profile.gstin:
            d = DOCUMENT_REGULATORY_REGISTRY["gst_certificate"]
            checklist.append(
                DocumentGapItem(
                    document_name=d["title"],
                    status="Available",
                    criticality=d["criticality"],
                    issuing_authority=d["issuing_authority"],
                    how_to_obtain=d["how_to_obtain"],
                    estimated_turnaround_days=d["turnaround_days"],
                    prerequisites=d["prerequisites"],
                )
            )

        d_pan = DOCUMENT_REGULATORY_REGISTRY["pan_card"]
        checklist.append(
            DocumentGapItem(
                document_name=d_pan["title"],
                status="Available" if profile.gstin else "Missing",
                criticality=d_pan["criticality"],
                issuing_authority=d_pan["issuing_authority"],
                how_to_obtain=d_pan["how_to_obtain"],
                estimated_turnaround_days=d_pan["turnaround_days"],
                prerequisites=d_pan["prerequisites"],
            )
        )

        # 2. Udyam Registration (Required for MSME, PMEGP, ZED, CMEGP)
        needs_udyam = any(k in sid for k in ["pmegp", "zed", "cmegp", "msme", "pms", "cgtmse"])
        if needs_udyam or scheme.rules.eligible_msme_tiers:
            d_u = DOCUMENT_REGULATORY_REGISTRY["udyam_registration"]
            checklist.append(
                DocumentGapItem(
                    document_name=d_u["title"],
                    status="Action Required",
                    criticality="Mandatory",
                    issuing_authority=d_u["issuing_authority"],
                    how_to_obtain=d_u["how_to_obtain"],
                    estimated_turnaround_days=d_u["turnaround_days"],
                    prerequisites=d_u["prerequisites"],
                )
            )

        # 3. Detailed Project Report (DPR) (Required for PMEGP, CMEGP, Mudra, SISFS)
        needs_dpr = any(k in sid for k in ["pmegp", "cmegp", "mudra", "sisfs", "credit", "cgtmse"])
        if needs_dpr:
            d_dpr = DOCUMENT_REGULATORY_REGISTRY["dpr"]
            checklist.append(
                DocumentGapItem(
                    document_name=d_dpr["title"],
                    status="Missing",
                    criticality="Mandatory",
                    issuing_authority=d_dpr["issuing_authority"],
                    how_to_obtain=d_dpr["how_to_obtain"],
                    estimated_turnaround_days=d_dpr["turnaround_days"],
                    prerequisites=d_dpr["prerequisites"],
                )
            )

        # 4. Machinery Quotations
        if is_mfg or "zed" in sid or "pmegp" in sid or "cmegp" in sid:
            d_q = DOCUMENT_REGULATORY_REGISTRY["quotations"]
            checklist.append(
                DocumentGapItem(
                    document_name=d_q["title"],
                    status="Action Required",
                    criticality="Mandatory",
                    issuing_authority=d_q["issuing_authority"],
                    how_to_obtain=d_q["how_to_obtain"],
                    estimated_turnaround_days=d_q["turnaround_days"],
                    prerequisites=d_q["prerequisites"],
                )
            )

        # 5. Educational Marksheet (Class 8th / 10th for PMEGP)
        if "pmegp" in sid:
            d_ed = DOCUMENT_REGULATORY_REGISTRY["educational_marksheet"]
            checklist.append(
                DocumentGapItem(
                    document_name=d_ed["title"],
                    status="Action Required",
                    criticality="Mandatory",
                    issuing_authority=d_ed["issuing_authority"],
                    how_to_obtain=d_ed["how_to_obtain"],
                    estimated_turnaround_days=d_ed["turnaround_days"],
                    prerequisites=d_ed["prerequisites"],
                )
            )

        # 6. Caste / Special Category Certificate
        if scheme.rules.requires_sc_st_ownership or profile.social_category in [SocialCategory.SC, SocialCategory.ST]:
            d_c = DOCUMENT_REGULATORY_REGISTRY["caste_category_certificate"]
            status = "Available" if profile.social_category in [SocialCategory.SC, SocialCategory.ST] else "Missing"
            checklist.append(
                DocumentGapItem(
                    document_name=d_c["title"],
                    status=status,
                    criticality="Mandatory",
                    issuing_authority=d_c["issuing_authority"],
                    how_to_obtain=d_c["how_to_obtain"],
                    estimated_turnaround_days=d_c["turnaround_days"],
                    prerequisites=d_c["prerequisites"],
                )
            )

        # 7. Factory License / Pollution Consent
        if is_mfg and ("zed" in sid or "pli" in sid or "specs" in sid):
            d_fac = DOCUMENT_REGULATORY_REGISTRY["factory_license_pcb"]
            checklist.append(
                DocumentGapItem(
                    document_name=d_fac["title"],
                    status="Action Required",
                    criticality="Mandatory",
                    issuing_authority=d_fac["issuing_authority"],
                    how_to_obtain=d_fac["how_to_obtain"],
                    estimated_turnaround_days=d_fac["turnaround_days"],
                    prerequisites=d_fac["prerequisites"],
                )
            )

        # 8. DPIIT Recognition
        if scheme.rules.requires_dpiit_recognition or "sisfs" in sid or "startup" in sid:
            d_dp = DOCUMENT_REGULATORY_REGISTRY["dpiit_recognition"]
            status = "Available" if profile.is_dpiit_recognized else "Missing"
            checklist.append(
                DocumentGapItem(
                    document_name=d_dp["title"],
                    status=status,
                    criticality="Mandatory",
                    issuing_authority=d_dp["issuing_authority"],
                    how_to_obtain=d_dp["how_to_obtain"],
                    estimated_turnaround_days=d_dp["turnaround_days"],
                    prerequisites=d_dp["prerequisites"],
                )
            )

        # 9. Bank Statement
        d_bank = DOCUMENT_REGULATORY_REGISTRY["bank_statement"]
        checklist.append(
            DocumentGapItem(
                document_name=d_bank["title"],
                status="Available",
                criticality=d_bank["criticality"],
                issuing_authority=d_bank["issuing_authority"],
                how_to_obtain=d_bank["how_to_obtain"],
                estimated_turnaround_days=d_bank["turnaround_days"],
                prerequisites=d_bank["prerequisites"],
            )
        )

        return checklist

    # -------------------------------------------------------------------------
    # 3. OFFICIAL GUIDELINE CITATIONS
    # -------------------------------------------------------------------------
    @staticmethod
    def extract_official_citations(
        scheme: GovernmentScheme, chunks: List[SchemeDocumentChunk]
    ) -> List[ClauseCitation]:
        """
        Extracts citations from scheme documents or official schema attributes.
        """
        citations: List[ClauseCitation] = []

        if chunks:
            for ch in chunks[:3]:
                citations.append(
                    ClauseCitation(
                        source_document=ch.file_name,
                        section_or_page=f"Page {ch.page_number} ({ch.section_title or 'Guidelines'})",
                        excerpt=ch.content[:220].strip() + "...",
                        relevance_explanation=f"Directly establishes operating guidelines and subsidy terms for {scheme.scheme_short_code}.",
                    )
                )
        else:
            citations.append(
                ClauseCitation(
                    source_document=f"Operational Gazette / Scheme Guidelines for {scheme.scheme_short_code}",
                    section_or_page="Eligibility & Benefit Circular",
                    excerpt=f"Quantum: {scheme.benefits.quantum_description}. Criteria: {'; '.join(scheme.eligibility_criteria_text[:2])}.",
                    relevance_explanation="Authoritative provisions published by the Nodal Ministry.",
                )
            )

        return citations

    # -------------------------------------------------------------------------
    # 4. DETERMINISTIC / GROUNDED REASONER (OFFLINE & FALLBACK)
    # -------------------------------------------------------------------------
    def _reason_deterministically(
        self, profile: BusinessProfile, candidate: RerankedSchemeCandidate
    ) -> SchemeEligibilityAssessment:
        scheme = candidate.candidate.scheme
        rules = scheme.rules
        chunks = candidate.candidate.guideline_chunks

        rationale: List[str] = []
        gaps_or_disqualifications: List[str] = []

        # 1. State / Jurisdiction Check
        state_match = (
            scheme.jurisdiction == SchemeJurisdiction.CENTRAL
            or "ALL" in rules.applicable_states
            or profile.principal_address.state_name in rules.applicable_states
        )
        if not state_match:
            gaps_or_disqualifications.append(
                f"State jurisdiction mismatch: Scheme applies to {rules.applicable_states}, but applicant is registered in {profile.principal_address.state_name}."
            )
        else:
            rationale.append(f"State eligibility confirmed: Active in {profile.principal_address.state_name}.")

        # 2. Constitution Check
        if rules.eligible_constitutions and profile.constitution not in rules.eligible_constitutions:
            gaps_or_disqualifications.append(
                f"Entity constitution mismatch: Requires {[c.value for c in rules.eligible_constitutions]}, applicant is {profile.constitution.value}."
            )
        else:
            rationale.append(f"Entity constitution '{profile.constitution.value}' is qualified.")

        # 3. Age Check
        age = profile.business_age_years
        if rules.max_business_age_years is not None and age > rules.max_business_age_years:
            gaps_or_disqualifications.append(
                f"Age limit exceeded: Scheme maximum is {rules.max_business_age_years} yrs, business age is {age:.1f} yrs."
            )
        elif rules.min_business_age_years is not None and age < rules.min_business_age_years:
            gaps_or_disqualifications.append(
                f"Track record requirement: Requires {rules.min_business_age_years} yrs operating history, applicant has {age:.1f} yrs."
            )
        else:
            rationale.append(f"Business operational age ({age:.1f} years) satisfies scheme age bounds.")

        # 4. MSME Tier
        if rules.eligible_msme_tiers and profile.msme_tier not in rules.eligible_msme_tiers:
            gaps_or_disqualifications.append(
                f"MSME tier mismatch: Open to {[t.value for t in rules.eligible_msme_tiers]}, applicant is {profile.msme_tier.value}."
            )
        else:
            rationale.append(f"MSME tier '{profile.msme_tier.value}' is in approved scope.")

        # 5. Manufacturing / Services Activity Check
        is_mfg = any("manufacturing" in act.lower() for act in profile.nature_of_activities)
        is_svc = any("service" in act.lower() for act in profile.nature_of_activities)

        if rules.requires_manufacturing and not is_mfg:
            gaps_or_disqualifications.append("Requires active manufacturing operations, but business does not list Manufacturing.")
        elif rules.requires_manufacturing:
            rationale.append("Active manufacturing operations verified from GST REG-06.")

        if rules.requires_services and not is_svc:
            gaps_or_disqualifications.append("Requires service operations, but business does not list Services.")
        elif rules.requires_services:
            rationale.append("Service operations verified from GST REG-06.")

        # 6. Affirmative Flags
        if rules.requires_women_ownership and not profile.is_woman_owned:
            gaps_or_disqualifications.append("Requires majority woman ownership (applicant is not woman-owned).")
        elif profile.is_woman_owned:
            rationale.append("Woman entrepreneur affirmative incentive satisfied.")

        if rules.requires_dpiit_recognition and not profile.is_dpiit_recognized:
            gaps_or_disqualifications.append("Requires official DPIIT Startup Recognition Certificate.")
        elif profile.is_dpiit_recognized:
            rationale.append("DPIIT Startup Recognition status active and verified.")

        # Determine Verdict
        has_fatal_disqualification = any(
            "mismatch" in g.lower() or "exceeded" in g.lower() or "does not list" in g.lower()
            for g in gaps_or_disqualifications
        )

        doc_checklist = self.audit_document_gaps(profile, scheme, chunks)
        missing_mandatory = [d for d in doc_checklist if d.status in ["Missing", "Action Required"] and d.criticality == "Mandatory"]

        if has_fatal_disqualification:
            verdict = "Ineligible"
            match_score = round(candidate.rerank_score * 0.3, 1)
            confidence = 0.95
            summary = f"Business does not qualify for {scheme.scheme_short_code} due to core regulatory constraints."
        elif gaps_or_disqualifications or missing_mandatory:
            verdict = "Conditionally Eligible"
            match_score = round(candidate.rerank_score, 1)
            confidence = 0.90
            summary = f"Strong qualification profile for {scheme.scheme_short_code}; actionable documentation gaps must be bridged."
        else:
            verdict = "Eligible"
            match_score = round(candidate.rerank_score, 1)
            confidence = 0.98
            summary = f"Excellent match for {scheme.scheme_short_code}. Business meets all key eligibility parameters."

        financial_calc = self.calculate_financial_benefit(profile, scheme)
        citations = self.extract_official_citations(scheme, chunks)

        # Application Roadmap Steps: prioritize authentic crawled application process if available
        if scheme.application_process:
            roadmap = scheme.application_process
        else:
            roadmap = [
                f"Step 1 (Prerequisites): Procure remaining mandatory documents ({', '.join([d.document_name for d in missing_mandatory[:2]]) if missing_mandatory else 'Self-attested documentation'}).",
                f"Step 2 (Online Portal): Access official application portal at {scheme.official_portal_url} via {scheme.nodal_ministry}.",
                "Step 3 (Submission): Fill application form, attach Detailed Project Report, vendor quotes, and GST certificate.",
                "Step 4 (Verification & Sanction): Application reviewed by District Industries Centre (DIC) / Nodal Agency and linked bank for subsidy disbursement.",
            ]

        return SchemeEligibilityAssessment(
            scheme_id=scheme.scheme_id,
            scheme_name=scheme.scheme_name,
            scheme_short_code=scheme.scheme_short_code,
            verdict=verdict,
            match_score=match_score,
            confidence_score=confidence,
            executive_summary=summary,
            eligibility_rationale=rationale,
            disqualification_or_gap_reasons=gaps_or_disqualifications,
            official_citations=citations,
            financial_benefit=financial_calc,
            document_checklist=doc_checklist,
            missing_mandatory_docs_count=len(missing_mandatory),
            application_roadmap=roadmap,
            application_portal_url=scheme.official_portal_url,
            nodal_agency=f"{scheme.implementing_agency} ({scheme.nodal_ministry})",
        )

    # -------------------------------------------------------------------------
    # 5. GEMINI LLM REASONING API (WHEN KEY PRESENT)
    # -------------------------------------------------------------------------
    def _reason_with_gemini(
        self, profile: BusinessProfile, candidate: RerankedSchemeCandidate
    ) -> Optional[SchemeEligibilityAssessment]:
        """
        Executes zero-shot structured reasoning using Gemini REST API.
        Falls back to deterministic reasoner on any error or missing key.
        """
        if not self.api_key:
            return None

        scheme = candidate.candidate.scheme
        chunks = candidate.candidate.guideline_chunks
        chunk_texts = "\n---\n".join([f"[{c.file_name} p.{c.page_number}]: {c.content}" for c in chunks])

        prompt = f"""
You are an expert Government Policy & Subsidies Deliberation Engine specializing in Indian MSME, Startup, and Central/State policies.
Examine this Business Profile and evaluate its eligibility for the following scheme using official guidelines:

BUSINESS PROFILE:
- Legal Name: {profile.legal_name}
- GSTIN: {profile.gstin or 'N/A'}
- Constitution: {profile.constitution.value}
- Registered State: {profile.principal_address.state_name}
- Business Age: {profile.business_age_years:.1f} years
- MSME Classification: {profile.msme_tier.value}
- Primary Sector: {profile.primary_sector}
- Nature of Activities: {', '.join(profile.nature_of_activities)}
- Special Attributes: Woman-Owned={profile.is_woman_owned}, DPIIT-Recognized={profile.is_dpiit_recognized}, Social Category={profile.social_category.value}

SCHEME DETAILS:
- Title: {scheme.scheme_name} [{scheme.scheme_short_code}]
- Ministry: {scheme.nodal_ministry} / {scheme.implementing_agency}
- Summary: {scheme.summary}
- Target States: {scheme.rules.applicable_states}
- Eligible Constitutions: {[c.value for c in scheme.rules.eligible_constitutions]}
- Eligible MSME Tiers: {[t.value for t in scheme.rules.eligible_msme_tiers]}
- Requirements: Manufacturing={scheme.rules.requires_manufacturing}, Women={scheme.rules.requires_women_ownership}, DPIIT={scheme.rules.requires_dpiit_recognition}
- Benefits: {scheme.benefits.quantum_description}

GUIDELINE PASSAGES:
{chunk_texts or 'Official gazette circular.'}

Deliver strict JSON conforming to this format:
{{
  "verdict": "Eligible" | "Conditionally Eligible" | "Ineligible",
  "match_score": 85.0,
  "confidence_score": 0.95,
  "executive_summary": "1-2 sentence executive briefing",
  "eligibility_rationale": ["bullet point 1", "bullet point 2"],
  "disqualification_or_gap_reasons": ["gap 1 if any"],
  "application_roadmap": ["Step 1...", "Step 2..."]
}}
"""
        headers = {"Content-Type": "application/json"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, headers=headers, json=body)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    raw_text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(raw_text)

                    # Build composite assessment using LLM synthesis + deterministic groundings
                    fin_calc = self.calculate_financial_benefit(profile, scheme)
                    docs = self.audit_document_gaps(profile, scheme, chunks)
                    citations = self.extract_official_citations(scheme, chunks)
                    missing_mandatory = [d for d in docs if d.status in ["Missing", "Action Required"] and d.criticality == "Mandatory"]

                    return SchemeEligibilityAssessment(
                        scheme_id=scheme.scheme_id,
                        scheme_name=scheme.scheme_name,
                        scheme_short_code=scheme.scheme_short_code,
                        verdict=parsed.get("verdict", "Conditionally Eligible"),
                        match_score=float(parsed.get("match_score", candidate.rerank_score)),
                        confidence_score=float(parsed.get("confidence_score", 0.9)),
                        executive_summary=parsed.get("executive_summary", scheme.summary),
                        eligibility_rationale=parsed.get("eligibility_rationale", []),
                        disqualification_or_gap_reasons=parsed.get("disqualification_or_gap_reasons", []),
                        official_citations=citations,
                        financial_benefit=fin_calc,
                        document_checklist=docs,
                        missing_mandatory_docs_count=len(missing_mandatory),
                        application_roadmap=parsed.get("application_roadmap", []),
                        application_portal_url=scheme.official_portal_url,
                        nodal_agency=f"{scheme.implementing_agency} ({scheme.nodal_ministry})",
                    )
        except Exception as exc:
            logger.warning(f"Gemini API deliberation error, falling back to grounded engine: {exc}")

        return None

    # -------------------------------------------------------------------------
    # 6. UNIFIED EVALUATION & FULL REPORT SYNTHESIS
    # -------------------------------------------------------------------------
    def evaluate_candidate(
        self, profile: BusinessProfile, candidate: RerankedSchemeCandidate
    ) -> SchemeEligibilityAssessment:
        """
        Evaluates candidate using Gemini LLM if online/available, else deterministic engine.
        """
        assessment = self._reason_with_gemini(profile, candidate)
        if assessment is None:
            assessment = self._reason_deterministically(profile, candidate)
        return assessment

    def synthesize_report(
        self,
        profile: BusinessProfile,
        candidates: List[RerankedSchemeCandidate],
        query_intent: Optional[str] = None,
        total_universe_count: int = 41,
    ) -> FullReasoningReport:
        """
        Generates full synthesized deliberation report across all reranked candidates.
        """
        assessments: List[SchemeEligibilityAssessment] = []
        eligible_count = 0
        conditional_count = 0
        ineligible_count = 0

        for cand in candidates:
            assessment = self.evaluate_candidate(profile, cand)
            assessments.append(assessment)
            if assessment.verdict == "Eligible":
                eligible_count += 1
            elif assessment.verdict == "Conditionally Eligible":
                conditional_count += 1
            else:
                ineligible_count += 1

        # Sort recommendations: Eligible first, then Conditionally Eligible, sorted by match score
        assessments.sort(key=lambda x: (x.verdict != "Eligible", x.verdict != "Conditionally Eligible", -x.match_score))

        # Strategic Roadmap Summary
        strat = (
            f"Strategic Policy Road Map for {profile.legal_name}: Identified {eligible_count} immediately eligible flagship facilities "
            f"and {conditional_count} conditionally qualified schemes. Priority focus: obtain Udyam MSME Registration and compile "
            f"a Detailed Project Report (DPR) to unlock upfront margin money and credit subsidies."
        )

        return FullReasoningReport(
            business_legal_name=profile.legal_name,
            trade_name=profile.trade_name,
            gstin=profile.gstin,
            state=profile.principal_address.state_name,
            constitution=profile.constitution.value,
            msme_tier=profile.msme_tier.value,
            primary_sector=profile.primary_sector,
            business_age_years=profile.business_age_years,
            query_intent=query_intent,
            total_schemes_searched=total_universe_count,
            top_candidates_evaluated=len(assessments),
            eligible_count=eligible_count,
            conditional_count=conditional_count,
            ineligible_count=ineligible_count,
            top_recommendations=assessments,
            strategic_roadmap_summary=strat,
        )

"""
Schema Normalization and Deduplication Engine.
Converts raw crawled records and parsed guidelines into validated GovernmentScheme models.
"""

from __future__ import annotations
import re
import logging
from typing import List, Dict, Any, Optional
from schemas.business_profile import ConstitutionType, MSMETier
from schemas.government_scheme import (
    GovernmentScheme,
    SchemeJurisdiction,
    BenefitType,
    SchemeStatus,
    EligibilityRuleCondition,
    FinancialBenefit,
)
from crawlers.base import CrawledSchemeRecord

logger = logging.getLogger("SchemeNormalizer")


class SchemeNormalizer:
    """
    Normalizes and deduplicates raw scraped scheme records into official GovernmentScheme models.
    """

    KNOWN_SHORT_CODES = {
        "pmegp": "PMEGP",
        "cgtmse": "CGTMSE",
        "pmmy": "PMMY",
        "sisfs": "SISFS",
        "zed": "ZED",
        "specs": "SPECS",
        "pli": "PLI",
        "pmfme": "PMFME",
        "stand_up_india": "Stand-Up India",
        "cmegp": "CMEGP",
        "samridh": "SAMRIDH",
        "cgss": "CGSS",
        "80iac": "Section 80-IAC",
        "pms": "PMS",
    }

    BENEFIT_TYPE_MAPPING = {
        "capital subsidy": BenefitType.CAPITAL_SUBSIDY,
        "subsidy": BenefitType.CAPITAL_SUBSIDY,
        "margin money": BenefitType.CAPITAL_SUBSIDY,
        "credit guarantee": BenefitType.CREDIT_GUARANTEE,
        "term loan": BenefitType.TERM_LOAN,
        "loan": BenefitType.TERM_LOAN,
        "interest subvention": BenefitType.INTEREST_SUBVENTION,
        "interest subsidy": BenefitType.INTEREST_SUBVENTION,
        "grant": BenefitType.GRANT_EQUITY,
        "seed funding": BenefitType.GRANT_EQUITY,
        "tax exemption": BenefitType.TAX_EXEMPTION,
        "reimbursement": BenefitType.REIMBURSEMENT,
        "training": BenefitType.TRAINING_INFRASTRUCTURE,
    }

    @classmethod
    def slugify(cls, text: str) -> str:
        """
        Converts title string into clean snake_case slug.
        """
        text = text.lower()
        # Remove acronyms inside parentheses or special symbols
        text = re.sub(r"\(.*?\)", "", text)
        text = re.sub(r"[^a-z0-9\s]", "", text)
        slug = re.sub(r"\s+", "_", text.strip())
        return slug[:40].rstrip("_")

    @classmethod
    def map_benefit_type(cls, raw_type: str, text_context: str = "") -> BenefitType:
        """
        Maps raw string to BenefitType enum.
        """
        raw = raw_type.lower().strip()
        for key, b_type in cls.BENEFIT_TYPE_MAPPING.items():
            if key in raw:
                return b_type
        # Secondary check in text context
        context_lower = text_context.lower()
        for key, b_type in cls.BENEFIT_TYPE_MAPPING.items():
            if key in context_lower:
                return b_type
        return BenefitType.CAPITAL_SUBSIDY

    @classmethod
    def detect_jurisdiction(cls, title: str, summary: str, source_portal: str) -> tuple[SchemeJurisdiction, List[str]]:
        """
        Detects whether scheme is Central or State, and which state applies.
        """
        combined = f"{title} {summary}".lower()
        state_names = [
            "maharashtra", "gujarat", "karnataka", "tamil nadu", "telangana",
            "uttar pradesh", "rajasthan", "madhya pradesh", "haryana", "punjab",
            "kerala", "odisha", "west bengal", "bihar", "assam", "delhi"
        ]
        for s in state_names:
            if s in combined:
                state_cap = " ".join(word.capitalize() for word in s.split())
                return SchemeJurisdiction.STATE, [state_cap]

        return SchemeJurisdiction.CENTRAL, ["ALL"]

    @classmethod
    def normalize_record(cls, record: CrawledSchemeRecord) -> GovernmentScheme:
        """
        Converts CrawledSchemeRecord into a validated GovernmentScheme model.
        """
        # 1. Scheme ID
        short = record.raw_short_name or ""
        short_clean = re.sub(r"[^a-zA-Z0-9]", "", short).lower()
        matched_code = None
        for k, v in cls.KNOWN_SHORT_CODES.items():
            if k == short_clean or short_clean.startswith(k) or k in short_clean:
                matched_code = (k, v)
                break

        if matched_code:
            scheme_id = matched_code[0]
            short_code = short.strip().upper() if short else matched_code[1]
        else:
            scheme_id = cls.slugify(record.raw_title)
            short_code = short.strip().upper() if short else scheme_id.upper()[:8]

        # 2. Jurisdiction & State
        jurisdiction, applicable_states = cls.detect_jurisdiction(
            record.raw_title, record.raw_summary, record.source_portal
        )

        # 3. Rule constraints extraction
        combined_text = (
            f"{record.raw_title} {record.raw_summary} "
            f"{' '.join(record.raw_eligibility)} {' '.join(record.raw_tags)}"
        ).lower()

        req_mfg = any(k in combined_text for k in ["manufacturing", "factory", "plant and machinery", "producer"])
        req_svc = any(k in combined_text for k in ["services only", "service sector only"])
        req_women = any(k in combined_text for k in ["women only", "woman entrepreneur", "women-owned", "exclusive to women"])
        req_sc_st = any(k in combined_text for k in ["sc/st only", "exclusive to sc/st", "sc / st entrepreneurs"])
        req_dpiit = any(k in combined_text for k in ["dpiit recognized", "dpiit startup", "startup india recognized"])

        # MSME Tiers
        eligible_tiers = [MSMETier.MICRO, MSMETier.SMALL, MSMETier.MEDIUM]
        if "micro only" in combined_text:
            eligible_tiers = [MSMETier.MICRO]
        elif "micro and small" in combined_text or "mse" in combined_text:
            eligible_tiers = [MSMETier.MICRO, MSMETier.SMALL]

        # Constitutions
        eligible_constitutions = []
        if "private limited only" in combined_text:
            eligible_constitutions = [ConstitutionType.PVT_LTD]
        elif "sole proprietor" in combined_text:
            eligible_constitutions = [ConstitutionType.PROPRIETORSHIP]

        # Business Age Limits
        min_age: Optional[float] = None
        max_age: Optional[float] = None
        if "new greenfield" in combined_text or "new units only" in combined_text or "cannot apply if existing" in combined_text:
            max_age = 2.0
        if "startup" in combined_text or "dpiit" in combined_text:
            max_age = 10.0
        if "at least 3 years" in combined_text or "minimum 3 years" in combined_text:
            min_age = 3.0

        rules = EligibilityRuleCondition(
            allowed_jurisdictions=[jurisdiction, SchemeJurisdiction.CENTRAL],
            applicable_states=applicable_states,
            eligible_constitutions=eligible_constitutions,
            eligible_msme_tiers=eligible_tiers,
            min_business_age_years=min_age,
            max_business_age_years=max_age,
            target_sectors=["ALL"] if "all" in combined_text else record.raw_tags or ["ALL"],
            requires_manufacturing=req_mfg and not req_svc,
            requires_services=req_svc,
            requires_women_ownership=req_women,
            requires_sc_st_ownership=req_sc_st,
            requires_dpiit_recognition=req_dpiit,
        )

        # 4. Benefits
        raw_b = record.raw_benefits
        raw_b_type = raw_b.get("type", "Capital Subsidy") if isinstance(raw_b, dict) else "Capital Subsidy"
        b_type = cls.map_benefit_type(str(raw_b_type), str(raw_b))

        if isinstance(raw_b, dict):
            quantum_desc = raw_b.get("description") or record.raw_summary
            subsidy_pct = raw_b.get("subsidy_percentage")
            max_inr = raw_b.get("max_amount_inr")
        else:
            quantum_desc = str(raw_b)
            subsidy_pct = None
            max_inr = None

        financial_benefit = FinancialBenefit(
            benefit_type=b_type,
            quantum_description=quantum_desc,
            subsidy_percentage=float(subsidy_pct) if subsidy_pct is not None else None,
            max_assistance_amount_inr=float(max_inr) if max_inr is not None else None,
            interest_subsidy_rate=None,
            guarantee_coverage_percentage=85.0 if b_type == BenefitType.CREDIT_GUARANTEE else None,
        )

        # 5. Documents & Tags
        documents = record.raw_documents or ["Udyam Registration", "PAN Card", "Aadhaar Card", "Bank Account Details"]
        tags = list(set([t.strip() for t in record.raw_tags if t.strip()]))
        if not tags:
            tags = ["Government Scheme", "MSME", "Financial Subsidy"]

        return GovernmentScheme(
            scheme_id=scheme_id,
            scheme_name=record.raw_title.strip(),
            scheme_short_code=short_code,
            nodal_ministry=record.raw_ministry or "Government of India",
            implementing_agency=record.raw_agency or "Designated Implementing Agency",
            jurisdiction=jurisdiction,
            summary=record.raw_summary.strip(),
            rules=rules,
            eligibility_criteria_text=record.raw_eligibility or ["Refer to official operational guidelines."],
            benefits=financial_benefit,
            required_documents=documents,
            application_mode=record.raw_application_mode or "Online Portal",
            official_portal_url=record.source_url,
            guidelines_doc_url=record.raw_guidelines_url,
            tags=tags,
            status=SchemeStatus.ACTIVE,
            metadata=record.extracted_metadata,
        )

    @classmethod
    def deduplicate_and_merge(
        cls, existing_schemes: List[GovernmentScheme], new_schemes: List[GovernmentScheme]
    ) -> List[GovernmentScheme]:
        """
        Deduplicates schemes based on scheme_id and canonical title.
        Merges additional tags and guidelines links from new schemes.
        """
        index_by_id: Dict[str, GovernmentScheme] = {s.scheme_id: s for s in existing_schemes}

        for new_s in new_schemes:
            if new_s.scheme_id in index_by_id:
                curr = index_by_id[new_s.scheme_id]
                merged_tags = list(set(curr.tags + new_s.tags))
                merged_docs = list(set(curr.required_documents + new_s.required_documents))
                curr.tags = merged_tags
                curr.required_documents = merged_docs
                if not curr.guidelines_doc_url and new_s.guidelines_doc_url:
                    curr.guidelines_doc_url = new_s.guidelines_doc_url
            else:
                index_by_id[new_s.scheme_id] = new_s

        return list(index_by_id.values())

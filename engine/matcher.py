"""
Deterministic Rule Matching Engine (Stage 1 Filter-First RAG).
Evaluates a BusinessProfile against GovernmentScheme eligibility rules.
Produces structured eligibility verdicts, disqualification reasons, and document checklists.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field

from schemas.business_profile import BusinessProfile, ConstitutionType, MSMETier, SocialCategory
from schemas.government_scheme import GovernmentScheme, SchemeJurisdiction


class SchemeMatchResult(BaseModel):
    scheme_id: str
    scheme_name: str
    scheme_short_code: str
    is_eligible: bool
    status: str = Field(..., description="'Eligible', 'Conditional / Gap Detected', or 'Disqualified'")
    score: float = Field(default=0.0, description="Rule-based relevance/fit score from 0.0 to 100.0")
    matching_criteria: List[str] = Field(default_factory=list)
    disqualification_reasons: List[str] = Field(default_factory=list)
    missing_prerequisites: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    application_portal: str
    quantum_of_benefit: str


class MatchReport(BaseModel):
    profile_legal_name: str
    profile_gstin: Optional[str]
    total_schemes_evaluated: int
    eligible_schemes_count: int
    conditional_schemes_count: int
    disqualified_schemes_count: int
    eligible_schemes: List[SchemeMatchResult] = Field(default_factory=list)
    conditional_schemes: List[SchemeMatchResult] = Field(default_factory=list)
    disqualified_schemes: List[SchemeMatchResult] = Field(default_factory=list)


class DeterministicSchemeMatcher:
    """
    Evaluates business profiles against scheme criteria deterministically.
    """

    @classmethod
    def evaluate_scheme(
        cls, profile: BusinessProfile, scheme: GovernmentScheme
    ) -> SchemeMatchResult:
        rules = scheme.rules
        disqualifications: List[str] = []
        matching_points: List[str] = []
        missing_prereqs: List[str] = []
        score = 50.0  # Base score for valid candidate

        # 1. State / Jurisdiction Check
        is_central = scheme.jurisdiction == SchemeJurisdiction.CENTRAL
        state_match = (
            "ALL" in rules.applicable_states
            or profile.principal_address.state_name in rules.applicable_states
        )
        if not is_central and not state_match:
            disqualifications.append(
                f"State jurisdiction mismatch: Scheme applies to {rules.applicable_states}, but business is registered in {profile.principal_address.state_name}."
            )
        else:
            matching_points.append(
                f"Location match: Scheme applies in {profile.principal_address.state_name} ({scheme.jurisdiction.value} scheme)."
            )
            score += 10.0

        # 2. Constitution / Legal Form Check
        if rules.eligible_constitutions:
            if profile.constitution in rules.eligible_constitutions:
                matching_points.append(
                    f"Entity type match: '{profile.constitution.value}' is an approved constitution."
                )
                score += 10.0
            else:
                disqualifications.append(
                    f"Entity type mismatch: Requires {[c.value for c in rules.eligible_constitutions]}, but business is '{profile.constitution.value}'."
                )

        # 3. Business Age Check
        age = profile.business_age_years
        if rules.max_business_age_years is not None and age > rules.max_business_age_years:
            disqualifications.append(
                f"Business age limit exceeded: Scheme maximum is {rules.max_business_age_years} years, but business age is {age:.1f} years."
            )
        elif rules.min_business_age_years is not None and age < rules.min_business_age_years:
            disqualifications.append(
                f"Minimum operational track record not met: Scheme requires at least {rules.min_business_age_years} years, but business is {age:.1f} years old."
            )
        else:
            matching_points.append(f"Business age ({age:.1f} years) satisfies eligibility constraints.")
            score += 5.0

        # 4. MSME Tier Check
        if profile.msme_tier != MSMETier.UNKNOWN and rules.eligible_msme_tiers:
            if profile.msme_tier in rules.eligible_msme_tiers:
                matching_points.append(f"MSME tier '{profile.msme_tier.value}' is eligible.")
                score += 5.0
            else:
                disqualifications.append(
                    f"MSME tier mismatch: Scheme open to {[t.value for t in rules.eligible_msme_tiers]}, but business tier is '{profile.msme_tier.value}'."
                )

        # 5. Sector / Activity Check
        is_mfg = any("manufacturing" in act.lower() for act in profile.nature_of_activities)
        is_svc = any("service" in act.lower() for act in profile.nature_of_activities)

        if rules.requires_manufacturing and not is_mfg:
            disqualifications.append("Requires active manufacturing operations, but business does not list Manufacturing.")
        if rules.requires_services and not is_svc:
            disqualifications.append("Requires service operations, but business does not list Services.")

        # Sector affinity boost
        if "ALL" not in rules.target_sectors:
            sector_hit = any(
                sec.lower() in profile.primary_sector.lower()
                or profile.primary_sector.lower() in sec.lower()
                for sec in rules.target_sectors
            )
            if sector_hit:
                matching_points.append(f"Target sector alignment: matches '{profile.primary_sector}'.")
                score += 15.0

        # 6. Affirmative / Specific Requirements (Women, SC/ST, DPIIT)
        if rules.requires_women_ownership:
            if profile.is_woman_owned:
                matching_points.append("Woman entrepreneur criteria satisfied.")
                score += 10.0
            else:
                disqualifications.append("Requires woman entrepreneur ownership (business is not woman-owned).")

        if rules.requires_sc_st_ownership:
            if profile.social_category in [SocialCategory.SC, SocialCategory.ST]:
                matching_points.append(f"SC/ST entrepreneur criterion satisfied ({profile.social_category.value}).")
                score += 10.0
            elif profile.social_category in [SocialCategory.GENERAL, SocialCategory.OBC]:
                disqualifications.append(f"Requires SC/ST promoter ownership (business registered under {profile.social_category.value}).")
            else:
                missing_prereqs.append("Requires SC/ST promoter certificate (social category currently unspecified).")

        if rules.requires_dpiit_recognition:
            if profile.is_dpiit_recognized:
                matching_points.append("DPIIT Startup Recognition verified.")
                score += 15.0
            else:
                missing_prereqs.append("Requires official DPIIT Startup Recognition Certificate (can be registered via Startup India portal).")

        # Final Verdict Resolution
        if disqualifications:
            is_eligible = False
            status = "Disqualified"
            score = 0.0
        elif missing_prereqs:
            is_eligible = False
            status = "Conditional / Gap Detected"
            score = min(score, 70.0)
        else:
            is_eligible = True
            status = "Eligible"
            score = min(score, 100.0)

        return SchemeMatchResult(
            scheme_id=scheme.scheme_id,
            scheme_name=scheme.scheme_name,
            scheme_short_code=scheme.scheme_short_code,
            is_eligible=is_eligible,
            status=status,
            score=round(score, 1),
            matching_criteria=matching_points,
            disqualification_reasons=disqualifications,
            missing_prerequisites=missing_prereqs,
            required_documents=scheme.required_documents,
            application_portal=scheme.official_portal_url,
            quantum_of_benefit=scheme.benefits.quantum_description,
        )

    @classmethod
    def match_all(
        cls, profile: BusinessProfile, schemes: List[GovernmentScheme]
    ) -> MatchReport:
        eligible: List[SchemeMatchResult] = []
        conditional: List[SchemeMatchResult] = []
        disqualified: List[SchemeMatchResult] = []

        for scheme in schemes:
            res = cls.evaluate_scheme(profile, scheme)
            if res.status == "Eligible":
                eligible.append(res)
            elif res.status == "Conditional / Gap Detected":
                conditional.append(res)
            else:
                disqualified.append(res)

        # Sort eligible schemes by score descending
        eligible.sort(key=lambda x: x.score, reverse=True)
        conditional.sort(key=lambda x: x.score, reverse=True)

        return MatchReport(
            profile_legal_name=profile.legal_name,
            profile_gstin=profile.gstin,
            total_schemes_evaluated=len(schemes),
            eligible_schemes_count=len(eligible),
            conditional_schemes_count=len(conditional),
            disqualified_schemes_count=len(disqualified),
            eligible_schemes=eligible,
            conditional_schemes=conditional,
            disqualified_schemes=disqualified,
        )

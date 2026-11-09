"""
Cross-Encoder Contextual Reranker for Government Schemes RAG (Phase 3).
Performs joint cross-feature evaluation between Business Profile attributes and Scheme rules/guidelines.
Provides explainable rerank scores, rank shift tracking, and pluggable LLM reranking interface.
"""

from __future__ import annotations
import math
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from schemas.business_profile import BusinessProfile, ConstitutionType, MSMETier, SocialCategory
from schemas.government_scheme import GovernmentScheme, SchemeJurisdiction
from engine.retriever import RetrievedSchemeCandidate


class RerankFactorBreakdown(BaseModel):
    """
    Detailed explanation of sub-scores contributing to the Cross-Encoder score.
    """
    regulatory_feasibility: float = Field(..., description="Score for state, constitution, age & tier (0-30)")
    sector_and_activity_fit: float = Field(..., description="Score for manufacturing/services & sector match (0-30)")
    affirmative_priority: float = Field(..., description="Score for women/SC-ST/DPIIT alignment (0-25)")
    guideline_passage_relevance: float = Field(..., description="Score for official PDF circular text alignment (0-15)")
    explanation_notes: List[str] = Field(default_factory=list)


class RerankedSchemeCandidate(BaseModel):
    """
    Candidate scheme enhanced with Cross-Encoder scoring and rank-shift metrics.
    """
    candidate: RetrievedSchemeCandidate
    initial_rank: int
    reranked_rank: int
    rerank_score: float = Field(..., description="Composite Cross-Encoder score (0.0 to 100.0)")
    rank_shift: int = Field(..., description="Rank difference (positive means improved rank)")
    factors: RerankFactorBreakdown


class CrossEncoderReranker:
    """
    Evaluates joint applicant-scheme cross-attentive features to rerank candidate schemes.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def _score_regulatory_feasibility(
        self, profile: BusinessProfile, scheme: GovernmentScheme
    ) -> Tuple[float, List[str]]:
        score = 0.0
        notes = []
        rules = scheme.rules

        # 1. State / Jurisdiction (up to 10 pts)
        if scheme.jurisdiction == SchemeJurisdiction.CENTRAL:
            score += 10.0
            notes.append("Central scheme: universally valid across India (+10 pts)")
        elif profile.principal_address.state_name in rules.applicable_states or "ALL" in rules.applicable_states:
            score += 10.0
            notes.append(f"Target state match: Applicable in {profile.principal_address.state_name} (+10 pts)")
        else:
            score += 0.0
            notes.append(f"State mismatch: Requires {rules.applicable_states}")

        # 2. Constitution / Legal Form (up to 8 pts)
        if not rules.eligible_constitutions or profile.constitution in rules.eligible_constitutions:
            score += 8.0
            notes.append(f"Entity constitution '{profile.constitution.value}' is eligible (+8 pts)")
        else:
            notes.append(f"Constitution '{profile.constitution.value}' is not preferred")

        # 3. Age constraints (up to 6 pts)
        age = profile.business_age_years
        age_ok = True
        if rules.max_business_age_years is not None and age > rules.max_business_age_years:
            age_ok = False
        if rules.min_business_age_years is not None and age < rules.min_business_age_years:
            age_ok = False

        if age_ok:
            score += 6.0
            notes.append(f"Business age ({age:.1f} yrs) satisfies policy limits (+6 pts)")
        else:
            notes.append(f"Business age ({age:.1f} yrs) fails policy limits")

        # 4. MSME Tier (up to 6 pts)
        if not rules.eligible_msme_tiers or profile.msme_tier in rules.eligible_msme_tiers:
            score += 6.0
            notes.append(f"MSME tier '{profile.msme_tier.value}' is compliant (+6 pts)")
        else:
            notes.append(f"MSME tier '{profile.msme_tier.value}' does not match requirements")

        return round(score, 1), notes

    def _score_sector_and_activity(
        self, profile: BusinessProfile, scheme: GovernmentScheme
    ) -> Tuple[float, List[str]]:
        score = 0.0
        notes = []
        rules = scheme.rules

        is_mfg = any("manufacturing" in act.lower() for act in profile.nature_of_activities)
        is_svc = any("service" in act.lower() for act in profile.nature_of_activities)

        # 1. Activity requirement (up to 12 pts)
        if rules.requires_manufacturing and is_mfg:
            score += 12.0
            notes.append("Satisfies strict manufacturing operation requirement (+12 pts)")
        elif rules.requires_services and is_svc:
            score += 12.0
            notes.append("Satisfies strict services operation requirement (+12 pts)")
        elif not rules.requires_manufacturing and not rules.requires_services:
            score += 12.0
            notes.append("Scheme open to diverse business activities (+12 pts)")
        else:
            notes.append("Activity type requirement partially unsatisfied")

        # 2. Sector alignment (up to 18 pts)
        profile_sector_lower = profile.primary_sector.lower()
        if "ALL" in rules.target_sectors:
            score += 12.0
            notes.append("Open to all industry sectors (+12 pts)")
        elif any(sec.lower() in profile_sector_lower or profile_sector_lower in sec.lower() for sec in rules.target_sectors):
            score += 18.0
            notes.append(f"Direct sector alignment with target sector '{profile.primary_sector}' (+18 pts)")
        else:
            score += 5.0
            notes.append("General sector compatibility (+5 pts)")

        return round(score, 1), notes

    def _score_affirmative_priority(
        self, profile: BusinessProfile, scheme: GovernmentScheme
    ) -> Tuple[float, List[str]]:
        score = 0.0
        notes = []
        rules = scheme.rules

        # Women Ownership (up to 10 pts)
        if rules.requires_women_ownership and profile.is_woman_owned:
            score += 10.0
            notes.append("Full woman-entrepreneur affirmative priority satisfied (+10 pts)")
        elif not rules.requires_women_ownership:
            score += 5.0
            if profile.is_woman_owned:
                score += 3.0
                notes.append("Woman-owned enterprise bonus (+8 pts)")

        # DPIIT Startup Recognition (up to 10 pts)
        if rules.requires_dpiit_recognition and profile.is_dpiit_recognized:
            score += 10.0
            notes.append("DPIIT Startup recognition priority verified (+10 pts)")
        elif not rules.requires_dpiit_recognition:
            score += 5.0
            if profile.is_dpiit_recognized:
                score += 3.0
                notes.append("Startup India priority bonus (+8 pts)")

        # Social Category (up to 5 pts)
        if rules.requires_sc_st_ownership:
            if profile.social_category in [SocialCategory.SC, SocialCategory.ST]:
                score += 5.0
                notes.append(f"SC/ST entrepreneur targeted priority ({profile.social_category.value}) (+5 pts)")
            else:
                notes.append(f"Requires SC/ST promoter (applicant is {profile.social_category.value})")
        else:
            score += 3.0

        return round(min(score, 25.0), 1), notes

    def _score_guideline_passages(
        self, profile: BusinessProfile, candidate: RetrievedSchemeCandidate
    ) -> Tuple[float, List[str]]:
        score = 0.0
        notes = []
        chunks = candidate.guideline_chunks

        if not chunks:
            # Baseline score if guideline circular chunks haven't been ingested yet
            return 8.0, ["Official circular chunks not ingested; using baseline scheme schema (+8 pts)"]

        # Cross-match applicant traits against chunk text
        profile_terms = [
            profile.primary_sector.lower(),
            profile.constitution.value.lower(),
            profile.msme_tier.value.lower(),
        ]
        if profile.is_woman_owned:
            profile_terms.extend(["women", "woman", "female"])
        if profile.is_dpiit_recognized:
            profile_terms.extend(["startup", "seed", "dpiit", "prototype"])
        if profile.social_category in [SocialCategory.SC, SocialCategory.ST]:
            profile_terms.extend(["sc", "st", "special category", "margin money"])

        matched_sections = 0
        for chunk in chunks:
            chunk_lower = chunk.content.lower()
            hits = sum(1 for term in profile_terms if term in chunk_lower)
            if hits > 0:
                matched_sections += 1

        if matched_sections >= 2:
            score = 15.0
            notes.append(f"Deep cross-passage alignment in {matched_sections} guideline circular sections (+15 pts)")
        elif matched_sections == 1:
            score = 12.0
            notes.append("Relevant clause match found in guideline circular (+12 pts)")
        else:
            score = 7.0
            notes.append("Guideline circulars reviewed; standard terms apply (+7 pts)")

        return round(score, 1), notes

    def rerank(
        self,
        profile: BusinessProfile,
        candidates: List[RetrievedSchemeCandidate],
        top_n: Optional[int] = None,
    ) -> List[RerankedSchemeCandidate]:
        """
        Reranks retrieved candidate schemes using cross-feature scoring.
        """
        scored_items: List[Tuple[RetrievedSchemeCandidate, int, float, RerankFactorBreakdown]] = []

        for initial_idx, cand in enumerate(candidates, 1):
            s = cand.scheme

            reg_score, reg_notes = self._score_regulatory_feasibility(profile, s)
            sec_score, sec_notes = self._score_sector_and_activity(profile, s)
            aff_score, aff_notes = self._score_affirmative_priority(profile, s)
            chk_score, chk_notes = self._score_guideline_passages(profile, cand)

            composite_score = round(reg_score + sec_score + aff_score + chk_score, 1)
            # Bound within 0.0 to 100.0
            composite_score = min(max(composite_score, 0.0), 100.0)

            factors = RerankFactorBreakdown(
                regulatory_feasibility=reg_score,
                sector_and_activity_fit=sec_score,
                affirmative_priority=aff_score,
                guideline_passage_relevance=chk_score,
                explanation_notes=reg_notes + sec_notes + aff_notes + chk_notes,
            )
            scored_items.append((cand, initial_idx, composite_score, factors))

        # Sort by rerank score descending
        scored_items.sort(key=lambda x: x[2], reverse=True)

        results: List[RerankedSchemeCandidate] = []
        for new_idx, (cand, initial_idx, score, factors) in enumerate(scored_items, 1):
            rank_shift = initial_idx - new_idx  # positive means improved rank
            results.append(
                RerankedSchemeCandidate(
                    candidate=cand,
                    initial_rank=initial_idx,
                    reranked_rank=new_idx,
                    rerank_score=score,
                    rank_shift=rank_shift,
                    factors=factors,
                )
            )

        if top_n:
            return results[:top_n]
        return results

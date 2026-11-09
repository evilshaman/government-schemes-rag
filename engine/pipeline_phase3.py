"""
Unified Phase 3 Orchestrator: Hybrid Retrieval, Contextual Reranking & LLM Reasoner Pipeline.
Provides an end-to-end interface connecting Business Profile extraction,
Hybrid Retrieval, Cross-Encoder Reranking, and Grounded Document Gap Deliberation.
"""

from __future__ import annotations
import os
import sys
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from schemas.business_profile import BusinessProfile
from schemas.reasoner_schema import FullReasoningReport, SchemeEligibilityAssessment
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore
from engine.retriever import HybridRetriever, RetrievedSchemeCandidate
from engine.reranker import CrossEncoderReranker, RerankedSchemeCandidate
from engine.reasoner import LLMEligibilityReasoner

logger = logging.getLogger("Phase3Pipeline")


class Phase3ReasonerPipeline:
    """
    Coordinates the complete Stage 2 & Stage 3 RAG workflow:
    Retrieval -> Contextual Reranking -> LLM Policy Deliberation & Document Gap Synthesis.
    """

    def __init__(
        self,
        knowledge_store: Optional[SchemeKnowledgeStore] = None,
        vector_store: Optional[SchemeVectorStore] = None,
        api_key: Optional[str] = None,
    ):
        self.store = knowledge_store or SchemeKnowledgeStore()
        self.vector_store = vector_store or SchemeVectorStore()
        self.retriever = HybridRetriever(knowledge_store=self.store, vector_store=self.vector_store)
        self.reranker = CrossEncoderReranker(api_key=api_key)
        self.reasoner = LLMEligibilityReasoner(api_key=api_key)

    def run(
        self,
        profile: BusinessProfile,
        query: Optional[str] = None,
        top_k_retrieve: int = 10,
        top_n_rerank: int = 5,
        apply_hard_filters: bool = True,
    ) -> FullReasoningReport:
        """
        Executes end-to-end Phase 3 pipeline on a BusinessProfile.
        """
        logger.info(f"Starting Phase 3 Pipeline for '{profile.legal_name}'...")
        total_schemes_count = len(self.store.list_schemes(status="Active", limit=500)) or 41

        # 1. Hybrid Retrieval (Dense Semantic + Lexical + RRF)
        retrieved_candidates = self.retriever.retrieve(
            profile=profile,
            query=query,
            top_k=top_k_retrieve,
            apply_hard_filters=apply_hard_filters,
        )
        logger.info(f"Retrieved {len(retrieved_candidates)} candidate schemes via Hybrid RRF.")

        # 2. Cross-Encoder Contextual Reranking
        reranked_candidates = self.reranker.rerank(
            profile=profile,
            candidates=retrieved_candidates,
            top_n=top_n_rerank,
        )
        logger.info(f"Reranked top {len(reranked_candidates)} candidates via Cross-Encoder scoring.")

        # 3. LLM Eligibility Verification & Document Gap Analysis
        report = self.reasoner.synthesize_report(
            profile=profile,
            candidates=reranked_candidates,
            query_intent=query,
            total_universe_count=total_schemes_count,
        )
        logger.info(
            f"Deliberation complete: {report.eligible_count} Eligible, "
            f"{report.conditional_count} Conditional, {report.ineligible_count} Ineligible."
        )

        return report

    @staticmethod
    def render_markdown_report(report: FullReasoningReport) -> str:
        """
        Renders FullReasoningReport as structured GitHub-flavored Markdown.
        """
        lines = [
            f"# Government Schemes Eligibility & Document Gap Analysis Report",
            f"**Generated on:** {report.generated_at}  ",
            f"**Entity Name:** `{report.business_legal_name}`  ",
            f"**Constitution:** {report.constitution} | **State:** {report.state} | **MSME Classification:** {report.msme_tier}  ",
            f"**Primary Sector:** {report.primary_sector} | **Business Age:** {report.business_age_years:.1f} years  ",
            "",
            "---",
            "",
            "## 1. Executive Summary & Policy Road Map",
            f"> {report.strategic_roadmap_summary}",
            "",
            f"- **Total Policy Universe Evaluated:** {report.total_schemes_searched} Schemes",
            f"- **High-Relevance Candidates Audited:** {report.top_candidates_evaluated}",
            f"- **Immediate Qualification (Eligible):** {report.eligible_count}",
            f"- **Conditional Qualification (Actionable Gaps):** {report.conditional_count}",
            f"- **Regulatory Disqualified (Ineligible):** {report.ineligible_count}",
            "",
            "---",
            "",
            "## 2. Top Recommended Schemes",
            "",
        ]

        for idx, item in enumerate(report.top_recommendations, 1):
            badge = "🟢 ELIGIBLE" if item.verdict == "Eligible" else ("🟡 CONDITIONALLY ELIGIBLE" if item.verdict == "Conditionally Eligible" else "🔴 INELIGIBLE")
            lines.extend([
                f"### {idx}. {item.scheme_name} (`{item.scheme_short_code}`)",
                f"**Verdict:** {badge} | **Match Score:** `{item.match_score}/100` | **Confidence:** `{item.confidence_score * 100:.0f}%`  ",
                f"**Nodal Agency:** {item.nodal_agency} | **Official Portal:** [{item.application_portal_url}]({item.application_portal_url})",
                "",
                f"**Executive Brief:** {item.executive_summary}",
                "",
                "#### Financial Benefit Package:",
                f"- **Benefit Category:** {item.financial_benefit.benefit_type}",
                f"- **Quantum Terms:** {item.financial_benefit.quantum_description}",
            ])
            if item.financial_benefit.estimated_eligible_amount_inr:
                lines.append(f"- **Estimated Assistance:** ₹{item.financial_benefit.estimated_eligible_amount_inr:,.2f}")
            if item.financial_benefit.special_affirmative_boost:
                lines.append(f"- **Affirmative Booster:** {item.financial_benefit.special_affirmative_boost}")

            lines.append("")
            lines.append("#### Qualification Rationale & Criteria:")
            for rat in item.eligibility_rationale:
                lines.append(f"- ✅ {rat}")

            if item.disqualification_or_gap_reasons:
                lines.append("")
                lines.append("#### Actionable Regulatory Gaps / Requirements:")
                for gap in item.disqualification_or_gap_reasons:
                    lines.append(f"- ⚠️ {gap}")

            if item.official_citations:
                lines.append("")
                lines.append("#### Official Circular Grounding Citations:")
                for cit in item.official_citations:
                    lines.append(f"> **[{cit.source_document} - {cit.section_or_page}]**: *\"{cit.excerpt}\"*  ")
                    lines.append(f"> *Impact:* {cit.relevance_explanation}")

            lines.append("")
            lines.append(f"#### Mandatory Document Compliance Checklist ({len(item.document_checklist)} Documents Audited):")
            lines.append("| Document Name | Status | Criticality | Issuing Authority | SLA |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for doc in item.document_checklist:
                status_icon = "✅ Available" if doc.status == "Available" else ("⚠️ Missing" if doc.status == "Missing" else "🔄 Action Required")
                lines.append(f"| **{doc.document_name}** | {status_icon} | {doc.criticality} | {doc.issuing_authority} | {doc.estimated_turnaround_days} Days |")

            lines.append("")
            lines.append("#### Step-by-Step Application Roadmap:")
            for step in item.application_roadmap:
                lines.append(f"1. {step}")

            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def print_terminal_report(report: FullReasoningReport):
        """
        Prints a clean, formatted ASCII report to the terminal console.
        """
        print("\n" + "=" * 80)
        print("   GOVERNMENT SCHEMES DISCOVERY & RAG PLATFORM - PHASE 3 REASONER REPORT")
        print("   Multi-Stage Hybrid Retrieval, Cross-Encoder Reranking & LLM Deliberation")
        print("=" * 80)
        print(f" Business Entity    : {report.business_legal_name}")
        print(f" Registration/State : {report.state} (Constitution: {report.constitution})")
        print(f" MSME Classification: {report.msme_tier} | Primary Sector: {report.primary_sector}")
        print(f" Business Age       : {report.business_age_years:.1f} years")
        print("-" * 80)
        print(f" Policy Universe Evaluated : {report.total_schemes_searched} Schemes")
        print(f" High-Relevance Candidates : {report.top_candidates_evaluated}")
        print(f" Verdict Breakdown         : {report.eligible_count} Eligible | {report.conditional_count} Conditional | {report.ineligible_count} Ineligible")
        print("=" * 80)

        for idx, item in enumerate(report.top_recommendations, 1):
            status_tag = f"[{item.verdict.upper()}]"
            print(f"\n{idx}. {item.scheme_name} ({item.scheme_short_code}) {status_tag}")
            print(f"   Match Score : {item.match_score}/100 (Confidence: {item.confidence_score * 100:.0f}%)")
            print(f"   Nodal Portal: {item.application_portal_url}")
            print(f"   Benefit     : {item.financial_benefit.quantum_description}")
            if item.financial_benefit.special_affirmative_boost:
                print(f"   Incentive   : {item.financial_benefit.special_affirmative_boost}")
            
            print("   Eligibility Checks:")
            for r in item.eligibility_rationale[:3]:
                print(f"     * [PASS] {r}")
            for g in item.disqualification_or_gap_reasons[:2]:
                print(f"     * [GAP]  {g}")

            missing_docs = [d for d in item.document_checklist if d.status in ["Missing", "Action Required"]]
            if missing_docs:
                print(f"   Actionable Document Gaps ({len(missing_docs)} required):")
                for d in missing_docs[:3]:
                    print(f"     - {d.document_name} -> Authority: {d.issuing_authority} (Est: {d.estimated_turnaround_days} days)")
                    print(f"       Action: {d.how_to_obtain}")
            else:
                print("   Document Checklist: All mandatory core documents verified.")

        print("\n" + "=" * 80)
        print(f" Strategic Road Map Summary:\n {report.strategic_roadmap_summary}")
        print("=" * 80 + "\n")

"""
Policy Copilot Chat API Route.
Provides an interactive AI chat assistant grounded in the official schemes knowledge base.
Features:
- Global general policy Q&A with hybrid vector search.
- Scheme-Scoped Chat: Directly anchors the conversation on a specific scheme candidate from Document Matching.
- Full Document Gap Analysis & Remediation in conversational responses.
- Out-of-Domain Guardrail: Rejects programming code, jokes, or non-policy queries.
- Semantic Relevance Thresholding: Prevents greedy, low-confidence scheme citations.
"""

from __future__ import annotations
import os
import re
import json
import logging
import httpx
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from schemas.business_profile import BusinessProfile
from schemas.government_scheme import GovernmentScheme
from schemas.reasoner_schema import DocumentGapItem
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore
from engine.reasoner import LLMEligibilityReasoner
from api.dependencies import get_knowledge_store, get_vector_store, get_eligibility_reasoner
from api.middleware import limiter
from core.config import settings

logger = logging.getLogger("ChatAPI")
router = APIRouter(prefix="/api/chat", tags=["Policy Copilot"])

# Minimum cosine relevance threshold required to consider a scheme citation relevant
MIN_RELEVANCE_THRESHOLD = 0.18

# Patterns for out-of-scope intent classification
OUT_OF_SCOPE_PATTERNS = [
    # Code generation & programming
    r"\b(write|create|generate|show|debug|give)\s+(a\s+)?(code|program|script|function|class|regex|sql)\b",
    r"\b(hello\s*world)\b",
    r"\b(in\s+(c|c\+\+|cpp|python|java|javascript|typescript|rust|go|php|html|css|ruby))\b",
    r"\b(write\s+(a\s+)?(poem|story|song|essay|joke|riddle))\b",
    r"\b(weather\s+in|recipe\s+for|who\s+won|movie\s+review)\b",
]

POLICY_KEYWORDS = [
    "scheme", "subsidy", "loan", "grant", "msme", "pmegp", "dpiit", "startup",
    "udyam", "tax", "gst", "cgtmse", "mudra", "standup", "interest", "incentive",
    "financial", "capital", "seed", "government", "ministry", "kvic", "sidbi", "specs", "zed", "clcss", "gap"
]


def detect_out_of_scope_query(text: str) -> Optional[str]:
    """
    Identifies if a query is clearly out of domain (coding tasks, creative writing, non-policy general trivia).
    """
    lower = text.lower().strip()
    
    # Check if query contains explicit policy keywords; if so, let it pass through
    has_policy_intent = any(term in lower for term in POLICY_KEYWORDS)
    if has_policy_intent:
        return None

    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, lower):
            return (
                "I am the **Government Schemes & MSME Policy Copilot**, specialized exclusively in Indian government "
                "subsidies, credit facilities, business registration (GST/Udyam), and grant eligibility.\n\n"
                "I cannot assist with general programming, code generation, or topics outside government policy and enterprise finance.\n\n"
                "*Note:* If your business operates in software development, electronics, or IT services, I can help you find relevant government programs such as the **SPECS Scheme** (Electronics Manufacturing), **SAMRIDH Accelerator**, or **Startup India Seed Fund Scheme**."
            )
    return None


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's policy or subsidy question")
    scheme_id: Optional[str] = Field(None, description="Optional target scheme ID to anchor discussion strictly to one scheme")
    history: List[ChatMessage] = Field(default_factory=list)
    profile: Optional[BusinessProfile] = Field(None, description="Optional loaded profile for contextual personalization")


class CitedSchemeBadge(BaseModel):
    scheme_id: str
    scheme_name: str
    scheme_short_code: str
    official_portal_url: str
    benefit_summary: str


class ChatResponse(BaseModel):
    reply: str
    cited_schemes: List[CitedSchemeBadge]
    suggested_actions: List[str]


@router.post("", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat_with_copilot(
    request: Request,
    req: ChatRequest,
    store: SchemeKnowledgeStore = Depends(get_knowledge_store),
    vector_store: SchemeVectorStore = Depends(get_vector_store),
    reasoner: LLMEligibilityReasoner = Depends(get_eligibility_reasoner),
):
    """
    Delivers a grounded conversational answer using hybrid vector retrieval and guideline chunks.
    Supports Scheme-Scoped discussions (when scheme_id is passed) and Global Policy search.
    """
    query = req.message.strip()

    # 1. Out-of-Domain Guardrail Check (only if not already scoped to a scheme)
    if not req.scheme_id:
        ood_reply = detect_out_of_scope_query(query)
        if ood_reply:
            return ChatResponse(
                reply=ood_reply,
                cited_schemes=[],
                suggested_actions=[
                    "Explore Startup India Seed Fund",
                    "Check SPECS (Electronics & IT)",
                    "Upload GST Certificate for Instant Matching",
                ],
            )

    cited_badges: List[CitedSchemeBadge] = []
    grounding_texts: List[str] = []
    target_scheme: Optional[GovernmentScheme] = None

    # Track real-time audited document gaps
    doc_gaps: List[DocumentGapItem] = []
    missing_docs: List[DocumentGapItem] = []
    available_docs: List[DocumentGapItem] = []

    # -------------------------------------------------------------------------
    # 2. Scheme-Scoped Focus (Anchored directly to a user-selected scheme card)
    # -------------------------------------------------------------------------
    if req.scheme_id:
        target_scheme = store.get_scheme(req.scheme_id)
        if target_scheme:
            cited_badges.append(
                CitedSchemeBadge(
                    scheme_id=target_scheme.scheme_id,
                    scheme_name=target_scheme.scheme_name,
                    scheme_short_code=target_scheme.scheme_short_code,
                    official_portal_url=target_scheme.official_portal_url,
                    benefit_summary=target_scheme.benefits.quantum_description,
                )
            )
            chunks = store.get_document_chunks_for_scheme(target_scheme.scheme_id)
            chunk_excerpts = " ".join([c.content for c in chunks[:4]])

            # Audit document compliance in real time against the applicant's profile
            if req.profile:
                doc_gaps = reasoner.audit_document_gaps(req.profile, target_scheme, chunks)
                missing_docs = [d for d in doc_gaps if d.status in ["Missing", "Action Required"]]
                available_docs = [d for d in doc_gaps if d.status == "Available"]

            gap_grounding = ""
            if doc_gaps:
                gap_grounding = (
                    f"\nAPPLICANT COMPLIANCE AUDIT FOR {req.profile.legal_name if req.profile else 'Applicant'}:\n"
                    f"- Actionable Document Gaps ({len(missing_docs)} Pending): " +
                    "; ".join([f"{d.document_name} [{d.status}] - Authority: {d.issuing_authority}, SLA: {d.estimated_turnaround_days}d, Action: {d.how_to_obtain}" for d in missing_docs]) +
                    f"\n- Already Verified Documents ({len(available_docs)}): " +
                    ", ".join([d.document_name for d in available_docs])
                )

            grounding_texts.append(
                f"FOCUSED SCHEME: {target_scheme.scheme_name} [{target_scheme.scheme_short_code}]\n"
                f"- Implementing Agency: {target_scheme.implementing_agency} ({target_scheme.nodal_ministry})\n"
                f"- Jurisdiction: {target_scheme.jurisdiction.value} | States: {', '.join(target_scheme.rules.applicable_states)}\n"
                f"- Benefit Type: {target_scheme.benefits.benefit_type.value}\n"
                f"- Financial Quantum & Assistance: {target_scheme.benefits.quantum_description}\n"
                f"- Subsidy %: {target_scheme.benefits.subsidy_percentage or 'N/A'}% | Ceiling: ₹{target_scheme.benefits.max_assistance_amount_inr:,.0f}\n"
                f"- Eligible Constitutions: {', '.join([c.value for c in target_scheme.rules.eligible_constitutions])}\n"
                f"- Eligible MSME Tiers: {', '.join([t.value for t in target_scheme.rules.eligible_msme_tiers])}\n"
                f"- Key Criteria: {'; '.join(target_scheme.eligibility_criteria_text)}\n"
                f"- Mandatory Documents: {', '.join(target_scheme.required_documents)}\n"
                f"- Official Portal: {target_scheme.official_portal_url}\n"
                f"- Circular Guidelines: {chunk_excerpts or 'Official Gazette notification.'}"
                f"{gap_grounding}"
            )

    # -------------------------------------------------------------------------
    # 3. Global Hybrid Vector Search (if not scoped to a scheme)
    # -------------------------------------------------------------------------
    if not target_scheme:
        state = req.profile.principal_address.state_name if req.profile else None
        entity = req.profile.constitution.value if req.profile else None
        tier = req.profile.msme_tier.value if req.profile and req.profile.msme_tier.value != "Unknown" else None

        raw_hits = vector_store.hybrid_search(
            query=query,
            state=state,
            entity_type=entity,
            msme_tier=tier,
            top_k=5,
        )

        search_hits = [hit for hit in raw_hits if hit.similarity_score >= MIN_RELEVANCE_THRESHOLD][:3]

        for hit in search_hits:
            scheme = store.get_scheme(hit.scheme_id)
            if scheme:
                cited_badges.append(
                    CitedSchemeBadge(
                        scheme_id=scheme.scheme_id,
                        scheme_name=scheme.scheme_name,
                        scheme_short_code=scheme.scheme_short_code,
                        official_portal_url=scheme.official_portal_url,
                        benefit_summary=scheme.benefits.quantum_description,
                    )
                )
                chunks = store.get_document_chunks_for_scheme(scheme.scheme_id)
                chunk_excerpts = " ".join([c.content[:200] for c in chunks[:2]])

                grounding_texts.append(
                    f"SCHEME: {scheme.scheme_name} [{scheme.scheme_short_code}]\n"
                    f"- Nodal Ministry: {scheme.nodal_ministry}\n"
                    f"- Benefit: {scheme.benefits.quantum_description}\n"
                    f"- Eligibility: {'; '.join(scheme.eligibility_criteria_text[:3])}\n"
                    f"- Required Documents: {', '.join(scheme.required_documents[:4])}\n"
                    f"- Application Mode: {scheme.application_mode}\n"
                    f"- Application Process Steps: {'; '.join(scheme.application_process[:5]) if scheme.application_process else 'Refer to official portal steps.'}\n"
                    f"- Portal: {scheme.official_portal_url}\n"
                    f"- Guideline Circular Excerpts: {chunk_excerpts or 'Official gazette circular.'}"
                )

    knowledge_context = "\n\n".join(grounding_texts)

    # -------------------------------------------------------------------------
    # 4. LLM Generation via Gemini (when GEMINI_API_KEY is configured)
    # -------------------------------------------------------------------------
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if api_key and grounding_texts:
        if target_scheme:
            system_instruction = (
                f"You are the official Government Schemes AI Copilot discussing the specific scheme '{target_scheme.scheme_name}' ({target_scheme.scheme_short_code}). "
                "Answer the user's question clearly, authoritatively, and in detail citing exact subsidy percentages, caps, and mandatory documents. "
                "If the user asks about document gaps, why they are conditional, or how to qualify, use the APPLICANT COMPLIANCE AUDIT provided to list the exact missing documents, issuing authorities, and how-to-obtain steps. "
                "Use ONLY the verified policy grounding provided. If applicant profile context is provided, personalize your advice."
            )
        else:
            system_instruction = (
                "You are the official Government Schemes AI Copilot. "
                "Answer the user's question clearly and authoritatively, citing exact subsidy percentages, caps, and mandatory documents. "
                "Use ONLY the verified policy grounding provided. If applicant profile context is provided, personalize your advice."
            )

        user_content = f"APPLICANT PROFILE CONTEXT:\n{req.profile.model_dump_json() if req.profile else 'No profile uploaded yet.'}\n\n"
        user_content += f"GOVERNMENT POLICY GROUNDING:\n{knowledge_context}\n\n"
        user_content += f"USER QUESTION: {query}"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": f"{system_instruction}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600},
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    llm_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    default_actions = [
                        f"Apply on {target_scheme.scheme_short_code} Portal" if target_scheme else "Check document gap analysis checklist",
                        "Verify Udyam MSME registration",
                        "Access official nodal application portal",
                    ]
                    return ChatResponse(
                        reply=llm_text,
                        cited_schemes=cited_badges,
                        suggested_actions=default_actions,
                    )
        except Exception as exc:
            logger.warning(f"Gemini API chat call failed, using deterministic grounded synthesis: {exc}")

    # -------------------------------------------------------------------------
    # 5. Deterministic Grounded Policy Answer Fallback
    # -------------------------------------------------------------------------
    if not cited_badges:
        reply = (
            f"Based on official government notifications, no direct policy or subsidy match was found for \"{query}\".\n\n"
            "To get accurate recommendations, please specify:\n"
            "- Your **industry sector** (e.g. *Food Processing*, *Textiles*, *Electronics*, *Renewable Energy*)\n"
            "- Your **funding requirement** (e.g. *Credit Guarantee*, *Capital Subsidy*, *Working Capital*, *Seed Grant*)\n"
            "- Or upload your **GST REG-06 / Udyam Certificate** for automated policy matching."
        )
        actions = ["Browse All 41 Schemes", "Upload GST Certificate for Instant Matching", "Explore Credit Guarantee (CGTMSE)"]

    elif target_scheme:
        # Scheme-Scoped Deep Advisory
        q_lower = query.lower()

        is_gap_or_report_query = any(w in q_lower for w in [
            "gap", "report", "analysis", "audit", "checklist", "missing", "document", 
            "obtain", "paperwork", "certificate", "invoice", "action", "list", "dpr"
        ])
        is_why_eligibility_query = any(w in q_lower for w in [
            "why", "not eligible", "not eligibile", "conditional", "qualif", "score", 
            "fit", "verdict", "disqualif", "reject", "pass", "fail"
        ])
        is_subsidy_calc_query = any(w in q_lower for w in [
            "subsidy", "calculat", "amount", "margin", "money", "how much", "rate", 
            "percent", "cap", "ceiling", "inr", "crore", "lakh", "loan"
        ])
        is_application_query = any(w in q_lower for w in [
            "how to apply", "apply", "process", "step", "portal", "submit", "procedure"
        ])

        # ---------------------------------------------------------------------
        # Branch 1: Document Gap Analysis & Remediation
        # ---------------------------------------------------------------------
        if is_gap_or_report_query and not is_why_eligibility_query:
            reply_lines = [
                f"### Document Gap & Compliance Analysis for **{target_scheme.scheme_name}** (`{target_scheme.scheme_short_code}`)",
                "",
                f"Administered by **{target_scheme.implementing_agency}** under the **{target_scheme.nodal_ministry}**.",
                "",
            ]
            if req.profile:
                reply_lines.append(f"**Target Business Entity:** `{req.profile.legal_name}` ({req.profile.principal_address.state_name} | {req.profile.constitution.value} | {req.profile.msme_tier.value} tier)")
                reply_lines.append(f"**Current Status:** {'**Conditionally Eligible** - Requires bridging ' + str(len(missing_docs)) + ' actionable document gap(s).' if missing_docs else '**Fully Document Compliant** - Ready for application filing!'}")
                reply_lines.append("")

            if missing_docs:
                reply_lines.append(f"#### Actionable Document Gaps to Resolve ({len(missing_docs)} Pending):")
                reply_lines.append("")
                for idx, doc in enumerate(missing_docs, 1):
                    reply_lines.extend([
                        f"{idx}. **{doc.document_name}** `[{doc.status.upper()}]`",
                        f"   - **Issuing Authority:** {doc.issuing_authority}",
                        f"   - **Estimated Turnaround (SLA):** ~{doc.estimated_turnaround_days} working days",
                        f"   - **How to Obtain:** {doc.how_to_obtain}",
                        f"   - **Prerequisites:** {', '.join(doc.prerequisites) if doc.prerequisites else 'Standard KYC documents'}",
                        "",
                    ])
            else:
                reply_lines.append("#### [VERIFIED] All Mandatory Scheme Documents on File!")
                reply_lines.append("")

            if available_docs:
                reply_lines.append("#### Verified Documents Already on File:")
                for doc in available_docs:
                    reply_lines.append(f"- [VERIFIED] **{doc.document_name}** (Verified from your uploaded registration document)")
                reply_lines.append("")

            reply_lines.append(f"Official Application Portal: [{target_scheme.official_portal_url}]({target_scheme.official_portal_url})")

            actions = [
                f"Apply on {target_scheme.scheme_short_code} Portal",
                f"Calculate {target_scheme.scheme_short_code} Subsidy Amount",
                "Why am I Conditionally Eligible?",
            ]

        # ---------------------------------------------------------------------
        # Branch 2: "Why am I not eligible / Why conditional?"
        # ---------------------------------------------------------------------
        elif is_why_eligibility_query:
            reply_lines = [
                f"### Qualification & Eligibility Deliberation for **{target_scheme.scheme_name}** (`{target_scheme.scheme_short_code}`)",
                "",
                f"Administered by **{target_scheme.implementing_agency}** under the **{target_scheme.nodal_ministry}**.",
                "",
            ]
            if req.profile:
                state_ok = "ALL" in target_scheme.rules.applicable_states or req.profile.principal_address.state_name in target_scheme.rules.applicable_states
                const_ok = not target_scheme.rules.eligible_constitutions or req.profile.constitution in target_scheme.rules.eligible_constitutions
                tier_ok = not target_scheme.rules.eligible_msme_tiers or req.profile.msme_tier in target_scheme.rules.eligible_msme_tiers
                all_rules_pass = state_ok and const_ok and tier_ok

                if all_rules_pass and missing_docs:
                    reply_lines.extend([
                        f"You are **not disqualified**! Your business structure **passes** all core government eligibility checks:",
                        f"- **State Jurisdiction ({req.profile.principal_address.state_name}):** `[PASS]` Verified eligible in {req.profile.principal_address.state_name}.",
                        f"- **Legal Constitution ({req.profile.constitution.value}):** `[PASS]` Approved entity type.",
                        f"- **MSME Classification ({req.profile.msme_tier.value}):** `[PASS]` Scope qualified.",
                        "",
                        f"#### Why You Are Marked 'Conditionally Eligible':",
                        f"You cannot be marked 100% 'Fully Eligible' yet because this scheme mandates **{len(missing_docs)} operational document(s)** that must be submitted with your application:",
                        "",
                    ])
                    for idx, doc in enumerate(missing_docs, 1):
                        reply_lines.append(f"{idx}. **{doc.document_name}** (`{doc.status}` | SLA: ~{doc.estimated_turnaround_days}d)")
                        reply_lines.append(f"   *Action Required:* {doc.how_to_obtain}")
                    reply_lines.extend([
                        "",
                        f"Once you fulfill these {len(missing_docs)} document requirements, your application unlocks full eligibility for the **{target_scheme.benefits.quantum_description}**.",
                    ])
                elif not all_rules_pass:
                    reply_lines.extend([
                        "**Eligibility Constraint Discovered:**",
                        f"- State: {'[PASS]' if state_ok else '[FAIL] State not in ' + str(target_scheme.rules.applicable_states)}",
                        f"- Constitution: {'[PASS]' if const_ok else '[FAIL] Scheme requires ' + str([c.value for c in target_scheme.rules.eligible_constitutions])}",
                        f"- Tier: {'[PASS]' if tier_ok else '[FAIL] Scheme requires ' + str([t.value for t in target_scheme.rules.eligible_msme_tiers])}",
                    ])
            else:
                reply_lines.extend([
                    "**Core Regulatory Criteria:**",
                    f"- **Applicable States:** {', '.join(target_scheme.rules.applicable_states)}",
                    f"- **Eligible Legal Entities:** {', '.join([c.value for c in target_scheme.rules.eligible_constitutions])}",
                    f"- **Eligible MSME Tiers:** {', '.join([t.value for t in target_scheme.rules.eligible_msme_tiers])}",
                    f"- **Mandatory Documents Required:** {', '.join(target_scheme.required_documents)}.",
                ])

            reply_lines.append("")
            reply_lines.append(f"Official Application Portal: [{target_scheme.official_portal_url}]({target_scheme.official_portal_url})")

            actions = [
                "Show Document Gap Action Steps",
                f"Calculate {target_scheme.scheme_short_code} Subsidy",
                f"Go to {target_scheme.scheme_short_code} Portal",
            ]

        # ---------------------------------------------------------------------
        # Branch 3: Financial Subsidy Quantum & Calculation
        # ---------------------------------------------------------------------
        elif is_subsidy_calc_query:
            reply_lines = [
                f"### Financial Assistance Quantum for **{target_scheme.scheme_name}** (`{target_scheme.scheme_short_code}`)",
                "",
                f"**Assistance Category:** {target_scheme.benefits.benefit_type.value}",
                f"**Financial Formula:**\n{target_scheme.benefits.quantum_description}",
                "",
                "**Assistance Ceilings & Rates:**",
                f"- **Maximum Assistance Cap:** ₹{target_scheme.benefits.max_assistance_amount_inr:,.0f}" if target_scheme.benefits.max_assistance_amount_inr else "- Maximum Assistance Cap: Subject to approved project cost appraisal",
                f"- **Subsidy Rate:** {target_scheme.benefits.subsidy_percentage}%" if target_scheme.benefits.subsidy_percentage else "- Subsidy Rate: Tiered based on enterprise category and location",
            ]
            if target_scheme.rules.requires_women_ownership or target_scheme.rules.requires_sc_st_ownership:
                reply_lines.append("- **Affirmative Boost:** Higher subsidy rates and reduced promoter contribution apply for women and SC/ST promoters.")

            reply_lines.extend([
                "",
                f"Official Application Guidelines: [{target_scheme.official_portal_url}]({target_scheme.official_portal_url})",
            ])
            actions = [
                f"Apply for {target_scheme.scheme_short_code} Subsidy",
                "Review Mandatory Document Gaps",
                "Why am I Conditionally Eligible?",
            ]

        # ---------------------------------------------------------------------
        # Branch 4: Application Roadmap & Steps
        # ---------------------------------------------------------------------
        elif is_application_query:
            reply_lines = [
                f"### Application Roadmap for **{target_scheme.scheme_name}** (`{target_scheme.scheme_short_code}`)",
                "",
                f"Administered by **{target_scheme.implementing_agency}** under the **{target_scheme.nodal_ministry}**.",
                f"**Application Mode:** {target_scheme.application_mode}",
                "",
            ]
            if target_scheme.application_process:
                reply_lines.append("**Official Step-by-Step Application Procedure:**")
                for step in target_scheme.application_process:
                    reply_lines.append(f"- {step}")
                reply_lines.append("")
            else:
                reply_lines.extend([
                    "**Step-by-Step Filing Roadmap:**",
                    "1. **Step 1 (Prerequisites):** Procure valid Udyam Registration Certificate and business PAN.",
                    "2. **Step 2 (DPR Preparation):** Prepare a Detailed Project Report detailing technical specifications, machinery quotes, and cash flow projections.",
                    "3. **Step 3 (Vendor Quotations):** Obtain competitive proforma invoices on OEM vendor letterhead with GSTIN numbers.",
                    f"4. **Step 4 (Online Submission):** Access the official portal at [{target_scheme.official_portal_url}]({target_scheme.official_portal_url}) and submit your application with supporting proofs.",
                    "5. **Step 5 (Sanction & Disbursement):** Nodal agency and partner bank appraise application and disburse capital subsidy / margin money.",
                    "",
                ])
            reply_lines.append(f"Official Application Portal: [{target_scheme.official_portal_url}]({target_scheme.official_portal_url})")
            actions = [
                f"Show Document Gaps for {target_scheme.scheme_short_code}",
                f"Go to {target_scheme.scheme_short_code} Application Portal",
                "Calculate Subsidy Quantum",
            ]

        # ---------------------------------------------------------------------
        # Branch 5: General Scheme Overview (Default)
        # ---------------------------------------------------------------------
        else:
            reply_lines = [
                f"### Overview of **{target_scheme.scheme_name}** (`{target_scheme.scheme_short_code}`)",
                "",
                f"Administered by **{target_scheme.implementing_agency}** under the **{target_scheme.nodal_ministry}**.",
                "",
                f"**Financial Benefit:**\n{target_scheme.benefits.quantum_description}",
                "",
                "**Key Qualifying Criteria:**",
            ]
            for crit in target_scheme.eligibility_criteria_text[:4]:
                reply_lines.append(f"- {crit}")

            if missing_docs:
                reply_lines.extend([
                    "",
                    f"**Actionable Document Gaps for Your Business:** {len(missing_docs)} pending ({', '.join([d.document_name for d in missing_docs])}). Ask *'Show my gap list'* to see step-by-step guidance.",
                ])

            reply_lines.extend([
                "",
                f"Official Application Portal: [{target_scheme.official_portal_url}]({target_scheme.official_portal_url})",
            ])
            actions = [
                f"Show Document Gap List for {target_scheme.scheme_short_code}",
                f"Why am I Conditionally Eligible?",
                f"How is the subsidy calculated?",
            ]

        reply = "\n".join(reply_lines)

    else:
        # Global scheme match response
        top_scheme = store.get_scheme(cited_badges[0].scheme_id)
        reply_lines = [
            f"### Policy Findings for: *\"{query}\"*",
            "",
            f"The primary relevant government policy is the **{top_scheme.scheme_name}** (`{top_scheme.scheme_short_code}`) "
            f"administered by the **{top_scheme.nodal_ministry}**.",
            "",
            f"**Financial Assistance Quantum:**\n{top_scheme.benefits.quantum_description}",
            "",
            "**Key Qualifying Criteria:**",
        ]
        for crit in top_scheme.eligibility_criteria_text[:3]:
            reply_lines.append(f"- {crit}")

        if top_scheme.required_documents:
            reply_lines.append("")
            reply_lines.append(f"**Mandatory Documents Required:** {', '.join(top_scheme.required_documents[:4])}.")

        reply_lines.append("")
        reply_lines.append(f"Official Application Portal: [{top_scheme.official_portal_url}]({top_scheme.official_portal_url})")

        reply = "\n".join(reply_lines)
        actions = [
            f"Apply on {top_scheme.scheme_short_code} Portal",
            "Run Full Document Gap Deliberation",
            "Prepare Detailed Project Report (DPR)",
        ]

    return ChatResponse(
        reply=reply,
        cited_schemes=cited_badges,
        suggested_actions=actions,
    )

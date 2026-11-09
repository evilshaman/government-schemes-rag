"""
Policy Copilot Chat API Route.
Provides an interactive AI chat assistant grounded in the official schemes knowledge base.
Answers specific queries with policy citations, margin money subsidy calculations, and application advice.
"""

from __future__ import annotations
import os
import json
import logging
import httpx
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from schemas.business_profile import BusinessProfile
from schemas.government_scheme import GovernmentScheme
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore
from api.dependencies import get_knowledge_store, get_vector_store

logger = logging.getLogger("ChatAPI")
router = APIRouter(prefix="/api/chat", tags=["Policy Copilot"])


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's policy or subsidy question")
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
async def chat_with_copilot(
    req: ChatRequest,
    store: SchemeKnowledgeStore = Depends(get_knowledge_store),
    vector_store: SchemeVectorStore = Depends(get_vector_store),
):
    """
    Delivers a grounded conversational answer using hybrid vector retrieval and guideline chunks.
    """
    query = req.message.strip()

    # Retrieve relevant schemes
    state = req.profile.principal_address.state_name if req.profile else None
    entity = req.profile.constitution.value if req.profile else None
    tier = req.profile.msme_tier.value if req.profile and req.profile.msme_tier.value != "Unknown" else None

    search_hits = vector_store.hybrid_search(
        query=query,
        state=state,
        entity_type=entity,
        msme_tier=tier,
        top_k=3,
    )

    cited_badges: List[CitedSchemeBadge] = []
    grounding_texts: List[str] = []

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
            # Fetch chunks if available
            chunks = store.get_document_chunks_for_scheme(scheme.scheme_id)
            chunk_excerpts = " ".join([c.content[:200] for c in chunks[:2]])

            grounding_texts.append(
                f"SCHEME: {scheme.scheme_name} [{scheme.scheme_short_code}]\n"
                f"- Nodal Ministry: {scheme.nodal_ministry}\n"
                f"- Benefit: {scheme.benefits.quantum_description}\n"
                f"- Eligibility: {'; '.join(scheme.eligibility_criteria_text[:3])}\n"
                f"- Required Documents: {', '.join(scheme.required_documents[:4])}\n"
                f"- Portal: {scheme.official_portal_url}\n"
                f"- Guideline Circular Excerpts: {chunk_excerpts or 'Official gazette circular.'}"
            )

    knowledge_context = "\n\n".join(grounding_texts)

    # Check for Gemini API key
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if api_key and grounding_texts:
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
                    return ChatResponse(
                        reply=llm_text,
                        cited_schemes=cited_badges,
                        suggested_actions=[
                            "Check document gap analysis checklist",
                            "Verify Udyam MSME registration",
                            "Access official nodal application portal",
                        ],
                    )
        except Exception as exc:
            logger.warning(f"Gemini API chat call failed, using deterministic grounded synthesis: {exc}")

    # Deterministic Grounded Policy Answer Fallback
    if not cited_badges:
        reply = (
            f"Based on official government notifications, no direct policy match was found for \"{query}\". "
            "Try specifying your sector (e.g. 'Food Processing', 'Textiles', 'Electronics') or funding requirement "
            "(e.g. 'Credit Guarantee', 'Capital Subsidy', 'Seed Grant')."
        )
        actions = ["Browse All 41 Schemes", "Upload GST Certificate for Instant Matching"]
    else:
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

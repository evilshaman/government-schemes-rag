"""
LLM Deliberation & Document Gap Analysis API Routes (Phase 3 Engine).
Provides endpoints for:
- End-to-end deliberation on a BusinessProfile (Retrieval -> Reranking -> Reasoner).
- Exporting synthesized analysis reports as formatted Markdown.
"""

from __future__ import annotations
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field

from schemas.business_profile import BusinessProfile
from schemas.reasoner_schema import FullReasoningReport
from engine.pipeline_phase3 import Phase3ReasonerPipeline
from api.dependencies import get_reasoner_pipeline
from api.middleware import limiter
from core.config import settings

logger = logging.getLogger("ReasonerAPI")
router = APIRouter(prefix="/api/schemes", tags=["Eligibility Reasoner & Gap Analysis"])


class DeliberateRequest(BaseModel):
    profile: BusinessProfile = Field(..., description="Target business digital twin extracted from documents")
    query: Optional[str] = Field(None, description="Optional strategic query or funding objective")
    top_k: int = Field(default=5, ge=1, le=15, description="Number of top reranked schemes to assess")
    apply_hard_filters: bool = Field(default=True, description="Enforce strict state and entity pre-filters")


class MarkdownExportResponse(BaseModel):
    file_name: str
    markdown_content: str


@router.post("/deliberate", response_model=FullReasoningReport)
@limiter.limit(settings.RATE_LIMIT_ANALYZE)
async def deliberate_on_profile(
    request: Request,
    req: DeliberateRequest,
    pipeline: Phase3ReasonerPipeline = Depends(get_reasoner_pipeline),
):
    """
    Executes the end-to-end Phase 3 Pipeline:
    1. Hybrid multi-channel candidate retrieval with Reciprocal Rank Fusion (RRF).
    2. Contextual Cross-Encoder reranking across regulatory, sectoral, affirmative, and guideline factors.
    3. Grounded LLM reasoning, financial benefit quantum calculation, and document gap analysis.
    """
    try:
        report = pipeline.run(
            profile=req.profile,
            query=req.query,
            top_k_retrieve=max(req.top_k * 2, 8),
            top_n_rerank=req.top_k,
            apply_hard_filters=req.apply_hard_filters,
        )
        return report
    except Exception as exc:
        logger.error(f"Deliberation pipeline failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deliberation pipeline error: {str(exc)}"
        )


@router.post("/export-markdown", response_model=MarkdownExportResponse)
async def export_markdown_report(
    report: FullReasoningReport,
):
    """
    Converts a FullReasoningReport into a downloadable GitHub Flavored Markdown document.
    """
    md_text = Phase3ReasonerPipeline.render_markdown_report(report)
    sanitized_name = "".join([c if c.isalnum() else "_" for c in report.business_legal_name[:30]])
    filename = f"{sanitized_name}_scheme_gap_report.md"

    return MarkdownExportResponse(
        file_name=filename,
        markdown_content=md_text,
    )

"""
Government Schemes Exploration & Hybrid Retrieval API Routes.
Provides endpoints for:
- Browsing all stored schemes with relational filtering (Jurisdiction, State, Benefit Type).
- Retrieving full details of a specific scheme and its official circular chunks.
- Executing hybrid semantic queries against the dense vector index.
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from schemas.government_scheme import GovernmentScheme, SchemeJurisdiction, BenefitType
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore, VectorSearchResult
from api.dependencies import get_knowledge_store, get_vector_store

logger = logging.getLogger("SchemesAPI")
router = APIRouter(prefix="/api/schemes", tags=["Schemes Knowledge Base"])


class SchemeListResponse(BaseModel):
    total_count: int
    returned_count: int
    schemes: List[GovernmentScheme]


class SchemeSearchRequest(BaseModel):
    query: str = Field(..., description="Semantic search query string")
    state: Optional[str] = Field(None, description="Target state filter (e.g. 'Maharashtra', 'Gujarat')")
    entity_type: Optional[str] = Field(None, description="Entity constitution filter")
    msme_tier: Optional[str] = Field(None, description="MSME tier filter ('Micro', 'Small', 'Medium')")
    top_k: int = Field(default=8, ge=1, le=50)


class SchemeDetailResponse(BaseModel):
    scheme: GovernmentScheme
    guideline_chunks_count: int
    guideline_chunks: List[Dict[str, Any]]


@router.get("", response_model=SchemeListResponse)
async def list_schemes(
    jurisdiction: Optional[str] = Query(None, description="Filter by 'Central' or 'State'"),
    state: Optional[str] = Query(None, description="Filter by state name"),
    benefit_type: Optional[str] = Query(None, description="Filter by benefit type"),
    search: Optional[str] = Query(None, description="Keyword search in title or short code"),
    limit: int = Query(50, ge=1, le=200),
    store: SchemeKnowledgeStore = Depends(get_knowledge_store),
):
    """
    Lists active government schemes with optional SQL predicate filters.
    """
    all_schemes = store.list_schemes(status="Active", jurisdiction=jurisdiction, state=state, limit=200)

    # In-memory keyword search & benefit filter
    filtered = all_schemes
    if benefit_type:
        filtered = [s for s in filtered if s.benefits.benefit_type.value.lower() == benefit_type.lower()]
    if search:
        s_lower = search.lower()
        filtered = [
            s for s in filtered
            if s_lower in s.scheme_name.lower() or s_lower in s.scheme_short_code.lower() or any(s_lower in t.lower() for t in s.tags)
        ]

    paginated = filtered[:limit]
    return SchemeListResponse(
        total_count=len(filtered),
        returned_count=len(paginated),
        schemes=paginated,
    )


@router.get("/{scheme_id}", response_model=SchemeDetailResponse)
async def get_scheme_details(
    scheme_id: str,
    store: SchemeKnowledgeStore = Depends(get_knowledge_store),
):
    """
    Retrieves full details of a specific scheme and its associated guideline document chunks.
    """
    scheme = store.get_scheme(scheme_id)
    if not scheme:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheme with ID '{scheme_id}' was not found in the knowledge store."
        )

    chunks = store.get_document_chunks_for_scheme(scheme_id)
    serialized_chunks = [
        {
            "chunk_id": c.chunk_id,
            "file_name": c.file_name,
            "page_number": c.page_number,
            "section_title": c.section_title,
            "content": c.content,
        }
        for c in chunks
    ]

    return SchemeDetailResponse(
        scheme=scheme,
        guideline_chunks_count=len(serialized_chunks),
        guideline_chunks=serialized_chunks,
    )


@router.post("/search", response_model=List[VectorSearchResult])
async def search_schemes(
    req: SchemeSearchRequest,
    vector_store: SchemeVectorStore = Depends(get_vector_store),
):
    """
    Executes hybrid semantic vector search with deterministic pre-filtering.
    """
    results = vector_store.hybrid_search(
        query=req.query,
        state=req.state,
        entity_type=req.entity_type,
        msme_tier=req.msme_tier,
        top_k=req.top_k,
    )
    return results

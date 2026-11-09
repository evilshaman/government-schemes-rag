"""
Knowledge Base Statistics API Route.
"""

from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter, Depends
from knowledge_base.storage import SchemeKnowledgeStore
from api.dependencies import get_knowledge_store

router = APIRouter(prefix="/api/stats", tags=["System Statistics"])


@router.get("", response_model=Dict[str, Any])
async def get_system_stats(
    store: SchemeKnowledgeStore = Depends(get_knowledge_store),
):
    """
    Returns aggregated knowledge base metrics, jurisdiction breakdown, and recent crawl history.
    """
    return store.get_statistics()

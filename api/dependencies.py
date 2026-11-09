"""
Dependency injection providers for FastAPI backend.
Manages singletons for SchemeKnowledgeStore, SchemeVectorStore, and Phase3ReasonerPipeline.
"""

from __future__ import annotations
import os
from functools import lru_cache
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore
from engine.pipeline_phase3 import Phase3ReasonerPipeline
from engine.retriever import HybridRetriever
from engine.reasoner import LLMEligibilityReasoner


@lru_cache(maxsize=1)
def get_knowledge_store() -> SchemeKnowledgeStore:
    return SchemeKnowledgeStore()


@lru_cache(maxsize=1)
def get_vector_store() -> SchemeVectorStore:
    vs = SchemeVectorStore()
    vs.load_index()
    return vs


@lru_cache(maxsize=1)
def get_hybrid_retriever() -> HybridRetriever:
    return HybridRetriever(
        knowledge_store=get_knowledge_store(),
        vector_store=get_vector_store(),
    )


@lru_cache(maxsize=1)
def get_reasoner_pipeline() -> Phase3ReasonerPipeline:
    return Phase3ReasonerPipeline(
        knowledge_store=get_knowledge_store(),
        vector_store=get_vector_store(),
    )


@lru_cache(maxsize=1)
def get_eligibility_reasoner() -> LLMEligibilityReasoner:
    return LLMEligibilityReasoner()

"""
Engine package for Government Schemes RAG.
"""

from engine.matcher import (
    DeterministicSchemeMatcher,
    SchemeMatchResult,
    MatchReport,
)
from engine.retriever import (
    HybridRetriever,
    RetrievedSchemeCandidate,
)
from engine.reranker import (
    CrossEncoderReranker,
    RerankedSchemeCandidate,
    RerankFactorBreakdown,
)
from engine.reasoner import (
    LLMEligibilityReasoner,
    DOCUMENT_REGULATORY_REGISTRY,
)
from engine.pipeline_phase3 import Phase3ReasonerPipeline

__all__ = [
    "DeterministicSchemeMatcher",
    "SchemeMatchResult",
    "MatchReport",
    "HybridRetriever",
    "RetrievedSchemeCandidate",
    "CrossEncoderReranker",
    "RerankedSchemeCandidate",
    "RerankFactorBreakdown",
    "LLMEligibilityReasoner",
    "DOCUMENT_REGULATORY_REGISTRY",
    "Phase3ReasonerPipeline",
]

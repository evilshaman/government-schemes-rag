"""
Knowledge Base Package for Government Schemes Discovery & RAG Platform.
Provides:
- SchemeKnowledgeStore (SQLite relational store)
- SchemeNormalizer (Validation and deduplication against GovernmentScheme)
- SchemeVectorStore (Dense semantic vector store & hybrid search engine)
"""

from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.normalizer import SchemeNormalizer
from knowledge_base.vector_store import SchemeVectorStore, VectorSearchResult

__all__ = [
    "SchemeKnowledgeStore",
    "SchemeNormalizer",
    "SchemeVectorStore",
    "VectorSearchResult",
]

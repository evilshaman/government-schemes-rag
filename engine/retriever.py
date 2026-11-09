"""
Hybrid Retrieval Engine for Government Schemes RAG (Phase 3).
Combines:
1. Stage 1 Deterministic Metadata Pre-Filtering (Jurisdiction, Entity Constitution, MSME Tier, Operation Type).
2. Stage 2 Dense Semantic Cosine Vector Retrieval (Vector Store).
3. Stage 2 Sparse Lexical BM25-style Keyword Retrieval.
4. Reciprocal Rank Fusion (RRF) to produce a high-recall, precision-ranked candidate set.
5. Association of official PDF guideline chunks for downstream grounded reasoning.
"""

from __future__ import annotations
import math
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from pydantic import BaseModel, Field

from schemas.business_profile import BusinessProfile
from schemas.government_scheme import GovernmentScheme, SchemeJurisdiction
from parsers.pdf_guidelines_parser import SchemeDocumentChunk
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore, VectorSearchResult


class RetrievedSchemeCandidate(BaseModel):
    """
    Candidate scheme bundled with its retrieval score, rank breakdown,
    and associated official guideline chunks.
    """
    scheme: GovernmentScheme
    rrf_score: float = Field(..., description="Reciprocal Rank Fusion score")
    dense_score: float = Field(default=0.0, description="Cosine similarity score from vector store")
    lexical_score: float = Field(default=0.0, description="Keyword BM25-style lexical score")
    dense_rank: Optional[int] = None
    lexical_rank: Optional[int] = None
    retrieval_reasons: List[str] = Field(default_factory=list)
    guideline_chunks: List[SchemeDocumentChunk] = Field(
        default_factory=list, description="Grounding chunks from official guideline circulars"
    )


class HybridRetriever:
    """
    Hybrid Retriever integrating relational filtering, dense embeddings, lexical search, and RRF.
    """

    def __init__(
        self,
        knowledge_store: Optional[SchemeKnowledgeStore] = None,
        vector_store: Optional[SchemeVectorStore] = None,
        rrf_k: int = 60,
        dense_weight: float = 0.6,
        lexical_weight: float = 0.4,
    ):
        self.store = knowledge_store or SchemeKnowledgeStore()
        self.vector_store = vector_store or SchemeVectorStore()
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.lexical_weight = lexical_weight

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [w for w in re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())]

    def _compute_lexical_score(self, query_tokens: List[str], scheme: GovernmentScheme) -> float:
        """
        Computes BM25-style term frequency score between query tokens and scheme text corpus.
        """
        corpus = (
            f"{scheme.scheme_name} {scheme.scheme_short_code} {scheme.nodal_ministry} "
            f"{scheme.summary} {' '.join(scheme.tags)} {' '.join(scheme.rules.target_sectors)} "
            f"{scheme.benefits.quantum_description}"
        ).lower()

        corpus_tokens = self._tokenize(corpus)
        if not corpus_tokens:
            return 0.0

        corpus_token_counts: Dict[str, int] = {}
        for tok in corpus_tokens:
            corpus_token_counts[tok] = corpus_token_counts.get(tok, 0) + 1

        score = 0.0
        doc_len = len(corpus_tokens)
        avg_len = 120.0
        k1 = 1.2
        b = 0.75

        for q_tok in query_tokens:
            tf = corpus_token_counts.get(q_tok, 0)
            if tf > 0:
                # BM25 term saturation formula
                norm_tf = (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * (doc_len / avg_len)))
                # Extra boost if token appears in scheme name or short code
                if q_tok in scheme.scheme_name.lower() or q_tok in scheme.scheme_short_code.lower():
                    norm_tf *= 2.0
                score += norm_tf

        return score

    def retrieve(
        self,
        profile: BusinessProfile,
        query: Optional[str] = None,
        top_k: int = 10,
        apply_hard_filters: bool = True,
    ) -> List[RetrievedSchemeCandidate]:
        """
        Executes hybrid retrieval:
        1. Fetch policy universe from SQLite.
        2. Apply deterministic metadata pre-filters.
        3. Score candidates with dense semantic vector search and sparse lexical search.
        4. Fuse ranks using Reciprocal Rank Fusion (RRF).
        5. Fetch relevant guideline chunks for top candidates.
        """
        all_schemes = self.store.list_schemes(status="Active", limit=500)
        if not all_schemes:
            # Fallback to loading seed schemes if database is empty
            import json, os
            seed_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "schemes_seed.json"
            )
            if os.path.exists(seed_path):
                with open(seed_path, "r", encoding="utf-8") as f:
                    all_schemes = [GovernmentScheme.model_validate(s) for s in json.load(f)]

        if not all_schemes:
            return []

        # 1. Deterministic metadata pre-filtering
        eligible_schemes: List[GovernmentScheme] = []
        is_mfg = any("manufacturing" in act.lower() for act in profile.nature_of_activities)
        is_svc = any("service" in act.lower() for act in profile.nature_of_activities)

        for s in all_schemes:
            rules = s.rules
            if apply_hard_filters:
                # State Filter
                state_match = (
                    s.jurisdiction == SchemeJurisdiction.CENTRAL
                    or "ALL" in rules.applicable_states
                    or profile.principal_address.state_name in rules.applicable_states
                )
                if not state_match:
                    continue

                # Constitution Filter (hard exclude if not in allowed list)
                if rules.eligible_constitutions and profile.constitution not in rules.eligible_constitutions:
                    continue

                # Activity Filter: If scheme strictly requires manufacturing and business is purely non-mfg
                if rules.requires_manufacturing and not is_mfg:
                    continue
                if rules.requires_services and not is_svc:
                    continue

            eligible_schemes.append(s)

        if not eligible_schemes:
            # Relax filters if too restrictive
            eligible_schemes = all_schemes

        # Construct intent query if not explicitly passed
        if not query or not query.strip():
            query_components = [
                profile.primary_sector,
                profile.constitution.value,
                profile.msme_tier.value,
                " ".join(profile.nature_of_activities),
                "subsidy grant loan financial assistance",
            ]
            if profile.is_woman_owned:
                query_components.append("woman entrepreneur")
            if profile.is_dpiit_recognized:
                query_components.append("startup seed fund")
            query = " ".join(query_components)

        query_tokens = self._tokenize(query)

        # 2. Dense Semantic Retrieval
        dense_results = self.vector_store.hybrid_search(
            query=query,
            state=profile.principal_address.state_name if apply_hard_filters else None,
            entity_type=profile.constitution.value if apply_hard_filters else None,
            top_k=len(eligible_schemes),
        )
        dense_score_map: Dict[str, float] = {r.scheme_id: r.similarity_score for r in dense_results}
        dense_rank_map: Dict[str, int] = {r.scheme_id: idx for idx, r in enumerate(dense_results, 1)}

        # 3. Sparse Lexical Scoring
        lexical_scored: List[Tuple[GovernmentScheme, float]] = []
        for s in eligible_schemes:
            l_score = self._compute_lexical_score(query_tokens, s)
            lexical_scored.append((s, l_score))

        lexical_scored.sort(key=lambda x: x[1], reverse=True)
        lexical_score_map: Dict[str, float] = {s.scheme_id: score for s, score in lexical_scored}
        lexical_rank_map: Dict[str, int] = {s.scheme_id: idx for idx, (s, _) in enumerate(lexical_scored, 1)}

        # 4. Reciprocal Rank Fusion (RRF)
        candidates: List[RetrievedSchemeCandidate] = []
        for s in eligible_schemes:
            s_id = s.scheme_id
            d_rank = dense_rank_map.get(s_id, len(eligible_schemes) + 50)
            l_rank = lexical_rank_map.get(s_id, len(eligible_schemes) + 50)

            # RRF Formula
            rrf = (self.dense_weight / (self.rrf_k + d_rank)) + (self.lexical_weight / (self.rrf_k + l_rank))

            # Domain Boosts
            reasons: List[str] = []
            if s.jurisdiction == SchemeJurisdiction.STATE and profile.principal_address.state_name in s.rules.applicable_states:
                rrf *= 1.15
                reasons.append(f"State-specific priority match for {profile.principal_address.state_name}")

            # Sector alignment boost
            if any(sec.lower() in profile.primary_sector.lower() for sec in s.rules.target_sectors) or "ALL" in s.rules.target_sectors:
                rrf *= 1.10
                reasons.append(f"Sector match with '{profile.primary_sector}'")

            # Woman-owned boost
            if s.rules.requires_women_ownership and profile.is_woman_owned:
                rrf *= 1.20
                reasons.append("Affirmative match: Woman entrepreneur targeted scheme")

            # DPIIT Startup boost
            if s.rules.requires_dpiit_recognition and profile.is_dpiit_recognized:
                rrf *= 1.20
                reasons.append("DPIIT Startup recognized priority match")

            # Fetch guideline chunks for this scheme
            chunks = self.store.get_document_chunks_for_scheme(s_id)

            candidates.append(
                RetrievedSchemeCandidate(
                    scheme=s,
                    rrf_score=round(rrf, 5),
                    dense_score=round(dense_score_map.get(s_id, 0.0), 4),
                    lexical_score=round(lexical_score_map.get(s_id, 0.0), 4),
                    dense_rank=d_rank if s_id in dense_rank_map else None,
                    lexical_rank=l_rank if s_id in lexical_rank_map else None,
                    retrieval_reasons=reasons,
                    guideline_chunks=chunks,
                )
            )

        # Sort by RRF score descending
        candidates.sort(key=lambda x: x.rrf_score, reverse=True)
        return candidates[:top_k]

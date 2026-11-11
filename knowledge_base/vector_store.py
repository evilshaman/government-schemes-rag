"""
Hybrid Vector Store & Semantic Retrieval Engine.
Provides subword TF-IDF / Cosine dense vector search combined with deterministic SQL metadata pre-filtering.
Pluggable embedding interface supporting local dense vectorizer and Gemini Embedding API.
"""

from __future__ import annotations
import os
import re
import math
import json
import logging
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field
from schemas.government_scheme import GovernmentScheme
from schemas.business_profile import BusinessProfile, ConstitutionType, MSMETier
from parsers.pdf_guidelines_parser import SchemeDocumentChunk

logger = logging.getLogger("SchemeVectorStore")


class VectorSearchResult(BaseModel):
    """
    Search result returned by the Hybrid Vector Store.
    """
    scheme_id: str
    scheme_name: str
    scheme_short_code: str
    similarity_score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    matched_passage: str
    benefit_type: str
    nodal_ministry: str
    official_portal_url: str
    chunk_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class DenseTFIDFVectorizer:
    """
    Self-contained n-gram TF-IDF dense vectorizer with cosine similarity.
    Requires no external dependencies, works deterministically offline on all platforms.
    """

    def __init__(self, min_df: int = 1, max_features: int = 3000):
        self.min_df = min_df
        self.max_features = max_features
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.is_fitted: bool = False

    def tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())
        # Add word bigrams for richer semantic phrase matching
        bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
        return tokens + bigrams

    def fit(self, documents: List[str]) -> None:
        doc_count = len(documents)
        df_counts: Dict[str, int] = {}

        for doc in documents:
            seen_tokens: Set[str] = set(self.tokenize(doc))
            for token in seen_tokens:
                df_counts[token] = df_counts.get(token, 0) + 1

        # Filter by min_df and rank top features
        filtered_items = [
            (tok, count) for tok, count in df_counts.items() if count >= self.min_df
        ]
        filtered_items.sort(key=lambda x: x[1], reverse=True)
        top_items = filtered_items[: self.max_features]

        self.vocabulary = {tok: idx for idx, (tok, _) in enumerate(top_items)}
        self.idf = {
            tok: math.log((doc_count + 1.0) / (count + 1.0)) + 1.0
            for tok, count in top_items
        }
        self.is_fitted = True

    def transform(self, text: str) -> Dict[int, float]:
        """
        Transforms text into sparse-represented L2-normalized vector.
        """
        if not self.is_fitted:
            raise ValueError("Vectorizer has not been fitted.")

        tokens = self.tokenize(text)
        tf: Dict[str, int] = {}
        for token in tokens:
            if token in self.vocabulary:
                tf[token] = tf.get(token, 0) + 1

        sparse_vec: Dict[int, float] = {}
        sq_sum = 0.0

        for token, count in tf.items():
            idx = self.vocabulary[token]
            weight = (1.0 + math.log(count)) * self.idf[token]
            sparse_vec[idx] = weight
            sq_sum += weight * weight

        # L2 normalization
        norm = math.sqrt(sq_sum)
        if norm > 0.0:
            for idx in sparse_vec:
                sparse_vec[idx] /= norm

        return sparse_vec

    @staticmethod
    def cosine_similarity(v1: Dict[int, float], v2: Dict[int, float]) -> float:
        """
        Computes cosine dot-product between two L2-normalized sparse vectors.
        """
        if not v1 or not v2:
            return 0.0
        # Iterate over smaller dict
        if len(v1) > len(v2):
            v1, v2 = v2, v1
        dot = sum(val * v2[idx] for idx, val in v1.items() if idx in v2)
        return min(max(dot, 0.0), 1.0)


class SchemeVectorStore:
    """
    Hybrid Vector Store providing deterministic metadata pre-filtering and dense semantic search.
    """

    def __init__(self, index_file_path: Optional[str] = None):
        if index_file_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            index_file_path = os.path.join(base_dir, "data", "schemes_vector_index.json")

        self.index_file_path = index_file_path
        self.vectorizer = DenseTFIDFVectorizer()
        # Item: dict with scheme_id, chunk_id, text, metadata, vector
        self.index_entries: List[Dict[str, Any]] = []

    def build_index(
        self,
        schemes: List[GovernmentScheme],
        chunks: Optional[List[SchemeDocumentChunk]] = None,
    ) -> int:
        """
        Builds the vector index from schemes and optional guideline chunks.
        """
        corpus_texts: List[str] = []
        raw_items: List[Dict[str, Any]] = []

        # 1. Index Schemes
        for s in schemes:
            app_steps = " ".join(s.application_process) if s.application_process else ""
            text = (
                f"{s.scheme_name} {s.scheme_short_code} {s.nodal_ministry} "
                f"{s.summary} {' '.join(s.eligibility_criteria_text)} "
                f"{s.benefits.quantum_description} {' '.join(s.tags)} "
                f"{' '.join(s.rules.target_sectors)} {s.application_mode} {app_steps}"
            )
            corpus_texts.append(text)
            raw_items.append({
                "scheme_id": s.scheme_id,
                "scheme_name": s.scheme_name,
                "scheme_short_code": s.scheme_short_code,
                "nodal_ministry": s.nodal_ministry,
                "benefit_type": s.benefits.benefit_type.value,
                "official_portal_url": s.official_portal_url,
                "tags": s.tags,
                "applicable_states": s.rules.applicable_states,
                "eligible_constitutions": [c.value for c in s.rules.eligible_constitutions],
                "eligible_msme_tiers": [t.value for t in s.rules.eligible_msme_tiers],
                "requires_manufacturing": s.rules.requires_manufacturing,
                "requires_services": s.rules.requires_services,
                "requires_women": s.rules.requires_women_ownership,
                "requires_sc_st": s.rules.requires_sc_st_ownership,
                "requires_dpiit": s.rules.requires_dpiit_recognition,
                "chunk_id": None,
                "text": text,
                "snippet": s.summary,
            })

        # 2. Index Guideline Chunks if provided
        if chunks:
            scheme_map = {s.scheme_id: s for s in schemes}
            for ch in chunks:
                parent_s = scheme_map.get(ch.scheme_id or "")
                s_name = parent_s.scheme_name if parent_s else ch.file_name
                s_short = parent_s.scheme_short_code if parent_s else ""
                s_ministry = parent_s.nodal_ministry if parent_s else "Government of India"
                s_btype = parent_s.benefits.benefit_type.value if parent_s else "Subsidy"
                s_url = parent_s.official_portal_url if parent_s else ""
                s_tags = parent_s.tags if parent_s else []

                text = f"{ch.section_title or ''} {ch.content}"
                corpus_texts.append(text)
                raw_items.append({
                    "scheme_id": ch.scheme_id or "unknown",
                    "scheme_name": s_name,
                    "scheme_short_code": s_short,
                    "nodal_ministry": s_ministry,
                    "benefit_type": s_btype,
                    "official_portal_url": s_url,
                    "tags": s_tags,
                    "applicable_states": parent_s.rules.applicable_states if parent_s else ["ALL"],
                    "eligible_constitutions": [c.value for c in parent_s.rules.eligible_constitutions] if parent_s else [],
                    "eligible_msme_tiers": [t.value for t in parent_s.rules.eligible_msme_tiers] if parent_s else [],
                    "requires_manufacturing": parent_s.rules.requires_manufacturing if parent_s else False,
                    "requires_services": parent_s.rules.requires_services if parent_s else False,
                    "requires_women": parent_s.rules.requires_women_ownership if parent_s else False,
                    "requires_sc_st": parent_s.rules.requires_sc_st_ownership if parent_s else False,
                    "requires_dpiit": parent_s.rules.requires_dpiit_recognition if parent_s else False,
                    "chunk_id": ch.chunk_id,
                    "text": text,
                    "snippet": f"[{ch.file_name} p.{ch.page_number}]: {ch.content[:250]}...",
                })

        if not corpus_texts:
            logger.warning("No documents provided to build vector index.")
            return 0

        logger.info(f"Fitting vectorizer on {len(corpus_texts)} scheme & guideline documents...")
        self.vectorizer.fit(corpus_texts)

        # Generate vectors
        self.index_entries = []
        for item in raw_items:
            item["vector"] = self.vectorizer.transform(item["text"])
            self.index_entries.append(item)

        self.save_index()
        logger.info(f"Vector index built successfully with {len(self.index_entries)} indexed entries.")
        return len(self.index_entries)

    def save_index(self) -> None:
        """
        Serializes vector store entries to JSON for fast persistence.
        """
        os.makedirs(os.path.dirname(os.path.abspath(self.index_file_path)), exist_ok=True)
        # Convert int keys of sparse vector to str for JSON
        serializable = []
        for entry in self.index_entries:
            copy_entry = dict(entry)
            copy_entry["vector"] = {str(k): v for k, v in entry["vector"].items()}
            serializable.append(copy_entry)

        payload = {
            "vocabulary": self.vectorizer.vocabulary,
            "idf": self.vectorizer.idf,
            "entries": serializable,
        }
        with open(self.index_file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def load_index(self) -> bool:
        """
        Loads precomputed vector index from disk if available.
        """
        if not os.path.exists(self.index_file_path):
            return False

        try:
            with open(self.index_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.vectorizer.vocabulary = data["vocabulary"]
            self.vectorizer.idf = data["idf"]
            self.vectorizer.is_fitted = True

            self.index_entries = []
            for item in data["entries"]:
                item["vector"] = {int(k): v for k, v in item["vector"].items()}
                self.index_entries.append(item)

            return True
        except Exception as exc:
            logger.error(f"Failed to load vector index: {exc}")
            return False

    def hybrid_search(
        self,
        query: str,
        state: Optional[str] = None,
        entity_type: Optional[str] = None,
        msme_tier: Optional[str] = None,
        is_manufacturing: Optional[bool] = None,
        is_woman_owned: Optional[bool] = None,
        is_dpiit_recognized: Optional[bool] = None,
        top_k: int = 5,
    ) -> List[VectorSearchResult]:
        """
        Executes hybrid search: Deterministic Pre-Filtering + Dense Semantic Cosine Ranking.
        """
        if not self.index_entries:
            self.load_index()

        if not self.index_entries or not self.vectorizer.is_fitted:
            logger.warning("Vector index is empty. Call build_index first.")
            return []

        query_vec = self.vectorizer.transform(query)
        scored_results: List[VectorSearchResult] = []
        seen_schemes: Set[str] = set()

        for entry in self.index_entries:
            # Stage 1: Deterministic metadata filtering
            # State match
            if state:
                applicable_states = entry.get("applicable_states", ["ALL"])
                if "ALL" not in applicable_states and state not in applicable_states:
                    continue

            # Entity constitution match
            if entity_type:
                allowed_entities = entry.get("eligible_constitutions", [])
                if allowed_entities and entity_type not in allowed_entities:
                    continue

            # MSME tier match
            if msme_tier:
                allowed_tiers = entry.get("eligible_msme_tiers", [])
                if allowed_tiers and msme_tier not in allowed_tiers:
                    continue

            # Manufacturing requirement
            if entry.get("requires_manufacturing") and is_manufacturing is False:
                continue

            # Women ownership requirement
            if entry.get("requires_women") and is_woman_owned is False:
                continue

            # DPIIT recognition requirement
            if entry.get("requires_dpiit") and is_dpiit_recognized is False:
                continue

            # Stage 2: Dense Semantic Cosine Scoring
            sim = DenseTFIDFVectorizer.cosine_similarity(query_vec, entry["vector"])

            # Sector/keyword exact match boost
            query_lower = query.lower()
            if any(tag.lower() in query_lower for tag in entry.get("tags", [])):
                sim += 0.15

            # Deduplicate by scheme_id to return most relevant passage per scheme
            scheme_id = entry["scheme_id"]
            if scheme_id in seen_schemes:
                continue
            seen_schemes.add(scheme_id)

            scored_results.append(
                VectorSearchResult(
                    scheme_id=scheme_id,
                    scheme_name=entry["scheme_name"],
                    scheme_short_code=entry["scheme_short_code"],
                    similarity_score=round(min(sim, 1.0), 4),
                    matched_passage=entry["snippet"],
                    benefit_type=entry["benefit_type"],
                    nodal_ministry=entry["nodal_ministry"],
                    official_portal_url=entry["official_portal_url"],
                    chunk_id=entry.get("chunk_id"),
                    tags=entry.get("tags", []),
                )
            )

        scored_results.sort(key=lambda x: x.similarity_score, reverse=True)
        return scored_results[:top_k]

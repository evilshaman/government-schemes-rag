"""
SQLite Relational Knowledge Store.
Provides ACID persistent storage for Government Schemes, Document Chunks, and Crawl Audit Logs.
"""

from __future__ import annotations
import os
import json
import sqlite3
import logging
import contextlib
from typing import List, Dict, Any, Optional, Generator
from datetime import datetime
from schemas.government_scheme import GovernmentScheme
from parsers.pdf_guidelines_parser import SchemeDocumentChunk

logger = logging.getLogger("SchemeKnowledgeStore")


class SchemeKnowledgeStore:
    """
    Persistent SQLite storage manager for schemes, document chunks, and crawl history.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "schemes_knowledge.db")
        
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_tables()

    @contextlib.contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging (WAL) for high-throughput concurrent reads and non-blocking writes
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_tables(self) -> None:
        """
        Initializes schema tables and indexes if they do not exist.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Schemes table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schemes (
                    scheme_id TEXT PRIMARY KEY,
                    scheme_name TEXT NOT NULL,
                    scheme_short_code TEXT,
                    nodal_ministry TEXT,
                    implementing_agency TEXT,
                    jurisdiction TEXT NOT NULL,
                    applicable_states TEXT NOT NULL,
                    benefit_type TEXT NOT NULL,
                    max_assistance_inr REAL,
                    subsidy_percentage REAL,
                    requires_manufacturing INTEGER DEFAULT 0,
                    requires_services INTEGER DEFAULT 0,
                    requires_women_ownership INTEGER DEFAULT 0,
                    requires_sc_st_ownership INTEGER DEFAULT 0,
                    requires_dpiit_recognition INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    official_portal_url TEXT,
                    guidelines_doc_url TEXT,
                    full_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_schemes_jurisdiction ON schemes(jurisdiction);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_schemes_benefit_type ON schemes(benefit_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_schemes_status ON schemes(status);")

            # 2. Scheme documents table (guideline chunks for citations & vector indexing)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheme_documents (
                    chunk_id TEXT PRIMARY KEY,
                    scheme_id TEXT,
                    file_name TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    section_title TEXT,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (scheme_id) REFERENCES schemes(scheme_id) ON DELETE CASCADE
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_docs_scheme_id ON scheme_documents(scheme_id);")

            # 3. Crawl history audit table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_history (
                    crawl_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_portal TEXT NOT NULL,
                    schemes_found INTEGER NOT NULL,
                    schemes_saved INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def save_scheme(self, scheme: GovernmentScheme) -> bool:
        """
        Saves or updates a GovernmentScheme record.
        """
        rules = scheme.rules
        benefits = scheme.benefits
        states_json = json.dumps(rules.applicable_states)
        scheme_json = scheme.model_dump_json()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO schemes (
                    scheme_id, scheme_name, scheme_short_code, nodal_ministry,
                    implementing_agency, jurisdiction, applicable_states,
                    benefit_type, max_assistance_inr, subsidy_percentage,
                    requires_manufacturing, requires_services, requires_women_ownership,
                    requires_sc_st_ownership, requires_dpiit_recognition, status,
                    official_portal_url, guidelines_doc_url, full_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(scheme_id) DO UPDATE SET
                    scheme_name=excluded.scheme_name,
                    scheme_short_code=excluded.scheme_short_code,
                    nodal_ministry=excluded.nodal_ministry,
                    implementing_agency=excluded.implementing_agency,
                    jurisdiction=excluded.jurisdiction,
                    applicable_states=excluded.applicable_states,
                    benefit_type=excluded.benefit_type,
                    max_assistance_inr=excluded.max_assistance_inr,
                    subsidy_percentage=excluded.subsidy_percentage,
                    requires_manufacturing=excluded.requires_manufacturing,
                    requires_services=excluded.requires_services,
                    requires_women_ownership=excluded.requires_women_ownership,
                    requires_sc_st_ownership=excluded.requires_sc_st_ownership,
                    requires_dpiit_recognition=excluded.requires_dpiit_recognition,
                    status=excluded.status,
                    official_portal_url=excluded.official_portal_url,
                    guidelines_doc_url=excluded.guidelines_doc_url,
                    full_json=excluded.full_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    scheme.scheme_id,
                    scheme.scheme_name,
                    scheme.scheme_short_code,
                    scheme.nodal_ministry,
                    scheme.implementing_agency,
                    scheme.jurisdiction.value,
                    states_json,
                    benefits.benefit_type.value,
                    benefits.max_assistance_amount_inr,
                    benefits.subsidy_percentage,
                    1 if rules.requires_manufacturing else 0,
                    1 if rules.requires_services else 0,
                    1 if rules.requires_women_ownership else 0,
                    1 if rules.requires_sc_st_ownership else 0,
                    1 if rules.requires_dpiit_recognition else 0,
                    scheme.status.value,
                    scheme.official_portal_url,
                    scheme.guidelines_doc_url,
                    scheme_json,
                ),
            )
            conn.commit()
            return True

    def get_scheme(self, scheme_id: str) -> Optional[GovernmentScheme]:
        """
        Retrieves a scheme by its unique slug ID.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT full_json FROM schemes WHERE scheme_id = ?", (scheme_id,))
            row = cursor.fetchone()
            if row:
                return GovernmentScheme.model_validate_json(row["full_json"])
            return None

    def list_schemes(
        self,
        status: Optional[str] = "Active",
        jurisdiction: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 200,
    ) -> List[GovernmentScheme]:
        """
        Lists schemes with optional SQL predicate filters.
        """
        query = "SELECT full_json FROM schemes WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)

        if jurisdiction:
            query += " AND jurisdiction = ?"
            params.append(jurisdiction)

        query += " ORDER BY scheme_name ASC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            schemes: List[GovernmentScheme] = []
            for row in rows:
                scheme = GovernmentScheme.model_validate_json(row["full_json"])
                if state:
                    states = scheme.rules.applicable_states
                    if "ALL" not in states and state not in states:
                        continue
                schemes.append(scheme)
            return schemes

    def save_document_chunks(self, chunks: List[SchemeDocumentChunk]) -> int:
        """
        Batch saves PDF guideline text chunks.
        """
        if not chunks:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for chunk in chunks:
                cursor.execute(
                    """
                    INSERT INTO scheme_documents (
                        chunk_id, scheme_id, file_name, page_number,
                        section_title, content, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        content=excluded.content,
                        section_title=excluded.section_title,
                        metadata_json=excluded.metadata_json;
                    """,
                    (
                        chunk.chunk_id,
                        chunk.scheme_id,
                        chunk.file_name,
                        chunk.page_number,
                        chunk.section_title,
                        chunk.content,
                        json.dumps(chunk.metadata),
                    ),
                )
            conn.commit()
            return len(chunks)

    def get_document_chunks_for_scheme(self, scheme_id: str) -> List[SchemeDocumentChunk]:
        """
        Retrieves all parsed guideline chunks for a specific scheme.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM scheme_documents WHERE scheme_id = ? ORDER BY page_number ASC",
                (scheme_id,),
            )
            rows = cursor.fetchall()
            return [
                SchemeDocumentChunk(
                    chunk_id=r["chunk_id"],
                    scheme_id=r["scheme_id"],
                    file_name=r["file_name"],
                    page_number=r["page_number"],
                    section_title=r["section_title"],
                    content=r["content"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                )
                for r in rows
            ]

    def log_crawl_run(
        self, source_portal: str, schemes_found: int, schemes_saved: int, status: str, error: Optional[str] = None
    ) -> int:
        """
        Logs a crawler run audit record.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO crawl_history (source_portal, schemes_found, schemes_saved, status, error_message)
                VALUES (?, ?, ?, ?, ?);
                """,
                (source_portal, schemes_found, schemes_saved, status, error),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_statistics(self) -> Dict[str, Any]:
        """
        Summarizes Knowledge Base statistics.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) AS total_schemes FROM schemes;")
            total_schemes = cursor.fetchone()["total_schemes"]

            cursor.execute("SELECT jurisdiction, COUNT(*) AS count FROM schemes GROUP BY jurisdiction;")
            jurisdictions = {r["jurisdiction"]: r["count"] for r in cursor.fetchall()}

            cursor.execute("SELECT benefit_type, COUNT(*) AS count FROM schemes GROUP BY benefit_type;")
            benefit_types = {r["benefit_type"]: r["count"] for r in cursor.fetchall()}

            cursor.execute("SELECT COUNT(*) AS total_chunks FROM scheme_documents;")
            total_chunks = cursor.fetchone()["total_chunks"]

            cursor.execute("SELECT COUNT(*) AS total_crawls FROM crawl_history;")
            total_crawls = cursor.fetchone()["total_crawls"]

            cursor.execute(
                "SELECT source_portal, status, timestamp FROM crawl_history ORDER BY crawl_id DESC LIMIT 5;"
            )
            recent_crawls = [dict(r) for r in cursor.fetchall()]

            return {
                "total_schemes": total_schemes,
                "total_guideline_chunks": total_chunks,
                "jurisdiction_breakdown": jurisdictions,
                "benefit_type_breakdown": benefit_types,
                "total_crawls_logged": total_crawls,
                "recent_crawl_history": recent_crawls,
            }

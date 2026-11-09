"""
PDF Scheme Guidelines & Notification Circular Ingestion Engine.
Extracts operational criteria, subsidy clauses, required documents, and chunks text for vector indexing.
"""

from __future__ import annotations
import os
import re
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import pypdf

logger = logging.getLogger("PDFGuidelinesParser")


class SchemeDocumentChunk(BaseModel):
    """
    A chunk of text from an official guideline PDF for vector embedding and retrieval citations.
    """
    chunk_id: str
    scheme_id: Optional[str] = None
    file_name: str
    page_number: int
    section_title: Optional[str] = None
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ParsedSchemeGuideline(BaseModel):
    """
    Structured extraction from an official operational guideline PDF.
    """
    file_path: str
    title: Optional[str] = None
    scheme_id: Optional[str] = None
    total_pages: int
    extracted_summary: str
    eligibility_points: List[str] = Field(default_factory=list)
    financial_benefits_text: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    subsidy_percentage: Optional[float] = None
    max_assistance_inr: Optional[float] = None
    chunks: List[SchemeDocumentChunk] = Field(default_factory=list)
    raw_text: str


class PDFGuidelinesParser:
    """
    Parser for government notification circulars and operational guideline PDFs.
    """

    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_text_from_pdf(self, file_path: str) -> tuple[str, List[tuple[int, str]]]:
        """
        Extracts raw text from PDF file page by page.
        Returns: (full_text, [(page_num, page_text), ...])
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        reader = pypdf.PdfReader(file_path)
        full_text_parts: List[str] = []
        page_texts: List[tuple[int, str]] = []

        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            # Clean up excessive whitespace
            clean_page_text = re.sub(r"\s+", " ", text).strip()
            if clean_page_text:
                page_texts.append((idx + 1, clean_page_text))
                full_text_parts.append(clean_page_text)

        full_text = "\n\n".join(full_text_parts)
        return full_text, page_texts

    def create_chunks(
        self,
        file_name: str,
        page_texts: List[tuple[int, str]],
        scheme_id: Optional[str] = None,
    ) -> List[SchemeDocumentChunk]:
        """
        Splits extracted pages into overlapping chunks suitable for semantic vector indexing.
        """
        chunks: List[SchemeDocumentChunk] = []
        chunk_counter = 1

        for page_num, text in page_texts:
            words = text.split()
            if not words:
                continue

            start = 0
            while start < len(words):
                end = min(start + self.chunk_size, len(words))
                chunk_words = words[start:end]
                chunk_text = " ".join(chunk_words)

                # Heuristic section detection
                section_title = None
                lines = chunk_text.split(".")
                if lines and len(lines[0].split()) < 10:
                    section_title = lines[0].strip()

                chunk_id = f"{os.path.splitext(file_name)[0]}_p{page_num}_c{chunk_counter}"
                chunks.append(
                    SchemeDocumentChunk(
                        chunk_id=chunk_id,
                        scheme_id=scheme_id,
                        file_name=file_name,
                        page_number=page_num,
                        section_title=section_title,
                        content=chunk_text,
                        metadata={
                            "word_count": len(chunk_words),
                            "start_word_index": start,
                        },
                    )
                )
                chunk_counter += 1
                if end == len(words):
                    break
                start += max(1, self.chunk_size - self.chunk_overlap)

        return chunks

    def extract_heuristics(self, full_text: str) -> Dict[str, Any]:
        """
        Extracts eligibility criteria, subsidy amounts, and documents using rule-based patterns.
        """
        eligibility: List[str] = []
        financial_points: List[str] = []
        documents: List[str] = []

        # Find eligibility clauses
        elig_pattern = re.compile(
            r"(?:eligibility|who can apply|qualifying criteria|target beneficiaries)[\s:]+(.*?)(?=(?:quantum|benefits|financial assistance|documents|application process|how to apply|$))",
            re.IGNORECASE | re.DOTALL,
        )
        match = elig_pattern.search(full_text)
        if match:
            raw_section = match.group(1)
            items = re.split(r"(?:\n\s*[-•*]|\d+\.\s+)", raw_section)
            for item in items:
                clean_item = item.strip()
                if len(clean_item) > 15 and len(clean_item) < 300:
                    eligibility.append(clean_item)

        # Find financial assistance / subsidy clauses
        fin_pattern = re.compile(
            r"(?:financial assistance|subsidy|quantum of assistance|loan limit|margin money)[\s:]+(.*?)(?=(?:eligibility|documents|how to apply|procedure|$))",
            re.IGNORECASE | re.DOTALL,
        )
        match = fin_pattern.search(full_text)
        if match:
            raw_section = match.group(1)
            items = re.split(r"(?:\n\s*[-•*]|\d+\.\s+)", raw_section)
            for item in items:
                clean_item = item.strip()
                if len(clean_item) > 15 and len(clean_item) < 300:
                    financial_points.append(clean_item)

        # Find document checklist clauses
        doc_pattern = re.compile(
            r"(?:documents required|mandatory documents|checklist|annexure)[\s:]+(.*?)(?=(?:eligibility|benefits|application|terms|$))",
            re.IGNORECASE | re.DOTALL,
        )
        match = doc_pattern.search(full_text)
        if match:
            raw_section = match.group(1)
            items = re.split(r"(?:\n\s*[-•*]|\d+\.\s+)", raw_section)
            for item in items:
                clean_item = item.strip()
                if len(clean_item) > 5 and len(clean_item) < 150:
                    documents.append(clean_item)

        # Extract numerical subsidy % and maximum INR if present
        subsidy_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:margin money|subsidy|concession)", full_text, re.IGNORECASE)
        subsidy_pct = float(subsidy_match.group(1)) if subsidy_match else None

        # Extract max amount in INR (Lakh or Crore)
        max_inr = None
        amt_match = re.search(r"(?:₹|Rs\.?|INR)\s*(\d+(?:\.\d+)?)\s*(Lakh|Crore|Cr|Lakhs)", full_text, re.IGNORECASE)
        if amt_match:
            num = float(amt_match.group(1))
            unit = amt_match.group(2).lower()
            if "crore" in unit or "cr" in unit:
                max_inr = num * 10000000.0
            else:
                max_inr = num * 100000.0

        return {
            "eligibility_points": eligibility,
            "financial_points": financial_points,
            "documents": documents,
            "subsidy_percentage": subsidy_pct,
            "max_assistance_inr": max_inr,
        }

    def parse_file(self, file_path: str, scheme_id: Optional[str] = None) -> ParsedSchemeGuideline:
        """
        Parses a guideline PDF file end-to-end.
        """
        file_name = os.path.basename(file_path)
        logger.info(f"Parsing guideline PDF: {file_name}")

        full_text, page_texts = self.extract_text_from_pdf(file_path)
        total_pages = len(page_texts)

        # Title heuristic: first non-empty lines on page 1
        title = None
        if page_texts:
            p1_words = page_texts[0][1].split()
            if len(p1_words) >= 3:
                title = " ".join(p1_words[:12])

        heuristics = self.extract_heuristics(full_text)
        chunks = self.create_chunks(file_name, page_texts, scheme_id=scheme_id)

        # Generate summary
        summary = full_text[:400].strip() + ("..." if len(full_text) > 400 else "")

        return ParsedSchemeGuideline(
            file_path=os.path.abspath(file_path),
            title=title,
            scheme_id=scheme_id,
            total_pages=total_pages,
            extracted_summary=summary,
            eligibility_points=heuristics["eligibility_points"],
            financial_benefits_text=heuristics["financial_points"],
            required_documents=heuristics["documents"],
            subsidy_percentage=heuristics["subsidy_percentage"],
            max_assistance_inr=heuristics["max_assistance_inr"],
            chunks=chunks,
            raw_text=full_text,
        )

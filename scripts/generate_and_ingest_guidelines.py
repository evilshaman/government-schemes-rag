"""
Script to generate official operational guideline circular PDFs for all government schemes
in the knowledge base, parse them into chunks, persist them in SQLite, and rebuild the vector index.
"""

from __future__ import annotations
import os
import sys
import re
import textwrap
import logging
from typing import List

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from schemas.government_scheme import GovernmentScheme
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore
from parsers.pdf_guidelines_parser import PDFGuidelinesParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GuidelinesIngestion")


def sanitize_text(text: str) -> str:
    """Sanitizes text to be encodable in standard PDF Latin-1 / Helvetica."""
    replacements = {
        "\u20b9": "Rs. ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "--",
        "\u2026": "...",
        "\u00a0": " ",
        "\u2022": "-",
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text.encode("latin-1", "replace").decode("latin-1")


def generate_multipage_pdf_bytes(pages_lines: List[List[str]]) -> bytes:
    """Constructs a valid multi-page PDF with standard Helvetica typography."""
    body = [b"%PDF-1.4"]
    offsets = []

    def add_obj(content: bytes):
        offsets.append(sum(len(b) + 1 for b in body))
        body.append(content)

    font_id = 3 + len(pages_lines) * 2
    page_ids = [3 + i * 2 for i in range(len(pages_lines))]

    add_obj(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    kids_str = " ".join(f"{pid} 0 R" for pid in page_ids)
    add_obj(f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {len(pages_lines)} >>\nendobj".encode("latin-1"))

    for idx, lines in enumerate(pages_lines):
        stream_lines = ["BT", "/F1 10 Tf", "50 740 Td", "14 TL"]
        for l in lines:
            sanitized = sanitize_text(l)
            esc = sanitized.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"({esc}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream_bytes = "\n".join(stream_lines).encode("latin-1")

        page_id = page_ids[idx]
        content_id = page_id + 1
        add_obj(
            f"{page_id} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>\nendobj".encode(
                "latin-1"
            )
        )
        add_obj(
            f"{content_id} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
            + stream_bytes
            + b"\nendstream\nendobj"
        )

    add_obj(f"{font_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj".encode("latin-1"))

    startxref = sum(len(b) + 1 for b in body)
    xref = [b"xref", f"0 {len(offsets) + 1}".encode("latin-1"), b"0000000000 65535 f "]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n ".encode("latin-1"))
    trailer = (
        b"trailer\n<< /Size "
        + str(len(offsets) + 1).encode("latin-1")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(startxref).encode("latin-1")
        + b"\n%%EOF"
    )

    return b"\n".join(body) + b"\n" + b"\n".join(xref) + b"\n" + trailer


def build_guideline_lines(scheme: GovernmentScheme) -> List[str]:
    """Generates structured circular text suitable for regex heuristic parsing."""
    lines: List[str] = []
    lines.append(f"GOVERNMENT OF INDIA - {scheme.nodal_ministry.upper()}")
    agency_txt = f" / {scheme.implementing_agency.upper()}" if scheme.implementing_agency else ""
    lines.append(f"OPERATIONAL GUIDELINES: {scheme.scheme_name.upper()} ({scheme.scheme_short_code.upper()}){agency_txt}")
    lines.append("")
    lines.append("1. Overview & Objective:")
    for wrap_l in textwrap.wrap(scheme.summary, width=75):
        lines.append(wrap_l)
    lines.append("")

    lines.append("2. Eligibility Criteria:")
    if scheme.eligibility_criteria_text:
        for i, crit in enumerate(scheme.eligibility_criteria_text, 1):
            wrapped = textwrap.wrap(crit, width=72)
            for j, wrap_l in enumerate(wrapped):
                lines.append(f"{i}. {wrap_l}" if j == 0 else f"   {wrap_l}")
    else:
        lines.append("1. Open to registered Indian business entities meeting nodal ministry norms.")
        if scheme.rules.eligible_msme_tiers:
            tiers = ", ".join(t.value for t in scheme.rules.eligible_msme_tiers)
            lines.append(f"2. Applicable to MSME tiers: {tiers}.")
        if scheme.rules.target_sectors:
            secs = ", ".join(scheme.rules.target_sectors)
            lines.append(f"3. Target industry sectors: {secs}.")

    lines.append("")
    lines.append("3. Financial Assistance and Subsidy:")
    fin_wrapped = textwrap.wrap(scheme.benefits.quantum_description, width=72)
    for j, wrap_l in enumerate(fin_wrapped):
        lines.append(f"1. {wrap_l}" if j == 0 else f"   {wrap_l}")

    if scheme.benefits.subsidy_percentage:
        lines.append(f"2. Concession or margin money subsidy rate of {scheme.benefits.subsidy_percentage} % subsidy.")
    if scheme.benefits.max_assistance_amount_inr:
        amt = scheme.benefits.max_assistance_amount_inr
        if amt >= 10000000.0:
            lines.append(f"3. Maximum financial assistance cap is Rs {amt / 10000000.0:.2f} Crore per unit.")
        else:
            lines.append(f"3. Maximum financial assistance cap is Rs {amt / 100000.0:.1f} Lakh per unit.")

    lines.append("")
    lines.append("4. Mandatory Documents Checklist:")
    if scheme.required_documents:
        for i, doc in enumerate(scheme.required_documents, 1):
            wrapped = textwrap.wrap(doc, width=72)
            for j, wrap_l in enumerate(wrapped):
                lines.append(f"{i}. {wrap_l}" if j == 0 else f"   {wrap_l}")
    else:
        lines.append("1. PAN Card and Certificate of Incorporation")
        lines.append("2. Udyam Registration Certificate")
        lines.append("3. Detailed Project Report (DPR)")

    lines.append("")
    lines.append("5. Application Procedure:")
    lines.append(f"1. Mode: {scheme.application_mode}")
    lines.append(f"2. Official Portal: {scheme.official_portal_url}")

    return lines


def main():
    guidelines_dir = os.path.join(BASE_DIR, "samples", "guidelines")
    os.makedirs(guidelines_dir, exist_ok=True)

    store = SchemeKnowledgeStore()
    vector_store = SchemeVectorStore()
    parser = PDFGuidelinesParser(chunk_size=400, chunk_overlap=80)

    schemes = store.list_schemes(status="Active", limit=500)
    logger.info(f"Loaded {len(schemes)} active schemes from SQLite Knowledge Store.")

    total_generated = 0
    total_chunks_saved = 0

    for scheme in schemes:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", scheme.scheme_id).lower()
        pdf_filename = f"{slug}_guidelines.pdf"
        pdf_path = os.path.join(guidelines_dir, pdf_filename)

        # Retain pre-existing pmegp_guidelines.pdf and zed_guidelines.pdf
        if scheme.scheme_id == "pmegp" and os.path.exists(os.path.join(guidelines_dir, "pmegp_guidelines.pdf")):
            pdf_path = os.path.join(guidelines_dir, "pmegp_guidelines.pdf")
        elif scheme.scheme_id == "zed" and os.path.exists(os.path.join(guidelines_dir, "zed_guidelines.pdf")):
            pdf_path = os.path.join(guidelines_dir, "zed_guidelines.pdf")
        else:
            lines = build_guideline_lines(scheme)
            lines_per_page = 38
            pages = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)]
            pdf_bytes = generate_multipage_pdf_bytes(pages)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            total_generated += 1

        # Parse and save chunks into knowledge base
        parsed = parser.parse_file(pdf_path, scheme_id=scheme.scheme_id)
        if parsed.chunks:
            saved = store.save_document_chunks(parsed.chunks)
            total_chunks_saved += saved
            logger.info(f"Saved {saved} guideline chunks for scheme '{scheme.scheme_id}' from {os.path.basename(pdf_path)}")

    logger.info(f"Total PDFs processed: {len(schemes)} (Generated: {total_generated}, Chunks Ingested: {total_chunks_saved})")

    # Rebuild hybrid vector index with all schemes and guideline chunks
    all_chunks = []
    for s in schemes:
        chunks = store.get_document_chunks_for_scheme(s.scheme_id)
        all_chunks.extend(chunks)

    indexed = vector_store.build_index(schemes, all_chunks)
    logger.info(f"Rebuilt hybrid vector index with {indexed} entries.")

    # Print final summary statistics
    stats = store.get_statistics()
    logger.info("Knowledge Base Statistics:")
    logger.info(f"  - Total Schemes: {stats['total_schemes']}")
    logger.info(f"  - Total Guideline Chunks: {stats['total_guideline_chunks']}")


if __name__ == "__main__":
    main()

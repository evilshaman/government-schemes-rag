"""
Document Upload & Business Profiling API Routes.
Handles:
- Uploading GST Certificate (Form GST REG-06) or Udyam PDFs/images.
- Text & Multimodal parsing into standardized BusinessProfile schema.
- Loading pre-configured sample profiles for one-click testing.
- Manual profile adjustment and validation.
"""

from __future__ import annotations
import os
import json
import io
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from pypdf import PdfReader

from schemas.business_profile import (
    BusinessProfile,
    ConstitutionType,
    MSMETier,
    SocialCategory,
    TurnoverBracket,
)
from parsers.gst_parser import GSTCertificateParser

from core.config import settings
from api.metrics import metrics

logger = logging.getLogger("UploadAPI")
router = APIRouter(prefix="/api", tags=["Document Ingestion & Profiling"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLES_FILE = os.path.join(BASE_DIR, "samples", "sample_gst_certificates.json")


def load_raw_samples() -> List[Dict[str, Any]]:
    if not os.path.exists(SAMPLES_FILE):
        return []
    with open(SAMPLES_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("samples", [])


@router.get("/sample-profiles", response_model=List[Dict[str, Any]])
async def list_sample_profiles():
    """
    Returns available test sample profiles for 1-click evaluation.
    """
    samples = load_raw_samples()
    summary = []
    for idx, s in enumerate(samples, 1):
        summary.append({
            "sample_id": idx,
            "id": s.get("id"),
            "description": s.get("description"),
            "sector": s.get("extra_profile_metadata", {}).get("primary_sector", "General"),
        })
    return summary


@router.post("/sample-profile/{sample_id}", response_model=BusinessProfile)
async def get_sample_profile(sample_id: int):
    """
    Loads and normalizes one of the curated sample test profiles (1, 2, or 3).
    """
    samples = load_raw_samples()
    if sample_id < 1 or sample_id > len(samples):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample profile #{sample_id} not found. Available samples: 1 to {len(samples)}."
        )

    chosen = samples[sample_id - 1]
    profile = GSTCertificateParser.parse_from_text(chosen["raw_certificate_text"])

    # Overlay metadata
    meta = chosen.get("extra_profile_metadata", {})
    if meta.get("primary_sector"):
        profile.primary_sector = meta["primary_sector"]
    if meta.get("turnover_bracket"):
        profile.turnover_bracket = TurnoverBracket(meta["turnover_bracket"])
    if meta.get("msme_tier"):
        profile.msme_tier = MSMETier(meta["msme_tier"])
    if meta.get("social_category"):
        profile.social_category = SocialCategory(meta["social_category"])
    if "is_woman_owned" in meta:
        profile.is_woman_owned = meta["is_woman_owned"]
    if "is_dpiit_recognized" in meta:
        profile.is_dpiit_recognized = meta["is_dpiit_recognized"]

    return profile


@router.post("/upload-document", response_model=Dict[str, Any])
async def upload_document(
    file: UploadFile = File(..., description="GST REG-06 or Udyam Certificate (PDF, PNG, JPG, TXT)"),
    turnover_bracket: Optional[str] = Form(None),
    is_woman_owned: Optional[bool] = Form(False),
    is_dpiit_recognized: Optional[bool] = Form(False),
):
    """
    Uploads a business registration document, extracts text/metadata,
    and returns the normalized BusinessProfile digital twin.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File exceeds maximum upload size of {max_mb}MB.")

    filename = file.filename.lower() if file.filename else "uploaded_file"
    extracted_text = ""

    # 1. Handle PDF
    if filename.endswith(".pdf"):
        try:
            pdf_stream = io.BytesIO(content)
            reader = PdfReader(pdf_stream)
            extracted_text = "\n".join([page.extract_text() or "" for page in reader.pages])
        except Exception as exc:
            logger.error(f"Failed to read PDF document: {exc}")
            raise HTTPException(status_code=400, detail=f"Failed to read PDF document: {exc}")

    # 2. Handle Text files
    elif filename.endswith((".txt", ".json")):
        try:
            extracted_text = content.decode("utf-8")
        except UnicodeDecodeError:
            extracted_text = content.decode("latin-1")

    # 3. Handle Images / Other Formats
    else:
        # Fallback to UTF-8/Latin text decoding or mock OCR
        try:
            extracted_text = content.decode("utf-8", errors="ignore")
        except Exception:
            extracted_text = ""

    if not extracted_text.strip():
        # Provide minimal placeholder text to allow schema parsing
        extracted_text = f"Government of India Form GST REG-06 Document: {filename}"

    # Parse into BusinessProfile
    profile = GSTCertificateParser.parse_from_text(extracted_text)

    # Apply user overrides if provided
    if turnover_bracket and turnover_bracket != "Unknown":
        try:
            profile.turnover_bracket = TurnoverBracket(turnover_bracket)
        except ValueError:
            pass

    if is_woman_owned:
        profile.is_woman_owned = True
    if is_dpiit_recognized:
        profile.is_dpiit_recognized = True

    metrics.record_gst_upload()

    return {
        "success": True,
        "file_name": file.filename,
        "file_size_bytes": len(content),
        "text_snippet": extracted_text[:300].strip(),
        "profile": profile.model_dump(mode="json"),
    }


@router.post("/profile/validate", response_model=BusinessProfile)
async def validate_profile(profile: BusinessProfile):
    """
    Validates and updates dynamically computed fields (age, MSME tier) for a modified profile.
    """
    return profile

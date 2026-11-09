"""
GST Certificate Parser Prototype (Form GST REG-06).
Supports:
1. Multimodal Gemini LLM Vision Extraction Prompting.
2. Deterministic Rule-Based & Regex Parsing for OCR / Text extracts.
3. State code mapping & Entity Normalization into BusinessProfile schema.
"""

from __future__ import annotations
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from schemas.business_profile import (
    BusinessAddress,
    BusinessProfile,
    ConstitutionType,
    MSMETier,
    TurnoverBracket,
)

# Load State Codes Map
CURRENT_DIR = Path(__file__).resolve().parent
DATA_DIR = CURRENT_DIR.parent / "data"
STATE_CODES_FILE = DATA_DIR / "gst_state_codes.json"

STATE_CODES_MAP: Dict[str, str] = {}
if STATE_CODES_FILE.exists():
    with open(STATE_CODES_FILE, "r", encoding="utf-8") as f:
        STATE_CODES_MAP = json.load(f)


# Prompt template for Gemini Multimodal Vision API
GST_MULTIMODAL_PROMPT = """
You are an expert Indian Government Document Extraction Engine specializing in GST Registration Certificates (Form GST REG-06).
Examine the uploaded document and extract all fields with zero hallucination.

Ensure the output is strictly valid JSON matching the following schema:
{
  "gstin": "15-character alphanumeric GSTIN",
  "legal_name": "Official legal name of the entity (Field 1)",
  "trade_name": "Operating/trade name if present (Field 2), otherwise null",
  "constitution_of_business": "One of: 'Proprietorship', 'Partnership', 'Private Limited Company', 'Public Limited Company', 'Limited Liability Partnership', 'Society/Trust', 'HUF', 'Other' (Field 3)",
  "principal_address": {
    "full_address": "Complete address as written (Field 4)",
    "district": "District name if determinable, otherwise null",
    "state_name": "State name",
    "state_code": "2-digit GST state code derived from GSTIN",
    "pincode": "6-digit PIN code"
  },
  "additional_addresses": [],
  "date_of_registration": "YYYY-MM-DD",
  "date_of_liability": "YYYY-MM-DD or null",
  "nature_of_activities": ["Manufacturing", "Wholesale Business", "Retail Business", "Provision of Services", "Export"],
  "hsn_sac_codes": ["List of HSN (goods) or SAC (services) codes listed in Annexure B"],
  "primary_sector": "Inferred primary sector (e.g. 'Electronics', 'Textiles', 'Food Processing', 'Information Technology', 'General')",
  "turnover_bracket": "Unknown",
  "msme_tier": "Unknown"
}

Extraction Guidelines:
- The first 2 digits of the GSTIN represent the State Code.
- Field 1 is Legal Name, Field 2 is Trade Name.
- Date of validity/registration is typically in DD/MM/YYYY format; convert it to YYYY-MM-DD.
- Inspect Annexure B for HSN (Goods) and SAC (Services) codes and descriptions.
- Return ONLY the raw JSON object, without backticks or markdown preamble.
"""


def get_gemini_extraction_prompt() -> str:
    """Returns the standardized multimodal vision prompt."""
    return GST_MULTIMODAL_PROMPT.strip()


def resolve_state_from_gstin(gstin: str) -> Tuple[str, str]:
    """
    Decodes the first two digits of GSTIN to state code and state name.
    """
    gstin = gstin.strip().upper()
    state_code = gstin[:2]
    state_name = STATE_CODES_MAP.get(state_code, "Unknown")
    return state_code, state_name


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """
    Parses date strings commonly found in Indian documents (DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD).
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    patterns = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y"]
    for pat in patterns:
        try:
            return datetime.strptime(date_str, pat).date()
        except ValueError:
            continue
    return None


def normalize_constitution(val: Optional[str]) -> ConstitutionType:
    """
    Normalizes variations of business constitutions into ConstitutionType enum.
    """
    if not val:
        return ConstitutionType.OTHER

    normalized = val.strip().lower()
    if "private limited" in normalized or "pvt ltd" in normalized or "pvt. ltd" in normalized:
        return ConstitutionType.PRIVATE_LIMITED
    elif "limited liability partnership" in normalized or "llp" in normalized:
        return ConstitutionType.LLP
    elif "public limited" in normalized:
        return ConstitutionType.PUBLIC_LIMITED
    elif "proprietor" in normalized or "individual" in normalized or "sole" in normalized:
        return ConstitutionType.PROPRIETORSHIP
    elif "partnership" in normalized:
        return ConstitutionType.PARTNERSHIP
    elif "society" in normalized or "trust" in normalized:
        return ConstitutionType.SOCIETY_TRUST
    elif "huf" in normalized or "hindu undivided" in normalized:
        return ConstitutionType.HUF
    return ConstitutionType.OTHER


class GSTCertificateParser:
    """
    Parser for GST Registration Certificate (Form GST REG-06).
    """

    @classmethod
    def parse_from_text(cls, text: str) -> BusinessProfile:
        """
        Deterministic regex & pattern-based parsing for OCR-extracted or plain text GST certificates.
        """
        # 1. GSTIN (15 characters: 2 digits, 5 letters, 4 digits, 1 letter, 1 alphanumeric, 'Z', 1 alphanumeric)
        gstin_match = re.search(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})\b", text, re.IGNORECASE)
        gstin = gstin_match.group(1).upper() if gstin_match else None

        # State resolution
        state_code = "99"
        state_name = "India"
        if gstin:
            state_code, state_name = resolve_state_from_gstin(gstin)

        # 2. Legal Name (Field 1)
        legal_name = "Unknown Legal Entity"
        legal_match = re.search(r"(?:1\.\s*Legal\s*Name|Legal\s*Name\s*[:\-])\s*([^\n\r]+)", text, re.IGNORECASE)
        if legal_match:
            legal_name = re.sub(r"^[:\-\s]+", "", legal_match.group(1)).strip()
        else:
            # Fallback search
            fallback_match = re.search(r"Registration Certificate\s*\n+([A-Z0-9\s.,&'-]+?)(?:\n|Trade Name)", text)
            if fallback_match:
                legal_name = re.sub(r"^[:\-\s]+", "", fallback_match.group(1)).strip()

        # 3. Trade Name (Field 2)
        trade_name = None
        trade_match = re.search(r"(?:2\.\s*Trade\s*Name(?:,\s*if\s*any)?|Trade\s*Name\s*[:\-])\s*([^\n\r]+)", text, re.IGNORECASE)
        if trade_match:
            candidate = re.sub(r"^[:\-\s]+", "", trade_match.group(1)).strip()
            if candidate.lower() not in ["na", "n/a", "null", "-", "none"]:
                trade_name = candidate

        # 4. Constitution of Business (Field 3)
        constitution_raw = "Other"
        const_match = re.search(r"(?:3\.\s*Constitution\s*of\s*Business|Constitution\s*of\s*Business\s*[:\-])\s*([^\n\r]+)", text, re.IGNORECASE)
        if const_match:
            constitution_raw = re.sub(r"^[:\-\s]+", "", const_match.group(1)).strip()
        constitution = normalize_constitution(constitution_raw)

        # 5. Principal Address (Field 4)
        address_raw = "Registered Address Not Specified"
        addr_match = re.search(r"(?:4\.\s*Address\s*of\s*Principal\s*Place\s*of\s*Business|Address\s*[:\-])\s*([\s\S]+?)(?=(?:5\.|\n\s*Date\s*of\s*Liability|$))", text, re.IGNORECASE)
        if addr_match:
            cleaned_addr = re.sub(r"^[:\-\s]+", "", addr_match.group(1))
            address_raw = re.sub(r"\s+", " ", cleaned_addr).strip()

        # Extract PIN code (6 digits)
        pin_match = re.search(r"\b([1-9][0-9]{5})\b", address_raw)
        pincode = pin_match.group(1) if pin_match else None

        # Extract District if present
        district = None
        dist_match = re.search(r"(?:District|Dist\.?)\s*[:\-]?\s*([A-Za-z]+)", address_raw, re.IGNORECASE)
        if dist_match:
            district = dist_match.group(1).strip()

        principal_address = BusinessAddress(
            full_address=address_raw,
            district=district,
            state_name=state_name,
            state_code=state_code,
            pincode=pincode,
        )

        # 6. Date of Liability (Field 5) & Date of Registration (Period of Validity from)
        reg_date: Optional[date] = None
        liability_date: Optional[date] = None

        date_of_reg_match = re.search(r"(?:Period\s*of\s*Validity\s*From|Date\s*of\s*Registration\s*[:\-])\s*([0-9]{2}[/\-.][0-9]{2}[/\-.][0-9]{2,4})", text, re.IGNORECASE)
        if date_of_reg_match:
            reg_date = parse_date(date_of_reg_match.group(1))

        liability_match = re.search(r"(?:Date\s*of\s*Liability\s*[:\-])\s*([0-9]{2}[/\-.][0-9]{2}[/\-.][0-9]{2,4})", text, re.IGNORECASE)
        if liability_match:
            liability_date = parse_date(liability_match.group(1))

        if not reg_date and liability_date:
            reg_date = liability_date
        elif not reg_date:
            reg_date = date.today()

        # 7. Nature of Activities & HSN/SAC codes
        activities = []
        for kw in ["Manufacturing", "Services", "Wholesale", "Retail", "Export", "Work Contract"]:
            if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
                activities.append(kw)
        if not activities:
            activities = ["General Commercial Activity"]

        # HSN / SAC Codes: search specifically for lines/tokens prefaced with HSN or SAC, or inside Annexure B
        hsn_sac_pattern = r"(?:HSN|SAC)\s*[:\-#]?\s*([0-9]{4,8})\b"
        found_codes = re.findall(hsn_sac_pattern, text, re.IGNORECASE)
        
        # If no explicit HSN/SAC prefix, check Annexure B section
        if not found_codes and "annexure b" in text.lower():
            annexure_b = text.lower().split("annexure b", 1)[1]
            found_codes = re.findall(r"\b([0-9]{4,8})\b", annexure_b)

        # Deduplicate while preserving order and ignore pincodes/years
        excluded_numbers = {str(pincode), str(reg_date.year) if reg_date else ""}
        cleaned_hsn = []
        for c in found_codes:
            if c not in excluded_numbers and len(c) in [4, 6, 8] and c not in cleaned_hsn:
                cleaned_hsn.append(c)

        # Infer Primary Sector
        sector = "General"
        text_lower = text.lower()
        if any(w in text_lower for w in ["software", "information technology", "tech", "saas", "digital"]):
            sector = "Information Technology"
        elif any(w in text_lower for w in ["electronic", "semiconductor", "circuit", "hardware"]):
            sector = "Electronics"
        elif any(w in text_lower for w in ["food", "beverage", "dairy", "grain", "agro", "spice"]):
            sector = "Food Processing"
        elif any(w in text_lower for w in ["textile", "garment", "fabric", "cotton", "apparel"]):
            sector = "Textiles & Apparel"
        elif any(w in text_lower for w in ["biotech", "pharma", "medical", "diagnostic", "health"]):
            sector = "Biotechnology"

        profile = BusinessProfile(
            gstin=gstin,
            legal_name=legal_name,
            trade_name=trade_name,
            constitution=constitution,
            principal_address=principal_address,
            date_of_registration=reg_date,
            date_of_liability=liability_date,
            nature_of_activities=activities,
            hsn_sac_codes=cleaned_hsn[:5],
            primary_sector=sector,
            turnover_bracket=TurnoverBracket.UNKNOWN,
            msme_tier=MSMETier.UNKNOWN,
        )

        return profile

    @classmethod
    def parse_from_json_dict(cls, data: Dict[str, Any]) -> BusinessProfile:
        """
        Hydrates a BusinessProfile directly from JSON output produced by Gemini Multimodal Vision API.
        """
        # Ensure date formats
        if isinstance(data.get("date_of_registration"), str):
            data["date_of_registration"] = parse_date(data["date_of_registration"]) or date.today()
        if isinstance(data.get("date_of_liability"), str):
            data["date_of_liability"] = parse_date(data["date_of_liability"])

        # Normalize constitution enum
        if "constitution_of_business" in data and "constitution" not in data:
            data["constitution"] = normalize_constitution(data.pop("constitution_of_business"))
        elif isinstance(data.get("constitution"), str):
            data["constitution"] = normalize_constitution(data["constitution"])

        # Ensure state resolution
        gstin = data.get("gstin")
        if gstin and isinstance(data.get("principal_address"), dict):
            state_code, state_name = resolve_state_from_gstin(gstin)
            if not data["principal_address"].get("state_code"):
                data["principal_address"]["state_code"] = state_code
            if not data["principal_address"].get("state_name") or data["principal_address"]["state_name"] == "Unknown":
                data["principal_address"]["state_name"] = state_name

        return BusinessProfile.model_validate(data)

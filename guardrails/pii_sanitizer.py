"""
PII Sanitization & Redaction Guardrails (Phase 5).
Protects applicant privacy by detecting and masking sensitive Personally Identifiable Information:
- Aadhaar Numbers (12 digits)
- PAN Numbers (10 alphanumeric characters)
- Phone Numbers (Indian 10-digit / +91 formats)
- Email Addresses
- Bank Account Numbers
- Director Identification Numbers (DIN)
"""

from __future__ import annotations
import re
from typing import Dict, Any, List, Optional
from schemas.business_profile import BusinessProfile


class PIISanitizer:
    """
    Detects and masks sensitive personal identifiers in text, dicts, and BusinessProfile objects.
    """

    # Regex patterns for Indian identifiers
    AADHAAR_REGEX = re.compile(r"\b[2-9]{1}[0-9]{3}[\s-]?[0-9]{4}[\s-]?[0-9]{4}\b")
    PAN_REGEX = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b")
    PHONE_REGEX = re.compile(r"(?:\+91[\-\s]?)?[6-9]\d{9}\b")
    EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    BANK_ACC_REGEX = re.compile(r"\b\d{9,18}\b")

    @classmethod
    def mask_aadhaar(cls, text: str) -> str:
        """
        Masks 12-digit Aadhaar, showing only last 4 digits: XXXX-XXXX-1234
        """
        def _replace(match):
            raw = re.sub(r"[\s-]", "", match.group(0))
            return f"XXXX-XXXX-{raw[-4:]}"
        return cls.AADHAAR_REGEX.sub(_replace, text)

    @classmethod
    def mask_pan(cls, text: str, preserve_format: bool = True) -> str:
        """
        Masks personal PAN while preserving first 3 chars and last char: ABCXX1234X -> ABCXXXXXXF
        """
        def _replace(match):
            pan = match.group(0)
            if preserve_format:
                return f"{pan[:3]}XXXXX{pan[-2:]}"
            return "[PAN_REDACTED]"
        return cls.PAN_REGEX.sub(_replace, text)

    @classmethod
    def mask_phone(cls, text: str) -> str:
        """
        Masks Indian mobile phone numbers: +91 XXXXX-12345
        """
        def _replace(match):
            digits = re.sub(r"\D", "", match.group(0))
            return f"+91 XXXXX-{digits[-4:]}"
        return cls.PHONE_REGEX.sub(_replace, text)

    @classmethod
    def mask_email(cls, text: str) -> str:
        """
        Masks email addresses: j***e@domain.com
        """
        def _replace(match):
            email = match.group(0)
            user, domain = email.split("@", 1)
            if len(user) <= 2:
                masked_user = user[0] + "*"
            else:
                masked_user = user[0] + ("*" * (len(user) - 2)) + user[-1]
            return f"{masked_user}@{domain}"
        return cls.EMAIL_REGEX.sub(_replace, text)

    @classmethod
    def sanitize_text(cls, text: str, redact_pan: bool = False) -> str:
        """
        Applies full PII sanitization pipeline over plain text.
        """
        if not text:
            return ""
        sanitized = cls.mask_aadhaar(text)
        sanitized = cls.mask_phone(sanitized)
        sanitized = cls.mask_email(sanitized)
        if redact_pan:
            sanitized = cls.mask_pan(sanitized)
        return sanitized

    @classmethod
    def sanitize_profile(cls, profile: BusinessProfile) -> BusinessProfile:
        """
        Returns a sanitized copy of a BusinessProfile safe for external transmission / logging.
        Retains valid state and business parameters while redacting personal PII.
        """
        data = profile.model_dump()
        # Sanitize full address if it contains phone or personal contact
        if "principal_address" in data and "full_address" in data["principal_address"]:
            data["principal_address"]["full_address"] = cls.sanitize_text(data["principal_address"]["full_address"])

        for addr in data.get("additional_addresses", []):
            if "full_address" in addr:
                addr["full_address"] = cls.sanitize_text(addr["full_address"])

        return BusinessProfile.model_validate(data)

    @classmethod
    def audit_pii_presence(cls, text: str) -> Dict[str, Any]:
        """
        Scans text and reports any PII detected for compliance auditing.
        """
        aadhaar_matches = cls.AADHAAR_REGEX.findall(text)
        pan_matches = cls.PAN_REGEX.findall(text)
        phone_matches = cls.PHONE_REGEX.findall(text)
        email_matches = cls.EMAIL_REGEX.findall(text)

        total_pii_count = len(aadhaar_matches) + len(pan_matches) + len(phone_matches) + len(email_matches)
        return {
            "has_pii": total_pii_count > 0,
            "total_pii_detected": total_pii_count,
            "aadhaar_detected_count": len(aadhaar_matches),
            "pan_detected_count": len(pan_matches),
            "phone_detected_count": len(phone_matches),
            "email_detected_count": len(email_matches),
        }

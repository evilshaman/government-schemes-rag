"""
Business Profile Schema for Government Schemes Discovery Engine.
Extracts and normalizes structured metadata from business registration documents
such as GST Registration Certificate (Form GST REG-06) and Udyam Registration.
"""

from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ConstitutionType(str, Enum):
    PROPRIETORSHIP = "Proprietorship"
    PARTNERSHIP = "Partnership"
    PRIVATE_LIMITED = "Private Limited Company"
    PUBLIC_LIMITED = "Public Limited Company"
    LLP = "Limited Liability Partnership"
    SOCIETY_TRUST = "Society/Trust"
    HUF = "Hindu Undivided Family"
    OTHER = "Other"


class MSMETier(str, Enum):
    MICRO = "Micro"
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    UNKNOWN = "Unknown"


class TurnoverBracket(str, Enum):
    BELOW_1_CR = "Below ₹1 Crore"
    CR_1_TO_5 = "₹1 Crore to ₹5 Crore"
    CR_5_TO_50 = "₹5 Crore to ₹50 Crore"
    CR_50_TO_250 = "₹50 Crore to ₹250 Crore"
    ABOVE_250_CR = "Above ₹250 Crore"
    UNKNOWN = "Unknown"


class SocialCategory(str, Enum):
    GENERAL = "General"
    SC = "SC"
    ST = "ST"
    OBC = "OBC"
    MINORITY = "Minority"
    UNKNOWN = "Unknown"


class BusinessAddress(BaseModel):
    full_address: str = Field(..., description="Complete address as listed on registration")
    city_or_town: Optional[str] = Field(None, description="City, town, or village")
    district: Optional[str] = Field(None, description="District name")
    state_name: str = Field(..., description="Full state or union territory name")
    state_code: str = Field(..., description="2-digit GST state code (e.g., '27' for Maharashtra)")
    pincode: Optional[str] = Field(None, description="6-digit postal code")


class BusinessProfile(BaseModel):
    """
    Standardized Business Profile representation extracted from documents.
    Serves as the input object for deterministic pre-filtering and hybrid RAG matching.
    """
    gstin: Optional[str] = Field(
        None,
        description="15-character Goods and Services Tax Identification Number"
    )
    legal_name: str = Field(
        ...,
        description="Official legal name of the entity as recognized by government"
    )
    trade_name: Optional[str] = Field(
        None,
        description="Operating/trade name if different from legal name"
    )
    constitution: ConstitutionType = Field(
        ...,
        description="Legal constitution/entity structure of the business"
    )
    principal_address: BusinessAddress = Field(
        ...,
        description="Principal place of business"
    )
    additional_addresses: List[BusinessAddress] = Field(
        default_factory=list,
        description="Branch offices, factories, or additional premises"
    )
    date_of_registration: date = Field(
        ...,
        description="Official date of registration (e.g. from GST REG-06 or Incorporation)"
    )
    date_of_liability: Optional[date] = Field(
        None,
        description="Date from which liability to register commenced"
    )
    business_age_years: float = Field(
        default=0.0,
        description="Age of business in years from registration date to present"
    )
    nature_of_activities: List[str] = Field(
        default_factory=list,
        description="E.g. Manufacturing, Retail Business, Wholesale, Services, Export"
    )
    hsn_sac_codes: List[str] = Field(
        default_factory=list,
        description="Extracted HSN (goods) or SAC (services) codes"
    )
    primary_sector: str = Field(
        default="General",
        description="Inferred or declared primary industry sector"
    )
    turnover_bracket: TurnoverBracket = Field(
        default=TurnoverBracket.UNKNOWN,
        description="Annual turnover bracket"
    )
    msme_tier: MSMETier = Field(
        default=MSMETier.UNKNOWN,
        description="MSME classification (Micro/Small/Medium/Large)"
    )
    social_category: SocialCategory = Field(
        default=SocialCategory.UNKNOWN,
        description="Social category of primary promoter / owner"
    )
    is_woman_owned: bool = Field(
        default=False,
        description="Whether primary promoter / majority shareholding is women-led"
    )
    is_dpiit_recognized: bool = Field(
        default=False,
        description="DPIIT Startup Recognition status"
    )
    has_zed_certification: bool = Field(
        default=False,
        description="Whether unit holds Zero Defect Zero Effect (ZED) certification"
    )

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().upper()
            if len(v) != 15:
                raise ValueError(f"GSTIN must be 15 characters long, got {len(v)}: '{v}'")
        return v

    @model_validator(mode="after")
    def calculate_age_and_defaults(self) -> BusinessProfile:
        # Dynamically compute business age in years
        today = date.today()
        if self.date_of_registration:
            days_diff = (today - self.date_of_registration).days
            self.business_age_years = round(max(0.0, days_diff / 365.25), 2)

        # Derive MSME Tier from Turnover if not explicitly set
        if self.msme_tier == MSMETier.UNKNOWN and self.turnover_bracket != TurnoverBracket.UNKNOWN:
            if self.turnover_bracket == TurnoverBracket.BELOW_1_CR:
                self.msme_tier = MSMETier.MICRO
            elif self.turnover_bracket == TurnoverBracket.CR_1_TO_5:
                self.msme_tier = MSMETier.MICRO
            elif self.turnover_bracket == TurnoverBracket.CR_5_TO_50:
                self.msme_tier = MSMETier.SMALL
            elif self.turnover_bracket == TurnoverBracket.CR_50_TO_250:
                self.msme_tier = MSMETier.MEDIUM
            elif self.turnover_bracket == TurnoverBracket.ABOVE_250_CR:
                self.msme_tier = MSMETier.LARGE

        return self

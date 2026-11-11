export interface BusinessAddress {
  full_address: string;
  city_or_town?: string | null;
  district?: string | null;
  state_name: string;
  state_code: string;
  pincode?: string | null;
}

export interface BusinessProfile {
  gstin?: string | null;
  legal_name: string;
  trade_name?: string | null;
  constitution: string;
  principal_address: BusinessAddress;
  date_of_registration: string;
  business_age_years: number;
  nature_of_activities: string[];
  hsn_sac_codes: string[];
  primary_sector: string;
  turnover_bracket: string;
  msme_tier: string;
  social_category: string;
  is_woman_owned: boolean;
  is_dpiit_recognized: boolean;
  has_zed_certification?: boolean;
}

export interface FinancialBenefitCalculation {
  benefit_type: string;
  quantum_description: string;
  subsidy_percentage?: number | null;
  max_cap_inr?: number | null;
  estimated_eligible_amount_inr?: number | null;
  special_affirmative_boost?: string | null;
}

export interface DocumentGapItem {
  document_name: string;
  status: "Available" | "Missing" | "Conditional" | "Action Required";
  criticality: "Mandatory" | "Recommended" | "Optional";
  issuing_authority: string;
  how_to_obtain: string;
  estimated_turnaround_days: number;
  prerequisites: string[];
}

export interface ClauseCitation {
  source_document: string;
  section_or_page: string;
  excerpt: string;
  relevance_explanation: string;
}

export interface SchemeEligibilityAssessment {
  scheme_id: string;
  scheme_name: string;
  scheme_short_code: string;
  verdict: "Eligible" | "Conditionally Eligible" | "Ineligible";
  match_score: number;
  confidence_score: number;
  executive_summary: string;
  eligibility_rationale: string[];
  disqualification_or_gap_reasons: string[];
  official_citations: ClauseCitation[];
  financial_benefit: FinancialBenefitCalculation;
  document_checklist: DocumentGapItem[];
  missing_mandatory_docs_count: number;
  application_roadmap: string[];
  application_portal_url: string;
  nodal_agency: string;
}

export interface FullReasoningReport {
  business_legal_name: string;
  trade_name?: string | null;
  gstin?: string | null;
  state: string;
  constitution: string;
  msme_tier: string;
  primary_sector: string;
  business_age_years: number;
  query_intent?: string | null;
  total_schemes_searched: number;
  top_candidates_evaluated: number;
  eligible_count: number;
  conditional_count: number;
  ineligible_count: number;
  top_recommendations: SchemeEligibilityAssessment[];
  strategic_roadmap_summary: string;
  generated_at: string;
}

export interface GovernmentScheme {
  scheme_id: string;
  scheme_name: string;
  scheme_short_code: string;
  nodal_ministry: string;
  implementing_agency: string;
  jurisdiction: string;
  summary: string;
  benefits: {
    benefit_type: string;
    quantum_description: string;
  };
  tags: string[];
  official_portal_url: string;
  application_mode?: string;
  application_process?: string[];
  application_process_md?: string | null;
}

export interface ChatRequest {
  message: string;
  scheme_id?: string | null;
  history?: Array<{ role: string; content: string }>;
  profile?: BusinessProfile | null;
}

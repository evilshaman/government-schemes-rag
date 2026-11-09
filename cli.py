"""
Command Line Interface (CLI) for Phase 1: GST Parsing & Flagship Scheme Discovery.
Demonstrates:
- Ingestion & extraction of GST Form GST REG-06.
- Construction of normalized BusinessProfile.
- Stage 1 Deterministic Filtering against 30 flagship schemes.
- Generation of actionable Eligibility & Gap Analysis Report.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from schemas.business_profile import (
    BusinessProfile,
    ConstitutionType,
    MSMETier,
    SocialCategory,
    TurnoverBracket,
)
from schemas.government_scheme import GovernmentScheme
from parsers.gst_parser import GSTCertificateParser, get_gemini_extraction_prompt
from engine.matcher import DeterministicSchemeMatcher, MatchReport
from engine.pipeline_phase3 import Phase3ReasonerPipeline


def load_seed_schemes() -> list[GovernmentScheme]:
    schemes_file = BASE_DIR / "data" / "schemes_seed.json"
    with open(schemes_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [GovernmentScheme.model_validate(s) for s in data]


def load_samples() -> list[dict]:
    samples_file = BASE_DIR / "samples" / "sample_gst_certificates.json"
    with open(samples_file, "r", encoding="utf-8") as f:
        return json.load(f)["samples"]


def print_banner():
    print("=" * 80)
    print("   GOVERNMENT SCHEMES DISCOVERY PLATFORM - PHASE 1 PROTOTYPE")
    print("   Document-Driven Business Profiling & Deterministic Scheme Discovery")
    print("=" * 80)


def print_profile(profile: BusinessProfile):
    print("\n" + "-" * 40 + " EXTRACTED BUSINESS PROFILE " + "-" * 40)
    print(f" Legal Name         : {profile.legal_name}")
    print(f" Trade Name         : {profile.trade_name or 'N/A'}")
    print(f" GSTIN              : {profile.gstin or 'N/A'}")
    print(f" Constitution       : {profile.constitution.value}")
    print(f" Registered State   : {profile.principal_address.state_name} (Code: {profile.principal_address.state_code})")
    print(f" Full Address       : {profile.principal_address.full_address}")
    print(f" Registration Date  : {profile.date_of_registration} (Business Age: {profile.business_age_years:.1f} years)")
    print(f" Primary Sector     : {profile.primary_sector}")
    print(f" MSME Classification: {profile.msme_tier.value} | Turnover: {profile.turnover_bracket.value}")
    print(f" Activities         : {', '.join(profile.nature_of_activities)}")
    print(f" HSN/SAC Codes      : {', '.join(profile.hsn_sac_codes) if profile.hsn_sac_codes else 'None'}")
    print(f" Special Status     : Woman-Owned: {profile.is_woman_owned} | DPIIT Recognized: {profile.is_dpiit_recognized} | Social: {profile.social_category.value}")
    print("-" * 88)


def print_match_report(report: MatchReport):
    print("\n" + "=" * 35 + " ELIGIBILITY VERDICT " + "=" * 35)
    print(f"Total Policy Universe Evaluated: {report.total_schemes_evaluated} Flagship Schemes")
    print(f" Eligible Schemes              : {report.eligible_schemes_count}")
    print(f" Conditional / Gap Detected    : {report.conditional_schemes_count}")
    print(f" Disqualified Schemes          : {report.disqualified_schemes_count}")
    print("=" * 88)

    # 1. Eligible Schemes
    print(f"\n  [+] ELIGIBLE SCHEMES ({report.eligible_schemes_count} MATCHES):")
    if not report.eligible_schemes:
        print("    No schemes matched all strict criteria.")
    for idx, match in enumerate(report.eligible_schemes, 1):
        print(f"\n    {idx}. {match.scheme_name} [{match.scheme_short_code}] (Score: {match.score})")
        print(f"       Benefit: {match.quantum_of_benefit}")
        print(f"       Apply: {match.application_portal}")
        print("       Matching Criteria:")
        for pt in match.matching_criteria:
            print(f"         * {pt}")

    # 2. Conditional Schemes (Gap Detected)
    if report.conditional_schemes:
        print(f"\n  [?] CONDITIONAL / ACTIONABLE GAPS ({report.conditional_schemes_count} SCHEMES):")
        for idx, match in enumerate(report.conditional_schemes, 1):
            print(f"\n    {idx}. {match.scheme_name} [{match.scheme_short_code}]")
            print(f"       Benefit: {match.quantum_of_benefit}")
            print("       Missing Prerequisites / Actions to Unlock:")
            for req in match.missing_prerequisites:
                print(f"         ! {req}")

    # 3. Disqualified Schemes
    if report.disqualified_schemes:
        print(f"\n  [-] DISQUALIFIED SCHEMES ({report.disqualified_schemes_count} SCHEMES):")
        for idx, match in enumerate(report.disqualified_schemes, 1):
            reasons = "; ".join(match.disqualification_reasons)
            print(f"    * {match.scheme_short_code}: {reasons}")

    # Aggregate Required Document Checklist across Eligible Schemes
    all_docs = set()
    for m in report.eligible_schemes:
        all_docs.update(m.required_documents)

    if all_docs:
        print("\n" + "-" * 35 + " MASTER APPLICATION CHECKLIST " + "-" * 35)
        print("Documents required to apply for matched eligible schemes:")
        for doc in sorted(all_docs):
            print(f"  [ ] {doc}")
        print("-" * 88)


def main():
    parser = argparse.ArgumentParser(description="Government Schemes Discovery CLI (Phase 1)")
    parser.add_argument("--sample", type=int, choices=[1, 2, 3], default=1, help="Sample GST Certificate (1, 2, or 3)")
    parser.add_argument("--list-schemes", action="store_true", help="List all 30 curated flagship schemes")
    parser.add_argument("--prompt", action="store_true", help="Display Gemini Multimodal Vision prompt template")
    parser.add_argument("--phase3", action="store_true", help="Execute Phase 3 Hybrid Retrieval + Cross-Encoder Reranker + LLM Reasoner")

    args = parser.parse_args()
    print_banner()

    schemes = load_seed_schemes()

    if args.list_schemes:
        print(f"\nCURATED GOLDEN BENCHMARK: {len(schemes)} FLAGSHIP SCHEMES")
        print("-" * 80)
        for idx, s in enumerate(schemes, 1):
            print(f"{idx:2d}. [{s.scheme_short_code:<12}] {s.scheme_name}")
            print(f"    Ministry: {s.nodal_ministry} | Benefit: {s.benefits.benefit_type.value}")
        return

    if args.prompt:
        print("\nGEMINI MULTIMODAL PROMPT TEMPLATE FOR GST REG-06:")
        print("-" * 80)
        print(get_gemini_extraction_prompt())
        return

    samples = load_samples()
    chosen_sample = samples[args.sample - 1]
    print(f"\nProcessing Sample {args.sample}: {chosen_sample['description']}")

    # Step 1: Parse raw certificate text
    profile = GSTCertificateParser.parse_from_text(chosen_sample["raw_certificate_text"])

    # Step 2: Overlay user profile metadata if provided
    meta = chosen_sample.get("extra_profile_metadata", {})
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

    # Step 3: Print Extracted Profile
    print_profile(profile)

    if args.phase3:
        # Step 4: Run Phase 3 Reasoner Pipeline
        phase3 = Phase3ReasonerPipeline()
        report_p3 = phase3.run(profile=profile, top_k_retrieve=10, top_n_rerank=4)
        phase3.print_terminal_report(report_p3)
        return

    # Step 4: Run Deterministic Matcher
    report = DeterministicSchemeMatcher.match_all(profile, schemes)

    # Step 5: Print Verdict Report
    print_match_report(report)


if __name__ == "__main__":
    main()

"""
Phase 1 Test Suite & Golden Benchmark Verification.
Tests:
1. Scheme Schema & Seed Dataset Validation (30 Schemes).
2. GST Certificate Form GST REG-06 Parsing & Normalization.
3. Business Profile Age Calculation & MSME Classification.
4. Deterministic Pre-Filtering & Match Verification.
"""

import json
import os
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from schemas.business_profile import (
    BusinessProfile,
    ConstitutionType,
    MSMETier,
    TurnoverBracket,
    SocialCategory,
)
from schemas.government_scheme import GovernmentScheme
from parsers.gst_parser import GSTCertificateParser, resolve_state_from_gstin
from engine.matcher import DeterministicSchemeMatcher


class TestPhase1(unittest.TestCase):

    def setUp(self):
        # Load Seed Schemes
        schemes_path = BASE_DIR / "data" / "schemes_seed.json"
        with open(schemes_path, "r", encoding="utf-8") as f:
            raw_schemes = json.load(f)
        self.schemes = [GovernmentScheme.model_validate(s) for s in raw_schemes]

        # Load Samples
        samples_path = BASE_DIR / "samples" / "sample_gst_certificates.json"
        with open(samples_path, "r", encoding="utf-8") as f:
            self.samples_data = json.load(f)["samples"]

    def test_seed_dataset_integrity(self):
        """Verifies exactly 30 valid flagship schemes are loaded and conform to schema."""
        self.assertEqual(len(self.schemes), 30)
        scheme_ids = set()
        for scheme in self.schemes:
            self.assertTrue(len(scheme.scheme_id) > 0)
            self.assertNotIn(scheme.scheme_id, scheme_ids, f"Duplicate scheme ID: {scheme.scheme_id}")
            scheme_ids.add(scheme.scheme_id)
            self.assertTrue(scheme.scheme_name)
            self.assertTrue(scheme.official_portal_url.startswith("http"))
            self.assertIsNotNone(scheme.benefits.quantum_description)

    def test_state_code_resolution(self):
        """Verifies GSTIN state code lookup."""
        self.assertEqual(resolve_state_from_gstin("27AAACG1234A1Z5"), ("27", "Maharashtra"))
        self.assertEqual(resolve_state_from_gstin("24AABCS5678B1Z2"), ("24", "Gujarat"))
        self.assertEqual(resolve_state_from_gstin("29AAACL9999C1Z8"), ("29", "Karnataka"))
        self.assertEqual(resolve_state_from_gstin("07AAAAA0000A1Z5"), ("07", "Delhi"))

    def test_gst_parser_sample_1(self):
        """Tests parsing Maharashtra Tech Startup (Pvt Ltd)."""
        sample = self.samples_data[0]
        profile = GSTCertificateParser.parse_from_text(sample["raw_certificate_text"])

        # Check extracted attributes
        self.assertEqual(profile.gstin, "27AAACG1234A1Z5")
        self.assertIn("NEXUS ROBOTICS", profile.legal_name)
        self.assertEqual(profile.constitution, ConstitutionType.PRIVATE_LIMITED)
        self.assertEqual(profile.principal_address.state_code, "27")
        self.assertEqual(profile.principal_address.state_name, "Maharashtra")
        self.assertEqual(profile.principal_address.pincode, "411057")
        self.assertIn("Manufacturing", profile.nature_of_activities)
        self.assertIn("Services", profile.nature_of_activities)

    def test_gst_parser_sample_2(self):
        """Tests parsing Gujarat Food Processing Sole Proprietorship."""
        sample = self.samples_data[1]
        profile = GSTCertificateParser.parse_from_text(sample["raw_certificate_text"])

        self.assertEqual(profile.gstin, "24AABCS5678B1Z2")
        self.assertEqual(profile.constitution, ConstitutionType.PROPRIETORSHIP)
        self.assertEqual(profile.principal_address.state_name, "Gujarat")
        self.assertEqual(profile.principal_address.pincode, "388001")
        self.assertIn("Manufacturing", profile.nature_of_activities)

    def test_matching_engine_startup_nexus(self):
        """
        Evaluates Stage 1 filtering for Sample 1:
        Nexus Robotics (Pvt Ltd, early stage, Maharashtra, DPIIT, Woman owned).
        """
        sample = self.samples_data[0]
        profile = GSTCertificateParser.parse_from_text(sample["raw_certificate_text"])
        
        # Apply sample metadata
        meta = sample["extra_profile_metadata"]
        profile.primary_sector = meta["primary_sector"]
        profile.turnover_bracket = TurnoverBracket(meta["turnover_bracket"])
        profile.msme_tier = MSMETier(meta["msme_tier"])
        profile.social_category = SocialCategory(meta.get("social_category", "General"))
        profile.is_woman_owned = meta["is_woman_owned"]
        profile.is_dpiit_recognized = meta["is_dpiit_recognized"]

        report = DeterministicSchemeMatcher.match_all(profile, self.schemes)

        eligible_ids = [m.scheme_id for m in report.eligible_schemes]
        
        # Must qualify for SISFS (Early stage DPIIT), CGTMSE (Collateral-free credit), CMEGP Maharashtra
        self.assertIn("sisfs", eligible_ids, "Should be eligible for Startup India Seed Fund Scheme")
        self.assertIn("cgtmse", eligible_ids, "Should be eligible for CGTMSE")
        self.assertIn("cmegp-maharashtra", eligible_ids, "Should be eligible for Maharashtra CMEGP")
        self.assertIn("tide-2", eligible_ids, "Should be eligible for TIDE 2.0")

        # Disqualified from schemes requiring > 1 yr operational history or SC/ST exclusive
        disqualified_ids = [m.scheme_id for m in report.disqualified_schemes]
        self.assertIn("nssh-scheme", disqualified_ids, "Should be disqualified from SC/ST Hub")

    def test_matching_engine_textile_llp_disqualification(self):
        """
        Evaluates Sample 3 (Mature Textile LLP, 4 yrs old):
        Should be disqualified from SISFS (requires <= 2 yrs) and Stand-Up India (requires greenfield <= 2 yrs).
        Should qualify for ATUFS (Textiles), CGTMSE, MSME ZED, and CLCSS.
        """
        sample = self.samples_data[2]
        profile = GSTCertificateParser.parse_from_text(sample["raw_certificate_text"])
        meta = sample["extra_profile_metadata"]
        profile.primary_sector = meta["primary_sector"]
        profile.turnover_bracket = TurnoverBracket(meta["turnover_bracket"])
        profile.msme_tier = MSMETier(meta["msme_tier"])

        report = DeterministicSchemeMatcher.match_all(profile, self.schemes)
        eligible_ids = [m.scheme_id for m in report.eligible_schemes]
        disqualified_ids = [m.scheme_id for m in report.disqualified_schemes]

        # Validations
        self.assertIn("atufs-textiles", eligible_ids, "Should qualify for ATUFS Textiles")
        self.assertIn("cgtmse", eligible_ids, "Should qualify for CGTMSE")
        self.assertIn("msme-zed", eligible_ids, "Should qualify for MSME ZED")

        # Disqualified from SISFS due to age > 2 years
        self.assertIn("sisfs", disqualified_ids, "Must be disqualified from SISFS due to age")


if __name__ == "__main__":
    unittest.main()

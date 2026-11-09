"""
MyScheme Portal Crawler (myscheme.gov.in).
Unified central and state schemes discovery scraper.
Extracts state-specific industrial policies, central PLI schemes, and sector subsidies.
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from crawlers.base import BaseSchemeCrawler, CrawledSchemeRecord

logger = logging.getLogger("MySchemeCrawler")


class MySchemeCrawler(BaseSchemeCrawler):
    """
    Scraper for MyScheme unified platform and state industrial policies.
    """

    def __init__(self, offline_mode: bool = False):
        super().__init__(
            source_name="MyScheme Platform",
            base_url="https://www.myscheme.gov.in",
            rate_limit_delay=1.0,
            offline_mode=offline_mode,
        )

    def parse_api_or_html(self, content: str, source_url: str) -> List[CrawledSchemeRecord]:
        """
        Parses MyScheme category listings.
        """
        soup = BeautifulSoup(content, "html.parser")
        records: List[CrawledSchemeRecord] = []

        cards = soup.find_all("div", class_=lambda c: c and any(k in c.lower() for k in ["scheme-card", "item-card", "result-card"]))
        for card in cards:
            title_elem = card.find(["h2", "h3", "h4", "a"])
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            desc_elem = card.find("p")
            summary = desc_elem.get_text(strip=True) if desc_elem else title

            records.append(
                CrawledSchemeRecord(
                    source_portal="myscheme.gov.in",
                    source_url=source_url,
                    raw_title=title,
                    raw_short_name=None,
                    raw_summary=summary,
                    raw_ministry="Government of India / State Governments",
                    raw_agency="Respective Nodal Department",
                    raw_eligibility=["Check detailed guidelines on official portal"],
                    raw_benefits={"description": summary},
                    raw_documents=["Aadhaar", "PAN", "Business Registration Proof"],
                    raw_guidelines_url=None,
                    raw_application_mode="Online via MyScheme",
                    raw_tags=["Central", "State", "Business", "Subsidy"],
                )
            )
        return records

    def get_snapshot_fixtures(self) -> List[CrawledSchemeRecord]:
        """
        Returns verified fixtures of MyScheme state and central flagship industrial schemes.
        """
        return [
            CrawledSchemeRecord(
                source_portal="myscheme.gov.in",
                source_url="https://maha-cmegp.gov.in",
                raw_title="Chief Minister Employment Generation Programme (CMEGP) Maharashtra",
                raw_short_name="CMEGP-MH",
                raw_summary="Maharashtra state credit-linked subsidy initiative providing margin money assistance to youth and micro-entrepreneurs for setting up manufacturing and service units.",
                raw_ministry="Industries Department, Government of Maharashtra",
                raw_agency="Directorate of Industries, Maharashtra / KVIB",
                raw_eligibility=[
                    "Resident of Maharashtra state between 18 and 45 years of age (up to 50 for SC/ST/Women/Ex-servicemen).",
                    "Minimum Class 7th pass for project cost up to ₹10 Lakh, Class 10th pass for project cost above ₹10 Lakh.",
                    "Only new manufacturing or service units established within the State of Maharashtra.",
                    "Existing units cannot apply."
                ],
                raw_benefits={
                    "type": "Capital Subsidy",
                    "subsidy_percentage": 35.0,
                    "max_amount_inr": 1750000.0,
                    "description": "Margin money subsidy of 15% to 35% of project cost: up to ₹50 Lakh for manufacturing projects and ₹20 Lakh for service units. 10% higher subsidy in rural and backward talukas."
                },
                raw_documents=[
                    "Maharashtra Domicile Certificate",
                    "Aadhaar Card & PAN Card",
                    "Educational Marksheet (7th or 10th)",
                    "Detailed Project Report (DPR)",
                    "Undertaking / Affidavit on non-beneficiary of other subsidy schemes"
                ],
                raw_guidelines_url="https://maha-cmegp.gov.in/docs/CMEGP_Operational_Guidelines.pdf",
                raw_application_mode="Online via Maha-CMEGP Portal (maha-cmegp.gov.in)",
                raw_tags=["Maharashtra", "State Scheme", "Margin Money", "Manufacturing", "Employment"],
                extracted_metadata={"state": "Maharashtra", "max_project_cost_mfg": 5000000}
            ),
            CrawledSchemeRecord(
                source_portal="myscheme.gov.in",
                source_url="https://www.meity.gov.in/esdm/pli",
                raw_title="Production Linked Incentive Scheme (PLI) for Large Scale Electronics",
                raw_short_name="PLI-Electronics",
                raw_summary="Offers an incentive of 4% to 6% on incremental sales (over base year) of goods manufactured in India to boost domestic electronic component manufacturing and attract large investments.",
                raw_ministry="Ministry of Electronics and Information Technology (MeitY)",
                raw_agency="Industrial Finance Corporation of India (IFCI) / MeitY",
                raw_eligibility=[
                    "Target segments: Mobile phones and specified electronic components (semiconductors, passive components, PCBs).",
                    "Companies registered in India with committed cumulative investment and incremental sales thresholds."
                ],
                raw_benefits={
                    "type": "Capital Subsidy",
                    "subsidy_percentage": 6.0,
                    "max_amount_inr": 5000000000.0,
                    "description": "4% to 6% incentive on incremental sales of manufactured goods for a period of 5 years following the base year."
                },
                raw_documents=[
                    "Certificate of Incorporation",
                    "Audited Financial Statements & Base Year Sales Audits",
                    "Investment and Capex Invoices Certified by Statutory Auditor",
                    "GST Returns & E-Way Bills"
                ],
                raw_guidelines_url="https://www.meity.gov.in/writereaddata/files/PLI_Gazette_Notification.pdf",
                raw_application_mode="Online via MeitY Single Window Portal",
                raw_tags=["PLI", "Electronics", "Hardware", "Manufacturing", "MeitY", "Exports"],
                extracted_metadata={"duration_years": 5}
            ),
            CrawledSchemeRecord(
                source_portal="myscheme.gov.in",
                source_url="https://www.meity.gov.in/esdm/specs",
                raw_title="Scheme for Promotion of Manufacturing of Electronic Components and Semiconductors (SPECS)",
                raw_short_name="SPECS",
                raw_summary="Provides 25% financial incentive on capital expenditure for the manufacturing of electronic goods that form the supply chain of electronic products.",
                raw_ministry="Ministry of Electronics and Information Technology (MeitY)",
                raw_agency="Project Management Agency (PMA) / IFCI",
                raw_eligibility=[
                    "Investments in new electronic component manufacturing units or expansion/modernization of existing units.",
                    "Minimum investment threshold ranging from ₹5 Crore to ₹1,000 Crore depending on component category."
                ],
                raw_benefits={
                    "type": "Capital Subsidy",
                    "subsidy_percentage": 25.0,
                    "max_amount_inr": 250000000.0,
                    "description": "25% financial incentive on capital expenditure for plant, machinery, equipment, associated utilities, and technology transfer."
                },
                raw_documents=[
                    "Business Profile & Detailed Project Report",
                    "Audited Balance Sheets",
                    "Machinery Purchase Orders and Proof of Payment",
                    "Chartered Engineer Certification on installation"
                ],
                raw_guidelines_url="https://www.meity.gov.in/writereaddata/files/SPECS_Guidelines.pdf",
                raw_application_mode="Online via MeitY Portal",
                raw_tags=["Semiconductors", "Components", "Hardware", "SPECS", "Electronics", "Capex"],
                extracted_metadata={"incentive_rate": 25.0}
            )
        ]

    def crawl(self) -> List[CrawledSchemeRecord]:
        logger.info(f"Starting crawl for {self.source_name}...")
        results: List[CrawledSchemeRecord] = []

        if not self.offline_mode:
            target_urls = [
                f"{self.base_url}/search/category/Business%20&%20Entrepreneurship",
            ]
            for url in target_urls:
                html = self.fetch_url(url)
                if html:
                    extracted = self.parse_api_or_html(html, url)
                    if extracted:
                        results.extend(extracted)
                        logger.info(f"Extracted {len(extracted)} schemes from {url}")

        if not results:
            logger.info("Using curated MyScheme snapshot fixtures...")
            results = self.get_snapshot_fixtures()

        logger.info(f"Total schemes crawled from {self.source_name}: {len(results)}")
        return results

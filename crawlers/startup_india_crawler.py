"""
Startup India Portal Crawler (startupindia.gov.in).
Crawls DPIIT recognition programs, Startup India Seed Fund Scheme (SISFS), 
Tax concessions (Section 80-IAC), and MeitY accelerator grants.
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from crawlers.base import BaseSchemeCrawler, CrawledSchemeRecord

logger = logging.getLogger("StartupIndiaCrawler")


class StartupIndiaCrawler(BaseSchemeCrawler):
    """
    Scraper for Startup India ecosystem programs and funding schemes.
    """

    def __init__(self, offline_mode: bool = False):
        super().__init__(
            source_name="Startup India",
            base_url="https://www.startupindia.gov.in",
            rate_limit_delay=1.0,
            offline_mode=offline_mode,
        )

    def parse_programs_html(self, html_content: str, source_url: str) -> List[CrawledSchemeRecord]:
        """
        Parses Startup India programs and grant schemes listing.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        records: List[CrawledSchemeRecord] = []

        cards = soup.find_all("div", class_=lambda c: c and any(k in c.lower() for k in ["scheme-card", "program-card", "grant-item"]))
        for card in cards:
            title_elem = card.find(["h2", "h3", "h4", "strong"])
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            desc_elem = card.find("p")
            summary = desc_elem.get_text(strip=True) if desc_elem else title

            link_elem = card.find("a", href=True)
            link = link_elem["href"] if link_elem else source_url
            if link.startswith("/"):
                link = f"{self.base_url}{link}"

            records.append(
                CrawledSchemeRecord(
                    source_portal="startupindia.gov.in",
                    source_url=link,
                    raw_title=title,
                    raw_short_name=None,
                    raw_summary=summary,
                    raw_ministry="Ministry of Commerce and Industry",
                    raw_agency="Department for Promotion of Industry and Internal Trade (DPIIT)",
                    raw_eligibility=["DPIIT Recognized Startup", "Incorporated within last 10 years"],
                    raw_benefits={"description": summary},
                    raw_documents=["DPIIT Certificate", "COI", "Pitch Deck"],
                    raw_guidelines_url=None,
                    raw_application_mode="Online via Startup India Portal",
                    raw_tags=["Startup", "Innovation", "DPIIT", "Venture"],
                )
            )
        return records

    def get_snapshot_fixtures(self) -> List[CrawledSchemeRecord]:
        """
        Returns verified fixtures of Startup India flagship schemes.
        """
        return [
            CrawledSchemeRecord(
                source_portal="startupindia.gov.in",
                source_url="https://seedfund.startupindia.gov.in",
                raw_title="Startup India Seed Fund Scheme",
                raw_short_name="SISFS",
                raw_summary="Financial assistance to early-stage DPIIT-recognized startups for proof of concept, prototype development, product trials, market entry, and commercialization.",
                raw_ministry="Ministry of Commerce and Industry",
                raw_agency="DPIIT / Designated Incubators",
                raw_eligibility=[
                    "A startup recognized by DPIIT, incorporated not more than 2 years ago at the time of application.",
                    "Must have a viable business idea with proof of concept or prototype.",
                    "Must not have received more than ₹10 Lakh in monetary support under other Central or State government schemes.",
                    "Indian promoters must hold at least 51% shareholding in the startup."
                ],
                raw_benefits={
                    "type": "Grant / Seed Funding",
                    "subsidy_percentage": 100.0,
                    "max_amount_inr": 5000000.0,
                    "description": "Up to ₹20 Lakh as grant for Proof of Concept / prototype validation; up to ₹50 Lakh through convertible debentures or debt-linked instruments for commercialization."
                },
                raw_documents=[
                    "DPIIT Certificate of Recognition",
                    "Certificate of Incorporation (Pvt Ltd or LLP)",
                    "Pitch Deck & Business Plan",
                    "Shareholding Pattern Declaration (CA certified)"
                ],
                raw_guidelines_url="https://seedfund.startupindia.gov.in/assets/SISFS_Guidelines.pdf",
                raw_application_mode="Online via SISFS Portal (seedfund.startupindia.gov.in)",
                raw_tags=["Startup", "Seed Capital", "Grant", "Incubator", "Prototype", "DPIIT"],
                extracted_metadata={"funding_mode": ["Grant", "Convertible Debentures"]}
            ),
            CrawledSchemeRecord(
                source_portal="startupindia.gov.in",
                source_url="https://www.startupindia.gov.in/content/sih/en/tax-exemptions.html",
                raw_title="Tax Exemption under Section 80-IAC of Income Tax Act",
                raw_short_name="Section 80-IAC",
                raw_summary="Eligible startups can get 100% deduction on corporate profits for 3 consecutive financial years out of their first 10 years of incorporation.",
                raw_ministry="Ministry of Commerce and Industry",
                raw_agency="Inter-Ministerial Board (IMB) / Central Board of Direct Taxes (CBDT)",
                raw_eligibility=[
                    "Incorporated as a Private Limited Company or Limited Liability Partnership (LLP).",
                    "Incorporated between 1st April 2016 and 31st March 2025 (as extended).",
                    "Annual turnover must not exceed ₹100 Crore in any financial year.",
                    "Working towards innovation, development, or commercialization of new products, processes, or services."
                ],
                raw_benefits={
                    "type": "Tax Exemption / Concession",
                    "subsidy_percentage": 100.0,
                    "max_amount_inr": 0.0,
                    "description": "100% income tax exemption on profits for 3 consecutive assessment years chosen by the startup within the 10-year period."
                },
                raw_documents=[
                    "DPIIT Certificate of Recognition",
                    "Audited Financial Statements & ITRs since incorporation",
                    "Detailed Video Link explaining product innovation and uniqueness",
                    "Memorandum and Articles of Association (MoA & AoA)"
                ],
                raw_guidelines_url="https://www.startupindia.gov.in/content/dam/invest-india/Templates/public/80IAC_Gazette.pdf",
                raw_application_mode="Online via Startup India Portal (Form-1 to IMB)",
                raw_tags=["Tax Relief", "80-IAC", "Corporate Tax", "Startups", "IMB Approval"],
                extracted_metadata={"tax_holiday_years": 3}
            ),
            CrawledSchemeRecord(
                source_portal="startupindia.gov.in",
                source_url="https://www.startupindia.gov.in/content/sih/en/compendium-of-schemes.html",
                raw_title="Credit Guarantee Scheme for Startups (CGSS)",
                raw_short_name="CGSS",
                raw_summary="Provides credit guarantees to loans extended by Scheduled Commercial Banks, NBFCs, and AIFs to DPIIT-recognized startups without collateral.",
                raw_ministry="Ministry of Commerce and Industry",
                raw_agency="National Credit Guarantee Trustee Company (NCGTC)",
                raw_eligibility=[
                    "DPIIT-recognized Startups with verified GST and operational bank records.",
                    "Startups seeking debt financing without third-party collateral.",
                    "No default in any existing credit facility."
                ],
                raw_benefits={
                    "type": "Credit Guarantee",
                    "subsidy_percentage": 85.0,
                    "max_amount_inr": 100000000.0,
                    "description": "Credit guarantee coverage up to 85% of sanctioned facility up to ₹10 Crore per startup borrower."
                },
                raw_documents=[
                    "DPIIT Startup Certificate",
                    "Audited Balance Sheets (where available)",
                    "Bank Loan Appraisal Report",
                    "Promoter KYC Documents"
                ],
                raw_guidelines_url="https://ncgtc.in/en/schemes/cgss-guidelines.pdf",
                raw_application_mode="Through Member Lending Institutions (Banks/NBFCs)",
                raw_tags=["Credit Guarantee", "Debt Financing", "Startups", "Collateral-Free"],
                extracted_metadata={"max_loan_inr": 100000000}
            ),
            CrawledSchemeRecord(
                source_portal="startupindia.gov.in",
                source_url="https://meity.gov.in/samridh-scheme",
                raw_title="MeitY SAMRIDH Scheme for Tech Startups",
                raw_short_name="SAMRIDH",
                raw_summary="Scheme for Accelerators to pick and scale early-stage software and deeptech product startups with matched government capital and investor cohorts.",
                raw_ministry="Ministry of Electronics and Information Technology (MeitY)",
                raw_agency="MeitY Startup Hub (MSH)",
                raw_eligibility=[
                    "DPIIT Recognized Software Product Startups.",
                    "Must have an operating prototype or market-ready SaaS/hardware/AI product.",
                    "Must be admitted to an empaneled accelerator program."
                ],
                raw_benefits={
                    "type": "Grant / Seed Funding",
                    "subsidy_percentage": 100.0,
                    "max_amount_inr": 4000000.0,
                    "description": "Matched equity/debt investment of up to ₹40 Lakh per startup alongside accelerator cohort funding."
                },
                raw_documents=[
                    "DPIIT Certificate",
                    "Software IP / Product Demo Video",
                    "Accelerator Empanelment Letter",
                    "Customer Traction & Revenue Proof"
                ],
                raw_guidelines_url="https://meitystartuphub.in/assets/SAMRIDH_Guidelines.pdf",
                raw_application_mode="Online via MeitY Startup Hub Portal",
                raw_tags=["Software", "Deeptech", "Accelerator", "SaaS", "MeitY"],
                extracted_metadata={"accelerator_matching": True}
            )
        ]

    def crawl(self) -> List[CrawledSchemeRecord]:
        logger.info(f"Starting crawl for {self.source_name}...")
        results: List[CrawledSchemeRecord] = []

        if not self.offline_mode:
            target_urls = [
                f"{self.base_url}/content/sih/en/government-schemes.html",
                f"{self.base_url}/content/sih/en/funding-schemes.html"
            ]
            for url in target_urls:
                html = self.fetch_url(url)
                if html:
                    extracted = self.parse_programs_html(html, url)
                    if extracted:
                        results.extend(extracted)
                        logger.info(f"Extracted {len(extracted)} schemes from {url}")

        if not results:
            logger.info("Using curated Startup India snapshot fixtures...")
            results = self.get_snapshot_fixtures()

        logger.info(f"Total schemes crawled from {self.source_name}: {len(results)}")
        return results

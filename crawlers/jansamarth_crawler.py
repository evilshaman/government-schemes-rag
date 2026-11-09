"""
Jan Samarth Portal Crawler (jansamarth.in).
Crawls National Portal for Credit-Linked Subsidies: PMEGP, Mudra, Stand-Up India, CGTMSE, and AIF.
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from crawlers.base import BaseSchemeCrawler, CrawledSchemeRecord

logger = logging.getLogger("JanSamarthCrawler")


class JanSamarthCrawler(BaseSchemeCrawler):
    """
    Scraper for Jan Samarth credit-linked government schemes.
    """

    def __init__(self, offline_mode: bool = False):
        super().__init__(
            source_name="Jan Samarth Portal",
            base_url="https://www.jansamarth.in",
            rate_limit_delay=1.0,
            offline_mode=offline_mode,
        )

    def parse_schemes_html(self, html_content: str, source_url: str) -> List[CrawledSchemeRecord]:
        """
        Parses Jan Samarth scheme cards and credit facility listings.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        records: List[CrawledSchemeRecord] = []

        cards = soup.find_all("div", class_=lambda c: c and any(k in c.lower() for k in ["scheme-box", "loan-card", "category-card"]))
        for card in cards:
            title_elem = card.find(["h3", "h4", "h5", "a"])
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
                    source_portal="jansamarth.in",
                    source_url=link,
                    raw_title=title,
                    raw_short_name=None,
                    raw_summary=summary,
                    raw_ministry="Ministry of Finance / MSME",
                    raw_agency="Member Lending Institutions (Banks)",
                    raw_eligibility=["Individual / Sole Proprietor / MSME", "Satisfactory CIBIL score"],
                    raw_benefits={"description": summary},
                    raw_documents=["Aadhaar", "PAN", "Bank Statement"],
                    raw_guidelines_url=None,
                    raw_application_mode="Online via Jan Samarth Portal",
                    raw_tags=["Credit", "Subsidy", "Bank Loan", "MSME"],
                )
            )
        return records

    def get_snapshot_fixtures(self) -> List[CrawledSchemeRecord]:
        """
        Returns verified fixtures of Jan Samarth credit schemes.
        """
        return [
            CrawledSchemeRecord(
                source_portal="jansamarth.in",
                source_url="https://www.jansamarth.in/business-activity-loan-schemes",
                raw_title="Credit Guarantee Fund Trust for Micro and Small Enterprises",
                raw_short_name="CGTMSE",
                raw_summary="Collateral-free credit facility for micro and small enterprises with guarantee coverage up to ₹5 Crore backed by SIDBI and Ministry of MSME.",
                raw_ministry="Ministry of Micro, Small and Medium Enterprises",
                raw_agency="SIDBI / CGTMSE Trust / MLIs",
                raw_eligibility=[
                    "New and existing Micro and Small Enterprises (Manufacturing and Services).",
                    "Retail trade enterprises up to ₹2 Crore exposure.",
                    "Educational institutions and training centers.",
                    "No third-party guarantee or collateral required."
                ],
                raw_benefits={
                    "type": "Credit Guarantee",
                    "subsidy_percentage": 85.0,
                    "max_amount_inr": 50000000.0,
                    "description": "Guarantee coverage up to 85% for loans up to ₹5 Lakh (Micro), 75% to 85% for loans up to ₹500 Lakh. Up to 85% coverage for women-owned enterprises and units in NER."
                },
                raw_documents=[
                    "Udyam Registration Certificate",
                    "GST Registration Certificate",
                    "PAN Card and KYC of Promoters",
                    "Projected Balance Sheets & Cash Flow Statement",
                    "Bank Account Statement for 12 months"
                ],
                raw_guidelines_url="https://www.cgtmse.in/files/CGTMSE_Circulars_2024.pdf",
                raw_application_mode="Apply via Member Lending Banks or Jan Samarth Portal",
                raw_tags=["Collateral Free", "Credit Guarantee", "Working Capital", "Term Loan", "SIDBI", "MSME"],
                extracted_metadata={"max_loan_cap_inr": 50000000}
            ),
            CrawledSchemeRecord(
                source_portal="jansamarth.in",
                source_url="https://www.jansamarth.in/pmegp-scheme",
                raw_title="Prime Minister's Employment Generation Programme",
                raw_short_name="PMEGP",
                raw_summary="Credit-linked margin money subsidy scheme to generate self-employment by establishing micro-enterprises in manufacturing and services.",
                raw_ministry="Ministry of Micro, Small and Medium Enterprises",
                raw_agency="KVIC / State KVI Boards / District Industries Centres (DIC)",
                raw_eligibility=[
                    "Any individual above 18 years of age.",
                    "Minimum Class 8th pass for manufacturing above ₹10 Lakh and services above ₹5 Lakh.",
                    "New greenfield projects only; existing units are not eligible for first loan.",
                    "Self Help Groups and Charitable Trusts are also eligible."
                ],
                raw_benefits={
                    "type": "Capital Subsidy",
                    "subsidy_percentage": 35.0,
                    "max_amount_inr": 1750000.0,
                    "description": "Margin money subsidy of 25% (Urban) to 35% (Rural) for Special Categories (Women, SC, ST, OBC, Ex-servicemen); 15% to 25% for General. Max manufacturing cost ₹50 Lakh, service ₹20 Lakh."
                },
                raw_documents=[
                    "Aadhaar & PAN Card",
                    "Detailed Project Report (DPR)",
                    "Class 8th / Educational Certificate",
                    "Caste / Category Certificate (if claiming special subsidy)",
                    "Gram Panchayat Rural Area Certificate"
                ],
                raw_guidelines_url="https://www.kviconline.gov.in/pmegpep/pmegpweb/docs/pmegpguidelines.pdf",
                raw_application_mode="Online via Jan Samarth or KVIC Portal",
                raw_tags=["PMEGP", "Margin Money", "Subsidy", "Self Employment", "Rural", "Manufacturing"],
                extracted_metadata={"first_loan_cap_mfg": 5000000, "first_loan_cap_svc": 2000000}
            ),
            CrawledSchemeRecord(
                source_portal="jansamarth.in",
                source_url="https://www.jansamarth.in/stand-up-india-scheme",
                raw_title="Stand-Up India Scheme for Women and SC/ST Entrepreneurs",
                raw_short_name="Stand-Up India",
                raw_summary="Facilitates bank loans between ₹10 Lakh and ₹1 Crore to at least one Scheduled Caste (SC) or Scheduled Tribe (ST) borrower and at least one woman borrower per bank branch for setting up a greenfield enterprise.",
                raw_ministry="Ministry of Finance",
                raw_agency="Department of Financial Services (DFS) / SIDBI / NABARD",
                raw_eligibility=[
                    "SC/ST and/or Woman entrepreneurs above 18 years of age.",
                    "Loans under the scheme are available for only greenfield (first-time) projects.",
                    "In case of non-individual enterprises, 51% shareholding must be held by SC/ST and/or women.",
                    "Borrower must not be in default to any bank or financial institution."
                ],
                raw_benefits={
                    "type": "Term Loan / Working Capital",
                    "subsidy_percentage": 0.0,
                    "max_amount_inr": 10000000.0,
                    "description": "Composite loan (term loan and working capital) between ₹10 Lakh and ₹100 Lakh covering up to 85% of project cost at lowest applicable bank interest rate."
                },
                raw_documents=[
                    "Identity and Address Proof (Aadhaar/PAN)",
                    "Caste Certificate (for SC/ST entrepreneurs)",
                    "Certificate of Incorporation / Partnership Deed showing 51% female/SC/ST ownership",
                    "Project Report detailing machinery and capital expenditure",
                    "Pollution clearance / licenses if applicable"
                ],
                raw_guidelines_url="https://www.standupmitra.in/Home/StandUpIndiaGuidelines.pdf",
                raw_application_mode="Online via Stand-Up Mitra / Jan Samarth",
                raw_tags=["Women Entrepreneurship", "SC/ST", "Greenfield", "Bank Loan", "Finance"],
                extracted_metadata={"min_loan_inr": 1000000, "max_loan_inr": 10000000}
            ),
            CrawledSchemeRecord(
                source_portal="jansamarth.in",
                source_url="https://www.jansamarth.in/mudra-loan-scheme",
                raw_title="Pradhan Mantri Mudra Yojana (PMMY)",
                raw_short_name="PMMY",
                raw_summary="Refinance agency scheme funding non-corporate, non-farm small/micro enterprises with collateral-free loans across Shishu, Kishore, and Tarun categories.",
                raw_ministry="Ministry of Finance",
                raw_agency="MUDRA / Commercial Banks / RRBs / Small Finance Banks / MFIs",
                raw_eligibility=[
                    "Any Indian citizen with a viable business plan for income-generating non-farm activities.",
                    "Sectors include manufacturing, processing, trading, retail, services, and allied agricultural activities."
                ],
                raw_benefits={
                    "type": "Term Loan / Working Capital",
                    "subsidy_percentage": 0.0,
                    "max_amount_inr": 2000000.0,
                    "description": "Loans in four tiers: Shishu (up to ₹50,000), Kishore (₹50,000 to ₹5 Lakh), Tarun (₹5 Lakh to ₹10 Lakh), and Tarun Plus (up to ₹20 Lakh). Zero collateral requirement."
                },
                raw_documents=[
                    "Aadhaar and PAN Card",
                    "Business Address Proof / Shop Establishment License",
                    "Last 6 months Bank Statement",
                    "Quotation of machinery / raw materials to be purchased"
                ],
                raw_guidelines_url="https://www.mudra.org.in/Docs/PMMY_Guidelines.pdf",
                raw_application_mode="Online via Jan Samarth / Udyamimitra or branch visit",
                raw_tags=["Mudra", "Microfinance", "Working Capital", "Collateral Free", "PMMY"],
                extracted_metadata={"tiers": ["Shishu", "Kishore", "Tarun", "Tarun Plus"]}
            )
        ]

    def crawl(self) -> List[CrawledSchemeRecord]:
        logger.info(f"Starting crawl for {self.source_name}...")
        results: List[CrawledSchemeRecord] = []

        if not self.offline_mode:
            target_urls = [
                f"{self.base_url}/all-schemes",
                f"{self.base_url}/business-activity-loan-schemes"
            ]
            for url in target_urls:
                html = self.fetch_url(url)
                if html:
                    extracted = self.parse_schemes_html(html, url)
                    if extracted:
                        results.extend(extracted)
                        logger.info(f"Extracted {len(extracted)} schemes from {url}")

        if not results:
            logger.info("Using curated Jan Samarth snapshot fixtures...")
            results = self.get_snapshot_fixtures()

        logger.info(f"Total schemes crawled from {self.source_name}: {len(results)}")
        return results

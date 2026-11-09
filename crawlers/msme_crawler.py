"""
MSME Portal Crawler (msme.gov.in / dcmsme.gov.in).
Crawls flagship Ministry of MSME schemes, guidelines, and benefits.
Supports live web scraping with BeautifulSoup and resilient fallback fixtures.
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from crawlers.base import BaseSchemeCrawler, CrawledSchemeRecord

logger = logging.getLogger("MSMECrawler")


class MSMECrawler(BaseSchemeCrawler):
    """
    Scraper for Ministry of Micro, Small & Medium Enterprises portal.
    """

    def __init__(self, offline_mode: bool = False):
        super().__init__(
            source_name="MSME Portal",
            base_url="https://msme.gov.in",
            rate_limit_delay=1.0,
            offline_mode=offline_mode,
        )

    def parse_scheme_html(self, html_content: str, source_url: str) -> List[CrawledSchemeRecord]:
        """
        Parses MSME scheme listing HTML into CrawledSchemeRecord instances.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        records: List[CrawledSchemeRecord] = []

        # Find scheme cards or table rows
        scheme_containers = soup.find_all(["div", "article"], class_=lambda c: c and "scheme" in c.lower())
        if not scheme_containers:
            scheme_containers = soup.find_all("table")

        for container in scheme_containers:
            title_tag = container.find(["h2", "h3", "h4", "a"])
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            desc_tag = container.find(["p", "div", "td"])
            summary = desc_tag.get_text(strip=True) if desc_tag else title

            # Extract links
            link_tag = container.find("a", href=True)
            scheme_url = link_tag["href"] if link_tag else source_url
            if scheme_url.startswith("/"):
                scheme_url = f"{self.base_url}{scheme_url}"

            # Extract list items for eligibility and documents
            eligibility_items = [li.get_text(strip=True) for li in container.find_all("li") if "eligible" in li.get_text().lower()]
            document_items = [li.get_text(strip=True) for li in container.find_all("li") if "document" in li.get_text().lower() or "proof" in li.get_text().lower()]

            records.append(
                CrawledSchemeRecord(
                    source_portal="msme.gov.in",
                    source_url=scheme_url,
                    raw_title=title,
                    raw_short_name=None,
                    raw_summary=summary,
                    raw_ministry="Ministry of Micro, Small and Medium Enterprises",
                    raw_agency="Office of Development Commissioner (DC-MSME)",
                    raw_eligibility=eligibility_items or ["Valid Udyam Registration Certificate required."],
                    raw_benefits={"description": summary},
                    raw_documents=document_items or ["Udyam Certificate", "GSTIN", "Bank Account Details"],
                    raw_guidelines_url=None,
                    raw_application_mode="Online via MSME Champions / Champions Portal",
                    raw_tags=["MSME", "Manufacturing", "Services", "Competitiveness"],
                )
            )

        return records

    def get_snapshot_fixtures(self) -> List[CrawledSchemeRecord]:
        """
        Returns verified fixtures of MSME schemes for offline reproducibility.
        """
        return [
            CrawledSchemeRecord(
                source_portal="msme.gov.in",
                source_url="https://zed.msme.gov.in",
                raw_title="MSME Sustainable (ZED) Certification Scheme",
                raw_short_name="ZED",
                raw_summary="Enables MSMEs to manufacture Zero Defect and Zero Effect goods through financial support on assessment and certification fees.",
                raw_ministry="Ministry of Micro, Small and Medium Enterprises",
                raw_agency="Quality Council of India (QCI) / MSME DFOs",
                raw_eligibility=[
                    "Any Micro, Small, or Medium Enterprise with valid Udyam Registration.",
                    "Must be an active manufacturing or production enterprise.",
                    "Special additional financial subsidy of 10% for Women and SC/ST owned MSMEs."
                ],
                raw_benefits={
                    "type": "Fee / Cost Reimbursement",
                    "subsidy_percentage": 80.0,
                    "max_amount_inr": 500000.0,
                    "description": "Financial assistance: 80% subsidy for Micro, 60% for Small, 50% for Medium on certification fees up to ₹5 Lakh."
                },
                raw_documents=[
                    "Udyam Registration Certificate",
                    "GST Registration Certificate",
                    "Factory License / Consent to Operate",
                    "Declaration on Zero Defect / Zero Effect parameters"
                ],
                raw_guidelines_url="https://zed.msme.gov.in/assets/guidelines/ZED_Guidelines.pdf",
                raw_application_mode="Online via ZED Portal (zed.msme.gov.in)",
                raw_tags=["Manufacturing", "Quality", "Clean Energy", "ZED", "Environment"],
                extracted_metadata={"certification_tiers": ["Bronze", "Silver", "Gold"]}
            ),
            CrawledSchemeRecord(
                source_portal="msme.gov.in",
                source_url="https://champions.gov.in/msme_champions/MSME_Innovative.htm",
                raw_title="MSME Innovative Scheme (Incubation, Design and IPR)",
                raw_short_name="MSME-Innovative",
                raw_summary="Fosters innovation, commercialization of ideas, design thinking, and intellectual property development among MSMEs and tech startups.",
                raw_ministry="Ministry of Micro, Small and Medium Enterprises",
                raw_agency="MSME Development and Facilitation Offices (MSME-DFO)",
                raw_eligibility=[
                    "Registered MSMEs with valid Udyam Registration.",
                    "Students, innovators, and start-ups associated with recognized Host Institutes (IITs, NITs, engineering colleges).",
                    "Focus on developing novel proof of concepts and patentable technologies."
                ],
                raw_benefits={
                    "type": "Grant / Seed Funding",
                    "subsidy_percentage": 100.0,
                    "max_amount_inr": 1500000.0,
                    "description": "Financial support up to ₹15 Lakh per approved idea for incubation; up to ₹40 Lakh for design projects; up to ₹5 Lakh for foreign patent registration."
                },
                raw_documents=[
                    "Udyam Certificate",
                    "Detailed Innovation Pitch & Concept Note",
                    "Host Institute Recommendation Letter",
                    "Patent / Trademark Search Report"
                ],
                raw_guidelines_url="https://innovative.msme.gov.in/guidelines.pdf",
                raw_application_mode="Online via MSME Innovative Portal",
                raw_tags=["Innovation", "IPR", "Patents", "Incubation", "Design", "R&D"],
                extracted_metadata={"components": ["Incubation", "Design", "IPR"]}
            ),
            CrawledSchemeRecord(
                source_portal="msme.gov.in",
                source_url="https://my.msme.gov.in/MyMsme/Reg/COM_SchemeDetails.aspx?s_id=05_01",
                raw_title="Procurement and Marketing Support (PMS) Scheme",
                raw_short_name="PMS",
                raw_summary="Promotes new market access initiatives, participation in national/international trade fairs, vendor development, and modern e-commerce onboarding.",
                raw_ministry="Ministry of Micro, Small and Medium Enterprises",
                raw_agency="Office of DC-MSME",
                raw_eligibility=[
                    "Micro and Small Enterprises with valid Udyam Registration.",
                    "Enterprises participating in state, national, or international trade exhibitions and expos."
                ],
                raw_benefits={
                    "type": "Fee / Cost Reimbursement",
                    "subsidy_percentage": 100.0,
                    "max_amount_inr": 150000.0,
                    "description": "100% stall charge reimbursement for SC/ST, Women, and NER entrepreneurs up to ₹1.5 Lakh for National Fairs; 80% for General MSEs."
                },
                raw_documents=[
                    "Udyam Registration",
                    "GST Certificate",
                    "Exhibition Stall Booking Receipt & Allotment Letter",
                    "Photographs of stall during expo",
                    "Cancelled Cheque"
                ],
                raw_guidelines_url="https://dcmsme.gov.in/schemes/PMS_Guidelines.pdf",
                raw_application_mode="Online via MyMSME Portal",
                raw_tags=["Marketing", "Trade Fairs", "Exhibitions", "MSEs", "Export"],
                extracted_metadata={"reimbursement_window_days": 45}
            ),
            CrawledSchemeRecord(
                source_portal="msme.gov.in",
                source_url="https://pmfme.mofpi.gov.in",
                raw_title="PM Formalisation of Micro food processing Enterprises Scheme",
                raw_short_name="PMFME",
                raw_summary="Centrally sponsored scheme providing financial, technical, and business support for the upgradation of micro food processing enterprises.",
                raw_ministry="Ministry of Food Processing Industries / MSME",
                raw_agency="State Nodal Agencies (SNA) / National Institute of Food Technology (NIFTEM)",
                raw_eligibility=[
                    "Existing or new micro food processing units (Individual proprietors, SHGs, FPOs, Cooperatives).",
                    "Enterprise must be involved in food processing and manufacturing.",
                    "Ownership status: Sole Proprietorship, Partnership, or LLP."
                ],
                raw_benefits={
                    "type": "Capital Subsidy",
                    "subsidy_percentage": 35.0,
                    "max_amount_inr": 1000000.0,
                    "description": "Credit-linked capital subsidy of 35% of eligible project cost with a maximum ceiling of ₹10 Lakh per unit."
                },
                raw_documents=[
                    "Udyam / FSSAI Registration",
                    "Bank Account Statement (6 months)",
                    "Detailed Project Report (DPR)",
                    "Quotations for food processing machinery"
                ],
                raw_guidelines_url="https://pmfme.mofpi.gov.in/docs/pmfme_guidelines.pdf",
                raw_application_mode="Online via PMFME National Portal",
                raw_tags=["Food Processing", "Agri-Business", "Micro Enterprises", "Manufacturing"],
                extracted_metadata={"one_district_one_product_focus": True}
            )
        ]

    def crawl(self) -> List[CrawledSchemeRecord]:
        """
        Executes MSME crawl. Attempts live fetch, falls back to fixtures.
        """
        logger.info(f"Starting crawl for {self.source_name}...")
        results: List[CrawledSchemeRecord] = []

        if not self.offline_mode:
            target_urls = [
                f"{self.base_url}/all-schemes",
                "https://dcmsme.gov.in/schemes.aspx",
            ]
            for url in target_urls:
                html = self.fetch_url(url)
                if html:
                    extracted = self.parse_scheme_html(html, url)
                    if extracted:
                        results.extend(extracted)
                        logger.info(f"Extracted {len(extracted)} schemes from {url}")

        if not results:
            logger.info("Using curated MSME snapshot fixtures...")
            results = self.get_snapshot_fixtures()

        logger.info(f"Total schemes crawled from {self.source_name}: {len(results)}")
        return results

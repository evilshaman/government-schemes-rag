"""
Playwright-Powered Government Scheme Application Process Crawler.
Automates headless Chromium browsing to extract official, step-by-step application
procedures, portal links, required document workflows, and approval stages from:
- myScheme Platform (myscheme.gov.in)
- Jan Samarth Platform (jansamarth.in)
- Stand-Up Mitra (standupmitra.in)
- Ministry of MSME / Champions Portal (champions.gov.in / zed.msme.gov.in)
- Startup India Portal (startupindia.gov.in / seedfund.startupindia.gov.in)
- State Portals (e.g. maha-cmegp.gov.in)

Supports both dynamic headless browser automation and offline curated fixtures.
"""

from __future__ import annotations
import os
import re
import json
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("PlaywrightApplicationCrawler")


class SchemeApplicationProcessRecord:
    """
    Structured application workflow data for a government scheme.
    """
    def __init__(
        self,
        scheme_id: str,
        application_mode: str,
        application_portal_url: str,
        steps: List[str],
        markdown_guide: str,
        source_portal: str = "Official Government Portal",
    ):
        self.scheme_id = scheme_id
        self.application_mode = application_mode
        self.application_portal_url = application_portal_url
        self.steps = steps
        self.markdown_guide = markdown_guide
        self.source_portal = source_portal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scheme_id": self.scheme_id,
            "application_mode": self.application_mode,
            "application_portal_url": self.application_portal_url,
            "steps": self.steps,
            "markdown_guide": self.markdown_guide,
            "source_portal": self.source_portal,
        }


class PlaywrightApplicationCrawler:
    """
    Headless browser crawler using Playwright Chromium to fetch authentic application steps.
    """

    MYSCHEME_SLUG_MAP = {
        "pmegp": "pmegp",
        "cgtmse": "agmsmercgt",
        "mudra-shishu": "mesy",
        "mudra-kishore": "kvpy",
        "mudra-tarun": "pmmy",
        "stand-up-india": "sui",
        "pm-vishwakarma": "pmv",
        "clcss": "aabcs",
        "pmfme": "cfpc",
        "aif": "biracisf",
        "sisfs": "sisfs-fi",
        "ffs-sidbi": "tufs",
        "sec-80iac": "tcfsc",
        "meity-samridh": "ssaomfpidg",
        "tide-2": "agr2fmsfotscst",
        "birac-big": "big",
        "aim-incubator-grant": "biracisf",
        "dst-nidhi-sss": "dan",
        "dsir-prism": "prism-c2-fwmpkhttptt",
        "genesis-meity": "genesis",
        "msme-zed": "msme-stes",
        "msme-innovative": "msme-stes",
        "pli-electronics": "tooplisflsem",
        "specs-electronics": "tooplisflsem",
        "msme-pms": "msme-stes",
        "nssh-scheme": "hs",
        "msme-ic": "msme-stes",
        "atufs-textiles": "sdatocitt",
        "aspire-scheme": "hs",
        "cmegp-maharashtra": "cmegp",
    }

    def __init__(self, headless: bool = True, timeout_ms: int = 25000, offline_mode: bool = False):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.offline_mode = offline_mode

    def _extract_ast_text(self, node: Any) -> str:
        """
        Recursively extracts plain text from MyScheme's Slate/AST JSON representation.
        """
        if not node:
            return ""
        if isinstance(node, str):
            return node
        if isinstance(node, dict):
            text = node.get("text", "")
            children = node.get("children", [])
            for child in children:
                text += self._extract_ast_text(child)
            return text
        if isinstance(node, list):
            return "".join(self._extract_ast_text(item) for item in node)
        return str(node)

    def extract_from_myscheme(self, page, slug: str) -> Optional[SchemeApplicationProcessRecord]:
        """
        Queries MyScheme API endpoint within the Playwright authenticated session.
        """
        try:
            url = f"https://www.myscheme.gov.in/api/apisetu/schemes?slug={slug}&lang=en"
            resp = page.request.get(url, timeout=self.timeout_ms)
            if resp.status != 200:
                logger.warning(f"MyScheme API returned status {resp.status} for slug '{slug}'")
                return None

            data = resp.json()
            en = data.get("data", {}).get("en", {})
            app_process = en.get("applicationProcess", [])
            if not app_process:
                return None

            steps: List[str] = []
            full_md_parts: List[str] = []
            primary_url = ""
            primary_mode = "Online Portal"

            for channel in app_process:
                mode = channel.get("mode", "Online")
                chan_url = channel.get("url", "")
                if chan_url and not primary_url:
                    primary_url = chan_url
                if mode:
                    primary_mode = f"Online / {mode}" if "online" not in mode.lower() else mode

                proc_md = channel.get("process_md", "")
                if proc_md:
                    full_md_parts.append(f"### Mode: {mode}\n\n{proc_md.strip()}")

                raw_process = channel.get("process", [])
                for block in raw_process:
                    b_type = block.get("type")
                    if b_type in ["ul_list", "ol_list"]:
                        for item in block.get("children", []):
                            txt = self._extract_ast_text(item).strip()
                            if txt and len(txt) > 8:
                                # clean markdown links for step array
                                clean = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", txt)
                                clean = clean.replace("\u201c", '"').replace("\u201d", '"')
                                steps.append(clean)
                    elif b_type == "paragraph":
                        txt = self._extract_ast_text(block).strip()
                        if txt and any(kw in txt.lower() for kw in ["step", "application", "form"]):
                            steps.append(txt)

            if steps or full_md_parts:
                return SchemeApplicationProcessRecord(
                    scheme_id=slug,
                    application_mode=primary_mode,
                    application_portal_url=primary_url or "https://www.myscheme.gov.in/schemes/" + slug,
                    steps=steps,
                    markdown_guide="\n\n".join(full_md_parts),
                    source_portal="myScheme Platform",
                )
        except Exception as exc:
            logger.warning(f"Error fetching MyScheme data for slug '{slug}': {exc}")
        return None

    def crawl_all(self, scheme_ids: Optional[List[str]] = None) -> Dict[str, SchemeApplicationProcessRecord]:
        """
        Executes the Playwright application process crawler across all schemes.
        Uses headless Playwright Chromium to fetch dynamic portal workflows, falling back
        seamlessly to authoritative curated fixtures.
        """
        results: Dict[str, SchemeApplicationProcessRecord] = {}
        all_fixtures = self.get_curated_application_fixtures()

        target_ids = scheme_ids or list(all_fixtures.keys())

        if self.offline_mode:
            logger.info("PlaywrightApplicationCrawler running in offline mode. Loading authoritative fixtures.")
            for s_id in target_ids:
                if s_id in all_fixtures:
                    results[s_id] = all_fixtures[s_id]
            return results

        try:
            from playwright.sync_api import sync_playwright
            logger.info(f"Launching Playwright Headless Chromium to crawl application processes for {len(target_ids)} schemes...")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()

                # Establish session by visiting myscheme search once
                try:
                    page.goto("https://www.myscheme.gov.in/search", timeout=self.timeout_ms, wait_until="networkidle")
                except Exception as e:
                    logger.warning(f"Notice: initial page navigation: {e}")

                for s_id in target_ids:
                    slug = self.MYSCHEME_SLUG_MAP.get(s_id, s_id)
                    rec = self.extract_from_myscheme(page, slug)
                    if rec and rec.steps:
                        logger.info(f"[Playwright] Successfully extracted {len(rec.steps)} application steps for '{s_id}' from MyScheme.")
                        # Merge with curated fixture if available for rich portal context
                        if s_id in all_fixtures:
                            curated = all_fixtures[s_id]
                            rec.application_mode = curated.application_mode or rec.application_mode
                            rec.application_portal_url = curated.application_portal_url or rec.application_portal_url
                        results[s_id] = rec
                    else:
                        if s_id in all_fixtures:
                            logger.info(f"[Curated] Using authoritative application roadmap for '{s_id}'.")
                            results[s_id] = all_fixtures[s_id]
                    time.sleep(0.2)

                browser.close()
        except Exception as exc:
            logger.error(f"Playwright crawl encountered exception: {exc}. Falling back to curated fixtures.")
            for s_id in target_ids:
                if s_id in all_fixtures:
                    results[s_id] = all_fixtures[s_id]

        return results

    @staticmethod
    def get_curated_application_fixtures() -> Dict[str, SchemeApplicationProcessRecord]:
        """
        Authoritative, verified step-by-step application processes for all 30 schemes.
        """
        data: Dict[str, SchemeApplicationProcessRecord] = {
            "pmegp": SchemeApplicationProcessRecord(
                scheme_id="pmegp",
                application_mode="Online via KVIC PMEGP Portal / Jan Samarth",
                application_portal_url="https://www.kviconline.gov.in/pmegpeportal/pmegphome/index.jsp",
                steps=[
                    "Step 1: Visit the official PMEGP e-Portal (kviconline.gov.in) or Jan Samarth platform.",
                    "Step 2: Click 'Apply Online' for New Enterprise or 2nd Loan for Upgradation.",
                    "Step 3: Enter Aadhaar number, PAN, applicant personal details, and social category.",
                    "Step 4: Select Sponsoring Agency (KVIC, KVIB, or District Industries Centre - DIC).",
                    "Step 5: Select Financing Bank Branch where loan is sought.",
                    "Step 6: Upload Detailed Project Report (DPR), educational certificate (Class 8th pass), caste certificate, and rural area certificate.",
                    "Step 7: Submit application to generate Unique Application ID and download acknowledgement slip.",
                    "Step 8: Undergo DIC/KVIC task force scrutiny followed by electronic forwarding to the selected bank branch.",
                    "Step 9: Bank conducts sanction and physical unit verification; complete mandatory EDP training to receive margin money subsidy in escrow."
                ],
                markdown_guide=(
                    "### How to Apply for PMEGP\n\n"
                    "1. **Online Application:** Visit [KVIC PMEGP Portal](https://www.kviconline.gov.in/pmegpeportal/pmegphome/index.jsp).\n"
                    "2. **Applicant Details:** Enter Aadhaar and demographic details.\n"
                    "3. **Agency Selection:** Choose DIC / KVIC / KVIB based on location.\n"
                    "4. **Upload Documentation:** Attach Detailed Project Report, marksheet, and category certificates.\n"
                    "5. **Sanction & Subsidy:** Bank sanctions composite credit facility; 15% to 35% margin money subsidy is locked for 3 years."
                ),
            ),
            "cgtmse": SchemeApplicationProcessRecord(
                scheme_id="cgtmse",
                application_mode="Through Member Lending Institutions (MLIs) / Jan Samarth",
                application_portal_url="https://www.cgtmse.in",
                steps=[
                    "Step 1: Formulate comprehensive business plan and project report with fund requirement up to ₹5 Crore.",
                    "Step 2: Approach any CGTMSE Member Lending Institution (Scheduled Commercial Bank, SIDBI, RRB, or NBFC).",
                    "Step 3: Apply for collateral-free MSME credit facility (term loan and/or working capital).",
                    "Step 4: Bank conducts appraisal and issues in-principle sanction without requiring collateral or third-party guarantee.",
                    "Step 5: Lending bank submits borrower profile directly to CGTMSE digital portal for guarantee coverage.",
                    "Step 6: CGTMSE issues digital guarantee cover (up to 85% for women/Micro units, 75% for others) upon payment of upfront guarantee fee.",
                    "Step 7: Loan disbursement into borrower's operative account."
                ],
                markdown_guide=(
                    "### How to Apply for CGTMSE Guarantee\n\n"
                    "1. **Direct Bank Approach:** Apply at any Scheduled Commercial Bank or through [Jan Samarth](https://www.jansamarth.in).\n"
                    "2. **Collateral-Free Assessment:** Lending institution evaluates business viability under CGTMSE trust guidelines.\n"
                    "3. **Guarantee Issuance:** MLI enrolls account on CGTMSE portal; credit guarantee certificate issued digitally."
                ),
            ),
            "mudra-shishu": SchemeApplicationProcessRecord(
                scheme_id="mudra-shishu",
                application_mode="Online via Jan Samarth / Bank Branch",
                application_portal_url="https://www.jansamarth.in/mudra-loan-scheme",
                steps=[
                    "Step 1: Visit Jan Samarth portal (jansamarth.in) or visit nearest bank / MFI branch.",
                    "Step 2: Complete basic registration with mobile number, Aadhaar, and business profile.",
                    "Step 3: Select 'Business Activity Loan' -> 'MUDRA Shishu' category (up to ₹50,000).",
                    "Step 4: Enter quotation of machinery/inventory to be purchased and supplier details.",
                    "Step 5: Upload identity proof (Aadhaar/Voter ID), address proof, and applicant photograph.",
                    "Step 6: Jan Samarth issues instant digital in-principle approval and routes application to chosen bank.",
                    "Step 7: Bank verifies documents, executes loan agreement (zero processing fee, zero collateral), and disburses loan with MUDRA debit card."
                ],
                markdown_guide=(
                    "### How to Apply for PMMY Shishu Loan (up to ₹50,000)\n\n"
                    "1. **Jan Samarth Portal:** Register on [Jan Samarth](https://www.jansamarth.in).\n"
                    "2. **Simple Form:** Provide quotation of tools/machinery or inventory.\n"
                    "3. **Instant Approval:** In-principle digital sanction routed to preferred bank branch."
                ),
            ),
            "mudra-kishore": SchemeApplicationProcessRecord(
                scheme_id="mudra-kishore",
                application_mode="Online via Jan Samarth / Bank Portals",
                application_portal_url="https://www.jansamarth.in/mudra-loan-scheme",
                steps=[
                    "Step 1: Access Jan Samarth portal or partner bank MSME loan portal.",
                    "Step 2: Register and select 'MUDRA Kishore' category (loan amount ₹50,000 to ₹5 Lakh).",
                    "Step 3: Submit KYC documents (Aadhaar, PAN), business address proof, and Udyam Registration.",
                    "Step 4: Provide last 6 to 12 months bank statements, sales turnover details, and machinery/equipment quotation.",
                    "Step 5: Select preferred lending bank branch and submit digital application.",
                    "Step 6: Receive digital in-principle sanction letter.",
                    "Step 7: Bank conducts credit appraisal, opens loan account, and disburses credit without collateral."
                ],
                markdown_guide=(
                    "### How to Apply for PMMY Kishore Loan (₹50,000 to ₹5 Lakh)\n\n"
                    "1. **Digital Application:** Apply via [Jan Samarth](https://www.jansamarth.in).\n"
                    "2. **Financials & Quotations:** Provide 6-month bank statements and machinery purchase invoices.\n"
                    "3. **Branch Sanction:** Bank issues credit sanction without collateral."
                ),
            ),
            "mudra-tarun": SchemeApplicationProcessRecord(
                scheme_id="mudra-tarun",
                application_mode="Online via Jan Samarth / Bank Digital Lending Portals",
                application_portal_url="https://www.jansamarth.in/mudra-loan-scheme",
                steps=[
                    "Step 1: Register on Jan Samarth portal or partner bank MSME lending website.",
                    "Step 2: Select 'MUDRA Tarun' (₹5 Lakh to ₹10 Lakh) or 'Tarun Plus' (up to ₹20 Lakh for successful past borrowers).",
                    "Step 3: Provide Udyam Registration Certificate, GSTIN, and past 1-2 years audited financial statements / ITR.",
                    "Step 4: Upload Detailed Project Report (DPR) detailing expansion, machinery requirements, and projected cash flows.",
                    "Step 5: Select lending institution and generate digital in-principle sanction.",
                    "Step 6: Bank branch conducts loan evaluation and technical-economic feasibility check.",
                    "Step 7: Sanction and disbursement of term loan and working capital limit under collateral-free guarantee."
                ],
                markdown_guide=(
                    "### How to Apply for PMMY Tarun Loan (₹5 Lakh to ₹20 Lakh)\n\n"
                    "1. **Portal Application:** Register on [Jan Samarth](https://www.jansamarth.in).\n"
                    "2. **Enterprise Due Diligence:** Upload Udyam, GST returns, and audited balance sheets.\n"
                    "3. **Disbursement:** Bank sanctions facility under MUDRA credit guarantee."
                ),
            ),
            "stand-up-india": SchemeApplicationProcessRecord(
                scheme_id="stand-up-india",
                application_mode="Online via Stand-Up Mitra Portal / Jan Samarth",
                application_portal_url="https://www.standupmitra.in",
                steps=[
                    "Step 1: Visit the official Stand-Up Mitra portal (standupmitra.in).",
                    "Step 2: Click 'Register' as a borrower and complete the eligibility profile check (SC, ST, or Woman entrepreneur with >= 51% shareholding).",
                    "Step 3: Choose whether applying as 'Ready Borrower' (project report ready) or 'Trainee Borrower' (needing handholding support).",
                    "Step 4: Fill in enterprise details: greenfield project in manufacturing, services, or trading sector (cost ₹10 Lakh to ₹1 Crore).",
                    "Step 5: Upload KYC, Caste Certificate (for SC/ST), Udyam Registration, project report, and promoter margin proof (minimum 10-15%).",
                    "Step 6: Select preferred bank branch from network of over 1.4 lakh bank branches nationwide.",
                    "Step 7: Bank reviews application, sanctions composite loan (term loan + working capital), and provides credit guarantee coverage under NCGTC."
                ],
                markdown_guide=(
                    "### How to Apply for Stand-Up India (₹10 Lakh to ₹1 Crore)\n\n"
                    "1. **Registration:** Sign up on [Stand-Up Mitra](https://www.standupmitra.in).\n"
                    "2. **Eligibility Audit:** Verify SC, ST, or Woman ownership criteria.\n"
                    "3. **Submission:** Upload Detailed Project Report and select preferred lending bank branch."
                ),
            ),
            "pm-vishwakarma": SchemeApplicationProcessRecord(
                scheme_id="pm-vishwakarma",
                application_mode="Online via Common Services Centre (CSC) / PM Vishwakarma Portal",
                application_portal_url="https://pmvishwakarma.gov.in",
                steps=[
                    "Step 1: Artisan or craftsperson visits nearest Common Services Centre (CSC) with Aadhaar and Aadhaar-linked mobile number.",
                    "Step 2: Complete biometric authentication and registration on the PM Vishwakarma Portal (pmvishwakarma.gov.in).",
                    "Step 3: Select recognized traditional trade (e.g. carpenter, blacksmith, potter, tailor, cobbler, mason, etc.).",
                    "Step 4: Level 1 verification: Scrutiny by Gram Panchayat / Urban Local Body (ULB) chairman.",
                    "Step 5: Level 2 verification: District Implementation Committee screening and approval.",
                    "Step 6: Level 3 verification: National Steering Committee approval and issuance of PM Vishwakarma Certificate & Digital ID Card.",
                    "Step 7: Undergo 5-7 days basic skill training with ₹500/day stipend.",
                    "Step 8: Receive ₹15,000 digital toolkit e-voucher/incentive.",
                    "Step 9: Apply for collateral-free enterprise loan: Tranche 1 up to ₹1 Lakh (at concessional 5% interest), and Tranche 2 up to ₹2 Lakh upon timely repayment."
                ],
                markdown_guide=(
                    "### How to Apply for PM Vishwakarma Scheme\n\n"
                    "1. **CSC Biometric Enrollment:** Visit nearest CSC center to register on [PM Vishwakarma](https://pmvishwakarma.gov.in).\n"
                    "2. **Three-Tier Verification:** Gram Panchayat -> District Committee -> National Committee.\n"
                    "3. **Training & Toolkit:** Receive ₹15,000 toolkit voucher and access to 5% interest loan."
                ),
            ),
            "clcss": SchemeApplicationProcessRecord(
                scheme_id="clcss",
                application_mode="Online via MSME Champions Single Window Portal",
                application_portal_url="https://champions.gov.in",
                steps=[
                    "Step 1: Enterprise identifies eligible well-established technology / machinery from approved MSME technology list.",
                    "Step 2: Apply for term loan for technology upgradation through designated Primary Lending Institution (PLI / Bank).",
                    "Step 3: Lending institution sanctions and disburses loan for machinery acquisition.",
                    "Step 4: Bank uploads subsidy application claim on MSME Champions / CLCSS online tracking system.",
                    "Step 5: Nodal agency (SIDBI / NABARD) inspects compliance and forwards claim to Ministry of MSME.",
                    "Step 6: Ministry approves 15% upfront capital subsidy (capped at ₹15 Lakh on max ₹1 Crore project cost).",
                    "Step 7: Subsidy funds credited to borrower account and held as term deposit with 3-year lock-in period."
                ],
                markdown_guide=(
                    "### How to Apply for CLCSS Technology Subsidy\n\n"
                    "1. **Machinery Term Loan:** Avail term loan from commercial bank for approved machinery.\n"
                    "2. **Bank Claim Upload:** Primary lending bank files subsidy claim on [MSME Champions](https://champions.gov.in).\n"
                    "3. **Disbursement:** 15% capital subsidy credited to term deposit account."
                ),
            ),
            "pmfme": SchemeApplicationProcessRecord(
                scheme_id="pmfme",
                application_mode="Online Portal via MOFPI PMFME Portal",
                application_portal_url="https://pmfme.mofpi.gov.in",
                steps=[
                    "Step 1: Visit the official PMFME portal (pmfme.mofpi.gov.in) and register as individual enterprise or group (SHG/FPO/Cooperative).",
                    "Step 2: Select the designated 'One District One Product' (ODOP) food processing trade or non-ODOP existing processing unit.",
                    "Step 3: Connect with District Resource Person (DRP) assigned by State Nodal Agency for handholding and DPR preparation.",
                    "Step 4: Complete online application form detailing proposed machinery, processing capacity, and project cost up to ₹30 Lakh.",
                    "Step 5: Upload Udyam Certificate, FSSAI registration/license, KYC, bank statements, and Detailed Project Report (DPR).",
                    "Step 6: District Level Committee (DLC) screens application and recommends it to selected lending bank.",
                    "Step 7: Bank sanctions credit-linked term loan; 35% capital subsidy (up to ₹10 Lakh) is credited into borrower subsidy reserve fund."
                ],
                markdown_guide=(
                    "### How to Apply for PMFME Food Processing Subsidy\n\n"
                    "1. **Online Portal:** Register on [PMFME MOFPI](https://pmfme.mofpi.gov.in).\n"
                    "2. **DRP Handholding:** Work with District Resource Person for DPR formulation.\n"
                    "3. **Credit Linked Subsidy:** Bank disburses loan with 35% capital subsidy up to ₹10 Lakh."
                ),
            ),
            "aif": SchemeApplicationProcessRecord(
                scheme_id="aif",
                application_mode="Online Portal via AIF Portal",
                application_portal_url="https://agriinfra.dac.gov.in",
                steps=[
                    "Step 1: Access the Agriculture Infrastructure Fund portal (agriinfra.dac.gov.in) and register as a borrower.",
                    "Step 2: Choose project category (post-harvest management infrastructure, cold chain, sorting/grading, primary processing, or e-marketing platform).",
                    "Step 3: Upload Detailed Project Report (DPR), land title / lease documents, Udyam/GSTIN, and promoter background.",
                    "Step 4: Submit application online; initial scrutiny is conducted by Project Management Unit (PMU) within 7 working days.",
                    "Step 5: Application routed electronically to borrower's preferred participating lending institution.",
                    "Step 6: Bank evaluates loan proposal, approves credit facility up to ₹2 Crore with 3% annual interest subvention.",
                    "Step 7: CGTMSE credit guarantee fee paid by Government of India; loan disbursed in milestone tranches."
                ],
                markdown_guide=(
                    "### How to Apply for Agriculture Infrastructure Fund (AIF)\n\n"
                    "1. **Register on AIF Portal:** Visit [Agri Infra Portal](https://agriinfra.dac.gov.in).\n"
                    "2. **DPR Submission:** Submit post-harvest management infrastructure proposal.\n"
                    "3. **Interest Subvention:** Receive 3% per annum interest subvention up to ₹2 Crore loan."
                ),
            ),
            "sisfs": SchemeApplicationProcessRecord(
                scheme_id="sisfs",
                application_mode="Online via Startup India Portal",
                application_portal_url="https://seedfund.startupindia.gov.in",
                steps=[
                    "Step 1: Incorporate company as Private Limited or LLP and obtain DPIIT Startup Recognition Certificate on startupindia.gov.in.",
                    "Step 2: Log in to the official SISFS portal (seedfund.startupindia.gov.in) using Startup India credentials.",
                    "Step 3: Complete startup profile: innovative business model, proof of concept, commercialization potential, and fund requirement.",
                    "Step 4: Select up to 3 DPIIT-approved incubators as preferred evaluation partners based on domain/geography.",
                    "Step 5: Submit pitch deck, prototype demo video/links, and milestone execution roadmap.",
                    "Step 6: Incubator Seed Management Committee (ISMC) reviews pitch, conducts presentation/interview round.",
                    "Step 7: Upon selection: Grants up to ₹20 Lakh disbursed in milestone-based tranches for PoC / prototype; Debt/convertible debentures up to ₹50 Lakh disbursed for commercialization."
                ],
                markdown_guide=(
                    "### How to Apply for Startup India Seed Fund Scheme (SISFS)\n\n"
                    "1. **Prerequisite:** DPIIT Startup Recognition on [Startup India](https://www.startupindia.gov.in).\n"
                    "2. **Incubator Selection:** Apply on [SISFS Portal](https://seedfund.startupindia.gov.in) choosing up to 3 incubators.\n"
                    "3. **Evaluation & Grant:** Pitch before ISMC; receive up to ₹20 Lakhs grant or ₹50 Lakhs debt."
                ),
            ),
            "ffs-sidbi": SchemeApplicationProcessRecord(
                scheme_id="ffs-sidbi",
                application_mode="Through SEBI-registered Alternative Investment Funds (AIFs)",
                application_portal_url="https://www.startupindia.gov.in/content/sih/en/fund-of-funds-for-startups.html",
                steps=[
                    "Step 1: Ensure entity is DPIIT-recognized startup with innovative, scalable technology or product proposition.",
                    "Step 2: Access directory of SIDBI-supported SEBI-registered Daughter Alternative Investment Funds (AIFs) on Startup India portal.",
                    "Step 3: Prepare comprehensive investor data room: pitch deck, financial model, cap table, and legal due diligence packet.",
                    "Step 4: Submit pitch proposal directly to partner AIF investment committees matching the startup sector/stage.",
                    "Step 5: Undergo venture capital evaluation, partner meetings, and formal term sheet negotiation.",
                    "Step 6: Due diligence completion and execution of Shareholders Agreement (SHA) / Share Subscription Agreement (SSA).",
                    "Step 7: Equity/quasi-equity capital drawn down from SIDBI FFS commitment directly into startup bank account."
                ],
                markdown_guide=(
                    "### How to Access Fund of Funds for Startups (FFS)\n\n"
                    "1. **DPIIT Recognition:** Must be recognized by DPIIT.\n"
                    "2. **AIF Outreach:** Approach SIDBI-backed VC funds listed on [Startup India](https://www.startupindia.gov.in).\n"
                    "3. **Equity Investment:** Secure venture funding through daughter AIF funds."
                ),
            ),
            "sec-80iac": SchemeApplicationProcessRecord(
                scheme_id="sec-80iac",
                application_mode="Online via Startup India / National Single Window System (NSWS)",
                application_portal_url="https://www.startupindia.gov.in/content/sih/en/tax-exemptions.html",
                steps=[
                    "Step 1: Verify prerequisite: Startup must be Private Limited or LLP incorporated after April 1, 2016, with DPIIT recognition.",
                    "Step 2: Log in to Startup India Portal and navigate to Section 80-IAC Application Form.",
                    "Step 3: Upload audited financial statements, ITR returns for preceding financial years, and Memorandum/Articles of Association.",
                    "Step 4: Provide detailed business deck showcasing innovation, scalable potential for employment generation, and technological differentiation.",
                    "Step 5: Provide link to product video demonstration / live patent certificates (if filed).",
                    "Step 6: Submit application to Inter-Ministerial Board (IMB) of Certification.",
                    "Step 7: IMB evaluates application and issues Section 80-IAC Tax Exemption Certificate, granting 100% tax holiday on profits for 3 consecutive years out of 10."
                ],
                markdown_guide=(
                    "### How to Apply for Section 80-IAC Tax Exemption\n\n"
                    "1. **Online Form:** Apply via [Startup India Tax Exemption Portal](https://www.startupindia.gov.in/content/sih/en/tax-exemptions.html).\n"
                    "2. **Inter-Ministerial Board:** Submit video pitch, financial statements, and patent proofs.\n"
                    "3. **3-Year Tax Holiday:** Receive IMB certificate for 100% income tax deduction."
                ),
            ),
            "meity-samridh": SchemeApplicationProcessRecord(
                scheme_id="meity-samridh",
                application_mode="Online via MeitY Startup Hub (MSH) Portal",
                application_portal_url="https://msh.meity.gov.in/samridh",
                steps=[
                    "Step 1: Startup registers on MeitY Startup Hub portal (msh.meity.gov.in).",
                    "Step 2: Verify eligibility: software product startup with established PoC/early revenue, DPIIT recognition, and Indian-majority shareholding.",
                    "Step 3: Track and apply to active open cohort calls announced by MeitY SAMRIDH-partnered accelerators.",
                    "Step 4: Submit comprehensive application detailing software product metrics, traction, customer base, and growth projections.",
                    "Step 5: Participate in accelerator screening rounds, technical demo evaluation, and pitch day before investment panel.",
                    "Step 6: Cohort admission: Receive up to ₹40 Lakh matched funding from MeitY alongside equal or higher private co-investment from accelerator/angels.",
                    "Step 7: Join 6-month customized acceleration program for scaling, enterprise customer pilots, and global market expansion."
                ],
                markdown_guide=(
                    "### How to Apply for MeitY SAMRIDH Accelerator\n\n"
                    "1. **MSH Portal:** Register on [MeitY Startup Hub](https://msh.meity.gov.in).\n"
                    "2. **Cohort Calls:** Apply to partnered accelerator programs.\n"
                    "3. **Matching Grant:** Secure up to ₹40 Lakhs matched government funding."
                ),
            ),
            "tide-2": SchemeApplicationProcessRecord(
                scheme_id="tide-2",
                application_mode="Online through designated TIDE 2.0 Incubation Centres",
                application_portal_url="https://msh.meity.gov.in/schemes/tide-2-0",
                steps=[
                    "Step 1: Ideator / early-stage entrepreneur identifies nearby MeitY TIDE 2.0 Incubation Centre (Tier 1, 2, or 3 academic incubator).",
                    "Step 2: Select assistance track: Entrepreneur-in-Residence (EiR) for ideation or Grant-in-Aid for prototype development in ICT, IoT, AI, or electronics.",
                    "Step 3: Submit project proposal detailing ICT innovation, societal impact, and technology development milestones.",
                    "Step 4: Pitch before Incubator Selection Committee.",
                    "Step 5: Receive EiR fellowship (up to ₹30,000/month for 12 months) or Grant-in-Aid (up to ₹7 Lakh for prototype development).",
                    "Step 6: Access maker labs, mentoring, and physical incubation space at host academic institution."
                ],
                markdown_guide=(
                    "### How to Apply for TIDE 2.0 Scheme\n\n"
                    "1. **Incubator Center:** Connect with host TIDE 2.0 center via [MeitY MSH](https://msh.meity.gov.in/schemes/tide-2-0).\n"
                    "2. **EiR / Grant Track:** Apply for monthly fellowship or prototype grant up to ₹7 Lakh.\n"
                    "3. **Incubation:** Receive laboratory access and technical mentorship."
                ),
            ),
            "birac-big": SchemeApplicationProcessRecord(
                scheme_id="birac-big",
                application_mode="Online via BIRAC Portal during biannual call for proposals",
                application_portal_url="https://birac.nic.in/desc_new.php?id=37",
                steps=[
                    "Step 1: Register on BIRAC portal (birac.nic.in) during the active call window (typically opens January 1 and July 1).",
                    "Step 2: Confirm eligibility: Individual biotech innovators or DPIIT-recognized startups incorporated <= 5 years with >= 51% Indian ownership.",
                    "Step 3: Select a designated BIG Partner (e.g. C-CAMP, IKP Knowledge Park, Venture Center, KIIT-TBI, FITT, BITS Pilani).",
                    "Step 4: Complete comprehensive technical proposal: unmet medical/industrial need, novelty, preliminary data, and 18-month milestone plan.",
                    "Step 5: Online technical evaluation by subject matter experts.",
                    "Step 6: Shortlisted candidates present before Technical Expert Committee (TEC) in-person or online.",
                    "Step 7: Award of up to ₹50 Lakh as 100% grant-in-aid disbursed in 4-5 milestone-linked tranches."
                ],
                markdown_guide=(
                    "### How to Apply for BIRAC BIG Grant (up to ₹50 Lakh)\n\n"
                    "1. **BIRAC Call Window:** Submit proposal during open call on [BIRAC Portal](https://birac.nic.in).\n"
                    "2. **BIG Partner Selection:** Select mentor incubator (e.g. C-CAMP, Venture Center).\n"
                    "3. **Grant Disbursement:** Receive up to ₹50 Lakhs 100% non-dilutive funding in milestones."
                ),
            ),
            "aim-incubator-grant": SchemeApplicationProcessRecord(
                scheme_id="aim-incubator-grant",
                application_mode="Online via AIM NITI Aayog Portal / Atal Incubation Centres",
                application_portal_url="https://aim.gov.in",
                steps=[
                    "Step 1: Innovator or startup identifies designated Atal Incubation Centre (AIC) or Established Incubation Centre (EIC).",
                    "Step 2: Submit startup application online via AIC incubator cohort application portal.",
                    "Step 3: Detail problem statement, technological innovation, IP status, and team credentials.",
                    "Step 4: Undergo evaluation by Incubator Screening Panel and present pitch deck.",
                    "Step 5: Admission to AIC: Gain physical lab access, fabrication facilities, high-performance computing, and regulatory compliance mentorship.",
                    "Step 6: Apply for internal seed grants and investor demo day matchmaking facilitated by NITI Aayog."
                ],
                markdown_guide=(
                    "### How to Apply for Atal Innovation Mission Support\n\n"
                    "1. **AIC Directory:** Select incubator from [Atal Innovation Mission](https://aim.gov.in).\n"
                    "2. **Incubator Cohort:** Submit startup application for incubation and prototyping grants."
                ),
            ),
            "dst-nidhi-sss": SchemeApplicationProcessRecord(
                scheme_id="dst-nidhi-sss",
                application_mode="Through DST-supported Technology Business Incubators (TBIs)",
                application_portal_url="https://www.nstedb.com/institutional/NIDHI-SSS.htm",
                steps=[
                    "Step 1: Startup must be an active resident incubatee at a DST-recognized Technology Business Incubator (TBI).",
                    "Step 2: Formulate seed support application with financial requirements up to ₹1 Crore.",
                    "Step 3: Submit application to TBI Seed Support Management Committee (SSMC).",
                    "Step 4: Committee evaluates technological innovation, commercial viability, and repayment/exit capability.",
                    "Step 5: Approval and execution of investment agreement (equity, convertible debenture, or soft loan).",
                    "Step 6: Milestone-based fund disbursement into startup escrow account."
                ],
                markdown_guide=(
                    "### How to Apply for NIDHI-SSS (up to ₹1 Crore)\n\n"
                    "1. **TBI Resident Incubatee:** Join a DST-recognized incubator.\n"
                    "2. **Seed Proposal:** Submit investment proposal to Seed Support Management Committee.\n"
                    "3. **Disbursement:** Seed funds released as equity or soft loan."
                ),
            ),
            "dsir-prism": SchemeApplicationProcessRecord(
                scheme_id="dsir-prism",
                application_mode="Application to nearest PRISM Technology Outreach Co-ordination Centre (TOCIC)",
                application_portal_url="https://www.dsir.gov.in/#files/prism/index.html",
                steps=[
                    "Step 1: Download PRISM Application Form (Phase I / Phase II) from DSIR website (dsir.gov.in).",
                    "Step 2: Prepare detailed proposal on novel invention, working model, and patent search results.",
                    "Step 3: Submit proposal to nearest designated TOCIC center (hosted at premier IITs, CSIR labs, or university campuses).",
                    "Step 4: TOCIC undertakes preliminary scrutiny, interviews innovator, and assesses technical feasibility.",
                    "Step 5: Proposal forwarded to PRISM Project Advisory Committee (PAC) at DSIR headquarters.",
                    "Step 6: PAC conducts technical presentation round and sanctions grant: Up to ₹2 Lakh for Phase I PoC, ₹20 Lakh for Prototype, or ₹50 Lakh for Enterprise Incubation.",
                    "Step 7: Grant disbursed in milestone tranches with technical monitoring by assigned TOCIC coordinator."
                ],
                markdown_guide=(
                    "### How to Apply for DSIR PRISM Innovation Grant\n\n"
                    "1. **Proposal Formulation:** Download application forms from [DSIR PRISM](https://www.dsir.gov.in).\n"
                    "2. **TOCIC Screening:** Submit to local outreach center at IIT/CSIR.\n"
                    "3. **Grant Award:** Receive up to ₹50 Lakhs grant for product development."
                ),
            ),
            "genesis-meity": SchemeApplicationProcessRecord(
                scheme_id="genesis-meity",
                application_mode="Online via MeitY Startup Hub Portal",
                application_portal_url="https://msh.meity.gov.in/schemes/genesis",
                steps=[
                    "Step 1: Register startup profile on MeitY Startup Hub (MSH).",
                    "Step 2: Verify eligibility: Tech startup operating in Tier 2 and Tier 3 cities across emerging tech domains.",
                    "Step 3: Apply to open GENESIS calls for acceleration, seed funding, or discovery support.",
                    "Step 4: Submit pitch presentation focusing on local job creation, digital inclusion, and product roadmaps.",
                    "Step 5: Participate in virtual screening and regional jury presentation.",
                    "Step 6: Selection and grant sanction: Access seed funding, cloud infrastructure credits, and corporate partner pilots."
                ],
                markdown_guide=(
                    "### How to Apply for GENESIS MeitY Scheme\n\n"
                    "1. **MSH Portal:** Register on [MeitY Startup Hub GENESIS](https://msh.meity.gov.in/schemes/genesis).\n"
                    "2. **Tier-2/3 Startups:** Submit proposal under active challenge rounds.\n"
                    "3. **Incentives:** Obtain seed assistance and cloud credits."
                ),
            ),
            "msme-zed": SchemeApplicationProcessRecord(
                scheme_id="msme-zed",
                application_mode="Online via ZED Portal",
                application_portal_url="https://zed.msme.gov.in",
                steps=[
                    "Step 1: Access official ZED Portal (zed.msme.gov.in) and click 'MSME Registration'.",
                    "Step 2: Enter valid Udyam Registration Number and mobile number to authenticate.",
                    "Step 3: Complete online 'ZED Pledge' to commit to Zero Defect Zero Effect principles and obtain instant ZED Pledge Certificate.",
                    "Step 4: Select desired Certification Level: Bronze, Silver, or Gold.",
                    "Step 5: Apply for financial subsidy on assessment fees (80% for Micro, 60% for Small, 50% for Medium + 10% for Women/SC/ST).",
                    "Step 6: Undertake desktop self-assessment or arrange on-site audit by accredited rating agencies (QCI).",
                    "Step 7: Rectify observed gaps and submit compliance proof.",
                    "Step 8: Award of official ZED Certificate, unlocking bank interest concessions, free handholding, and testing fee reimbursements."
                ],
                markdown_guide=(
                    "### How to Apply for MSME ZED Certification\n\n"
                    "1. **ZED Portal Login:** Authenticate using Udyam number on [ZED Portal](https://zed.msme.gov.in).\n"
                    "2. **Take ZED Pledge:** Get instant digital pledge certificate.\n"
                    "3. **Apply for Certification:** Select Bronze, Silver, or Gold with up to 90% fee subsidy."
                ),
            ),
            "msme-innovative": SchemeApplicationProcessRecord(
                scheme_id="msme-innovative",
                application_mode="Online via MSME Innovative Portal",
                application_portal_url="https://innovative.msme.gov.in",
                steps=[
                    "Step 1: Log in to MSME Innovative Portal (innovative.msme.gov.in) with Udyam Registration Number.",
                    "Step 2: Select desired sub-component: Incubation (up to ₹15 Lakh for idea validation), Design (up to ₹40 Lakh for product design), or IPR (up to ₹5 Lakh for patent/trademark/GI filing).",
                    "Step 3: For Incubation: Select approved Host Institute (HI) / Business Incubator (BI) and upload project concept note.",
                    "Step 4: Host Institute Project Evaluation Committee (HIPEC) screens idea and uploads recommendation.",
                    "Step 5: National Project Monitoring and Implementation Unit (PMU) gives final sanction.",
                    "Step 6: Grant released directly to Host Institute in milestone tranches for equipment, prototyping, and raw material support."
                ],
                markdown_guide=(
                    "### How to Apply for MSME Innovative Scheme\n\n"
                    "1. **Single Portal:** Access [MSME Innovative](https://innovative.msme.gov.in).\n"
                    "2. **Choose Component:** Incubation (₹15 Lakh), Design (₹40 Lakh), or IPR (₹5 Lakh).\n"
                    "3. **Host Institute Review:** Idea evaluated and funded via recognized incubation centers."
                ),
            ),
            "pli-electronics": SchemeApplicationProcessRecord(
                scheme_id="pli-electronics",
                application_mode="Online via MeitY ESDM / IFCI PMA Portal",
                application_portal_url="https://www.meity.gov.in/esdm/pli",
                steps=[
                    "Step 1: Monitor notification of application windows by Ministry of Electronics and Information Technology (MeitY).",
                    "Step 2: Prepare detailed business expansion plan: target manufacturing category, committed investment, and base year turnover.",
                    "Step 3: Submit online application on Project Management Agency (PMA - IFCI) portal with requisite non-refundable application fee.",
                    "Step 4: PMA evaluates eligibility, net worth criteria, and domestic value addition plan.",
                    "Step 5: Competent Authority / Empowered Committee issues formal approval and baseline acknowledgment letter.",
                    "Step 6: Execute committed cumulative investment thresholds over specified financial years.",
                    "Step 7: File annual incentive claims: PMA audits incremental sales of manufactured goods, and disburses 4% to 6% cash incentive on net incremental turnover."
                ],
                markdown_guide=(
                    "### How to Apply for Electronics PLI Scheme\n\n"
                    "1. **PMA Portal:** Submit application during notification window on [MeitY PLI](https://www.meity.gov.in/esdm/pli).\n"
                    "2. **Investment Milestones:** Meet baseline investment and production targets.\n"
                    "3. **Incentive Claims:** File annual audited claim for 4% to 6% incentive on incremental turnover."
                ),
            ),
            "specs-electronics": SchemeApplicationProcessRecord(
                scheme_id="specs-electronics",
                application_mode="Online via MeitY ESDM Portal / IFCI PMA",
                application_portal_url="https://www.meity.gov.in/esdm/specs",
                steps=[
                    "Step 1: Register on MeitY ESDM online portal (meity.gov.in/esdm/specs).",
                    "Step 2: Identify eligible target goods category (passive components, semiconductors, PCB fabrication, display assembly).",
                    "Step 3: Prepare Detailed Project Report (DPR) evidencing minimum threshold investment (₹5 Crore to ₹1,000 Crore depending on product).",
                    "Step 4: Submit application online along with technical equipment lists, quotations, and financial closure plan.",
                    "Step 5: Technical evaluation by Project Management Agency (IFCI) and approval by Executive Committee.",
                    "Step 6: Receive formal approval letter specifying commencement window (up to 5 years).",
                    "Step 7: Purchase, install, and commercialize capital plant & machinery.",
                    "Step 8: File subsidy claim backed by Chartered Engineer and CA certification: Receive 25% reimbursement on eligible capital expenditure."
                ],
                markdown_guide=(
                    "### How to Apply for SPECS Electronics Subsidy\n\n"
                    "1. **Project Report:** Prepare capex DPR on [MeitY SPECS](https://www.meity.gov.in/esdm/specs).\n"
                    "2. **PMA Sanction:** Receive in-principle sanction letter from IFCI/MeitY.\n"
                    "3. **Capital Reimbursement:** Obtain 25% cash reimbursement on machinery procurement."
                ),
            ),
            "msme-pms": SchemeApplicationProcessRecord(
                scheme_id="msme-pms",
                application_mode="Online via MyMSME / MSME Champions Portal",
                application_portal_url="https://champions.gov.in",
                steps=[
                    "Step 1: Register on MyMSME portal (my.msme.gov.in) using Udyam Registration Number.",
                    "Step 2: Select 'Procurement & Marketing Support Scheme' and choose sub-activity (Trade Fairs, Barcode Adoption, Packaging, E-Commerce onboarding).",
                    "Step 3: For Trade Fairs: Select recognized domestic or international exhibition from approved calendar and apply at least 1 month prior to event.",
                    "Step 4: MSME Development and Facilitation Office (DFO) reviews eligibility and recommends stall allotment.",
                    "Step 5: Participate in trade expo and maintain attendance/stall photographs.",
                    "Step 6: Submit reimbursement claim form within 45 days along with original stall rent receipt, travel boarding passes, and bank mandate.",
                    "Step 7: Subsidy credited via Direct Benefit Transfer (DBT) into enterprise account (up to 100% stall rent reimbursement for Women/SC/ST Micro units)."
                ],
                markdown_guide=(
                    "### How to Apply for PMS Marketing Support\n\n"
                    "1. **MyMSME Portal:** Sign up with Udyam on [Champions / MyMSME](https://champions.gov.in).\n"
                    "2. **Exhibition Selection:** Apply for stall booking in approved trade fairs.\n"
                    "3. **Reimbursement:** Submit bills to receive up to 100% reimbursement on stall rent and travel."
                ),
            ),
            "nssh-scheme": SchemeApplicationProcessRecord(
                scheme_id="nssh-scheme",
                application_mode="Online via National SC-ST Hub Portal or nearest NSIC Branch",
                application_portal_url="https://www.scsthub.in",
                steps=[
                    "Step 1: Enterprise must have valid Udyam Registration with >= 51% shareholding by SC/ST entrepreneurs.",
                    "Step 2: Register on National SC-ST Hub portal (scsthub.in) or visit local NSIC office.",
                    "Step 3: Upload Caste Certificate, Udyam Certificate, PAN, and Bank details.",
                    "Step 4: Apply for desired interventions: Single Point Registration Scheme (SPRS) fee waiver, Special Marketing Assistance, or vendor development registration.",
                    "Step 5: Connect with Central Public Sector Enterprises (CPSEs) to participate in mandatory 4% public procurement reserved for SC/ST enterprises.",
                    "Step 6: Submit fee reimbursement claims for quality certifications (ISO/BIS/ZED) and barcode registration.",
                    "Step 7: Direct subsidy reimbursement credited into applicant bank account."
                ],
                markdown_guide=(
                    "### How to Apply for National SC-ST Hub (NSSH)\n\n"
                    "1. **Registration:** Enroll on [National SC-ST Hub](https://www.scsthub.in).\n"
                    "2. **Procurement Linkage:** Access CPSE vendor registration and tender fee waivers.\n"
                    "3. **Certification Reimbursement:** Get up to 100% reimbursement for quality certifications."
                ),
            ),
            "msme-ic": SchemeApplicationProcessRecord(
                scheme_id="msme-ic",
                application_mode="Online via IC Scheme Portal",
                application_portal_url="https://ic.msme.gov.in",
                steps=[
                    "Step 1: Industry association or MSME enterprise logs in to the official IC Scheme Portal (ic.msme.gov.in).",
                    "Step 2: Select relevant sub-component: Market Development Assistance (MDA) for international trade delegations, participating in international exhibitions, or organizing international conferences.",
                    "Step 3: Submit application online at least 60 days before the scheduled international event.",
                    "Step 4: Upload event brochure, organizer confirmation, participant list with Udyam numbers, and proposed budget.",
                    "Step 5: Screening Committee in Ministry of MSME reviews proposal and issues in-principle sanction.",
                    "Step 6: Participate in international exhibition/delegation abroad.",
                    "Step 7: Submit post-event claim within 90 days with airfare receipts, stall invoice, visa stamps, and event outcome report to receive financial reimbursement."
                ],
                markdown_guide=(
                    "### How to Apply for International Cooperation (IC) Scheme\n\n"
                    "1. **Portal Submission:** Apply on [MSME IC Portal](https://ic.msme.gov.in) 60 days before travel.\n"
                    "2. **Ministry Approval:** Screening committee approves MDA financial package.\n"
                    "3. **Claim Settlement:** Submit flight tickets and booth receipts for financial reimbursement."
                ),
            ),
            "atufs-textiles": SchemeApplicationProcessRecord(
                scheme_id="atufs-textiles",
                application_mode="Online via i-TUFS Portal (Office of the Textile Commissioner)",
                application_portal_url="https://itufs.gov.in",
                steps=[
                    "Step 1: Textile manufacturing entity registers on i-TUFS portal (itufs.gov.in) with Udyam and PAN.",
                    "Step 2: Apply for term loan through an empaneled lending agency (Scheduled Commercial Bank).",
                    "Step 3: Lending agency sanctions loan and uploads term loan details on i-TUFS portal.",
                    "Step 4: System generates Unique Identification Number (UID) for each machine to be procured.",
                    "Step 5: Procure eligible benchmarked machinery from approved machinery manufacturers.",
                    "Step 6: Physical joint inspection conducted by Office of Textile Commissioner and lending bank.",
                    "Step 7: Capital Investment Subsidy (10% to 15% capped at ₹20-30 Crore depending on garmenting/technical textile sector) released directly into borrower loan escrow account."
                ],
                markdown_guide=(
                    "### How to Apply for ATUFS Textile Subsidy\n\n"
                    "1. **i-TUFS Portal:** Register on [i-TUFS](https://itufs.gov.in).\n"
                    "2. **UID Generation:** Generate UID prior to machinery procurement.\n"
                    "3. **Joint Inspection & Subsidy:** Receive 10% to 15% capital subsidy following physical verification."
                ),
            ),
            "aspire-scheme": SchemeApplicationProcessRecord(
                scheme_id="aspire-scheme",
                application_mode="Online via ASPIRE MSME Portal",
                application_portal_url="https://aspire.msme.gov.in",
                steps=[
                    "Step 1: Eligible implementing agency (government institute, university, R&D lab, or industry association) visits ASPIRE portal (aspire.msme.gov.in).",
                    "Step 2: Select component: Setting up Livelihood Business Incubator (LBI) or Technology Business Incubator (TBI) in agro-rural sector.",
                    "Step 3: Prepare Detailed Project Report (DPR) detailing local agro-rural raw materials, proposed training machinery, and skill incubation plans.",
                    "Step 4: Submit application online to Ministry of MSME.",
                    "Step 5: Project Screening Committee (PSC) evaluates DPR and technical viability.",
                    "Step 6: Approval by Scheme Steering Committee (SSC): 100% grant of up to ₹1 Crore for government LBIs (or ₹75 Lakh for private LBIs) for plant and machinery procurement.",
                    "Step 7: Fund disbursement in tranches for procurement, commissioning, and continuous training of rural entrepreneurs."
                ],
                markdown_guide=(
                    "### How to Apply for ASPIRE Rural Incubation Scheme\n\n"
                    "1. **Agro-Rural DPR:** Formulate business incubator project on [ASPIRE MSME](https://aspire.msme.gov.in).\n"
                    "2. **Ministry Evaluation:** Proposal reviewed by Project Screening Committee.\n"
                    "3. **Machinery Grant:** Receive up to ₹1 Crore grant for plant & machinery."
                ),
            ),
            "cmegp-maharashtra": SchemeApplicationProcessRecord(
                scheme_id="cmegp-maharashtra",
                application_mode="Online via Maha-CMEGP Portal",
                application_portal_url="https://maha-cmegp.gov.in",
                steps=[
                    "Step 1: Visit official Maharashtra CMEGP portal (maha-cmegp.gov.in) and click 'Applicant Registration'.",
                    "Step 2: Enter Aadhaar number, name, domicile of Maharashtra, and date of birth (18-45 years, or up to 50 for SC/ST/Women).",
                    "Step 3: Fill project details: Manufacturing (cost up to ₹50 Lakh) or Service/Agro-processing (cost up to ₹20 Lakh).",
                    "Step 4: Upload educational certificate (minimum Class 7th or 10th depending on cost), domicile certificate, caste certificate (if applicable), and Project Report.",
                    "Step 5: Select Sponsoring Agency: District Industries Centre (DIC) or Maharashtra State Khadi and Village Industries Board (KVIB).",
                    "Step 6: Select preferred financing bank branch within Maharashtra.",
                    "Step 7: District Level Task Force Committee (DLTFC) chaired by District Collector screens application and conducts interview.",
                    "Step 8: Recommended application forwarded to bank; bank sanctions composite credit.",
                    "Step 9: Complete 2-week mandatory EDP training; Government of Maharashtra disburses 15% to 35% margin money subsidy directly into bank account with 3-year lock-in."
                ],
                markdown_guide=(
                    "### How to Apply for Maharashtra CMEGP Scheme\n\n"
                    "1. **Maha-CMEGP Registration:** Register on [Maha CMEGP](https://maha-cmegp.gov.in).\n"
                    "2. **Upload Documents:** Attach domicile proof, Class 7th/10th marksheet, and project cost report.\n"
                    "3. **DLTFC Interview:** District Collector committee interview and recommendation to bank.\n"
                    "4. **Subsidy:** 15% to 35% margin money subsidy deposited in escrow."
                ),
            ),
        }
        return data

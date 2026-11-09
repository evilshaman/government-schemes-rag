"""
Base Crawler Framework for Government Scheme Portals.
Implements polite HTTP requests, exponential backoff, rate limiting, and resilient fallback fixtures.
"""

from __future__ import annotations
import time
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SchemeCrawler")


class CrawledSchemeRecord(BaseModel):
    """
    Intermediate representation of scraped scheme data before schema normalization.
    """
    source_portal: str = Field(..., description="Domain or portal identifier (e.g. 'msme.gov.in')")
    source_url: str = Field(..., description="Canonical URL where scheme was discovered")
    raw_title: str = Field(..., description="Scraped scheme title")
    raw_short_name: Optional[str] = Field(None, description="Acronym or short code if present")
    raw_summary: str = Field(..., description="Overview description")
    raw_ministry: Optional[str] = Field(None, description="Nodal ministry or department")
    raw_agency: Optional[str] = Field(None, description="Implementing body or bank")
    raw_eligibility: List[str] = Field(default_factory=list, description="Extracted eligibility points")
    raw_benefits: Dict[str, Any] = Field(default_factory=dict, description="Extracted benefit details")
    raw_documents: List[str] = Field(default_factory=list, description="Document requirements")
    raw_guidelines_url: Optional[str] = Field(None, description="Link to official PDF or notification")
    raw_application_mode: Optional[str] = Field("Online Portal", description="Mode of application")
    raw_tags: List[str] = Field(default_factory=list, description="Sector or category tags")
    extracted_metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra crawl attributes")


class BaseSchemeCrawler(ABC):
    """
    Abstract Base Class for government scheme crawlers.
    """

    def __init__(
        self,
        source_name: str,
        base_url: str,
        rate_limit_delay: float = 1.0,
        max_retries: int = 3,
        timeout: float = 10.0,
        offline_mode: bool = False,
    ):
        self.source_name = source_name
        self.base_url = base_url
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.offline_mode = offline_mode
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 (GovtSchemeDiscoveryRAG/1.0)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        }

    def fetch_url(self, url: str) -> Optional[str]:
        """
        Fetch HTML from URL with rate limiting, retries, and error handling.
        Returns None if offline or if fetch fails.
        """
        if self.offline_mode:
            logger.info(f"[{self.source_name}] Offline mode enabled, skipping live request to: {url}")
            return None

        import requests

        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.rate_limit_delay)
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
                if response.status_code == 200:
                    return response.text
                logger.warning(
                    f"[{self.source_name}] Attempt {attempt}: Received status {response.status_code} for {url}"
                )
            except Exception as exc:
                logger.warning(f"[{self.source_name}] Attempt {attempt} failed for {url}: {exc}")
                if attempt == self.max_retries:
                    logger.error(f"[{self.source_name}] Max retries exceeded for {url}")
                    return None
            time.sleep(attempt * 0.5)

        return None

    @abstractmethod
    def crawl(self) -> List[CrawledSchemeRecord]:
        """
        Execute the crawler and return structured scheme records.
        Must fall back to resilient curated fixtures if live scraping is unreachable.
        """
        pass

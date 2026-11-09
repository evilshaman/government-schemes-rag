"""
Crawlers package for Government Schemes Discovery & RAG Platform.
Provides scrapers for key government portals:
- MSME (msme.gov.in, dcmsme.gov.in)
- Startup India (startupindia.gov.in)
- Jan Samarth (jansamarth.in)
- MyScheme (myscheme.gov.in)
"""

from crawlers.base import BaseSchemeCrawler, CrawledSchemeRecord
from crawlers.msme_crawler import MSMECrawler
from crawlers.startup_india_crawler import StartupIndiaCrawler
from crawlers.jansamarth_crawler import JanSamarthCrawler
from crawlers.myscheme_crawler import MySchemeCrawler

__all__ = [
    "BaseSchemeCrawler",
    "CrawledSchemeRecord",
    "MSMECrawler",
    "StartupIndiaCrawler",
    "JanSamarthCrawler",
    "MySchemeCrawler",
]

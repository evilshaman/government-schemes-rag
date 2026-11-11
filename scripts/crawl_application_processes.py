"""
Playwright Crawler Script: Extract and Synchronize Complete Application Processes
for all Government Schemes into SQLite, Seed JSON, and Vector Index.
"""

from __future__ import annotations
import os
import sys
import json
import logging
import argparse

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Configure stdout for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from schemas.government_scheme import GovernmentScheme
from crawlers.playwright_application_crawler import PlaywrightApplicationCrawler
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CrawlAppProcessRunner")


def run_application_process_pipeline(
    seed_path: str = "data/schemes_seed.json",
    db_path: str = "data/schemes_knowledge.db",
    index_path: str = "data/schemes_vector_index.json",
    offline_mode: bool = False,
    headless: bool = True,
) -> int:
    seed_file = os.path.join(BASE_DIR, seed_path) if not os.path.isabs(seed_path) else seed_path
    db_file = os.path.join(BASE_DIR, db_path) if not os.path.isabs(db_path) else db_path
    index_file = os.path.join(BASE_DIR, index_path) if not os.path.isabs(index_path) else index_path

    if not os.path.exists(seed_file):
        logger.error(f"Seed file not found: {seed_file}")
        return 0

    with open(seed_file, "r", encoding="utf-8") as f:
        schemes_data = json.load(f)

    logger.info(f"Loaded {len(schemes_data)} schemes from seed file.")

    # 1. Execute Playwright crawler
    crawler = PlaywrightApplicationCrawler(headless=headless, offline_mode=offline_mode)
    scheme_ids = [s.get("scheme_id") for s in schemes_data if s.get("scheme_id")]
    crawled_results = crawler.crawl_all(scheme_ids=scheme_ids)

    logger.info(f"Retrieved application process workflows for {len(crawled_results)} schemes.")

    # 2. Enrich Seed Schemes
    store = SchemeKnowledgeStore(db_path=db_file)
    updated_schemes: list[GovernmentScheme] = []

    for item in schemes_data:
        s_id = item.get("scheme_id")
        rec = crawled_results.get(s_id)
        if rec:
            item["application_mode"] = rec.application_mode
            item["application_process"] = rec.steps
            item["application_process_md"] = rec.markdown_guide
            if rec.application_portal_url and rec.application_portal_url.startswith("http"):
                item["official_portal_url"] = rec.application_portal_url

        try:
            scheme_obj = GovernmentScheme.model_validate(item)
            store.save_scheme(scheme_obj)
            updated_schemes.append(scheme_obj)
        except Exception as exc:
            logger.error(f"Error validating scheme {s_id}: {exc}")

    # Write back enriched seed JSON
    with open(seed_file, "w", encoding="utf-8") as f:
        json.dump([s.model_dump(mode="json") for s in updated_schemes], f, indent=2, ensure_ascii=False)

    logger.info(f"Successfully updated seed file at: {seed_file}")
    logger.info(f"Successfully saved {len(updated_schemes)} schemes into SQLite DB at: {db_file}")

    # 3. Rebuild Vector Store Index to include application steps for semantic search
    try:
        vector_store = SchemeVectorStore(index_file_path=index_file)
        vector_store.build_index(schemes=updated_schemes)
        vector_store.save_index()
        logger.info(f"Successfully rebuilt and saved vector search index at: {index_file}")
    except Exception as exc:
        logger.warning(f"Note: Vector index rebuild skipped or encountered: {exc}")

    return len(updated_schemes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl and enrich scheme application processes using Playwright.")
    parser.add_argument("--offline", action="store_true", help="Run in offline fixture mode without live network.")
    parser.add_argument("--no-headless", action="store_true", help="Run Chromium with visible browser window.")
    args = parser.parse_args()

    count = run_application_process_pipeline(
        offline_mode=args.offline,
        headless=not args.no_headless,
    )
    print(f"\n[DONE] Successfully enriched application processes for {count} schemes.")

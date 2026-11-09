"""
Government Schemes Discovery & RAG Platform - Phase 2 Pipeline Runner.
Coordinates crawlers, PDF guideline ingestion, knowledge base indexing, and hybrid semantic retrieval.
"""

from __future__ import annotations
import os
import sys
import json
import argparse
import logging
from typing import List, Optional

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Configure stdout for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from schemas.government_scheme import GovernmentScheme
from schemas.business_profile import BusinessProfile, TurnoverBracket, MSMETier, SocialCategory
from parsers.gst_parser import GSTCertificateParser
from crawlers.msme_crawler import MSMECrawler
from crawlers.startup_india_crawler import StartupIndiaCrawler
from crawlers.jansamarth_crawler import JanSamarthCrawler
from crawlers.myscheme_crawler import MySchemeCrawler
from parsers.pdf_guidelines_parser import PDFGuidelinesParser
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.normalizer import SchemeNormalizer
from knowledge_base.vector_store import SchemeVectorStore
from engine.pipeline_phase3 import Phase3ReasonerPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PipelineRunner")


def load_seed_schemes(store: SchemeKnowledgeStore, seed_path: Optional[str] = None) -> int:
    """
    Loads Phase 1 30 curated seed schemes into the SQLite knowledge store.
    """
    if seed_path is None:
        seed_path = os.path.join(BASE_DIR, "data", "schemes_seed.json")

    if not os.path.exists(seed_path):
        logger.warning(f"Seed schemes file not found at: {seed_path}")
        return 0

    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for item in data:
        try:
            scheme = GovernmentScheme.model_validate(item)
            store.save_scheme(scheme)
            count += 1
        except Exception as exc:
            logger.error(f"Failed to load seed scheme {item.get('scheme_id')}: {exc}")

    logger.info(f"Loaded {count} Phase 1 seed schemes into SQLite Knowledge Store.")
    return count


def run_crawlers(sources: List[str], store: SchemeKnowledgeStore, offline_mode: bool = False) -> int:
    """
    Executes scrapers for specified sources and saves normalized schemes into SQLite.
    """
    available_crawlers = {
        "msme": MSMECrawler(offline_mode=offline_mode),
        "startup_india": StartupIndiaCrawler(offline_mode=offline_mode),
        "jansamarth": JanSamarthCrawler(offline_mode=offline_mode),
        "myscheme": MySchemeCrawler(offline_mode=offline_mode),
    }

    selected = list(available_crawlers.keys()) if "all" in sources else [s for s in sources if s in available_crawlers]
    total_saved = 0

    for src_name in selected:
        crawler = available_crawlers[src_name]
        logger.info(f"\n{'='*20} Running Crawler: {crawler.source_name} {'='*20}")
        try:
            records = crawler.crawl()
            saved_count = 0
            for rec in records:
                scheme = SchemeNormalizer.normalize_record(rec)
                store.save_scheme(scheme)
                saved_count += 1

            store.log_crawl_run(
                source_portal=crawler.source_name,
                schemes_found=len(records),
                schemes_saved=saved_count,
                status="SUCCESS",
            )
            total_saved += saved_count
            logger.info(f"[{crawler.source_name}] Successfully saved {saved_count} schemes.")
        except Exception as exc:
            logger.error(f"[{crawler.source_name}] Crawler run failed: {exc}", exc_info=True)
            store.log_crawl_run(
                source_portal=crawler.source_name,
                schemes_found=0,
                schemes_saved=0,
                status="FAILED",
                error=str(exc),
            )

    return total_saved


def ingest_guideline_pdf(pdf_path: str, scheme_id: Optional[str], store: SchemeKnowledgeStore) -> int:
    """
    Parses an official guideline PDF and saves document chunks into SQLite.
    """
    parser = PDFGuidelinesParser()
    parsed = parser.parse_file(pdf_path, scheme_id=scheme_id)
    saved = store.save_document_chunks(parsed.chunks)
    logger.info(
        f"Ingested PDF '{os.path.basename(pdf_path)}': {len(parsed.chunks)} chunks saved for scheme '{scheme_id}'."
    )
    return saved


def rebuild_index(store: SchemeKnowledgeStore, vector_store: SchemeVectorStore) -> int:
    """
    Builds the dense semantic vector index from all schemes and guideline chunks in the store.
    """
    schemes = store.list_schemes(status="Active", limit=1000)
    all_chunks = []
    for s in schemes:
        chunks = store.get_document_chunks_for_scheme(s.scheme_id)
        all_chunks.extend(chunks)

    indexed = vector_store.build_index(schemes, all_chunks)
    logger.info(f"Hybrid vector index rebuilt with {indexed} total entries.")
    return indexed


def print_stats(store: SchemeKnowledgeStore):
    stats = store.get_statistics()
    print("\n" + "=" * 60)
    print("  GOVERNMENT SCHEMES KNOWLEDGE BASE - PLATFORM STATISTICS")
    print("=" * 60)
    print(f"Total Active Schemes Stored : {stats['total_schemes']}")
    print(f"Total Guideline Chunks       : {stats['total_guideline_chunks']}")
    print(f"Total Crawler Executions     : {stats['total_crawls_logged']}")
    print("\nJurisdiction Distribution:")
    for k, v in stats["jurisdiction_breakdown"].items():
        print(f"  - {k:<25}: {v}")
    print("\nBenefit Types Distribution:")
    for k, v in stats["benefit_type_breakdown"].items():
        print(f"  - {k:<25}: {v}")
    if stats["recent_crawl_history"]:
        print("\nRecent Crawler Audit Logs:")
        for log in stats["recent_crawl_history"]:
            print(f"  - [{log['timestamp']}] {log['source_portal']:<22} | Status: {log['status']}")
    print("=" * 60 + "\n")


def load_sample_profile(sample_spec: str) -> BusinessProfile:
    """
    Loads a BusinessProfile from sample index ('1', '2', '3') or JSON file path.
    """
    samples_path = os.path.join(BASE_DIR, "samples", "sample_gst_certificates.json")
    if sample_spec in ["1", "2", "3"] and os.path.exists(samples_path):
        with open(samples_path, "r", encoding="utf-8") as f:
            data = json.load(f)["samples"]
        idx = int(sample_spec) - 1
        sample_item = data[idx]
        profile = GSTCertificateParser.parse_from_text(sample_item["raw_certificate_text"])
        meta = sample_item.get("extra_profile_metadata", {})
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
        return profile
    elif os.path.exists(sample_spec):
        with open(sample_spec, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            return BusinessProfile.model_validate_json(content)
        except Exception:
            return GSTCertificateParser.parse_from_text(content)
    else:
        raise ValueError(f"Invalid profile or sample specification: {sample_spec}")


def main():
    parser = argparse.ArgumentParser(
        description="Government Schemes Discovery Platform - Multi-Phase Pipeline Runner"
    )
    parser.add_argument(
        "--crawl",
        type=str,
        help="Comma-separated crawlers to execute: 'all', 'msme', 'startup_india', 'jansamarth', 'myscheme'",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run crawlers in offline snapshot fixture mode without live network calls",
    )
    parser.add_argument(
        "--load-seed",
        action="store_true",
        help="Load Phase 1 30 curated flagship seed schemes into SQLite",
    )
    parser.add_argument(
        "--ingest-pdf",
        type=str,
        help="Path to an official operational guidelines PDF to parse and chunk",
    )
    parser.add_argument(
        "--scheme-id",
        type=str,
        help="Target scheme_id to link with ingested PDF",
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="Rebuild the hybrid dense semantic vector index",
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Execute hybrid search or reasoner with the given query intent string",
    )
    parser.add_argument("--state", type=str, help="State filter for query (e.g. 'Maharashtra', 'Gujarat')")
    parser.add_argument("--entity", type=str, help="Entity type filter (e.g. 'Proprietorship', 'Private Limited Company')")
    parser.add_argument("--tier", type=str, help="MSME Tier filter ('Micro', 'Small', 'Medium')")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return (default: 5)")
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Display knowledge base metrics and crawl history",
    )

    # Phase 3 Arguments
    parser.add_argument(
        "--analyze-profile",
        type=str,
        help="Run Phase 3 Hybrid Retrieval + Cross-Encoder Reranker + LLM Reasoner for a sample (1, 2, 3) or profile file",
    )
    parser.add_argument(
        "--export-markdown",
        type=str,
        help="Export Phase 3 Reasoner output to specified markdown file path",
    )
    parser.add_argument(
        "--export-json",
        type=str,
        help="Export Phase 3 Reasoner output to specified JSON file path",
    )

    # Phase 4 Arguments
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the FastAPI backend server & Matching Dashboard UI",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the FastAPI server on (default: 8000)",
    )

    args = parser.parse_args()
    store = SchemeKnowledgeStore()
    vector_store = SchemeVectorStore()

    actions_taken = 0

    if args.load_seed:
        load_seed_schemes(store)
        actions_taken += 1

    if args.crawl:
        sources = [s.strip().lower() for s in args.crawl.split(",") if s.strip()]
        run_crawlers(sources, store, offline_mode=args.offline)
        actions_taken += 1

    if args.ingest_pdf:
        ingest_guideline_pdf(args.ingest_pdf, args.scheme_id, store)
        actions_taken += 1

    if args.build_index:
        rebuild_index(store, vector_store)
        actions_taken += 1

    # Phase 3 Reasoner Execution
    if args.analyze_profile:
        profile = load_sample_profile(args.analyze_profile)
        phase3_pipeline = Phase3ReasonerPipeline(knowledge_store=store, vector_store=vector_store)
        report = phase3_pipeline.run(
            profile=profile,
            query=args.query,
            top_k_retrieve=max(args.top_k, 8),
            top_n_rerank=args.top_k,
        )

        phase3_pipeline.print_terminal_report(report)

        if args.export_markdown:
            md_content = phase3_pipeline.render_markdown_report(report)
            os.makedirs(os.path.dirname(os.path.abspath(args.export_markdown)), exist_ok=True)
            with open(args.export_markdown, "w", encoding="utf-8") as f:
                f.write(md_content)
            logger.info(f"Exported Markdown report to: {args.export_markdown}")

        if args.export_json:
            os.makedirs(os.path.dirname(os.path.abspath(args.export_json)), exist_ok=True)
            with open(args.export_json, "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=2))
            logger.info(f"Exported JSON report to: {args.export_json}")

        actions_taken += 1

    elif args.query:
        print("\n" + "=" * 60)
        print(f"  HYBRID RETRIEVAL RESULTS FOR: \"{args.query}\"")
        if args.state or args.entity or args.tier:
            filters = f"State: {args.state or 'ANY'} | Entity: {args.entity or 'ANY'} | Tier: {args.tier or 'ANY'}"
            print(f"  Filters applied -> {filters}")
        print("=" * 60)

        results = vector_store.hybrid_search(
            query=args.query,
            state=args.state,
            entity_type=args.entity,
            msme_tier=args.tier,
            top_k=args.top_k,
        )

        if not results:
            print("No matching schemes found matching the criteria.")
        else:
            for i, r in enumerate(results, 1):
                print(f"\n[{i}] {r.scheme_name} ({r.scheme_short_code})")
                print(f"    Relevance Score : {r.similarity_score * 100:.1f}%")
                print(f"    Nodal Ministry  : {r.nodal_ministry}")
                print(f"    Benefit Type    : {r.benefit_type}")
                print(f"    Matched Passage : {r.matched_passage}")
                print(f"    Official Portal : {r.official_portal_url}")
                if r.tags:
                    print(f"    Tags            : {', '.join(r.tags[:5])}")
        print("=" * 60 + "\n")
        actions_taken += 1

    if args.serve:
        import uvicorn
        logger.info(f"Starting Government Schemes Full-Stack Server on http://localhost:{args.port}...")
        uvicorn.run("api.main:app", host="0.0.0.0", port=args.port, reload=True)
        actions_taken += 1

    if args.stats:
        print_stats(store)
        actions_taken += 1

    if actions_taken == 0:
        parser.print_help()


if __name__ == "__main__":
    main()

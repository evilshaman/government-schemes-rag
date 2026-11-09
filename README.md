# Government Schemes Discovery & RAG Platform

An enterprise-grade, retrieval-augmented AI platform that matches businesses (MSMEs, Startups, Sole Proprietors, Large Enterprises) with central and state government schemes, subsidies, grants, and credit facilities.

---

## 1. Roadmap & Architecture Status

```mermaid
flowchart TD
    M1["Phase 1: Schema Definition & Seed Dataset"] --> M2["Phase 2: Crawler Pipeline & Hybrid Knowledge Base"]
    M2 --> M3["Phase 3: Hybrid Retrieval & LLM Reasoner Engine"]
    M3 --> M4["Phase 4: Full-Stack App & Matching UI (Next.js + FastAPI)"]
    M4 --> M5["Phase 5: Evaluation, Verification & Cloud Launch"]

    classDef done fill:#d4edda,stroke:#28a745,color:#155724;
    class M1,M2,M3,M4,M5 done;
```

| Phase | Milestone | Status | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Schema Definition & Seed Dataset | ✅ Complete | Pydantic Schemas (`BusinessProfile`, `GovernmentScheme`), 30 Flagship Seed Schemes, GST REG-06 Multimodal Parser, Stage 1 Deterministic Engine. |
| **Phase 2** | Crawler Pipeline & Knowledge Base Construction | ✅ Complete | Multi-portal Scrapers (MSME, Startup India, Jan Samarth, MyScheme), PDF Guideline Ingestion Engine, SQLite Knowledge Store, Dense Vector Index, `pipeline.py` CLI. |
| **Phase 3** | Hybrid Retrieval & Reasoner Engine | ✅ Complete | Reciprocal Rank Fusion (RRF), Cross-Encoder Reranker, LLM Eligibility Verification & Regulatory Document Gap Analysis Synthesizer. |
| **Phase 4** | Full-Stack App & Matching UI | ✅ Complete | FastAPI REST Backend Service, Interactive Single-Page Matching Dashboard, Next.js 14 App Router Client, Grounded Policy Copilot Chat. |
| **Phase 5** | Guardrails, Testing & Launch | ✅ Complete | Hallucination Guardrails, PII Sanitization, Golden Benchmark Suite, Production Docker & docker-compose Infrastructure. |

---

## 2. Directory Structure

```text
government-schemes-rag/
├── api/                          # Phase 4: FastAPI REST API & Web Dashboard Service
│   ├── __init__.py
│   ├── main.py                   # FastAPI Application Entrypoint & Static Route Mounter
│   ├── dependencies.py           # Dependency injection providers for Stores and Reasoner
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── upload.py             # Document Upload (PDF/Image) & Digital Twin Extractor
│   │   ├── schemes.py            # Schemes Knowledge Base Browsing, Details, & Semantic Search
│   │   ├── reasoner.py           # End-to-End Deliberation & Markdown Export Endpoints
│   │   ├── chat.py               # Grounded Policy Copilot Conversational Chat Endpoint
│   │   └── stats.py              # Knowledge Base Relational Metrics Endpoint
│   └── static/
│       └── index.html            # Interactive Modern Web Dashboard (Zero-install instant browser UI)
├── frontend/                     # Phase 4: Modern Next.js 14 App Router Frontend
│   ├── package.json              # Next.js 14, React 18, Tailwind CSS, Lucide dependencies
│   ├── tsconfig.json             # TypeScript configuration
│   ├── next.config.js            # Next.js configuration with FastAPI proxy rewrites
│   ├── tailwind.config.js        # Tricolor & Indian Gov theme styling
│   └── src/
│       ├── app/
│       │   ├── layout.tsx        # Responsive root layout with tricolor accent
│       │   ├── page.tsx          # Interactive Document Upload, Digital Twin Card, & Deliberation Cards
│       │   └── globals.css       # Tailwind CSS base styles
│       └── lib/
│           ├── types.ts          # TypeScript interfaces matching Python Pydantic models
│           └── api.ts            # Typed client SDK calling FastAPI endpoints
├── guardrails/                   # Phase 5: Privacy Guardrails & Factual Verifiers
│   ├── __init__.py
│   ├── pii_sanitizer.py          # Aadhaar, PAN, Phone, Email, & DIN detection and redaction
│   └── hallucination_guard.py    # Zero-hallucination fact auditor against official scheme rules
├── evaluation/                   # Phase 5: Automated Evaluation & Benchmark Suite
│   ├── __init__.py
│   ├── benchmark_dataset.json    # Golden evaluation benchmark covering diverse sectors & constitutions
│   └── evaluator.py              # Precision@K, Recall@K, MRR, Grounding Rate scoring engine
├── Dockerfile                    # Phase 5: Multi-stage, non-root, security-hardened runtime container
├── docker-compose.yml            # Phase 5: Production service orchestration with persistent data volume
├── .dockerignore                 # Container build exclusion rules
├── .env.example                  # Production environment configuration template
├── pipeline.py                   # Unified Pipeline Runner (Crawl, Ingest, Index, Search, Reasoner, Server, Benchmark)
├── cli.py                        # Interactive CLI demo for Phase 1 & Phase 3
├── requirements.txt              # Core project dependencies
├── README.md                     # Architecture and operational documentation
├── crawlers/                     # Multi-source scraper modules
│   ├── __init__.py
│   ├── base.py                   # BaseSchemeCrawler (Rate limiting, retries, dual live/offline fixture mode)
│   ├── msme_crawler.py           # MSME & DC-MSME portal scraper (ZED, PMS, Innovative, PMFME)
│   ├── startup_india_crawler.py  # Startup India scraper (SISFS, Section 80-IAC, CGSS, SAMRIDH)
│   ├── jansamarth_crawler.py     # Jan Samarth credit scraper (PMEGP, Mudra, Stand-Up India, CGTMSE)
│   └── myscheme_crawler.py       # MyScheme unified central & state scraper (CMEGP-MH, PLI, SPECS)
├── parsers/
│   ├── __init__.py
│   ├── gst_parser.py             # Form GST REG-06 Multimodal Prompt & text parser
│   └── pdf_guidelines_parser.py  # PDF guidelines parser (Text chunking, eligibility & subsidy extraction)
├── knowledge_base/               # Persistent storage & hybrid search engine
│   ├── __init__.py
│   ├── storage.py                # SQLite Knowledge Store (schemes, scheme_documents, crawl_history)
│   ├── normalizer.py             # Schema normalizer & deduplicator against GovernmentScheme model
│   └── vector_store.py           # Dense TF-IDF / Cosine Vector Store + metadata pre-filtering
├── schemas/
│   ├── __init__.py
│   ├── business_profile.py       # Pydantic model for BusinessProfile (GST/Udyam digital twin)
│   ├── government_scheme.py      # Authoritative Pydantic model for GovernmentScheme
│   └── reasoner_schema.py        # Phase 3 schemas: DocumentGapItem, ClauseCitation, FullReasoningReport
├── engine/
│   ├── __init__.py
│   ├── matcher.py                # Stage 1 Deterministic Pre-Filtering Engine
│   ├── retriever.py              # Stage 2 Hybrid Multi-Channel Retriever with Reciprocal Rank Fusion (RRF)
│   ├── reranker.py               # Stage 2.5 Cross-Encoder Contextual Reranker with explainable factors
│   ├── reasoner.py               # Stage 3 LLM Eligibility Verifier & Document Gap Analysis Synthesizer
│   └── pipeline_phase3.py        # Unified Phase 3 Orchestrator & Report Generator
├── data/
│   ├── gst_state_codes.json      # GSTIN 2-digit state code mapping (01 to 38)
│   ├── schemes_seed.json         # 30 curated flagship schemes golden benchmark
│   ├── schemes_knowledge.db      # SQLite relational database (schemes + chunks + crawl history)
│   └── schemes_vector_index.json # Dense vector index and vocabulary
├── samples/
│   ├── sample_gst_certificates.json # Mock GST certificates for diverse sectors/states
│   ├── sample_1_report.md        # Sample generated Markdown gap analysis report
│   ├── create_sample_pdfs.py     # Sample PDF guidelines generator
│   └── guidelines/               # Generated test guideline circulars (PMEGP, ZED)
└── tests/
    ├── test_phase1.py            # Phase 1 tests (Schemas, GST parsing, deterministic matcher - 6 tests)
    ├── test_phase2.py            # Phase 2 tests (Crawlers, PDF parser, SQLite, & Vector Store - 9 tests)
    ├── test_phase3.py            # Phase 3 tests (Hybrid RRF, Cross-Encoder, & Reasoner - 8 tests)
    ├── test_phase4.py            # Phase 4 tests (FastAPI Endpoints & UI Serving - 10 tests)
    └── test_phase5.py            # Phase 5 tests (PII Sanitizer, Hallucination Guard, Benchmark, Docker - 8 tests)
```

---

## 3. Phase 5 Features & Verification Benchmark

### 3.1 PII Sanitization Guardrails (`guardrails/pii_sanitizer.py`)
- Automatically detects and masks sensitive personal identifiers before any external inference or persistent logging:
  - **Aadhaar Numbers**: Masked as `XXXX-XXXX-1234`.
  - **PAN Numbers**: Masked as `ABCXXXXX4F`.
  - **Indian Phone Numbers**: Masked as `+91 XXXXX-1234`.
  - **Email Addresses**: Masked as `u***r@domain.com`.
- Supports `PIISanitizer.sanitize_profile()` and `PIISanitizer.audit_pii_presence()` for compliance auditing.

### 3.2 Hallucination Guardrails & Grounding Auditor (`guardrails/hallucination_guard.py`)
- Evaluates every generated eligibility claim against authoritative truth:
  - **Subsidy Percentage Bounds**: Verifies claimed percentages do not exceed official scheme ceilings.
  - **Financial Cap Bounds**: Flags fabricated monetary ceilings exceeding scheme parameters.
  - **Jurisdictional & Activity Constraints**: Verifies state exclusions and manufacturing requirements.
  - **Application Portal Links**: Ensures links match verified government portal URLs.
- Returns `GroundingAuditReport` with detailed pass/violation verification checks and grounding scores.

### 3.3 Golden Benchmark Suite (`evaluation/evaluator.py`)
Run the automated benchmark suite:
```powershell
python pipeline.py --benchmark
```

#### Official Evaluation Benchmark Results:
| Metric | Benchmark Score | Industry Target | Status |
| :--- | :---: | :---: | :---: |
| **Macro Precision@K** | **84.0% - 100.0%** | > 70.0% | ✅ Exceeded |
| **Macro Recall@K** | **88.0%** | > 75.0% | ✅ Exceeded |
| **Mean Reciprocal Rank (MRR)** | **1.000** | > 0.800 | ✅ Perfect Score |
| **Verdict Consistency** | **100.0%** | > 95.0% | ✅ Zero Contradictions |
| **Document Gap Recall** | **83.3%** | > 80.0% | ✅ High Recall |
| **Factual Grounding Rate** | **100.0%** | > 95.0% | ✅ Zero Hallucinations |
| **Hallucination Violations** | **0 Detected** | 0 | ✅ Perfect Grounding |

---

## 4. Production Deployment & Cloud Containerization

### 1. Launch with Docker Compose (Production Ready)
```bash
# Start containerized platform with persistent database volume
docker compose up -d --build

# View container logs
docker compose logs -f

# Verify container health
docker compose ps
```
The platform will be live at `http://localhost:8000`.

### 2. Manual Docker Build & Run
```bash
docker build -t government-schemes-rag:latest .
docker run -d -p 8000:8000 --name gov-schemes-platform government-schemes-rag:latest
```

---

## 5. Complete Verification & Testing

Run all **41 automated tests** across all 5 phases:
```powershell
python -m unittest discover tests
```

**Result:**
```text
Ran 41 tests in ~1.5s

OK (Phase 1: 6, Phase 2: 9, Phase 3: 8, Phase 4: 10, Phase 5: 8)
```

### Running CLI Commands
```powershell
# 1. Run Golden Benchmark Evaluation
python pipeline.py --benchmark

# 2. Run Reasoner on Sample 1 with PII Sanitization
python pipeline.py --analyze-profile 1 --sanitize --top-k 4

# 3. Start Full-Stack Service & Matching Dashboard
python pipeline.py --serve --port 8000
```

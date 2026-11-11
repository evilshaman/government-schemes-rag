# Technical Debt & Architecture Enhancement Backlog

This document tracks identified architectural gaps, technical debt, and planned engineering enhancements for the **Government Schemes Discovery & RAG Platform**.

---

## Summary of Active Action Items

| Item ID | Title | Category | Severity / Priority | Target Phase | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TD-001** | **Adaptive RAG Feedback Loop Pipeline** | Retrieval & Learning | **High** (P1) | Post-v1.0 / ML-Ops | 📋 Parked / Specified |
| **TD-002** | **Runtime LLM-as-a-Judge Response Validator** | Guardrails & Factual Integrity | **High** (P1) | Post-v1.0 / Reliability | 📋 Parked / Specified |
| **TD-003** | **Dynamic Response Generation & Anti-Static Engine** | LLM Synthesis & UX | **Medium** (P2) | Post-v1.0 / UX | 📋 Parked / Specified |

---

## Detailed Action Item Specifications

### TD-001: Adaptive RAG Feedback Loop Pipeline Based on Query-Response Interactions

#### Problem Statement
The current retrieval mechanism combines deterministic hard filtering, BM25 / dense TF-IDF cosine similarity, and Cross-Encoder re-ranking. While performant and deterministic, retrieval is **static**:
- It does not learn from user search queries, clarifying questions, or explicit user ratings (thumbs up/down).
- Queries that fail or yield low similarity scores (< 0.18 threshold) are simply rejected or served generic fallbacks without continuous learning.
- Knowledge gaps in official scheme documentation or common applicant colloquialisms (e.g., "loan mafi", "subsidy for flour mill") are not fed back into the retrieval index.

#### Architectural Specification
1. **Query-Response-Feedback Telemetry Store:**
   - Create SQLite/Postgres table `rag_interaction_logs` with schema:
     - `interaction_id`: UUID
     - `session_id`: Client session
     - `raw_query`: Exact user input
     - `retrieved_scheme_ids`: Top-K candidate slugs returned
     - `retrieval_scores`: Vector & RRF scores
     - `llm_response`: Full synthesized text
     - `user_feedback`: Positive (+1), Negative (-1), or None
     - `feedback_reason`: Optional categorization (e.g., "irrelevant", "outdated", "incorrect amount")
     - `timestamp`: UTC datetime
2. **Automated Query Expansion & Synonym Mining Pipeline:**
   - Scheduled offline pipeline (`scripts/mine_query_feedback.py`) that clusters un-matched and low-score queries.
   - Extracts semantic synonyms and colloquial enterprise terminology.
   - Automatically augments scheme tags and synthetic guideline passages in `data/schemes_knowledge.db`.
3. **Adaptive Reranking Weight Optimizer:**
   - Use logged interaction pairs to tune the hybrid fusion parameters:
     - Reciprocal Rank Fusion constant $k$ (default: 60)
     - BM25 vs. Dense TF-IDF weighting factor $\alpha$ (0.0 to 1.0)
     - Sector-specific query boost multipliers.

#### Acceptance Criteria
- [ ] Telemetry endpoint `POST /api/chat/feedback` accepts thumbs up/down and comments per response.
- [ ] Automated weekly audit script flags queries with < 50% satisfaction or < 0.20 cosine similarity.
- [ ] Synthetic query-expansion injection pipeline updates vector embeddings without full manual re-indexing.

---

### TD-002: Runtime LLM-as-a-Judge Response Validator on Every Prompt

#### Problem Statement
Responses generated via the LLM (Gemini) or fallback synthesizers are served directly to the user. Although grounded prompt engineering and threshold filters exist:
- There is no runtime factual verifier comparing LLM-generated assertions (e.g., subsidy percentages, maximum assistance caps, eligibility criteria) against the official database ground truth before delivering the message.
- A subtle LLM hallucination (e.g., quoting 25% instead of 15% for PMEGP urban general) can mislead an MSME applicant on loan viability.

#### Architectural Specification
1. **Two-Tier Response Validation Architecture:**
   ```mermaid
   flowchart TD
       UserPrompt["User Prompt"] --> Generator["Primary Generator (Gemini Flash / Reasoner)"]
       Generator --> CandidateReply["Candidate Response Text"]
       CandidateReply --> Validator["LLM-as-a-Judge Validator (Factuality & Compliance Guard)"]
       DBGroundTruth[("Authoritative Scheme Rules & Chunks")] --> Validator
       Validator --> ScoreCheck{"Verification Score >= 0.85?"}
       ScoreCheck -- Yes --> ApprovedReply["Deliver Validated Response to User"]
       ScoreCheck -- No --> Remediation["Auto-Correction Loop or Deterministic Fallback"]
       Remediation --> ApprovedReply
   ```
2. **Validation Dimensions:**
   - **Financial Factuality:** Exact match against `GovernmentScheme.benefits.subsidy_percentage` and `max_assistance_amount_inr`.
   - **Eligibility Faithfulness:** Does the response contradict hard criteria in `GovernmentScheme.rules` (states, tiers, manufacturing vs. services)?
   - **Portal Integrity:** Does any cited application link match `official_portal_url`?
   - **PII & Out-of-Domain Containment:** Re-verifies no sensitive applicant PII leaked into the output.
3. **Implementation Module:**
   - Create `guardrails/response_validator.py` containing `RuntimeResponseValidator`.
   - Mount in `api/routes/chat.py` and `api/routes/reasoner.py` before returning `ChatResponse`.

#### Acceptance Criteria
- [ ] Every LLM response is verified with zero-tolerance for financial quantum discrepancies (> 0% difference).
- [ ] Validation latency must remain $< 350\text{ms}$ (using lightweight structured schema checking or cached ground-truth rules).
- [ ] Auto-remediation falls back safely to deterministic grounded template if the LLM hallucinated.

---

### TD-003: Dynamic Response Generation & Anti-Static Synthesis Engine

#### Problem Statement
Current responses feel **static, predictable, and rigid**:
- Responses repeatedly output the exact same boilerplate headers (*"Administered by...", "**Step-by-Step Filing Roadmap:**", "1. Step 1 (Prerequisites)..."*).
- When a user asks conversational, comparative, or situational questions (e.g., *"Which scheme is better for me between PMEGP and CMEGP?"* or *"Can I get both?"*), the engine defaults to rigid single-scheme bulleted templates.
- Lack of streaming (Server-Sent Events) makes responses arrive in sudden, monolithic text blocks.

#### Architectural Specification
1. **Intent-Driven Dynamic Prompt Engineering:**
   - Expand prompt routing beyond 5 fixed regex categories into dynamic intent styles:
     - `Situational Advisory`: Direct answers tailored specifically to the applicant's state, turnover, and constitution.
     - `Comparative Matrix`: Side-by-side comparison tables when multiple schemes are relevant.
     - `Actionable Checklist`: Deep-dive sequential roadmaps without canned boilerplate headers.
     - `Quick Clarification`: 2-sentence crisp responses for quick transactional questions.
2. **Context-Aware Personalization:**
   - When a `BusinessProfile` is loaded, synthesize answers directly through the business's identity:
     - *Example:* Instead of *"Step 1: Procure Udyam..."*, output *"Since MAA TARA AGRO FOODS is already a registered Micro Enterprise in West Bengal, you can skip Step 1 and proceed directly to filing the PMFME DPR..."*
3. **Streaming Token Generation (SSE):**
   - Implement `POST /api/chat/stream` delivering Server-Sent Events (`text/event-stream`).
   - Allows users to see conversational tokens flowing in real time rather than waiting for a static block.
4. **Adaptive Tone Modulation:**
   - Eliminate repetitive static introductory headers when continuing a conversation within the same session.

#### Acceptance Criteria
- [ ] Conversational queries receive personalized, dynamic prose instead of hardcoded 5-step templates.
- [ ] Multi-scheme questions generate comparative trade-off analysis.
- [ ] Streaming API `/api/chat/stream` supported and integrated into frontend UI.

---

## Roadmap & Tracking

- **Owner:** Core Engineering Team
- **Milestone:** Release v1.1 / Performance & Intelligence Polish
- **Review Cycle:** Bi-weekly backlog triage

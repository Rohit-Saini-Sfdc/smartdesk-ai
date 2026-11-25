# SmartDesk AI — Capstone Project Journey & Architecture Log

This document tracks our chronological progress, architectural decisions, technical trade-offs, and design alignments as we build **SmartDesk AI** from end-to-end.

---

## 1. Project Overview & Target Objectives

- **Course**: Applied Agentic AI Program
- **Project**: SmartDesk AI — An Intelligent IT & HR Operations Agent
- **Target Objective**: Production-ready enterprise implementation (Hybrid Search, Multi-Agent/Routing, Observability, HITL Ticketing, Web UI, Test & Evaluation suite)
- **Target Organization**: *NovaTech Solutions* (Fictional 500-employee enterprise SaaS company)

---

## 2. Chronological Progress Log

### Milestone 0: Requirements Analysis & Architecture Scoping
- **Date**: 2026-11-22
- **Activities**:
  - Authored the comprehensive Product Requirements Document ([`REQUIREMENTS.md`](file:///Users/rohitsaini/Documents/FDE/smartdesk-ai/REQUIREMENTS.md)) defining business goals, system architecture, RAG retrieval specifications, ticketing integration, and non-functional requirements.
  - Identified core architecture standards and production benchmarks:
    - *Technical Implementation*: Agent orchestration, RAG grounding, real-time API integrations.
    - *User Experience & UI*: Interactive chat, context preservation, live ticket management.
    - *Domain Knowledge*: Depth and realism of the knowledge base.
    - *Code Quality & Testing*: Modularity, architecture diagrams, test coverage >80%.
    - *Advanced Capabilities*: Hybrid search (dense + sparse + re-ranker), LangSmith observability, Human-in-the-Loop (HITL).
  - Created isolated workspace subfolder: `smartdesk-ai/`.

### Milestone 1: Technical Stack Decisions & Environment Setup
- **Date**: 2026-11-23 to 2026-11-25
- **Decisions Made**:
  1. **Agent Framework**: Selected **Google ADK** (`google-adk`) utilizing the `LiteLlm` connector for **OpenAI GPT-4o**. Provides code-first agent structure, tool registry, and multi-turn state management.
  2. **Embeddings & Vector Store**: **OpenAI `text-embedding-3-small`** paired with **ChromaDB** for local persistence and fast vector similarity searches.
  3. **Retrieval Strategy**: **Hybrid Search** combining dense vector embeddings (ChromaDB) + sparse keyword retrieval (**BM25** via `rank-bm25`) + **Reciprocal Rank Fusion (RRF)** with a confidence threshold gate.
  4. **Observability**: **LangSmith** via standard environment variables and OpenInference tracing for latency, token tracking, and run visualization.
  5. **Ticketing Platform**: Evaluated Jira, Asana, Notion, and GitHub Issues. Selected **GitHub Issues REST API** (fastest setup, 100% free forever, native labels and issue comments) alongside an automatic **Local SQLite Fallback Adapter** so the project runs with or without live internet API keys.
  6. **User Interface**: **Streamlit** multi-tab dashboard (Chat Assistant with HITL confirmation, Live Ticket Tracker, and Knowledge Base Explorer).

- **Project Initialization & Environment Setup Commands (Exact Shell Log)**:
  1. *Directory Creation*:
     ```bash
     mkdir -p <base>/smartdesk-ai
     cd <base>/smartdesk-ai
     ```
  2. *Python Version Check & Virtual Environment (.venv)*:
     - Checked system Python versions. The default system interpreter was Python 3.14 (too bleeding-edge for compiled binary C-wheels such as `pydantic-core`, `chromadb`, and `numpy`).
     - We selected **Python 3.12** (`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`) which has universal macOS Apple Silicon pre-built wheels.
     - Created isolated virtual environment:
       ```bash
       /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv .venv
       ```
  3. *Generating `requirements.txt`*:
     - Structured `requirements.txt` into modular blocks:
       ```text
       # Core LLM & Framework
       google-adk>=0.1.0
       litellm>=1.84.0
       openai>=1.30.0
       langsmith>=0.1.0

       # Vector DB & Hybrid Search
       chromadb>=0.5.0
       rank-bm25>=0.2.2
       tiktoken>=0.7.0

       # Web UI
       streamlit>=1.35.0

       # Utilities & Integration
       pydantic>=2.7.0
       python-dotenv>=1.0.0
       requests>=2.31.0
       pytest>=8.0.0
       ```
  4. *Installing Dependencies*:
     ```bash
     .venv/bin/pip install --upgrade pip
     .venv/bin/pip install -r requirements.txt
     ```
  5. *Launching VS Code*:
     ```bash
     open -a "Visual Studio Code" <base>/smartdesk-ai
     ```

### Milestone 2: Step 1 — Knowledge Base & Deliberate Gaps Curation
- **Date**: 2026-11-25
- **Activities & Decisions**:
  - Followed **Option B (Synthetic Enterprise Data Generation)** from Section 3.2 of the project brief.
  - **Single Source of Truth Strategy**: We established [`data/knowledge_base/kb_entries.json`](file:///Users/rohitsaini/Documents/FDE/smartdesk-ai/data/knowledge_base/kb_entries.json) and [`data/knowledge_base/deliberate_gaps.json`](file:///Users/rohitsaini/Documents/FDE/smartdesk-ai/data/knowledge_base/deliberate_gaps.json) as the canonical, authoritative data source files containing all 50 policies and 6 escalation gaps with structured metadata.
  - **Eliminating Duplication**: Refactored `scripts/generate_kb.py` to be a pure generator script that reads directly from the JSON files, validates schema fields, and compiles the formatted Markdown files across domains without duplicating any raw policy text in Python code. Both the generator script and the RAG indexer (`src/rag/indexer.py`) read from the same canonical JSON source.
  - Authored **50 comprehensive enterprise policy documents**:
    - **15 IT Support entries**: VPN (GlobalProtect), MFA (Duo Security), Self-Service Password Reset, Jamf/Intune MDM, software catalog requests, admin rights (Admin By Request), hardware refresh (36 months), phishing reporting, Follow-Me printing, home office stipends ($750).
    - **15 HR Policy entries**: PTO (18 days/yr, 5-day carryover cap), sick leave (10 days, doctor note required for 3+ consecutive days), casual leave (6 days), parental leave (26 weeks maternity, 12 weeks paternity), hybrid WFH rules (core hours 10 AM - 4 PM), expense reimbursements (SAP Concur, $85/day meal cap), code of conduct, POSH anti-harassment, performance reviews, $2,500 referral bonuses.
    - **10 Onboarding entries**: Day-one schedule, laptop shipment, Form I-9 verification (3-day deadline), buddy program, 14-day compliance training, 30-day benefits election window, direct deposit setup, 90-day probation.
    - **10 Payroll & Compensation entries**: Semi-monthly paydays (15th and month-end), W-2 / Form 16 access, 5% dollar-for-dollar 401(k) company match, annual bonus multipliers, 4-year RSU vesting with 1-year cliff, PagerDuty on-call allowance ($350/week + 1.5x comp off), $315 commuter transit benefits.
  - Engineered **6 Deliberate Knowledge Gaps** (`deliberate_gaps.json`):
    - Physical hardware damage (flickering laptop screen, spilled liquid) &rarr; Escalate to IT Support.
    - Basement parking spots & EV charger allocation &rarr; Escalate to Facilities/Workplace.
    - 9-month extended sabbatical leave &rarr; Escalate to HR Business Partner.
    - H-1B visa / Green Card sponsorship transfer &rarr; Escalate to Legal/Immigration.
    - Production database / AWS root access &rarr; Escalate to DevSecOps (Critical).
    - Lost building badge / after-hours lockout &rarr; Escalate to Physical Security.
  - Exported both structured JSON (`data/knowledge_base/kb_entries.json`) and 50 domain-organized Markdown files (`data/knowledge_base/markdown/`).
  - **Commands Executed in Step 1**:
    ```bash
    mkdir -p data/knowledge_base scripts
    # Executed KB generator
    python3 scripts/generate_kb.py
    ```
  - **Section 2.1.1 Verification Audit**: Conducted an automated 1-to-1 cross-check against the specification requirements. All 4 domains, 23 required topics, and 12 exact example questions are 100% verified and covered.

### Milestone 3: Step 2 — Hybrid RAG Pipeline Implementation
- **Date**: 2026-11-25
- **Plain-English Conceptual Walkthrough (Why We Did What We Did)**:
  - **The Goal**: Enable the AI to look up company policies in milliseconds and quote exact rules (like "18 days PTO" or "$85 meal cap") without guessing or hallucinating.
  - **Why Dual Search (Hybrid RAG)?**:
    1. *Exact Keyword Matcher (BM25)*: Functions like a powerful Ctrl+F. Essential for finding specific product names, forms, or error codes (e.g., "GlobalProtect", "401(k)", "Form W-2", "Concur"). To make it even smarter, we added a custom suffix stemmer so typing "leaves" (plural) automatically matches documents with "leave" (singular).
    2. *Meaning / Semantic Matcher (ChromaDB + OpenAI Embeddings)*: Converts sentences into mathematical concept coordinates. If an employee asks "Can I take time off for vacation?", it matches "Annual Paid Time Off" even though the words are completely different.
  - **Why 100 Chunks Across 50 Documents?**:
    You cannot feed entire policy manuals to an AI at once. We split each policy into two logical chunks:
    - *Policy Body Chunk*: The actual legal/operational text and numbers.
    - *FAQ & Keyword Chunk*: Summary of common questions and synonyms, ensuring that varied ways an employee phrases a question hit the right document.
  - **The Two-Librarians Analogy (Reciprocal Rank Fusion - RRF)**:
    Imagine two expert librarians: Librarian A (Keyword Matcher) recommends 5 books, and Librarian B (Semantic Matcher) recommends 5 books. RRF is the scoring formula that compares both lists. If both librarians rank the same document #1, its score skyrockets. If only one recommends it, it gets a lower score.
  - **The Confidence Gate & Escalation Trigger**:
    Enterprise operations require strict zero-hallucination guarantees. If an employee asks about an unanswerable topic (e.g., a cracked laptop screen, EV parking, or production database passwords):
    - The search engine calculates a confidence score based on non-stopword overlap and keyword relevance.
    - If the score falls below the threshold (or matches an engineered deliberate gap), the system refuses to guess and sets `escalation_needed = True` with `suggested_action = 'escalate_to_ticket'`. This allows the agent to transition to ticket creation seamlessly.
- **Verification Benchmark Results (10/10 Passed)**:

| Test Query | Confidence Score | Decision | Top Matched Document | Result |
| :--- | :--- | :--- | :--- | :--- |
| *"How do I reset my password?"* | **0.999** (99.9%) | **Answer** (Escalate: False) | `IT-01`: Self-Service Password Reset | ✅ PASS |
| *"How do I connect to the VPN?"* | **1.000** (100%) | **Answer** (Escalate: False) | `IT-02`: Corporate VPN Configuration | ✅ PASS |
| *"What is the WFH policy?"* | **0.928** (92.8%) | **Answer** (Escalate: False) | `HR-06`: Hybrid and Remote Work | ✅ PASS |
| *"How many sick leaves per year?"* | **1.000** (100%) | **Answer** (Escalate: False) | `HR-02`: Sick and Medical Leave Policy | ✅ PASS |
| *"When is payday?"* | **0.907** (90.7%) | **Answer** (Escalate: False) | `PAY-01`: Monthly Payday Schedule | ✅ PASS |
| *"How does vesting work?"* | **1.000** (100%) | **Answer** (Escalate: False) | `PAY-06`: Equity & Stock Options Vesting | ✅ PASS |
| *"My laptop screen is flickering constantly..."* | **0.150** (Low) | **Escalate to Ticket: True** | *(Flagged for IT Support Ticket)* | ✅ PASS |
| *"How do I reserve a parking spot in basement?"* | **0.150** (Low) | **Escalate to Ticket: True** | *(Flagged for Facilities Ticket)* | ✅ PASS |
| *"Can I take a 9-month unpaid sabbatical?"* | **0.150** (Low) | **Escalate to Ticket: True** | *(Flagged for HR BP Ticket)* | ✅ PASS |
| *"I need root access to production AWS database"* | **0.150** (Low) | **Escalate to Ticket: True** | *(Flagged for DevSecOps Ticket)* | ✅ PASS |

- **Deliverables & Files Created**:
  - `src/__init__.py`: Package initialization file marking `src` as a root Python package for modular, absolute imports.
  - `src/rag/__init__.py`: Package initialization file exposing `KnowledgeBaseIndexer`, `HybridRetriever`, and `RetrievalResult` for clean import syntax (`from src.rag import HybridRetriever`).
  - `src/rag/indexer.py`: Chunking and indexing logic for ChromaDB & BM25.
  - `src/rag/hybrid_retriever.py`: Hybrid search, RRF fusion, confidence gating, and escalation detection.
  - `data/chroma_db/`: Persistent vector store database containing all 100 indexed chunks.
  - `.gitignore`: Configured to exclude virtual environments (`.venv/`), environment variables/secrets (`.env`), machine-specific vector store binaries (`data/chroma_db/`), and OS caches.

- **Commands Executed in Step 2**:
  ```bash
  # 1. Execute indexing pipeline
  .venv/bin/python src/rag/indexer.py

  # 2. Run retrieval & confidence benchmark
  .venv/bin/python -c "
  import sys; sys.path.append('.')
  from src.rag.hybrid_retriever import HybridRetriever
  retriever = HybridRetriever()
  res = retriever.retrieve('How do I reset my password?')
  print(res.suggested_action, res.confidence)
  "
  ```

---

## 3. Architecture & Design Decisions Log

| Decision ID | Area | Choice | Rationale & Architectural Impact |
| :--- | :--- | :--- | :--- |
| **AD-01** | Knowledge Base Architecture | JSON Source-of-Truth + Markdown Compiler Script | We established `data/knowledge_base/kb_entries.json` and `deliberate_gaps.json` as the sole canonical source of truth. The Python script (`generate_kb.py`) reads directly from these JSON files to generate the Markdown files, and `indexer.py` reads from them to build vector/BM25 indexes. This completely eliminates data duplication and keeps code strictly separated from data. |
| **AD-02** | Escalation Mechanism | Confidence threshold gate + Explicit deliberate gap mapping | Ensures zero hallucination on unknown questions and deterministic escalation to support tickets. |
| **AD-03** | Retrieval Engine | Dense (ChromaDB) + Sparse (BM25) Hybrid Search | Hybrid search addresses exact keyword lookup (product names, error codes) while dense search handles semantic intent. Provides production-ready hybrid retrieval. |
| **AD-04** | Ticketing Integration | GitHub Issues API + Local SQLite Fallback | Real-world API integration that requires no paid enterprise licenses. SQLite fallback prevents failures if offline or running in mock mode. |
| **AD-05** | Human-in-the-Loop | Explicit pre-submission confirmation gate | Mandatory requirement under Section 2.2.2; agent reviews ticket summary with employee before calling write API. |
| **AD-06** | Python Packaging Strategy | Explicit `__init__.py` files at package roots | Added `src/__init__.py` and `src/rag/__init__.py` to designate directories as formal Python packages, allowing clean absolute imports throughout the application and test suites. |

---

## 4. Current Status & Next Steps

- [x] **Step 1: Knowledge Base & Escalation Gaps Curation** (Complete)
- [x] **Step 2: Build Hybrid RAG Pipeline (ChromaDB + BM25 + RRF Re-ranker)** (Complete)
- [ ] **Step 3: Implement Ticketing Service Adapter (GitHub Issues + SQLite Fallback)** *(Next)*
- [ ] **Step 4: Build Google ADK Multi-Tool Agent (GPT-4o via LiteLLM)**
- [ ] **Step 5: Develop Streamlit Multi-Tab Application**
- [ ] **Step 6: Add Pytest Suite & RAG Evaluation**
- [ ] **Step 7: Finalize Documentation, Architecture Diagrams & Deployment Setup**

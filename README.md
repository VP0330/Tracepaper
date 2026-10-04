# Tracepaper: Agentic SOX Control Testing with Enforced Provenance

## Problem

Internal audit teams manually test controls: pull a sample from a population, chase down evidence for each item, check attributes, document conclusions in a workpaper, and flag exceptions. Every conclusion must be traceable to a specific page of a specific document, and a reviewer has to be able to verify it.

**Tracepaper** automates this while making unsupported claims structurally impossible.

## Core Thesis

Every assertion the system makes must carry a citation that resolves to:
- `document_id`
- `page` number
- `bounding_box` (normalized 0–1)
- `quoted_span` (text excerpt)

That citation must be mechanically validated against extracted source text before the finding is allowed to leave the pipeline. A finding whose citation does not resolve is rejected and retried, not surfaced. The system prefers `disposition="insufficient_evidence"` over a plausible guess.

## Stack

- **Backend**: Python 3.11, FastAPI, Pydantic v2, uv for dependency management
- **LLM**: Provider-abstracted client (Ollama or Anthropic) via `LLMClient` protocol
  - Default: `qwen2.5:7b-instruct` (set `LLM_MODEL` to use a larger model if you have the memory; the 14B model can be killed by the OOM killer on CPU-only machines)
  - PostgreSQL response cache keyed by provider/model, prompt, and schema
- **Embeddings**: Local via sentence-transformers (all-MiniLM-L6-v2)
- **OCR**: pdfplumber/PyMuPDF for text layer; Tesseract fallback for scanned pages
- **Retrieval**: PostgreSQL full-text search + sentence-transformers dense + Reciprocal Rank Fusion
- **Storage**: PostgreSQL via SQLAlchemy; binary uploads, identities, rules, findings, and chunks are persisted there
- **Frontend**: React + Vite + TypeScript, Tailwind (Phase 5)
- **Tests**: pytest; CI: GitHub Actions
- **Local Dev**: Makefile + docker-compose

## Hardware Requirements

**Minimum**: ≥12GB VRAM or unified memory if running Ollama locally.

If you have <12GB, use the Anthropic provider (`LLM_PROVIDER=anthropic`) and set `LLM_API_KEY`.

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Ollama) OR Ollama installed locally
- uv (Python package manager)

### 1. Clone and Install

```bash
git clone https://github.com/VP0330/Tracepaper.git
cd Tracepaper
make dev
```

For a local development setup, start PostgreSQL and Ollama:

```powershell
docker compose up -d postgres ollama
```

The default PostgreSQL URL is `postgresql+psycopg://tracepaper:tracepaper@localhost:5432/tracepaper`. Override it with `DATABASE_URL` in `.env` if needed. Copy `.env.example` to `.env` before customizing settings.

Start PostgreSQL and Ollama before running the app. Local PostgreSQL defaults to:

```text
postgresql+psycopg://tracepaper:tracepaper@localhost:5432/tracepaper
```

For local development, the Compose services can be started with:

```powershell
docker compose up -d postgres ollama
```

Set `DATABASE_URL` in `.env` if your PostgreSQL connection differs. Auth records, uploaded file bytes, extracted chunks, audit rules, and review flags are persisted in PostgreSQL.

This will:
- Install dependencies with uv
- Check Ollama connectivity
- Print setup status

### 2. Pull Models

```bash
make models
```

Downloads the models listed in `scripts/pull_models.py` to Ollama.

### 3. Run Tests

```bash
make test
```

Runs pytest with coverage reporting.

### 4. Linting & Type Checking

```bash
make lint
```

Runs ruff and mypy.

## Project Phases

- **Phase 0 (Scaffold)** ✓ Repo structure, config, LLMClient protocol, CI, Makefile
- **Phase 1** Synthetic evidence corpus for three controls (40 items each)
- **Phase 2** Ingestion with provenance: text extraction, OCR, `resolve_citation()` function
- **Phase 3** Retrieval: hybrid BM25 + dense + RRF
- **Phase 4** Agent loop: tools, control definitions (YAML), enforcement pipeline
- **Phase 5** Reviewer UI: FastAPI + React, split-pane workpaper view
- **Phase 6** Eval harness: metrics, ablations, hand-labeled citation precision
- **Phase 7** Ship: docs, Dockerfile, seeded demo, 90-second live script

## Current Phase Status

- **Phase 5** Reviewer API and React/Vite reviewer workspace are available.
- **Phase 6** Deterministic evaluation harness and result comparison are available.
- **Phase 7** Seeded local demo is available with `make demo`.
- PostgreSQL is the application database; SQLite is retained only for isolated tests.
- Uploaded files are stored as PostgreSQL binary data; their extracted chunks and audit metadata are stored in the same database.

### Start the application

Provision the first administrator (once, with PostgreSQL running):

```powershell
python -m tracepaper.auth_admin
```

Start the API from the repository root:

```powershell
$env:PYTHONPATH = "$PWD/src"
uvicorn tracepaper.api:app --reload
```

In a second terminal, start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, sign in as the bootstrapped administrator, and use Team to issue reviewer invitations. Upload PDF, CSV, or EML evidence; Ollama classifies/extracts it, then enabled rules create discrepancy flags for review.

### Document classification (database-driven)

Classification is configured entirely in PostgreSQL, not in code. Edits take effect on the next upload with no restart.

| Table | Purpose |
| --- | --- |
| `classification_types` | `category` (`document` or `control`), `value`, `label`, `description`, `sort_order`, `enabled`. Only enabled rows are offered to the model and the UI. |
| `prompt_templates` | `document_understanding` (page classification; supports `{document_types}` and `{control_types}`) and `document_extraction` (field extraction; supports `{document_type}` and `{document_type_description}`). |
| `document_segments` | Created automatically. One row per detected section: page range, type, control, confidence, summary, extracted fields. |

Uploads are processed in two passes:

1. **Classify** every page on its own (type, control, confidence, summary).
2. **Split and extract**: consecutive pages with the same type form a section, and fields are extracted once per section from that section's text. Sections classified `other` skip extraction.

The document-level type is the longest section that is not `other`. The UI shows each section as an expandable item with its summary and extracted fields. A 12-page PDF makes roughly 12 classification calls plus one extraction call per section, so expect it to be slow on CPU. If a prompt row is missing or no types are enabled, the upload fails with a clear error and there is no code fallback. The rules form reads its options from `GET /api/v1/classification-types`.
### Run the seeded workflow

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m tracepaper.corpus.cli --full --seed 42
python run_phase2a.py
python run_phase2b.py
python run_phase3.py
python -m tracepaper.eval.harness
python -m tracepaper.eval.compare
```

Start the reviewer API with `uvicorn tracepaper.api:app --reload`, then run the frontend from `frontend/` with `npm install; npm run dev`.

Each phase gates before the next to catch design issues early.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Workpaper Reviewer UI                   │
│                    (React + FastAPI)                        │
└─────────────────────────────────────────────────────────────┘
                            ↑
                            │
┌─────────────────────────────────────────────────────────────┐
│               Agent Loop (Tool-Use)                         │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Tool Calls:                                        │    │
│  │  - search_evidence() ──→ Retrieval Module           │    │
│  │  - fetch_page()                                     │    │
│  │  - extract_fields()                                 │    │
│  │  - compare_dates/amounts (Python)                   │    │
│  │  - record_finding()                                 │    │
│  │  - flag_insufficient_evidence()                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                    ↓                                        │
│  Enforcement Pipeline:                                      │
│  1. Schema validation (retry-repair if needed)              │
│  2. Citation resolution (resolve_citation checks)           │
│  3. Deterministic recomputation                             │
└─────────────────────────────────────────────────────────────┘
          ↑                          ↑
          │                          │
    ┌─────────────────┐    ┌──────────────────┐
    │  LLM Client     │    │ Retrieval        │
    │ (Ollama/Claude) │    │ (BM25 + Dense)   │
    │                 │    │ PostgreSQL FTS   │
    │ PostgreSQL Cache│    │ Sentence-XF      │
    └─────────────────┘    └──────────────────┘
                               ↑
                               │
                    ┌──────────────────────┐
                    │ Evidence Ingestion   │
                    │ - Text Layer         │
                    │ - OCR Fallback       │
                    │ - Citation Validator │
                    │ (resolve_citation)   │
                    └──────────────────────┘
                               ↑
                               │
                    ┌──────────────────────┐
                    │ Document Corpus      │
                    │ (PostgreSQL + BLOBs) │
                    └──────────────────────┘
```

## Configuration

Settings are loaded from environment variables or `.env`:

```bash
# LLM
LLM_PROVIDER=ollama              # or "anthropic"
LLM_MODEL=qwen2.5:7b-instruct    # larger models need more memory
OLLAMA_HOST=http://localhost:11435   # docker-compose maps Ollama to host port 11435
ANTHROPIC_API_KEY=sk-...         # if using Anthropic

# Embeddings
EMBEDDINGS_MODEL=all-MiniLM-L6-v2

# Storage
DATABASE_URL=postgresql+psycopg://tracepaper:tracepaper@localhost:5432/tracepaper
CACHE_DIR=.cache

# Logging
LOG_LEVEL=info
CACHE_ENABLED=true               # Disable for testing
```

## Development Workflow

1. Write code in `src/tracepaper/`
2. Write tests in `tests/` (pytest)
3. Run `make test` to verify
4. Run `make lint` to check style
5. Commit with a clear message

All changes go through GitHub Actions CI (lint + test) before merging.

## LLMClient Protocol

The agent code imports only from `tracepaper.llm.client`, not from `ollama` or `anthropic`. This keeps the agent provider-agnostic:

```python
from tracepaper.llm.client import LLMClient, ChatResponse

# Select implementation at runtime
from tracepaper.config import get_settings

settings = get_settings()
if settings.llm_provider == "ollama":
    from tracepaper.llm.ollama import OllamaClient
    client = OllamaClient(host=settings.ollama_host, model=settings.llm_model)
else:
    from tracepaper.llm.anthropic import AnthropicClient
    client = AnthropicClient(api_key=settings.anthropic_api_key, model=settings.llm_model)

# Same interface for both
response = client.chat(messages, tools=tools, json_schema=schema)
```

## Testing

Run all tests:

```bash
make test
```

Run a specific test file:

```bash
pytest tests/test_config.py -v
```

Run with coverage report:

```bash
pytest tests/ --cov=src/tracepaper --cov-report=html
```

## Docker & Compose

Start all services (Ollama + API):

```bash
docker-compose up -d
```

Check logs:

```bash
docker-compose logs -f tracepaper-api
docker-compose logs -f ollama
```

Stop services:

```bash
docker-compose down
```

## Contributing

- Keep commits small and descriptive
- Run `make lint` and `make test` before pushing
- Each phase gates at a specific checkpoint before moving to the next

## License

MIT

---

**Phase 0 Status**: ✓ Complete. Ready for Phase 1 (synthetic corpus generation).

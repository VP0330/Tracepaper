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
  - Default: `qwen2.5:14b-instruct` (or 7b-instruct if ≤12GB VRAM)
  - Disk cache on LLM calls (keyed on provider + model + prompt hash + tool schema hash)
- **Embeddings**: Local via sentence-transformers (all-MiniLM-L6-v2)
- **OCR**: pdfplumber/PyMuPDF for text layer; Tesseract fallback for scanned pages
- **Retrieval**: SQLite FTS5 for BM25 + sentence-transformers dense + Reciprocal Rank Fusion
- **Storage**: SQLite via SQLAlchemy
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

This will:
- Install dependencies with uv
- Check Ollama connectivity
- Print setup status

### 2. Pull Models

```bash
make models
```

Downloads `qwen2.5:14b-instruct` and `qwen2.5:7b-instruct` to Ollama.

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
    │ (Ollama/Claude)│    │ (BM25 + Dense)   │
    │                │    │ SQLite FTS5      │
    │  Disk Cache    │    │ Sentence-XF      │
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
                    │ (SQLite + PDF Store) │
                    └──────────────────────┘
```

## Configuration

Settings are loaded from environment variables or `.env`:

```bash
# LLM
LLM_PROVIDER=ollama              # or "anthropic"
LLM_MODEL=qwen2.5:14b-instruct   # or 7b-instruct
OLLAMA_HOST=http://localhost:11434
ANTHROPIC_API_KEY=sk-...         # if using Anthropic

# Embeddings
EMBEDDINGS_MODEL=all-MiniLM-L6-v2

# Storage
DB_PATH=tracepaper.db
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

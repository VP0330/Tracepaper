.PHONY: help dev test lint models seed eval eval-compare demo clean

help:
	@echo "Tracepaper - Agentic SOX control testing"
	@echo ""
	@echo "Available targets:"
	@echo "  make dev              Install dependencies and start dev environment"
	@echo "  make test             Run pytest with coverage"
	@echo "  make lint             Run ruff and mypy"
	@echo "  make models           Pull required Ollama models"
	@echo "  make seed             Generate synthetic test corpus (Phase 1)"
	@echo "  make eval             Run evaluation harness (Phase 6)"
	@echo "  make eval-compare     Compare eval results across runs"
	@echo "  make demo             Run the seeded local demo"
	@echo "  make clean            Remove cache and build artifacts"

dev: install-deps check-ollama
	@echo "✓ Development environment ready"
	@echo "  Start Ollama service: docker-compose up ollama"
	@echo "  Run tests: make test"
	@echo "  Start API: uvicorn tracepaper.api:app --reload"

install-deps:
	@echo "Installing dependencies with uv..."
	uv pip install -e .
	uv pip install -e ".[dev]"

check-ollama:
	@echo "Checking Ollama connectivity..."
	@python scripts/check_ollama.py || (echo "ERROR: Ollama not reachable at http://localhost:11434"; exit 1)

models: check-ollama
	@echo "Pulling Ollama models..."
	@python scripts/pull_models.py

test:
	@echo "Running tests..."
	pytest tests/ -v --cov=src/tracepaper --cov-report=term-missing

lint:
	@echo "Running linters..."
	ruff check src/ tests/
	mypy src/tracepaper

seed:
	@echo "Generating synthetic corpus (Phase 1)..."
	@python -m tracepaper.corpus.generator

eval:
	@echo "Running evaluation harness (Phase 6)..."
	@python -m tracepaper.eval.harness

eval-compare:
	@echo "Comparing eval results..."
	@python -m tracepaper.eval.compare

demo:
	@echo "Running seeded Tracepaper demo..."
	@python demo/seed_demo.py

clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage .mypy_cache build dist *.egg-info
	rm -rf .cache/

install-pre-commit:
	@echo "Installing pre-commit hooks..."
	pre-commit install

docker-build:
	@echo "Building Docker image..."
	docker-compose build

docker-up:
	@echo "Starting services..."
	docker-compose up -d

docker-down:
	@echo "Stopping services..."
	docker-compose down

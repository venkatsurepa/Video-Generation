.PHONY: dev lint format typecheck test test-all test-coverage ci \
       docker-dev docker-build seed validate-dag clean install install-hooks

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

dev:
	cd backend && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

install:
	cd backend && pip install -e ".[dev]"
	cd video && npm ci

install-hooks:
	pre-commit install

# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

lint:
	cd backend && ruff check src/ tests/

format:
	cd backend && ruff check --fix src/ tests/ && ruff format src/ tests/

typecheck:
	cd backend && mypy src/ --ignore-missing-imports --no-strict-optional

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test:
	cd backend && pytest tests/ -v -m "not integration" --tb=short

test-all:
	cd backend && pytest tests/ -v --tb=short

test-coverage:
	cd backend && pytest tests/ -v --cov=src --cov-report=html --cov-report=term -m "not integration"

# ---------------------------------------------------------------------------
# CI (runs all checks in sequence)
# ---------------------------------------------------------------------------

ci: lint typecheck test
	@echo "All CI checks passed"

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

docker-dev:
	docker compose up --build

docker-build:
	docker build -f backend/Dockerfile -t crimemill:latest .

# ---------------------------------------------------------------------------
# Database & Validation
# ---------------------------------------------------------------------------

seed:
	cd backend && python scripts/seed_dev_data.py

validate-dag:
	cd backend && python scripts/validate_dag.py

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/htmlcov backend/coverage.xml
	rm -rf video/node_modules video/dist

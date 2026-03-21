.PHONY: dev lint test format docker-build docker-run install install-dev

install:
	cd backend && pip install .

install-dev:
	cd backend && pip install -e ".[dev]"

dev:
	bash scripts/dev.sh

lint:
	bash scripts/lint.sh

test:
	bash scripts/test.sh

format:
	cd backend && ruff check --fix src/ tests/ && ruff format src/ tests/

docker-build:
	docker build -t crimemill-api backend/

docker-run:
	docker run --env-file .env -p 8000:8000 crimemill-api

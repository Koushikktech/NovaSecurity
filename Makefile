.PHONY: setup dev doctor test lint build demo eval smoke clean

PYTHON ?= python3
VENV ?= ../.venv
VENV_BIN ?= $(VENV)/bin


setup:
	@echo "Setting up Python virtual environment..."
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install uv==0.12.2
	UV_PROJECT_ENVIRONMENT="$(abspath $(VENV))" $(VENV_BIN)/uv sync --locked --no-install-project --inexact --project backend
	@echo "Setting up frontend packages..."
	cd frontend && npm ci
	@echo "Setup complete."

dev:
	PYTHONPATH=backend $(VENV_BIN)/python backend/main.py

doctor:
	PYTHONPATH=backend $(VENV_BIN)/python backend/cli.py doctor

test:
	PYTHONPATH="backend:fixtures/demo-api" $(VENV_BIN)/pytest -v backend/tests

lint:
	$(VENV_BIN)/ruff check backend/schemas backend/ingestion backend/analysis backend/review backend/verification backend/remediation backend/routes backend/persistence backend/providers backend/api.py backend/github_connection.py backend/storage.py backend/runtime_budget.py backend/config.py backend/cli.py backend/tests

build:
	cd frontend && npm run build

demo:
	PYTHONPATH=backend $(VENV_BIN)/python backend/cli.py review --repo fixtures/demo-api

eval:
	PYTHONPATH=backend $(VENV_BIN)/python evals/pipeline.py

smoke: doctor test eval
	@echo "Smoke tests passed successfully."

clean:
	rm -rf backend/data/workspaces/*
	rm -rf .pytest_cache backend/__pycache__

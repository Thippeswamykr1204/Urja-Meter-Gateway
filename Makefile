PYTHON ?= .venv/bin/python3
RUFF ?= .venv/bin/ruff
MYPY ?= .venv/bin/mypy

.PHONY: install api web test lint typecheck export-openapi smoke

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt
	cd apps/web && npm install

api:
	$(PYTHON) -m uvicorn app.main:app --app-dir apps/api --reload

web:
	cd apps/web && npm run dev

test:
	$(PYTHON) -m pytest -q

lint:
	$(RUFF) check .
	cd apps/web && npm run lint

typecheck:
	$(MYPY) .
	cd apps/web && npm run build

export-openapi:
	$(PYTHON) tools/export_openapi/main.py

smoke:
	cd apps/web && npm run smoke

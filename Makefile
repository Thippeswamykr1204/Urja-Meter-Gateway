PYTHON ?= .venv/bin/python3
RUFF ?= .venv/bin/ruff
MYPY ?= .venv/bin/mypy
UV ?= uv

.PHONY: install api web test test-repeat lint typecheck export-openapi check-openapi smoke verify

install:
	python3 -m venv .venv
	if command -v $(UV) >/dev/null 2>&1; then \
		$(UV) pip install --python $(PYTHON) -r requirements.lock; \
	else \
		$(PYTHON) -m pip install -r requirements.lock; \
	fi
	cd apps/web && npm install
	cd apps/web && npx playwright install chromium

api:
	$(PYTHON) -m uvicorn app.main:app --app-dir apps/api --reload

web:
	cd apps/web && npm run dev

test:
	$(PYTHON) -m pytest -q
	cd apps/web && npm run test

test-repeat:
	cd apps/web && npm run test:repeat

lint:
	$(RUFF) check .
	cd apps/web && npm run lint

typecheck:
	$(MYPY) .
	cd apps/web && npm run build

export-openapi:
	$(PYTHON) tools/export_openapi/main.py

check-openapi:
	$(PYTHON) tools/export_openapi/main.py --check

smoke:
	cd apps/web && npm run smoke

verify:
	$(PYTHON) tools/verify.py

# Verification record

Generated on **2026-10-27** by `make verify`.

Python tests passed: **75**.
Overall Python coverage: **86%**.
Vitest tests passed: **11**.
Repeated Vitest runs passed: **5/5**.
Playwright tests passed: **8**.

## Checks

| Command | Result |
|---|---|
| `ruff check .` | pass |
| `mypy .` | pass |
| `python -m coverage erase` | pass |
| `python -m coverage run -m pytest -q -rA` | pass |
| `python -m coverage report --fail-under=85` | pass |
| `python -m coverage json -o .coverage.json` | pass |
| `python tools/check_coverage.py .coverage.json` | pass |
| `uv pip compile requirements.txt --python-version 3.11 --universal --output-file flock-requirements.lock --custom-compile-command 'uv pip compile requirements.txt --python-version 3.11 --universal --output-file requirements.lock'` | pass |
| `diff -u requirements.lock flock-requirements.lock` | pass |
| `python tools/export_openapi/main.py --check` | pass |
| `npm run test` | pass |
| `npm run test:repeat` | pass |
| `npm run check:generated-types` | pass |
| `npm run lint` | pass |
| `npm run build` | pass |
| `npm run smoke` | pass |

## Live portal status

The live portal was not tested. Portal-specific routes, fields, session markers, units, timestamps, pagination, and request limits remain `UNVERIFIED` until captured and redacted.

## Frontend chunk note

The map route now loads MapLibre in a separate route chunk. The current build reports the route shell and MapLibre dependency separately; MapLibre remains the largest browser dependency.

## Known limitations

- Browser smoke requires the local API and frontend development server.
- The product remains single-instance by design, using SQLite and in-process coordination.
- Live portal protocol behavior remains `UNVERIFIED`.

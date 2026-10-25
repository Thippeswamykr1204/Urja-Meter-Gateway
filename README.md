# Flock Energy / Urja Meter Ops API

This repository contains a read-only FastAPI service, a local SQLite index, and a React operations console for the Urja Meter Ops take-home. It exposes a stable JSON contract without requiring downstream users to navigate the legacy portal.

The live network evidence block was not present in the supplied workspace. Demo mode is therefore the truthful default. The live adapter refuses to guess portal paths, session markers, units, or date semantics; those values are configured only after they are observed and recorded in `PROTOCOL.md`.

## Product surface

- `/api/v1/meters`: server-side search, filters, pagination, bounding box, radius, and sorting.
- `/api/v1/meters/{id}`: canonical meter details with provenance and quality flags.
- `/api/v1/meters/{id}/consumption`: indexed readings with hour/day/month aggregation and summaries.
- `/api/v1/hierarchy`: reconstructed hierarchy with rollups, orphan nodes, cycles, and duplicate records preserved.
- `/api/v1/overview`, `/api/v1/quality`, `/api/v1/insights/signals`, `/api/v1/sync/status`.
- `/health` liveness and `/ready` dependency readiness.
- `/docs` and committed `openapi.json`.

The console includes the overview, meter explorer, meter detail chart, clustered spatial view, hierarchy tree, quality report, command palette, light/dark theme, keyboard focus states, stale/error/empty/loading states, and reduced-motion behavior.

## Structure

```text
apps/api/app/{adapter,parsers,domain,store,services,api/v1,core}/
apps/api/tests/{unit,adapter,contract}/
apps/web/src/{app,components,features,lib}/
apps/web/tests/
apps/api/migrations/  fixtures/  tools/  docs/
README.md  PROTOCOL.md  REFLECTION.md  openapi.json  .env.example
```

The adapter knows HTTP and portal payloads. Parsers are pure. The catalog service owns freshness, indexing, aggregation, and signals. The API owns authentication and the public contract. The browser calls only same-origin API paths.

## Fresh clone setup

Requirements: Python 3.11+ and Node.js 18+.

```bash
git clone <repository-url>
cd FlockEnergy
make install
cp .env.example .env
```

Run the API:

```bash
source .venv/bin/activate
make api
```

Run the console in another terminal:

```bash
make web
```

Open `http://127.0.0.1:5173`. The API is at `http://127.0.0.1:8000`; interactive documentation is at `/docs`.

The Vite development proxy adds the server-side API key. `API_READ_KEY`, `API_ADMIN_KEY`, and `API_PROXY_TARGET` are read by Vite from the process environment or `.env`; they are not placed in browser JavaScript. In a production deployment, put the console and API behind the same origin and have the reverse proxy inject the read key for public API requests and the admin key for refresh controls.

## Configuration

`.env.example` lists every setting. The important local values are:

```dotenv
APP_ENV=local
DEMO_MODE=true
API_READ_KEY=local-development-read-key
API_ADMIN_KEY=local-development-admin-key
DATABASE_URL=sqlite:///./flock_energy.db
```

Production refuses the local development keys and requires distinct read and admin keys. Portal credentials are environment-only. The integration is read-only.

To enable live mode, first capture and redact the real browser exchange. Then configure the observed paths and affirmative login signal:

```dotenv
DEMO_MODE=false
PORTAL_USERNAME=...
PORTAL_PASSWORD=...
PORTAL_LOGIN_PATH=...
PORTAL_METER_LIST_PATH=...
PORTAL_METER_DETAIL_PATH=...
PORTAL_CONSUMPTION_PATH=...
PORTAL_HIERARCHY_PATH=...
PORTAL_SESSION_COOKIE_NAME=...
PORTAL_LOGIN_PAGE_MARKERS=...
```

The adapter will not accept a successful login unless a configured session cookie or post-login marker is present. It never uses an arbitrary URL word or a generic username/password page as an expiry signal.

## Example requests

List meters:

```bash
curl -H 'X-API-Key: local-development-read-key' \
  'http://127.0.0.1:8000/api/v1/meters?page=1&page_size=25&sort=name&order=asc'
```

The demo response has this shape; runtime timestamps are generated when the local index is written:

```json
{
  "data": [
    {
      "id": "MTR-1001",
      "serial_number": "URJA-1001",
      "name": "North feeder / A-01",
      "status": "active",
      "quality": {"flags": [], "issue_count": 0, "notes": []},
      "provenance": {"source": "demo", "stale": false, "age_seconds": 0}
    }
  ],
  "provenance": {"source": "index", "stale": false, "age_seconds": 0},
  "meta": {"page": 1, "page_size": 25, "total": 3, "has_next": false}
}
```

Read consumption with a documented aggregation level:

```bash
curl -H 'X-API-Key: local-development-read-key' \
  'http://127.0.0.1:8000/api/v1/meters/MTR-1001/consumption?granularity=day'
```

Refresh requires the admin key:

```bash
curl -X POST -H 'X-API-Key: local-development-admin-key' \
  'http://127.0.0.1:8000/api/v1/refresh'
```

## Data and quality rules

Missing values remain `null`; they never become zero. Original timestamps and values are retained when normalization occurs. Naive timestamps use the configured portal timezone and receive an `assumed_timezone` flag. Locale ambiguity, unknown units, invalid values, duplicate IDs/readings, out-of-order readings, negative values, orphan nodes, and cycles are visible in quality summaries.

Hour, day, and month aggregation sums valid values in each bucket, reports the bucket count and missing count, and keeps the first observed unit only when the bucket is unit-consistent. The API does not silently convert undocumented units.

## Storage, sync, and scale

SQLite uses WAL, a migration table, FTS5, meter metadata, readings keyed by `(meter_id, timestamp)`, hierarchy records, and sync run history. SQLite is appropriate for a local catalog and modest write volume. In-process aggregation and one-process rate limiting are the limits: very large reading histories, many concurrent writers, or multiple API instances require Postgres/PostGIS, incremental cursors, a durable job queue, and a shared rate limiter.

Startup sync runs once. A configured `SYNC_INTERVAL_SECONDS` starts a single background sync task with jitter. Reads serve indexed data immediately and schedule a background refresh when its configured TTL is exceeded. If an index has no data, the service uses the adapter as a live fallback and stores the result.

## Tests and checks

```bash
make lint
make typecheck
make test
make export-openapi
cd apps/web && npm run smoke
```

CI also runs `coverage report`, checks that regenerated OpenAPI matches `openapi.json`, builds the console, and runs the browser smoke test.

The mock portal in `tools/mock_portal` replays sanitized fixtures and supports session expiry, login-page responses with status 200, 404, 429, 500, slow responses, and malformed responses. `tools/sanitize_fixtures/main.py` removes secret-key values and email-shaped values from JSON fixtures.

## Intentional omissions

- Exact live portal routes, selectors, cookies, and request parameters are not committed because the evidence block was empty.
- No bulk export is used because its existence was not observed.
- Closed historical periods have storage support but no immutable-period policy beyond the configured zero-TTL default; the real portal evidence should establish that policy.
- A distributed deployment layer is not included: the local product uses SQLite and bounded in-process rate limiting by design.

## Documentation

- [Protocol record](PROTOCOL.md)
- [Reflection](REFLECTION.md)
- [Architecture](docs/architecture.md)
- [Freshness rules](docs/freshness.md)
- [Platform path](docs/platform-path.md)
- [OpenAPI contract](openapi.json)

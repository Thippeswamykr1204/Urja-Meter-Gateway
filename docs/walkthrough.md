# Interview walkthrough

## What the service does

The service presents a stable read-only API and local operations console over a legacy meter portal. The browser never calls the portal directly. It calls the FastAPI contract, which reads a local SQLite index and refreshes through a narrow adapter interface when data is stale or absent.

## Login and expiry

The HTTP adapter owns the persistent `httpx` client and cookie jar. Portal paths, form field names, success markers, and expiry markers are configuration values. Empty values are rejected rather than guessed. When a read returns `401`, `403`, or a configured login-page marker, one coroutine performs login under a single-flight lock. Other callers reuse the resulting session. A failed recovery enters a cooldown so concurrent callers cannot create a login storm.

The adapter checks the retried response again. A response that still looks unauthenticated becomes a typed session-expiry error instead of being parsed as empty data.

## Data quirks and quality

No live portal quirks are claimed yet. The parser and domain models preserve original values, retain nulls, and attach quality flags when a timestamp, number, unit, duplicate, hierarchy relationship, or reading value cannot be interpreted safely. A future live protocol record must replace each `UNVERIFIED` entry with a captured fact.

## Why SQLite

SQLite keeps the take-home easy to clone and run, supports WAL and FTS5, and is sufficient for a local catalog with one coordinated writer. The service stores indexed meters, readings, hierarchy data, coverage, checkpoints, sync runs, dataset status, and conflict history. A successful empty read is distinct from a failed refresh, and a failed refresh leaves the last successful snapshot available but stale.

## Freshness rules

Each dataset records its source, fetch time, index time, stale state, partial state, and record counts. Reads use indexed data when it is fresh enough. A stale or missing dataset schedules a background refresh. Refresh writes are committed as one snapshot so readers do not observe a mixture of old and new datasets.

## Scale boundary

The first limits are SQLite write serialization, in-process aggregation, local FTS maintenance, and a single-process rate limiter. At 10 times the current dataset size, measured query and refresh timings should determine whether indexes and batch sizes are sufficient. At 100 times the size, the documented migration path is Postgres for transactional storage, PostGIS for spatial queries, incremental sync cursors, durable background work, and shared rate-limit state. Those components are not built here.

## Honest status

The local demo and API contract are tested. The live portal has not been tested because its request and response exchange has not been captured. The repository therefore does not claim live routes, selectors, units, pagination, expiry markers, bulk access, or rate limits.

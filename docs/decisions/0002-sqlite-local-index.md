# Decision: SQLite local index

## Decision

Use SQLite with WAL and FTS5 for the local index.

## Why

It needs no service process, fits the Mac development environment, supports indexed search, and leaves a clear Postgres/PostGIS migration path for larger data volumes.

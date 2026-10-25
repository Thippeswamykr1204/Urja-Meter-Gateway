# Decision: provenance on every response

## Decision

Return `source`, `fetched_at`, `stale`, and an optional portal timestamp in a common response envelope.

## Why

Consumers should be able to tell local index data from upstream data without inferring freshness from an HTTP status or a page title. The flag is explicit and survives cache or sync changes.

# Decision: provenance on every response

## Decision

Return `source`, `fetched_at`, `indexed_at`, `stale`, `partial`, `data_status`, `age_seconds`, and an optional portal timestamp in a common response envelope.

## Why

Consumers should be able to tell local index data from upstream data without inferring freshness from an HTTP status or a page title. The status distinguishes a successful empty fetch from an upstream failure, while the timestamps distinguish portal time, fetch time, and local indexing time. The fields are explicit and survive cache or sync changes.

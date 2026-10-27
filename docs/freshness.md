# Freshness rules

Every public data envelope includes `source`, `fetched_at`, `indexed_at`, `portal_timestamp` when observed, `stale`, `partial`, `data_status`, and `age_seconds`. `fetched_at` is when the adapter or fixture was obtained, `indexed_at` is when the local SQLite snapshot was written, `portal_timestamp` is an upstream timestamp only when the source provides one, and `age_seconds` is measured from `fetched_at` to the response time. The service uses configured TTLs and an index-first read policy.

| Data type | Setting | Behavior |
|---|---|---|
| Meter metadata | `METER_METADATA_TTL_SECONDS` | Serve the local index immediately; schedule a background refresh when stale |
| Hierarchy | `HIERARCHY_TTL_SECONDS` | Serve stored hierarchy immediately; schedule a background refresh when stale |
| Recent consumption | `RECENT_CONSUMPTION_TTL_SECONDS` | Serve indexed readings immediately; refresh in the background when stale |
| Closed history | `CLOSED_HISTORY_TTL_SECONDS` | Default `0`; no immutable historical policy is claimed without portal evidence |

Startup performs one sync. `SYNC_INTERVAL_SECONDS > 0` starts a single background task with jitter. A refresh is single-flight through the sync coordinator, requested background refreshes are held by strong task references, and each run is recorded in `sync_runs` with counts, duration, rejection count, checkpoint, and a safe error class when applicable.

If the index has no data for a requested meter, hierarchy, or reading set, the adapter is used as a live fallback. The response provenance identifies that fallback as `live` or `demo`; indexed responses identify `index`. `data_status=empty` means a successful fetch contained no records. `data_status=stale`, `partial`, or `unavailable` must not be interpreted as an empty dataset.

Consumption coverage is stored per meter and date range. A request fetches only uncovered ranges, and any uncovered overlap remains `partial` rather than being presented as complete. Failed refreshes never replace the last successful snapshot.

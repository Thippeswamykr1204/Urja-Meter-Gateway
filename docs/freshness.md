# Freshness rules

Every public data envelope includes `source`, `fetched_at`, `stale`, and `age_seconds`. The service uses configured TTLs and an index-first read policy.

| Data type | Setting | Behavior |
|---|---|---|
| Meter metadata | `METER_METADATA_TTL_SECONDS` | Serve the local index immediately; schedule a background refresh when stale |
| Hierarchy | `HIERARCHY_TTL_SECONDS` | Serve stored hierarchy immediately; schedule a background refresh when stale |
| Recent consumption | `RECENT_CONSUMPTION_TTL_SECONDS` | Serve indexed readings immediately; refresh in the background when stale |
| Closed history | `CLOSED_HISTORY_TTL_SECONDS` | Default `0`; no immutable historical policy is claimed without portal evidence |

Startup performs one sync. `SYNC_INTERVAL_SECONDS > 0` starts a single background task with jitter. A refresh is single-flight through the catalog service, and each run is recorded in `sync_runs` with counts and an error message when applicable.

If the index has no data for a requested meter, hierarchy, or reading set, the adapter is used as a live fallback. The response provenance identifies that fallback as `live` or `demo`; indexed responses identify `index`.

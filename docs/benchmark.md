# SQLite benchmark

The benchmark creates a temporary SQLite database for each dataset size. Each synthetic meter has one interval reading, a coordinate, and a shared synthetic hierarchy root.

## Measured results

| Size | Insert meters | Insert readings | List | Search | Radius | Aggregation | Hierarchy rollup |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 0.3003s | 0.1280s | 0.0042s | 0.0321s | 0.0504s | 0.0927s | 0.0096s |
| 100,000 | 5.7347s | 1.6724s | 0.0428s | 0.0387s | 0.5361s | 1.8396s | 0.1320s |

## Data-scale note

SQLite remains attractive for a local catalog because indexed list, search, radius, aggregation, and hierarchy operations are measurable in one process without infrastructure. The first strain points are serialized writes, FTS maintenance, in-process aggregation, and keeping a large reading set in Python for rollups.

At a larger production scale, the concrete migration path is Postgres for transactional storage, PostGIS for spatial filtering, incremental portal cursors instead of full refreshes, durable background work for checkpoints, and a shared rate limiter. Those components are documented rather than built here.

## Raw result data

```json
[
  {
    "meters": 10000,
    "readings": 10000,
    "insert_meters_seconds": 0.3003,
    "insert_readings_seconds": 0.128,
    "list_seconds": 0.0042,
    "list_rows": 50,
    "list_total": 10000,
    "search_seconds": 0.0321,
    "search_rows": 50,
    "search_total": 10000,
    "radius_seconds": 0.0504,
    "radius_rows": 50,
    "radius_total": 10000,
    "aggregation_seconds": 0.0927,
    "aggregation_buckets": 1,
    "hierarchy_seconds": 0.0096,
    "hierarchy_roots": 1
  },
  {
    "meters": 100000,
    "readings": 100000,
    "insert_meters_seconds": 5.7347,
    "insert_readings_seconds": 1.6724,
    "list_seconds": 0.0428,
    "list_rows": 50,
    "list_total": 100000,
    "search_seconds": 0.0387,
    "search_rows": 50,
    "search_total": 10000,
    "radius_seconds": 0.5361,
    "radius_rows": 50,
    "radius_total": 100000,
    "aggregation_seconds": 1.8396,
    "aggregation_buckets": 1,
    "hierarchy_seconds": 0.132,
    "hierarchy_roots": 1
  }
]
```

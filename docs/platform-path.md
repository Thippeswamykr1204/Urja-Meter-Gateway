# Platform path

The adapter interface is the seam for adding another utility system without coupling the API routes to a particular portal. A larger product could add a system registry, per-system credentials in a managed secret store, a durable job queue, incremental sync cursors, and Postgres/PostGIS for high-volume spatial and historical queries.

SQLite is right-sized for a local take-home catalog and is not intended for large concurrent writes or deep historical analytics. A migration would retain canonical models and replace the store with Postgres tables, PostGIS indexes, and a worker-backed sync process. Freshness policies should remain explicit per data type.

Commercial or operational use requires authorization from the Urja Meter Ops system owner and should follow that owner's security, rate-limit, privacy, and change-management requirements.

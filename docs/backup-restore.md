# SQLite backup and restore

The local catalog is a single SQLite file configured by `DATABASE_URL`. WAL mode is enabled by the store. Use SQLite's online backup API rather than copying only the main file while the service is running.

## Backup

Stop scheduled refreshes or stop the API, then run:

```bash
sqlite3 ./flock_energy.db "PRAGMA wal_checkpoint(FULL);"
sqlite3 ./flock_energy.db ".backup './backups/flock_energy-$(date +%Y%m%d-%H%M%S).db'"
```

The application also exposes the same SQLite online-backup primitive through `SQLiteStore.backup()` for an operational wrapper. Backups should be stored outside the repository and tested before they are needed.

## Restore

1. Stop the API.
2. Keep the failed database for investigation.
3. Replace the configured database with the selected backup.
4. Start the API and run `GET /ready` with the read key.
5. Verify `/api/v1/sync/status`, `/api/v1/meters`, and `/api/v1/quality`.

Example shell sequence:

```bash
mv ./flock_energy.db ./flock_energy.failed-$(date +%Y%m%d-%H%M%S).db
cp ./backups/flock_energy-20261025-120000.db ./flock_energy.db
make api
curl -H 'X-API-Key: local-development-read-key' http://127.0.0.1:8000/ready
```

The migration runner applies any newer SQL migrations on startup. Restore is intended for one local instance; it does not coordinate concurrent writers or multiple API processes.

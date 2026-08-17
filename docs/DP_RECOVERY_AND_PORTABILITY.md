# Recovery and settings portability

Worker commands added by DP-REC-001/002:

- `db-status` — SQLite quick-check as JSON;
- `db-backup` — copy database/WAL/SHM into a timestamped recovery directory;
- `db-recover` — no-op for a healthy database; for a damaged SQLite database, back it up before invoking the existing recovery path and report before/after state;
- `settings-export [path]` — versioned JSON containing only allowlisted non-secret settings;
- `settings-import <path>` — validate version, field allowlist, values/ranges and atomically update only allowed `.env` keys while preserving existing secrets.

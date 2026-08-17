# DP-OBS-001 — Unified operational status snapshot

**Status:** IMPLEMENTED, CI acceptance pending.

## Goal

Discount Parser now has one stable, secret-free operational snapshot instead of requiring support to mentally join `/system`, `/runs`, doctor output and database counters.

## Interfaces

Frozen/source worker:

```text
DiscountParserWorker.exe status-json
```

Local web panel after setup:

```text
GET /system/status.json
```

The support bundle also includes the same model as `diagnostics/operational-status.json`.

## State model

The top-level state is one of:

- `ok` — required doctor checks pass, setup is complete, and enabled sources are not stale/failed;
- `warning` — setup is incomplete, an optional doctor check fails, an enabled source is stale, or its latest run failed;
- `error` — at least one required doctor check fails.

Source freshness uses three configured collection intervals with a six-hour minimum. This avoids classifying one delayed collection cycle as stale while still surfacing installations that stopped collecting.

## Process visibility

The web endpoint can report bot/scheduler running state and PID because the web `ProcessManager` owns those child processes on the packaged desktop application.

The standalone `status-json` worker command does **not** pretend it can observe another process manager. It returns `observed=false`, `running=null`, `pid=null` when process state is not available from that execution context.

## Privacy boundary

The snapshot contains no `.env`, raw configuration secrets, Telegram credentials, proxy credentials, raw offers or publication message IDs. Source errors are passed through the normal secret redactor. Aggregate output uses an explicit field allowlist.

## Acceptance

DP-OBS-001 is complete when tests prove:

- deterministic `ok` / `warning` / `error` classification;
- stale and failed source reporting;
- required doctor failure -> `error`;
- secret values are absent from serialized snapshots;
- worker `status-json` emits valid JSON;
- `/system/status.json` returns JSON only after setup and returns a safe 409 warning before setup;
- support bundle includes the same operational snapshot;
- repository CI, delivery, installed acceptance and Windows reproducibility remain green.

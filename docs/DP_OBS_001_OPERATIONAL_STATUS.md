# DP-OBS-001 — Unified operational status snapshot

**Status:** COMPLETE — merged to canonical `main` on 2026-08-17.  
**Canonical merge:** `f15a8252b97be63bf98ac5333f0e7cdd0b757805`  
**Issue:** #18 — closed as completed.

## Goal

Discount Parser has one stable, secret-free operational snapshot instead of requiring support to mentally join `/system`, `/runs`, doctor output and database counters.

## Interfaces

Frozen/source worker:

```text
DiscountParserWorker.exe status-json
```

Local web panel after setup:

```text
GET /system/status.json
```

The support bundle includes the same model as `diagnostics/operational-status.json`.

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

## Reconciliation with current `main`

The first DP-OBS-001 branch was based on an earlier canonical commit and became conflicted after the Windows installer hardening work. Before reconciliation, its original head was preserved at:

```text
backup/dp-obs-001-pre-reconcile-20260817
```

The active feature branch was then rebuilt from current canonical `main` and only the seven DP-OBS-001 files/changes were reapplied. This avoided carrying stale-base formatting reversions or unrelated changes back into `main`.

The reconciled feature head was:

```text
af2881b2315301cc332ed0e9a582f6f99bcc7fba
```

It was exactly ahead of `main` with no behind commits before merge.

## Acceptance evidence

All required pull-request gates passed on the reconciled head:

- multi-platform repository CI — PASS;
- `build-delivery` — PASS;
- Windows reproducibility — PASS;
- Windows installed acceptance — PASS;
- the installed-acceptance run also retained the DP-WIN-P0.2 installer resilience gate — PASS.

The accepted behavior is covered by tests for:

- deterministic `ok` / `warning` / `error` classification;
- stale and failed source reporting;
- required doctor failure -> `error`;
- removal/redaction of secret values from serialized snapshots;
- worker `status-json` valid JSON output;
- `/system/status.json` normal response and safe pre-setup HTTP 409;
- support bundle inclusion of the same operational snapshot;
- continued compatibility with controlled Windows build/install/reproducibility gates.

PR #19 was merged to canonical `main` as:

```text
f15a8252b97be63bf98ac5333f0e7cdd0b757805
```

Issue #18 closed automatically through the PR completion link.

## Definition of done

All DP-OBS-001 criteria are satisfied. Any future additions to the status schema must preserve the secret-free boundary and must not add raw offer/publication identifiers or configuration credential values without a deliberate schema/privacy review.

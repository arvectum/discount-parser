# DP-DIAG-001 — Sanitized support bundle

**Status:** IMPLEMENTED, CI acceptance pending.

## Goal

When Discount Parser misbehaves, support should receive one archive with enough machine-readable evidence to diagnose the installation without asking the customer to send `.env`, the SQLite database, or arbitrary screenshots/files.

## Command

Installed/frozen Windows build:

```powershell
DiscountParserWorker.exe support-bundle
```

Optional explicit output path:

```powershell
DiscountParserWorker.exe support-bundle C:\Temp\discount-parser-support.zip
```

Source/dev environment:

```bash
python -m src.worker_entry support-bundle
```

Without an explicit path the archive is written below the mutable runtime root:

`support/discount-parser-support.zip`

## Included data

The archive is allowlist-based and contains only:

- `diagnostics/runtime.json` — OS/Python/frozen/runtime-path metadata;
- `diagnostics/configuration.json` — non-secret settings plus boolean “configured/not configured” flags for secret settings;
- `diagnostics/doctor.json` — existing doctor checks;
- `diagnostics/smoke-report.json` — aggregate operational counters when the DB can be read;
- `logs/app.log` and known rotated `app.log.N` files when present, limited to the newest 2 MiB per file and sanitized again during bundle creation;
- `manifest.json` — file sizes and SHA-256 values for every payload file.

## Explicit exclusions

The bundle never includes:

- `.env`;
- `discount_parser.db` or WAL/SHM files;
- raw database rows or offers;
- arbitrary files from the runtime directory;
- unknown log files.

## Redaction

The support-bundle layer performs defense-in-depth redaction even if an old log predates current logging filters. It removes or masks:

- Telegram bot tokens;
- Telegram channel/admin identifiers in credential-style fields;
- passwords/secrets/API keys/API hashes/sessions/access tokens;
- Authorization/Proxy-Authorization/Cookie/Set-Cookie/X-API-Key headers;
- credentials embedded in HTTP/S proxy URLs.

Configuration output contains only safe values and booleans indicating whether secret settings are configured. Secret values are never serialized.

## Failure behavior

The archive is written atomically through a temporary ZIP. If collection or archive validation fails, the incomplete temporary archive is deleted. The command does not silently fall back to copying the runtime directory.

Doctor/smoke failures themselves are recorded as sanitized diagnostic errors so a broken installation can still produce a useful support bundle.

## Operator procedure

1. Close nothing unless support specifically asks; the command is read-only with respect to application state.
2. Run `DiscountParserWorker.exe support-bundle` from the installed Discount Parser directory.
3. Send only the generated ZIP to support.
4. Do **not** send `.env` or `discount_parser.db` unless a separate, explicit support procedure requires it.

## Acceptance

DP-DIAG-001 is complete when CI proves:

- allowlist-only archive contents;
- `.env` and SQLite exclusion;
- redaction of representative Telegram/header/proxy/generic secrets;
- correct SHA-256/size manifest;
- command inclusion in the frozen worker entry point;
- repository regressions remain green.

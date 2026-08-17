# Discount Parser — operational hardening roadmap

**Canonical repository:** `arvectum/discount-parser`  
**Canonical branch:** `main`  
**Updated:** 2026-08-17  
**Execution priority:** ChatGPT + GitHub/GitHub Actions first. OpenCode/local Windows is used only when a gate genuinely cannot be executed in GitHub-hosted Windows or requires the customer's/owner's real environment.

The original MVP implementation roadmap remains in [`ROADMAP.md`](ROADMAP.md). This document is the current post-MVP operational/release hardening roadmap.

## Status legend

- ✅ COMPLETE — implementation and required repository/CI gate accepted.
- 🔴 P0 IN PROGRESS — current customer-blocking work.
- 🟡 IN PROGRESS — implementation exists but acceptance/merge is not complete.
- ⏳ QUEUED — not started in the current hardening pass.
- ⛔ EXTERNAL BLOCKER — cannot be completed from the repository until an external platform condition changes.

## P0 — canonical repository, release and Windows delivery safety

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 1 | **DP-REPO-001 — Canonical repository & release provenance audit** | ✅ COMPLETE | ChatGPT + GitHub |
| 2 | **DP-REPO-002 — Canonical history recovery & ref reconciliation** | ✅ COMPLETE | ChatGPT + GitHub |
| 3 | **DP-REL-001 — Reproducible/immutable release identity** | ✅ COMPLETE | ChatGPT + GitHub; one-time repository immutability setting completed by owner |
| 4 | **DP-CI-001 — Reproducible Windows installer build** | ✅ COMPLETE | ChatGPT + GitHub Actions / Windows runner |
| 5 | **DP-CI-002 — Windows installed acceptance in GitHub Actions** | ✅ COMPLETE | ChatGPT + GitHub Actions / Windows runner |
| 6 | **DP-CI-003 — Release gate** | ✅ COMPLETE | ChatGPT + GitHub Actions |
| 7 | **DP-WIN-P0.2 — Installer shortcut/rollback hardening** | ✅ COMPLETE | ChatGPT + GitHub Actions / Windows runner; physical customer re-test remains DP-WIN-001 |
| 8 | **DP-REPO-003 — GitVerse stale `main.lock` mirror unblock** | ⛔ EXTERNAL BLOCKER | GitVerse platform/operator, then ChatGPT + GitHub Actions rerun |

### DP-WIN-P0.2 — completed acceptance

Customer feedback #3 showed two linked Windows failures:

1. `IPersistFile::Save failed; code 0x80070005` while Setup created `Desktop\Discount Parser.lnk`;
2. subsequent `CreateProcess failed; code 2` for `%LOCALAPPDATA%\DiscountParser\DiscountParser.exe`.

The engineering hotfix was merged by PR #20 into canonical `main` as commit `4fa6eb03e4bcdd39e3a4db8e9c45378552c07541` after all pre-merge gates passed. The accepted contract now guarantees:

- Desktop shortcut creation is no longer a fatal `[Icons]` operation;
- Desktop shortcut is optional and created best-effort after payload installation;
- shell/COM/ACL shortcut-save failure is caught and logged without rolling back the installed payload;
- `DiscountParser.exe` existence is checked before link creation;
- Start Menu remains an installer-managed launch path independent of Desktop;
- product-owned Desktop shortcut is removed on uninstall;
- a Unicode/Cyrillic install path is exercised natively on a Windows runner;
- native CI proves clean install → in-place reinstall → uninstall → reinstall → uninstall;
- native CI deliberately forces the Desktop `CreateShellLink` failure boundary and proves Setup still returns success, installed payload remains present, and Start Menu still launches the installed executable;
- DP-CI-001 reproducibility, normal CI, build-delivery, DP-CI-002 installed-runtime acceptance, and DP-WIN-P0.2 resilience all passed on the merge candidate.

The DP-WIN-P0.2 machine-readable evidence reported `PASS` for both the Unicode lifecycle and blocked-Desktop-shortcut scenarios. Physical reproduction on the customer's actual Windows profile remains the later DP-WIN-001 acceptance gate and is not required to keep the deterministic repository fix merged.

## P1 — supportability, observability, security and recovery

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 9 | **DP-DIAG-001 — Sanitized support bundle** | ✅ COMPLETE | ChatGPT + GitHub |
| 10 | **DP-OBS-001 — Unified operational status / offer-pipeline visibility** | ✅ COMPLETE | ChatGPT + GitHub + GitHub Actions; merged by PR #19 |
| 11 | **DP-SEC-001 — Local web-panel mutation protection & secret-redaction hardening** | ⏳ QUEUED | ChatGPT + GitHub |
| 12 | **DP-REC-001 — Self-service recovery** | ⏳ QUEUED | ChatGPT + GitHub; Windows runner where install-state behavior is involved |
| 13 | **DP-REC-002 — Export/import settings** | ⏳ QUEUED | ChatGPT + GitHub |
| 14 | **DP-QA-001 — Parser regression corpus** | ⏳ QUEUED | ChatGPT + GitHub |
| 15 | **DP-QA-002 — Data-quality regression matrix** | ⏳ QUEUED | ChatGPT + GitHub |

### DP-OBS-001 — completed acceptance

PR #19 was reconciled onto canonical `main` after the DP-WIN-P0.2 changes. The original feature head was preserved at `backup/dp-obs-001-pre-reconcile-20260817`, then the feature branch was rebuilt from the current `main` so no stale-base conflict or unrelated rollback was carried forward.

Accepted behavior now includes:

- one machine-readable `ok` / `warning` / `error` operational state contract;
- doctor required/optional failure summaries;
- per-source freshness, latest-run counters and sanitized errors;
- allowlisted aggregate counters with no raw offers/publication IDs;
- process state only when genuinely observed by the desktop `ProcessManager`;
- `DiscountParserWorker.exe status-json`;
- local `GET /system/status.json` with safe pre-setup HTTP 409;
- reuse of the same model in `diagnostics/operational-status.json` inside the sanitized support bundle.

Acceptance on reconciled head `af2881b2315301cc332ed0e9a582f6f99bcc7fba`:

- normal multi-platform CI — PASS;
- `build-delivery` — PASS;
- Windows reproducibility — PASS;
- Windows installed acceptance, including DP-WIN-P0.2 resilience — PASS.

PR #19 was merged to canonical `main` as `f15a8252b97be63bf98ac5333f0e7cdd0b757805`; issue #18 closed automatically as completed.

## P2 — customer documentation

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 16 | **DP-DOC-001 — Customer manual** | ⏳ QUEUED | ChatGPT + GitHub |
| 17 | **DP-DOC-002 — Troubleshooting guide** | ⏳ QUEUED | ChatGPT + GitHub |

## Physical Windows gates — defer until GitHub work is exhausted

These gates intentionally require a real Windows machine, real customer-like filesystem/network state, or real Telegram credentials. They are not pulled forward while an equivalent GitHub Actions gate can answer the question.

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 18 | **DP-WIN-001 — Real installed Windows/customer acceptance** | ⏳ DEFERRED | Windows notebook + OpenCode / human operator |
| 19 | **DP-WIN-002 — Real Telegram E2E** | ⏳ DEFERRED | Windows notebook + OpenCode; real bot/channel |
| 20 | **DP-WIN-003 — Real source/network sweep** | ⏳ DEFERRED | Windows notebook + OpenCode; real network routes/sources |

When the roadmap reaches DP-WIN-001 and no earlier ChatGPT/GitHub task remains, stop autonomous repository work and issue a precise OpenCode specification for the physical Windows acceptance.

## Current next action

**DP-SEC-001 — harden local web-panel mutations and secret redaction, add deterministic regression coverage, run repository/Windows gates, and merge when green.**

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
| 7 | **DP-WIN-P0.2 — Installer shortcut/rollback hardening** | 🔴 P0 IN PROGRESS | ChatGPT + GitHub Actions / Windows runner; physical customer re-test is a later DP-WIN-001 gate |
| 8 | **DP-REPO-003 — GitVerse stale `main.lock` mirror unblock** | ⛔ EXTERNAL BLOCKER | GitVerse platform/operator, then ChatGPT + GitHub Actions rerun |

### DP-WIN-P0.2 — acceptance contract

Customer feedback #3 showed two linked Windows failures:

1. `IPersistFile::Save failed; code 0x80070005` while Setup created `Desktop\Discount Parser.lnk`;
2. subsequent `CreateProcess failed; code 2` for `%LOCALAPPDATA%\DiscountParser\DiscountParser.exe`.

The P0 fix is complete only when all repository/CI conditions below pass:

- Desktop shortcut creation is no longer a fatal `[Icons]` operation;
- Desktop shortcut is optional and created best-effort after payload installation;
- shell/COM/ACL shortcut-save failure is caught and logged without rolling back the installed payload;
- `DiscountParser.exe` existence is checked before link creation;
- Start Menu remains an installer-managed launch path independent of Desktop;
- product-owned Desktop shortcut is removed on uninstall;
- a Unicode/Cyrillic install path is exercised natively on a Windows runner;
- native CI proves clean install → in-place reinstall → uninstall → reinstall → uninstall;
- native CI deliberately forces `CreateShellLink` failure and proves Setup still returns success, installed payload remains present, and the Start Menu shortcut points to the installed executable;
- existing DP-CI-001 reproducibility and DP-CI-002 installed-runtime gates remain green.

Physical reproduction on the customer's actual Windows profile is deliberately **not** required to merge the engineering fix; it is retained as DP-WIN-001 acceptance after a new installer is produced.

## P1 — supportability, observability, security and recovery

P1 resumes only after DP-WIN-P0.2 no longer blocks Windows delivery.

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 9 | **DP-DIAG-001 — Sanitized support bundle** | ✅ COMPLETE | ChatGPT + GitHub |
| 10 | **DP-OBS-001 — Unified operational status / offer-pipeline visibility** | 🟡 IN PROGRESS — PR #19 exists; paused behind P0 hotfix | ChatGPT + GitHub; Windows installed acceptance in CI |
| 11 | **DP-SEC-001 — Local web-panel mutation protection & secret-redaction hardening** | ⏳ QUEUED | ChatGPT + GitHub |
| 12 | **DP-REC-001 — Self-service recovery** | ⏳ QUEUED | ChatGPT + GitHub; Windows runner where install-state behavior is involved |
| 13 | **DP-REC-002 — Export/import settings** | ⏳ QUEUED | ChatGPT + GitHub |
| 14 | **DP-QA-001 — Parser regression corpus** | ⏳ QUEUED | ChatGPT + GitHub |
| 15 | **DP-QA-002 — Data-quality regression matrix** | ⏳ QUEUED | ChatGPT + GitHub |

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

**DP-WIN-P0.2 — finish native GitHub Actions acceptance, merge the hotfix, update this roadmap to COMPLETE, then resume DP-OBS-001 PR #19.**

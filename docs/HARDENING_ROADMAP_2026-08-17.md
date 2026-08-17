# Discount Parser — operational hardening roadmap

**Canonical repository:** `arvectum/discount-parser`  
**Canonical branch:** `main`  
**Updated:** 2026-08-17  
**Execution priority:** ChatGPT + GitHub/GitHub Actions first. OpenCode/local Windows is used only when a gate genuinely cannot be executed in GitHub-hosted Windows or requires the customer's/owner's real environment.

The original MVP implementation roadmap remains in [`ROADMAP.md`](ROADMAP.md). This document is the current post-MVP operational/release hardening roadmap.

## Status legend

- ✅ COMPLETE — implementation and required repository/CI gate accepted.
- 🟡 IN PROGRESS — implementation exists but acceptance/merge is not complete.
- ⏳ QUEUED / DEFERRED — intentionally not started yet.
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
| 8 | **DP-REPO-003 — GitVerse stale `main.lock` mirror unblock** | ⛔ EXTERNAL BLOCKER — issue #34 | GitVerse platform/operator, then GitHub Actions rerun |

## P1 — supportability, observability, security and recovery

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 9 | **DP-DIAG-001 — Sanitized support bundle** | ✅ COMPLETE | ChatGPT + GitHub |
| 10 | **DP-OBS-001 — Unified operational status / offer-pipeline visibility** | ✅ COMPLETE | ChatGPT + GitHub + GitHub Actions; PR #19 |
| 11 | **DP-SEC-001 — Local web-panel mutation protection & secret-redaction hardening** | 🟡 IMPLEMENTED, CI acceptance pending — issue #23 | ChatGPT + GitHub |
| 12 | **DP-REC-001 — Self-service recovery** | 🟡 IMPLEMENTED, CI acceptance pending — issue #24 | ChatGPT + GitHub |
| 13 | **DP-REC-002 — Export/import settings** | 🟡 IMPLEMENTED, CI acceptance pending — issue #25 | ChatGPT + GitHub |
| 14 | **DP-QA-001 — Parser regression corpus** | 🟡 IMPLEMENTED, CI acceptance pending — issue #26 | ChatGPT + GitHub |
| 15 | **DP-QA-002 — Data-quality regression matrix** | 🟡 IMPLEMENTED, CI acceptance pending — issue #27 | ChatGPT + GitHub |

### DP-SEC-001 acceptance contract

- external `Origin` and external fallback `Referer` cannot mutate the local panel;
- loopback Origin/Referer remains usable and untrusted Host remains rejected;
- logging redaction covers named/generic tokens, passwords, API credentials, Authorization/Proxy-Authorization, cookies, session identifiers, Telegram channel/admin identifiers and URL-embedded credentials;
- nested structured JSON logging extras are recursively redacted.

### DP-REC-001 / DP-REC-002 contract

New worker commands are repository-tested: `db-status`, `db-backup`, `db-recover`, `settings-export`, `settings-import`. Recovery separates database files from `.env`, creates a timestamped backup before destructive recovery, and reports integrity as machine-readable JSON. Settings portability is versioned, allowlisted, atomically written, range/enum validated, and explicitly excludes credential-bearing fields while preserving existing secret `.env` entries on import.

### DP-QA-001 / DP-QA-002 contract

The five production HTML adapters have a versioned offline corpus with declared expected offer count and merchant/title/discount/promo invariants. A separate data-quality matrix covers expiry parsing, conditions, geographic scope and publication eligibility including the `failed` retry / `pending|published` exclusion boundary.

## P2 — customer documentation

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 16 | **DP-DOC-001 — Customer manual** | 🟡 IMPLEMENTED, CI/merge pending — issue #28 | ChatGPT + GitHub |
| 17 | **DP-DOC-002 — Troubleshooting guide** | 🟡 IMPLEMENTED, CI/merge pending — issue #29 | ChatGPT + GitHub |

The Russian customer manual and symptom-first troubleshooting guide cover current installer behavior, onboarding, operations, diagnostics, database recovery, secret-free settings portability and support escalation.

## Physical Windows gates — stop point after repository-only completion

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 18 | **DP-WIN-001 — Real installed Windows/customer acceptance** | ⏳ DEFERRED — issue #31 | Windows notebook + OpenCode / human operator |
| 19 | **DP-WIN-002 — Real Telegram E2E** | ⏳ DEFERRED — issue #32 | Windows notebook + OpenCode; real bot/channel |
| 20 | **DP-WIN-003 — Real source/network sweep** | ⏳ DEFERRED — issue #33 | Windows notebook + OpenCode; real network routes/sources |

When all repository-only tasks above are green and merged, the next action is DP-WIN-001. At that point autonomous work stops and an exact OpenCode specification must be issued; DP-WIN-002 and DP-WIN-003 remain blocked by completion of the previous physical gate.

## Current next action

**Run the full repository/build/Windows CI matrix for DP-SEC-001 through DP-DOC-002, fix every deterministic failure, merge only on full PASS, then change the roadmap next action to DP-WIN-001 and stop for OpenCode handoff.**

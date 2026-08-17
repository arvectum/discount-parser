# Discount Parser — operational hardening roadmap

**Canonical repository:** `arvectum/discount-parser`  
**Canonical branch:** `main`  
**Updated:** 2026-08-17  
**Execution priority:** ChatGPT + GitHub/GitHub Actions first; physical Windows/OpenCode only where real machine, credentials or network are required.

## Status legend

- ✅ COMPLETE — implementation and required CI acceptance passed.
- ⏳ DEFERRED — intentionally waiting for its prerequisite/local gate.
- ⛔ EXTERNAL BLOCKER — requires an external platform/operator action.

## P0 — repository, release and Windows delivery safety

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 1 | DP-REPO-001 — Canonical repository & release provenance audit | ✅ COMPLETE | ChatGPT + GitHub |
| 2 | DP-REPO-002 — Canonical history recovery & ref reconciliation | ✅ COMPLETE | ChatGPT + GitHub |
| 3 | DP-REL-001 — Reproducible/immutable release identity | ✅ COMPLETE | ChatGPT + GitHub |
| 4 | DP-CI-001 — Reproducible Windows installer build | ✅ COMPLETE | GitHub Actions / Windows |
| 5 | DP-CI-002 — Windows installed acceptance | ✅ COMPLETE | GitHub Actions / Windows |
| 6 | DP-CI-003 — Release gate | ✅ COMPLETE | GitHub Actions |
| 7 | DP-WIN-P0.2 — Installer shortcut/rollback hardening | ✅ COMPLETE | GitHub Actions / Windows |
| 8 | DP-REPO-003 — GitVerse stale `main.lock` mirror unblock | ⛔ EXTERNAL BLOCKER — issue #34 | GitVerse operator/platform |

## P1 — supportability, security, recovery and QA

| Order | Task | Status | Acceptance |
| --- | --- | --- | --- |
| 9 | DP-DIAG-001 — Sanitized support bundle | ✅ COMPLETE | existing CI |
| 10 | DP-OBS-001 — Unified operational status | ✅ COMPLETE | PR #19 |
| 11 | DP-SEC-001 — Local mutation protection & secret-redaction hardening | ✅ COMPLETE — issue #23 | cross-origin/referer/host + recursive redaction tests |
| 12 | DP-REC-001 — Self-service recovery | ✅ COMPLETE — issue #24 | `db-status`, `db-backup`, `db-recover` tests |
| 13 | DP-REC-002 — Export/import settings | ✅ COMPLETE — issue #25 | secret-free versioned allowlist + validation/preservation tests |
| 14 | DP-QA-001 — Parser regression corpus | ✅ COMPLETE — issue #26 | five production HTML adapters, offline corpus |
| 15 | DP-QA-002 — Data-quality regression matrix | ✅ COMPLETE — issue #27 | validity/conditions/geo/publication matrix |

The accepted repository-only batch passed on head `2e46aa075905da8a91fb1daa90b22059caac49eb`: multi-platform `ci`, `build-delivery`, Windows reproducibility, Windows installed acceptance, installed application exercise and DP-WIN-P0.2 installer resilience all PASS.

## P2 — customer documentation

| Order | Task | Status | Artifact |
| --- | --- | --- | --- |
| 16 | DP-DOC-001 — Customer manual | ✅ COMPLETE — issue #28 | `docs/CUSTOMER_MANUAL_RU.md` |
| 17 | DP-DOC-002 — Troubleshooting guide | ✅ COMPLETE — issue #29 | `docs/TROUBLESHOOTING_RU.md` |

## Physical Windows gates — local stop point

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 18 | **DP-WIN-001 — Real installed Windows/customer acceptance** | ⏳ NEXT — issue #31 | Windows notebook + OpenCode / human operator |
| 19 | DP-WIN-002 — Real Telegram E2E | ⏳ DEFERRED — issue #32 | Windows notebook; real bot/channel |
| 20 | DP-WIN-003 — Real source/network sweep | ⏳ DEFERRED — issue #33 | Windows notebook; real network/sources |

DP-WIN-002 starts only after DP-WIN-001 passes; DP-WIN-003 starts only after DP-WIN-002 passes.

## Current next action

**DP-WIN-001 — stop autonomous repository work and execute the prepared OpenCode specification on the physical Windows notebook.**

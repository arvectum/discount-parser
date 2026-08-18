# Discount Parser — operational hardening roadmap

**Canonical repository:** `arvectum/discount-parser`  
**Canonical branch:** `main`  
**Updated:** 2026-08-18  
**Execution priority:** ChatGPT + GitHub/GitHub Actions first; physical Windows/OpenCode only where real machine, credentials or network are required.

## Status legend

- ✅ COMPLETE — implementation and required CI/physical acceptance passed.
- 🟡 IN PROGRESS — implementation/acceptance preparation is underway; required final gate has not passed yet.
- ⏳ NEXT — next roadmap action, not started yet.
- ⏳ DEFERRED — intentionally postponed and not blocking the current delivery cycle.
- ⛔ EXTERNAL BLOCKER — requires an external platform/operator action and blocks acceptance only when explicitly marked as release-blocking.

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
| 8 | DP-REPO-003 — GitVerse stale `main.lock` mirror unblock | ⏳ DEFERRED / NON-BLOCKING — issue #34 closed `not planned`; mirror manual-only | GitVerse operator/platform if revisited |

### GitVerse disposition

GitHub remains the canonical repository and source of release truth. GitVerse is a recovery replica only and is not part of the Discount Parser customer/release acceptance gate.

A fresh mirror rerun on 2026-08-18 passed canonical lineage preflight and then failed only because the GitVerse backend could not create `refs/heads/main.lock` because that lock file already existed. The failure is server-side repository state, not a canonical-history or application defect.

For the current delivery cycle the mirror is intentionally manual-only. No force-push, prune, branch deletion/recreation or destructive ref reconciliation is permitted. Issue #34 records the canonical deferred decision; historical duplicate issue #7 is closed as duplicate.

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

## Physical Windows gates

| Order | Task | Status | Where |
| --- | --- | --- | --- |
| 18 | **DP-WIN-001 — Real installed Windows/customer acceptance** | ✅ COMPLETE — issue #31 | Windows notebook + human operator |
| 19 | **DP-WIN-002 — Real Telegram E2E** | ✅ COMPLETE — issue #32 | Windows notebook; real bot/channel |
| 20 | **DP-WIN-003 — Real source/network sweep** | ✅ COMPLETE — issue #33 / PRs #50, #51 | Windows notebook; real network/sources |
| 21 | **DP-AUTO-003 — Physical handoff specification** | ✅ COMPLETE — issue #36 | Superseded by successful execution of DP-WIN-001/002/003 |

### DP-WIN-001 accepted physical baseline

Physical acceptance passed against canonical source `4496e6c8e42ce7af3e3fb50667d1ec913eb52415` and installer SHA-256 `1426d7bba01cb3c609dc9ee4fae66e6c9825d4c4aa4a94764145be785e37190b`.

Accepted evidence includes: canonical installed Worker identity `d12bc6eb89765c98eadd999422dedd8c17c619b4cbcacae26110aedb50e20288`; `doctor`, `status-json`, `db-status`; Start Menu and web UI; `/system/status.json`; support-bundle privacy; DB backup; secret-free settings export/import roundtrip; restart; same-version reinstall; uninstall payload/shortcut cleanup; clean reinstall; final restart; evidence privacy.

The earlier R3/R4 stale-Worker failures were diagnosed as a test-harness lifecycle error: OpenCode timed out/terminated interactive Inno Setup before completion. The same canonical installer completed normally in a human-owned PowerShell process and replaced the stale Worker successfully. Installer/uninstaller lifecycle checks on physical Windows must therefore be human-owned or otherwise use a runner that waits for true process completion without an external timeout.

### DP-WIN-002 accepted physical baseline

Physical Real Telegram E2E acceptance passed on the Windows notebook against canonical main `8d0c1e5eef0d23db9ea1881c48c1a3a74f0319dc`, accepted build tree `65dd5de1822f2da11f64bb7d808e63b85a5e617c`, installer SHA-256 `E84BBC85C7F7A294D865F118B83267C9C7B652ECCEAC8359059DEC5CA0DBD665`, and installed Worker SHA-256 `F8E119EBBC1333100AC322F781AD05E95A3CC363A4A3B40927C2F5F90B7C286E`.

Windows initially marked the downloaded installer/runner with `Zone.Identifier`; the files were explicitly unblocked before execution. The accepted installer completed with exit code `0`. `doctor`, `status-json`, and `db-status` all passed.

`DiscountParserWorker.exe telegram-e2e` passed the full live contract using the installed runtime credentials and product network routing: `getMe`, `getChat`, and `getChatMember`; administrator/posting rights; real manual publication; `failed → retry → published` with the same publication row reused; isolated real autopost; restoration of the original publication filter; removal of synthetic database rows; and successful deletion of three Telegram probe messages.

Evidence file `acceptance/dp-win-002-real-telegram-e2e.json` reported `PASS`, `credentials_embedded=false`, and passed the privacy check. No code/repository changes were made during the physical gate and no secrets were printed. Issue #32 is closed as completed.

### DP-WIN-003 accepted physical baseline

PR #50 added the canonical installed command `DiscountParserWorker.exe source-network-sweep`, real legacy/registry collection, sanitized direct/proxy/system reachability diagnostics, observed production route evidence, database backup/integrity checks, scheduler cadence validation and privacy-gated evidence. It also fixed the registry scheduler cadence defect so `check_interval_minutes` is honored by scheduled collection while targeted/manual collection remains immediate.

Physical run #1 exposed a real upgrade-state defect: an enabled orphaned `legacy_adapter` mirror could remain in the registry after its YAML key was removed or renamed. PR #51 added upgrade-safe reconciliation that retires only orphaned `legacy_adapter` rows and explicitly preserves user-owned nonlegacy collectors.

Final physical rerun passed on the Windows notebook against canonical main `85fa00761c8ee41b4d057e62fa07458c1030fb93`, tree `e7092f713c266d5e1f32b3c243667efaa3659b25`, installer SHA-256 `EDDE6B75579D12BE86751CA60F1C9EAF3F391BBBF618FD9853E4CC28BB0C3AD0`, and installed Worker SHA-256 `D4E1D574C7B120BF94D61AA36A0D953194CE87D3F40CF8A9A6C968CE2C0B26B7`.

Acceptance evidence reported: overall `PASS`; `credentials_embedded=false`; privacy PASS; network loopback PASS; scheduler cadence PASS; all enabled sources PASS; database integrity PASS; source_count `10`; orphaned enabled legacy mirrors `0`. Five promo aggregators collected with errors `0` via the direct route and five Telegram public sources collected with errors `0` via the system route. Issue #33 is closed as completed.

## Current cycle status

**CURRENT HARDENING CYCLE: COMPLETE.**

All GitHub-canonical repository/release tasks, support/security/recovery/QA tasks, customer documentation tasks and required physical Windows gates are complete. DP-REPO-003 is deliberately deferred as a non-blocking recovery-replica concern and is not part of customer acceptance.

The validated customer installer from the final physical DP-WIN-003 baseline has SHA-256 `EDDE6B75579D12BE86751CA60F1C9EAF3F391BBBF618FD9853E4CC28BB0C3AD0`. The customer delivery was sent on 2026-08-18. Further product work should proceed in a new roadmap cycle driven by customer feedback and separately prioritized enhancements rather than reopening completed hardening gates.

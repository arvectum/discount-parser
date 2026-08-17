# DP-REPO-002 — Canonical history recovery & ref reconciliation

**Status:** COMPLETE for canonical GitHub history recovery and provenance reconciliation.

**Canonical repository:** `arvectum/discount-parser`

**Canonical product merge head:** `2b1bf59987b5e189e27733d32dc7a776853b823b`

This record documents the recovery performed on 2026-08-17. A later documentation-only merge containing this file may advance `main`; `2b1bf59987b5e189e27733d32dc7a776853b823b` remains the product-state reconciliation point described below.

## 1. Starting state

DP-REPO-001 established GitHub as the canonical repository and left the repository intentionally fail-closed because the accepted product history was still ahead on GitVerse.

Verified starting points:

- DP-REPO-001 starting/control-plane base: `bc91a0597e6686f494326f7420b8f4b133ee4913`.
- GitHub `main` after DP-REPO-001: `ea92608d210d0fd3026685715cd163eceacbf5c5`.
- Live GitVerse `main`: `ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5`.
- GitHub/GitVerse merge base before reconciliation: `bc91a0597e6686f494326f7420b8f4b133ee4913`.
- Accepted Windows installer SHA-256 evidence: `E001979A77FF40F3C2FEF84594BE1C57B0C57979CDF331A3EE1D620AD4024509`.
- Accepted Windows recovery tag name: `discount-parser-windows-recovery-hotfix-2026-08-16`; only the prefix `b6ba4e0` survived in the initial operator evidence after the former destructive mirror had deleted the ref.

No force push, history rewrite, squash, rebase, prune, or destructive ref cleanup was used during recovery.

## 2. Recovered accepted product line

The GitVerse object graph rooted at `ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5` was imported into GitHub and preserved as `recovery/gitverse-main-ff8efb4-20260817` before canonical reconciliation.

The five product-line commits after the common base are:

1. `063cd378cc45634008131a8901061ea401c25ef0` — `fix: restore Discount Parser release line after main divergence`
2. `7c3d3a689d5339b1ee3d2efd897c329719ad96ec` — `fix: make failed Telegram publications retryable`
3. `770d8d3fc11b734909a512841851ef6b25ae7d63` — `Merge hotfix: failed Telegram publication retry`
4. `11f12e8d4371fdbce3675c76b2a557af355d8bd1` — `Windows recovery: fix installer failures, implement automatic DB recovery, enhance security logging, and improve dashboard metrics`
5. `ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5` — `Finalizing Windows recovery: improved logging, DB recovery, and dashboard transparency`

The graph comparison showed that the GitHub side contained only the DP-REPO-001 control-plane commit after the same common base, so the two accepted histories could be reconciled by ordinary merge without rewriting either parent history.

## 3. Exact accepted Windows commit recovery

The initially known `b6ba4e0` prefix was resolved against the GitVerse repository API to the exact commit:

`b6ba4e0808d640e938bdd53eb1cf87b2416cca10`

Commit subject:

`Security: improve Telegram token redaction regex to catch tokens in URLs`

Independent GitVerse Actions history provided the surviving ref evidence:

- run `1328224`: `refs/tags/discount-parser-windows-recovery-hotfix-2026-08-16` → `b6ba4e0808d640e938bdd53eb1cf87b2416cca10`;
- run `1328221`: `refs/heads/release/windows-recovery-final-tested` → `b6ba4e0808d640e938bdd53eb1cf87b2416cca10`.

Graph comparison then proved that `b6ba4e0808d640e938bdd53eb1cf87b2416cca10` is exactly one commit ahead of `ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5`, with no commits behind. Its product diff is limited to `src/shared/logging.py` (2 additions / 2 deletions).

The accepted installer hash above and the recovered exact ref/commit chain are historical provenance evidence. They do **not** constitute a reproducible-build cryptographic attestation that the installer bytes can be regenerated from the commit. That stronger release-attestation requirement belongs to DP-REL-001.

## 4. Restored verified refs

Only refs whose targets were independently recovered were recreated:

| Ref | Restored target | Evidence basis |
|---|---|---|
| `refs/tags/discount-parser-telegram-hotfix-2026-08-15` | `770d8d3fc11b734909a512841851ef6b25ae7d63` | GitVerse historical Actions run |
| `refs/tags/discount-parser-windows-recovery-hotfix-2026-08-16` | `b6ba4e0808d640e938bdd53eb1cf87b2416cca10` | exact commit lookup + GitVerse run `1328224` |
| `refs/heads/release/windows-recovery-final-tested` | `b6ba4e0808d640e938bdd53eb1cf87b2416cca10` | GitVerse run `1328221` |
| `refs/heads/fix/windows-installer-startup-recovery` | `ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5` | latest surviving GitVerse run `1328062`; earlier run `1327021` recorded `11f12e8d...` |

The Windows recovery tag had earlier historical targets in GitVerse run history, so this audit does not claim that it was immutable in the past. It restores the **final independently verified accepted target** and treats the restored GitHub tag as immutable going forward.

## 5. Ref reconciliation matrix

Automated ancestry and `git cherry` patch-equivalence analysis was executed against the recovered accepted product head. Patch-bearing divergent candidates were preserved rather than silently merged or deleted.

The primary unique candidates were:

| Ref | Tip | Product-only commits | Ref-only commits | Patch-unique in ref | Disposition |
|---|---|---:|---:|---:|---|
| `feature/r12-promko-http-reveal-final` | `d45037e1...` | 6 | 1 | 1 | preserve / forensic |
| `fix/source-registry-delete-ui` | `54f5d19...` | 6 | 9 | 6 | preserve / forensic |
| `fix/source-registry-edit-ui` | `3520c582...` | 6 | 11 | 7 | preserve / forensic |
| `fix/sqlite-0005-downgrade` | `d0e8963...` | 6 | 13 | 8 | preserve / forensic |
| `fix/telegram-source-collection` | `952efed...` | 6 | 5 | 4 | preserve / forensic |
| `fix/windows-registry-seed-cli` | `1d2bfc5...` | 6 | 7 | 5 | preserve / forensic |
| `hotfix/customer-feedback-20260812` | `bd14055...` | 6 | 15 | 9 | preserve / forensic |
| `hotfix/windows-worker-lifecycle-20260813` | `bbb701b...` | 6 | 17 | 11 | preserve / forensic |
| `reconcile/r10-ace21cc` | `518541c...` | 116 | 2 | 2 | preserve / forensic |
| `recovery/r12-full` | `802d86d...` | 6 | 3 | 3 | preserve / forensic |
| tag `r12-recovered-2026-08-11` | `7775e8f...` | 6 | 4 | 3 | preserve / forensic |
| tag `r12.1-telegram-fix-2026-08-11` | `628ae58...` | 6 | 6 | 4 | preserve / forensic |
| tag `r12.2-rc1` | `cd37cb8...` | 6 | 14 | 8 | preserve / forensic |

The reconciliation workflow also evaluated the matching GitVerse quarantine copies and other recovery refs. Aliases pointing to the same tips are omitted from this summary table to avoid double-counting.

**Accounting decision:** every patch-bearing divergent ref remains reachable. None of its unique commits was discarded. None was merged into canonical `main` merely because it existed: there was no independent acceptance evidence that those divergent branches superseded the accepted Windows lineage. Their retention is the forensic account required before any future cleanup or selective recovery.

No ref cleanup is part of DP-REPO-002.

## 6. Canonical merge sequence

The accepted history was reconciled in two ordinary merges:

1. PR #5 merged recovered GitVerse `ff8efb4186...` into GitHub `main` and produced merge commit `2e221492c9cb460a99f83eefa1cd104a78e4deb9`.
2. Post-merge graph verification discovered that final accepted Windows commit `b6ba4e080...` was a direct one-commit descendant of `ff8efb4186...`. PR #6 then merged that exact commit after validation, producing canonical product merge head `2b1bf59987b5e189e27733d32dc7a776853b823b`.

Post-merge ancestry checks prove:

- DP-REPO-001 `ea92608d210d0fd3026685715cd163eceacbf5c5` is an ancestor of canonical `main` (`behind_by = 0`);
- recovered GitVerse product head `ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5` is an ancestor of canonical `main` (`behind_by = 0`);
- final accepted Windows commit `b6ba4e0808d640e938bdd53eb1cf87b2416cca10` is an ancestor of canonical `main` (`behind_by = 0`).

This means the histories are reconciled in one canonical graph, not merely copied into adjacent recovery refs.

## 7. Validation gates

Before the final accepted Windows commit was merged:

- CI passed on Ubuntu, Windows, macOS ARM, and macOS Intel;
- database migration/doctor and CLI smoke passed on all four CI jobs;
- delivery build passed for Windows x64, macOS ARM64, and macOS Intel;
- Windows UI/worker executable build, frozen smoke, native installer packaging, and artifact upload all passed;
- both macOS frozen smokes and DMG builds passed.

The recovered `ff8efb4186...` product head had also passed the same cross-platform CI and delivery-build family before the first canonical merge.

## 8. GitVerse mirror status

The mirror remains fail-closed and non-destructive.

After canonical reconciliation, mirror lineage preflight succeeds: GitVerse `main` is an ancestor of canonical GitHub `main`. The subsequent normal push is rejected by GitVerse because the remote backend reports a persistent stale lock:

`cannot lock ref 'refs/heads/main' ... refs/heads/main.lock: File exists`

Final observed failed mirror run: GitHub Actions `32007431091`.

No force update, prune, ref deletion, or delete/recreate workaround was attempted. GitHub therefore remains canonical while GitVerse replication is externally blocked. This operational debt is tracked separately as **DP-REPO-003 / issue #7 — GitVerse stale main.lock mirror unblock**.

## 9. Acceptance result

DP-REPO-002 acceptance is satisfied for canonical history recovery:

- GitVerse accepted object graph imported into GitHub recovery refs — PASS;
- exact final `b6ba4e0...` target recovered — PASS;
- recovery/hotfix/release refs analyzed by ancestry and patch equivalence — PASS;
- patch-bearing divergent refs accounted for and preserved before any cleanup — PASS;
- canonical `main` reconciled without provenance rewrite — PASS;
- only independently verified deleted release/recovery refs restored — PASS;
- accepted Windows lineage tied to exact commit `b6ba4e0808d640e938bdd53eb1cf87b2416cca10` — PASS;
- mirror remains fail-closed and non-destructive — PASS;
- GitVerse replica advancement — BLOCKED externally by stale `main.lock`, transferred to DP-REPO-003 and not treated as a canonical-history failure.

## 10. Follow-up rules

1. Do not delete the forensic/recovery refs as part of routine cleanup until a separate review determines whether their unique patches should be abandoned, selectively recovered, or archived.
2. Do not move the restored accepted tags.
3. Do not work around GitVerse `main.lock` with force push or delete/recreate semantics.
4. DP-REL-001 should add immutable release provenance/attestation so future installer hashes are generated and bound to release commits automatically rather than reconstructed retrospectively.

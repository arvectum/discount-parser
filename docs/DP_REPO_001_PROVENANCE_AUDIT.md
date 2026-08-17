# DP-REPO-001 — Canonical repository & release provenance audit

Status: **DONE — audit complete; repository history reconciliation required**  
Audit date: **2026-08-17**  
Canonical control plane: **GitHub `arvectum/discount-parser`**  
Canonical integration branch: **`main`**  
Canonical product head: **NOT YET DECLARED** — current GitHub `main` is missing newer release/hotfix lineage that must be recovered and reconciled before it can be treated as the authoritative product state.

## 1. Purpose

This audit establishes where Discount Parser repository and release truth must live, inventories current refs and release evidence, identifies provenance gaps, and defines fail-closed rules that prevent loss of recovery/release history while the repositories are reconciled.

The audit deliberately separates two concepts:

1. **Canonical control plane** — the repository where changes, CI, release policy and future release records are governed.
2. **Canonical product head** — the exact commit that contains the latest accepted product state.

GitHub is designated as the canonical control plane. The current GitHub `main` cannot yet be declared the canonical product head because newer product/release evidence exists outside its reachable history.

## 2. Evidence snapshot

### GitHub repository

- repository: `arvectum/discount-parser`;
- default/integration branch: `main`;
- `main` at audit start: `bc91a0597e6686f494326f7420b8f4b133ee4913`;
- that commit only adds the GitHub → GitVerse mirror workflow on top of `5062362bd25f871e4f3645873159368a071e5b38`;
- pre-remediation branch inventory: 33 branches, including `main`, legacy `master`, `backup/*`, `local/*`, recovery branches and several newer hotfix branches;
- GitHub Releases: none;
- GitHub tags at audit start:
  - `r12-recovered-2026-08-11` → `7775e8f97a68a2870fbb63503f01d33794ba27e3`;
  - `r12.1-telegram-fix-2026-08-11` → `628ae5836c0f86260a1b3be08c75e40d987c3e38`;
  - `r12.2-rc1` → `cd37cb8209af719135412a14f4d3f53ebfeb52f0`.

### Graph relationships

All three GitHub release-like tags diverge from current GitHub `main` after merge base `5062362bd25f871e4f3645873159368a071e5b38`:

- `r12-recovered-2026-08-11`: 4 commits not in GitHub `main`;
- `r12.1-telegram-fix-2026-08-11`: 6 commits not in GitHub `main`;
- `r12.2-rc1`: 14 commits not in GitHub `main`.

Additional hotfix branches also contain product changes not reachable from current GitHub `main`. Therefore, `main` is not presently a complete product-history superset.

### Accepted Windows delivery evidence

The latest operator acceptance record available to this audit reports:

- remote `main` SHA: `ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5`;
- recovery tag: `discount-parser-windows-recovery-hotfix-2026-08-16` on commit beginning `b6ba4e0`;
- accepted installer SHA-256: `E001979A77FF40F3C2FEF84594BE1C57B0C57979CDF331A3EE1D620AD4024509`.

The new fail-closed GitVerse preflight then independently fetched GitVerse `main` and confirmed it is exactly:

```text
ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5
```

At the same time GitHub `main` was `bc91a0597e6686f494326f7420b8f4b133ee4913`, and the ancestry check failed. The push step was skipped entirely. Therefore the accepted remote `main` SHA is now **live-verified from GitVerse by GitHub Actions**, not merely operator-reported.

`ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5` is still **not present in the current GitHub object graph**. The recovery tag location and installer SHA-256 remain operator/release evidence until their exact surviving objects/artifacts are recovered. They must be reconciled during DP-REPO-002 before any history is rewritten or refs are removed.

## 3. Critical mirror incident found by the audit

The scheduled GitHub → GitVerse workflow on 2026-08-17 used:

```text
git push --force --prune gitverse \
  'refs/heads/*:refs/heads/*' \
  'refs/tags/*:refs/tags/*'
```

Because GitVerse contained recovery/release refs that were absent from GitHub, this command attempted to make the replica destructively identical to an incomplete GitHub graph.

The run deleted these GitVerse-only refs before the push of `main` failed:

- branch `fix/windows-installer-startup-recovery`;
- branch `release/windows-recovery-final-tested`;
- tag `discount-parser-telegram-hotfix-2026-08-15`;
- tag `discount-parser-windows-recovery-hotfix-2026-08-16`.

The same run then failed to update GitVerse `main` because the GitVerse server reported an existing `refs/heads/main.lock` file. This produced a partial and provenance-hostile mirror operation: remote-only provenance refs were removed while canonical `main` was not updated.

### Immediate remediation in DP-REPO-001

The mirror workflow is changed to **fail closed**:

- no `--force`;
- no `--prune`;
- GitVerse remote-only refs are never deleted automatically;
- before any push, GitVerse `main` is fetched;
- if GitVerse `main` is ahead of or diverged from GitHub `main`, the workflow exits with an error **before pushing any refs**;
- only an ancestor/equal GitVerse `main` may receive a normal non-force push from GitHub.

### Live validation of the remediation

The hardened workflow was executed from the audit branch and behaved as designed:

- configuration validation: PASS;
- canonical GitHub mirror clone: PASS;
- GitVerse `main` fetch: PASS;
- ancestry preflight: expected FAIL because GitVerse `main = ff8efb4…` is not an ancestor of GitHub `main = bc91a05…`;
- push branches/tags step: **SKIPPED**;
- no force, prune, deletion or partial ref update occurred.

Until DP-REPO-002 reconciles history, this fail-closed result is the correct/safe behavior.

## 4. Release provenance audit

Current `build-delivery.yml` has several provenance gaps:

1. Tag-triggered builds match only `v*`, while all current GitHub release-like tags use `r*` and the accepted recovery tag used `discount-parser-*`.
2. The workflow uploads ephemeral GitHub Actions artifacts but does not create GitHub Releases.
3. It does not emit a release provenance manifest containing commit SHA, Git ref, workflow run ID and artifact hashes.
4. It does not persist an immutable SHA-256 checksum record beside a release artifact.
5. Existing GitHub release-like tags are not reachable from current `main`, so they cannot currently prove a linear `main → tag → build → installer` chain.
6. The accepted Windows installer hash is available in operational evidence, but not yet attached to a durable GitHub release record.

Result: **artifact build capability exists, but durable release provenance is not yet complete.**

## 5. Canonical repository policy established by this audit

Effective immediately:

- **GitHub `arvectum/discount-parser` is the canonical control plane.**
- GitVerse is a **replica/recovery remote**, not an independent source to overwrite blindly and not a remote that may be pruned while reconciliation is pending.
- `main` becomes the canonical product head only after DP-REPO-002 proves that the accepted product/release history has been recovered into GitHub and all retained release commits are reachable or intentionally archived with documented lineage.
- A production/client release may only be cut from a commit reachable from canonical `main`.
- Release tags are immutable provenance records: never move, force-update or delete them as part of routine mirroring.
- A release must retain at minimum: full commit SHA, immutable tag, CI run identity, artifact filename, SHA-256, target platform/architecture and acceptance status.
- Old `backup/*`, `local/*`, recovery and hotfix refs must not be deleted merely for cleanliness. They may be cleaned only after ancestry/equivalence is proven and recovery refs are no longer needed.
- Force-pushes to `main` and automated pruning of replica refs are prohibited for normal operation.

## 6. Risk register

| Finding | Severity | State after DP-REPO-001 |
|---|---:|---|
| GitHub `main` missing newer release/hotfix lineage | Critical | Open; recovery required |
| Destructive `--force --prune` mirror | Critical | Remediated and live-validated |
| Accepted Windows commit absent from GitHub | Critical | Open; GitVerse SHA live-verified |
| Release-like tags diverge from `main` | High | Open; reconcile, do not rewrite blindly |
| GitHub Releases absent | High | Open; release pipeline hardening required |
| `v*` build trigger mismatches existing `r*`/recovery tags | High | Open |
| No durable build provenance/checksum manifest | High | Open |
| Large set of backup/local/recovery branches | Medium | Quarantined by policy; cleanup deferred |
| README/roadmap describe older CI/release state | Medium | Open; update after canonical recovery |

## 7. Gate and result

`DP-REPO-001` is complete when the following are true:

- [x] canonical control-plane decision is documented;
- [x] GitHub refs/tags/releases/workflows are inventoried;
- [x] release graph divergence is identified;
- [x] accepted GitVerse `main` SHA is independently live-verified;
- [x] external installer/tag evidence is recorded without pretending it is already GitHub-native;
- [x] destructive mirror behavior is identified and made fail-closed;
- [x] fail-closed mirror behavior is live-validated;
- [x] deletion/force policy for provenance refs is defined;
- [x] follow-up recovery and release-provenance work is explicitly gated.

**DP-REPO-001 RESULT: PASS (audit/remediation).**  
**Repository provenance state: NOT RECONCILED.**

## 8. Required follow-up

### DP-REPO-002 — Canonical history recovery & ref reconciliation

Must run before branch cleanup or declaration of a canonical product head:

1. fetch/import the live-verified GitVerse `main` object graph rooted at `ff8efb4186ebccca2c30cc78b8fefb5ec7cd0cf5`;
2. recover/prove the full SHA behind the accepted recovery-tag target beginning `b6ba4e0` and any surviving/deleted release refs;
3. reconstruct the ancestry of the accepted 2026-08-16 Windows installer;
4. compare all unique GitHub/GitVerse recovery/hotfix branches by graph and patch equivalence;
5. import the accepted lineage into GitHub without fabricating history;
6. create a clean canonical `main` only after all unique product commits are accounted for;
7. restore retained provenance tags if they were removed from GitVerse and point them only to verified original objects.

### DP-REL-001 — Immutable release provenance pipeline

After DP-REPO-002:

- choose one canonical tag convention;
- make tag-triggered delivery match that convention;
- generate machine-readable provenance manifest and SHA-256 checksums;
- publish durable GitHub Release records for production/client artifacts;
- tie acceptance evidence to the exact release tag and artifact hash.

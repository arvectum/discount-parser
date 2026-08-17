# DP-CI-001 — Reproducible Windows installer build

**Status:** COMPLETE — accepted on canonical `main` on 2026-08-17.

## Goal

A Windows installer is acceptable only when two independent clean GitHub-hosted Windows builds of the same source produce the same `DiscountParser-Setup.exe` bytes.

This task does not install the resulting Setup executable. Installed acceptance is DP-CI-002.

## Controlled inputs

The canonical machine-readable contract is `packaging/windows/build-manifest.json`.

It controls:

- exact CPython version;
- exact pip version;
- exact Python runtime/build dependency closure in `requirements/windows-build.lock`;
- exact PyInstaller and hooks versions;
- exact Inno Setup 6 compiler version;
- fixed `PYTHONHASHSEED`;
- `SOURCE_DATE_EPOCH` derived from the source commit timestamp;
- maximum installer byte-size budget.

The Windows dependency closure is installed with `--no-deps --only-binary=:all:` and followed by `pip check`; the project itself is then installed editable with `--no-deps --no-build-isolation`. This prevents a clean build from silently resolving a different transitive dependency while still validating that the recorded closure satisfies package metadata.

## Deterministic packaging

`scripts/build_windows_ci.ps1` is the single controlled Windows packaging implementation used by both normal delivery CI and the dedicated reproducibility gate.

PyInstaller runs with a fixed `PYTHONHASHSEED` and commit-derived `SOURCE_DATE_EPOCH`.

The Inno Setup `[Files]` entry uses `notimestamp`, so source file modification times are not stored in the installer payload.

## Reproducibility gate

`.github/workflows/windows-reproducibility.yml` launches two independent `windows-2025` jobs for every relevant pull request and repeats the same gate after relevant changes land on canonical `main`.

Each replica:

1. checks out the same source;
2. loads the versioned build manifest;
3. installs the exact CPython/dependency/toolchain inputs;
4. builds the frozen UI and worker;
5. runs migration/doctor smoke against the frozen worker;
6. compiles the Inno installer;
7. creates `windows-build-provenance.json` with installer SHA-256, size, source SHA, toolchain identity, and dependency-lock hash;
8. uploads the installer and evidence.

A third job downloads both independent results and fails unless the actual Setup executable SHA-256 values match and the provenance records agree.

## Size budget

The last known-good pre-DP-CI-001 Windows CI artifact contained a `DiscountParser-Setup.exe` of 51,377,528 bytes with SHA-256:

`0e8c95604ee5d936a155745b922fd7caeda6973793311aeb7f6844abc03e7ed4`

The initial controlled budget is 64 MiB (67,108,864 bytes). The budget is intentionally larger than the known-good baseline but small enough to fail on a major unexplained payload increase.

This historical hash is a baseline only. DP-CI-001 does not require future installers to equal that historical installer; it requires two builds of the same current source to equal each other.

## Acceptance evidence

Implementation PR #11 passed:

- repository CI across Linux, Windows, macOS ARM64, and macOS Intel;
- normal three-platform `build-delivery`;
- two independent Windows installer builds and byte comparison.

The implementation was merged as canonical commit:

`15ab7c06c1224edcc848b8960b153094b288ee73`

The dedicated canonical-main reproducibility run was GitHub Actions run `32026733028`. Both independent Windows builds passed and the compare job reported:

- SHA-256: `f543e79baf48758d820cff8f18439acdc3f3610ecb0b7932fd24aab2c778954d`;
- size: `50,990,262` bytes;
- provenance comparison: PASS;
- size budget: PASS.

The earlier final PR-head reproducibility run `32026400695` also passed before merge. The canonical-main hash differs from the PR merge-ref hash by design because `SOURCE_DATE_EPOCH` is bound to the exact source commit; within each exact source identity, both independent builds are bit-for-bit identical.

## Acceptance

| Requirement | State |
|---|---|
| Exact controlled Windows build manifest | PASS |
| Exact Windows Python/dependency closure | PASS |
| Exact PyInstaller/Inno toolchain identity | PASS |
| Fixed deterministic build environment | PASS |
| Smoke database excluded from package | PASS |
| Installer size budget | PASS |
| Independent build replica A | PASS |
| Independent build replica B | PASS |
| Actual Setup.exe SHA-256 equality | PASS |
| Provenance equality | PASS |
| Normal repository CI | PASS |
| Normal three-platform delivery build | PASS |
| Canonical `main` replay | PASS |

**DP-CI-001: PASS / COMPLETE.**

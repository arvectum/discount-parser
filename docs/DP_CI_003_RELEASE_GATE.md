# DP-CI-003 — Release gate

**Status:** IMPLEMENTED, PR acceptance pending.

## Goal

A `v*` tag is not sufficient authorization to publish a Discount Parser release. Publication is allowed only when the exact tagged source is the current canonical `main` HEAD, canonical CI has passed for that exact commit, and the exact Windows installer that would be released passes both independent byte reproducibility and real installed acceptance.

## Gate graph

For a canonical release-tag push, `build-delivery` first builds the three delivery artifacts. Publication then depends on three release-only gates:

1. `release-source-gate` — validates the tag format, exact tag target, exact current `origin/main` HEAD, no pre-existing Release, and a successful canonical `ci` push run for the exact source SHA.
2. `release-repro-gate` — downloads the Windows installer produced by the release workflow, independently rebuilds the same exact source under the DP-CI-001 controlled toolchain, and requires the two actual Setup executables and their provenance to bind to one SHA-256.
3. `release-installed-gate` — downloads that same primary Windows release artifact and executes the DP-CI-002 silent install/migrate/doctor/local-onboarding/uninstall harness against it on a clean Windows runner.

The `release` publication job has `needs: [build, release-source-gate, release-repro-gate, release-installed-gate]`. A failed, missing, or skipped required gate prevents publication.

## Durable evidence

Each gate emits machine-readable evidence. The final publication job combines it into `release-gate.json` and requires all three records to have:

- schema `release-gate/v1`;
- task `DP-CI-003`;
- `status=PASS`;
- the exact release source SHA;
- one shared Windows installer SHA for the reproducibility and installed-acceptance gates.

`release-gate.json` is included in `SHA256SUMS`, GitHub artifact attestations, draft Release assets, and final published-asset verification.

## Fail-closed properties

- historical/stale `main` commits cannot be newly released while a newer canonical `main` HEAD exists;
- a green PR run is not accepted as canonical CI evidence;
- a CI run from another branch/commit/event is not accepted;
- rebuilding a different Windows installer blocks publication;
- installed acceptance of a different installer blocks publication;
- missing machine-readable evidence blocks bundling;
- an existing Release with the tag is never overwritten;
- release assets are still attached to a draft before publication under DP-REL-001.

## Testing boundary

No synthetic production tag or GitHub Release is created for DP-CI-003 implementation. Regression tests validate the release dependency graph and every evidence validator; the existing PR workflows exercise the same controlled Windows build, reproducibility and installed-runtime harnesses without publishing anything.

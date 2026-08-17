# DP-CI-002 — Windows installed acceptance in GitHub Actions

**Status:** COMPLETE — accepted on canonical `main` on 2026-08-17.

## Goal

DP-CI-002 closes the gap between “the Windows installer was built” and “the built installer can install and run the application”. The gate executes the real `DiscountParser-Setup.exe` on an ephemeral GitHub-hosted Windows VM and exercises the installed runtime without production secrets.

Physical/customer Windows acceptance remains DP-WIN-001.

## Boundary

DP-CI-002 deliberately does not:

- use a real Telegram bot token or channel;
- publish messages;
- require customer configuration;
- test a physical Windows workstation;
- replace DP-CI-001 reproducibility.

It reuses the exact DP-CI-001 build contract and then validates the resulting installer as an installed application.

## Installed acceptance sequence

`.github/workflows/windows-installed-acceptance.yml` runs on `windows-2025` for relevant pull requests and relevant changes on canonical `main`.

The job:

1. loads the DP-CI-001 controlled build manifest;
2. installs the exact CPython/dependency closure;
3. verifies the exact Inno Setup compiler identity;
4. builds `DiscountParser-Setup.exe` through `scripts/build_windows_ci.ps1`;
5. installs the Setup executable silently into an isolated `RUNNER_TEMP` directory and waits for the Inno GUI-subsystem process to exit;
6. requires the installer to exit successfully and produce an installation log;
7. verifies the installed executable/config/migration payload;
8. proves the installer-created runtime database exists in the installed directory and not in the source checkout;
9. reruns installed `migrate` to prove the migrated state is idempotent;
10. runs installed `DiscountParserWorker.exe doctor` and requires `ok=true`;
11. starts the installed GUI on an isolated loopback port;
12. waits for `/onboarding/1` to return HTTP 200;
13. proves an unconfigured first-run UI did not start a `DiscountParserWorker` bot/scheduler process;
14. stops the GUI;
15. runs the Inno uninstaller silently, waits for it to exit, and requires exit code 0;
16. proves installed application payload files were removed;
17. uploads installer/uninstaller/doctor/HTTP logs and machine-readable acceptance evidence even when the gate fails.

## Secret boundary

No repository secret is referenced by the installed-acceptance workflow. The application remains intentionally unconfigured and is expected to show onboarding. Telegram configuration is an optional doctor check until the owner completes setup, so this gate validates the installed product without fabricating customer credentials.

## Machine-readable evidence

`scripts/windows_installed_acceptance.ps1` writes `installed-acceptance.json` containing source SHA, installer SHA-256, installation exit code and payload, database isolation, migrate and doctor results, local HTTP/onboarding status, worker isolation, uninstall result, and final PASS/FAIL status. The evidence contains no Telegram credentials.

## Acceptance evidence

Implementation PR #13 passed all three gates on final head `24144d37aa97b86f3fc321eb4e15e2aaa2363320`:

- repository CI run `32028081548`: PASS;
- three-platform `build-delivery` run `32028081511`: PASS;
- installed Windows run `32028081540`: PASS.

PR #13 was merged without bypass as canonical commit:

`2588c169332d4f7bbfce59c37f960bd2bc28e96f`

Canonical-main installed acceptance run `32028465879` passed with machine-readable evidence:

- installer SHA-256: `107b3c490d9d92a301a3cc53ca9378c48b84bdff9e2e24fc59b0541744b30384`;
- installer exit code: `0`;
- required installed payload: PASS;
- installer-created DB in isolated installed directory: PASS;
- second installed migration: exit `0`;
- installed doctor: exit `0`, `ok=true`;
- local web UI: HTTP `200` on port `18765`, onboarding detected;
- unconfigured worker isolation: PASS;
- silent uninstall: exit `0`, installed application payload removed.

The first failing installed run also proved the gate is fail-closed: an asynchronous Inno invocation produced no exit code and was rejected. The harness was corrected to use `Start-Process -Wait -PassThru` for both installer and uninstaller, and regression coverage now protects that behavior.

## Acceptance matrix

| Requirement | State |
|---|---|
| Reuse DP-CI-001 controlled installer build | PASS |
| Real Setup.exe execution on clean Windows VM | PASS |
| Installer exit code captured synchronously | PASS |
| Installed payload validation | PASS |
| Runtime DB path isolation | PASS |
| Installed migration idempotency | PASS |
| Installed doctor | PASS |
| Installed local web/onboarding startup | PASS |
| No Telegram secrets required | PASS |
| No unconfigured bot/scheduler worker | PASS |
| Real silent uninstall | PASS |
| Evidence/log artifact on success/failure | PASS |
| PR CI/delivery/installed gates | PASS |
| Canonical `main` replay | PASS |

**DP-CI-002: PASS / COMPLETE.**

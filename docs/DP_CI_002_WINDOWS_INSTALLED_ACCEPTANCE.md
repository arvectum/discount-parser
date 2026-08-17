# DP-CI-002 — Windows installed acceptance in GitHub Actions

**Status:** IMPLEMENTED, CI acceptance pending on PR.

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
5. installs the Setup executable silently into an isolated `RUNNER_TEMP` directory;
6. requires the installer to exit successfully and produce an installation log;
7. verifies the installed executable/config/migration payload;
8. proves the installer-created runtime database exists in the installed directory and not in the source checkout;
9. reruns installed `migrate` to prove the migrated state is idempotent;
10. runs installed `DiscountParserWorker.exe doctor` and requires `ok=true`;
11. starts the installed GUI on an isolated loopback port;
12. waits for `/onboarding/1` to return HTTP 200;
13. proves an unconfigured first-run UI did not start a `DiscountParserWorker` bot/scheduler process;
14. stops the GUI;
15. runs the Inno uninstaller silently;
16. proves installed application payload files were removed;
17. uploads installer/uninstaller/doctor/HTTP logs and machine-readable acceptance evidence even when the gate fails.

## Secret boundary

No repository secret is referenced by the installed-acceptance workflow. The application remains intentionally unconfigured and is expected to show onboarding. Telegram configuration is an optional doctor check until the owner completes setup, so this gate can validate the installed product without fabricating customer credentials.

## Machine-readable evidence

`scripts/windows_installed_acceptance.ps1` writes `installed-acceptance.json` containing:

- source commit SHA;
- installer filename and SHA-256;
- installation directory and exit code;
- required payload list;
- installer-created database evidence;
- explicit migrate exit code;
- doctor exit code and `ok` state;
- web port, HTTP status, and onboarding-page state;
- proof that no unconfigured worker remained running;
- uninstaller exit code and payload-removal state;
- final PASS/FAIL status.

The evidence contains no Telegram credentials.

## Acceptance

DP-CI-002 is complete only when:

- repository regression CI passes;
- the installed-acceptance workflow passes on the implementation PR;
- the implementation is merged without bypassing checks;
- the same installed-acceptance workflow passes on canonical `main`;
- final acceptance evidence is recorded here.

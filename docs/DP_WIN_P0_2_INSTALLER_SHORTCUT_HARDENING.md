# DP-WIN-P0.2 — Installer shortcut/rollback hardening

**Priority:** P0 — customer-blocking Windows delivery defect  
**Status:** COMPLETE — merged to canonical `main` on 2026-08-17  
**Customer evidence:** feedback #3, 2026-08-17  
**Canonical merge:** `4fa6eb03e4bcdd39e3a4db8e9c45378552c07541`

## Problem

The customer supplied two Windows Setup failures from the latest delivery:

1. while Setup was creating `C:\Users\Анастасия\Desktop\Discount Parser.lnk`, Windows returned `IPersistFile::Save failed; code 0x80070005` (`Access denied`);
2. a later launch attempted `C:\Users\Анастасия\AppData\Local\DiscountParser\DiscountParser.exe` and failed with `CreateProcess failed; code 2` (`file not found`).

The previous installer declared the Desktop shortcut directly in Inno Setup `[Icons]`. `[Icons]` is processed as part of the actual installation transaction, so a shortcut-save exception can make a convenience artifact a delivery blocker. The existing `[Code]` section claimed the Desktop icon was optional but contained no implementation that changed this behavior.

The second screenshot is consistent with an interrupted/rolled-back or otherwise incomplete install followed by a launch path pointing at an executable that is no longer present. The engineering fix therefore removes Desktop shortcut persistence from the fatal install path instead of asking the customer to elevate privileges.

## Fix

`packaging/windows/installer.iss` now enforces these boundaries:

- `PrivilegesRequired=lowest` remains unchanged; the per-user installer does not require elevation;
- the Start Menu shortcut remains in `[Icons]` as the normal installer-managed launch path;
- the Desktop shortcut is represented by an optional `desktopicon` task but is **not** present in `[Icons]`;
- after the payload has been installed (`ssPostInstall`), Pascal code checks that `DiscountParser.exe` exists and calls `CreateShellLink` only then;
- `CreateShellLink` is inside `try..except`; shell/COM/ACL failures are logged and are explicitly non-fatal;
- an existing product-owned Desktop `.lnk` is removed best-effort before recreation so a successful reinstall does not intentionally preserve a stale link;
- the manually-created Desktop `.lnk` is explicitly removed by `[UninstallDelete]`;
- no wildcard or broad Desktop cleanup is used.

This directly covers the customer failure boundary because a shortcut-creation exception is now handled inside the installer code instead of being allowed to abort Setup.

## Native Windows regression gate

`scripts/windows_installer_resilience.ps1` is run by `.github/workflows/windows-installed-acceptance.yml` against the actual newly-built `DiscountParser-Setup.exe`.

It adds two scenarios on the GitHub-hosted Windows runner.

### Scenario A — Unicode install path + lifecycle

The application is installed under a path containing Cyrillic components (`Пользователь-Анастасия`), then the gate requires:

1. initial Setup exit code `0`;
2. installed `DiscountParser.exe` and `DiscountParserWorker.exe`;
3. launching the Desktop `.lnk` through the Windows shell starts the exact `DiscountParser.exe` from the Unicode install path;
4. launching the Start Menu `.lnk` starts that same expected installed executable;
5. in-place reinstall succeeds and both shortcuts still launch the expected executable;
6. uninstall succeeds and removes the product-owned Desktop link;
7. reinstall after uninstall succeeds and recreates working shortcuts;
8. final uninstall succeeds.

The gate deliberately validates shortcuts by launching them and observing the resulting Windows process path instead of relying on the `WScript.Shell` shortcut-property adapter, which can degrade non-ASCII path text on the hosted runner. This does not rename the GitHub-hosted Windows account, but it exercises the Unicode filesystem, shell-link and process-launch path used by the installer.

### Scenario B — forced Desktop shortcut-save failure

The gate deliberately occupies the exact Desktop `Discount Parser.lnk` pathname with a directory before Setup starts. This forces the `CreateShellLink` exception boundary used by the best-effort Desktop shortcut implementation.

Acceptance requires all of the following simultaneously:

- Setup still exits `0`;
- installed application payload remains present;
- Setup log contains the DP-WIN-P0.2 best-effort failure marker;
- the Start Menu shortcut still launches the installed `DiscountParser.exe` from the expected install directory;
- uninstall succeeds after the synthetic blocker is removed.

The test does not depend on one particular HRESULT. The contract being tested is that a Desktop `CreateShellLink` failure is non-fatal to the application payload.

## Acceptance evidence

PR #20 was accepted on merge candidate `8115ef2e3fd6a498a9786519a3fa7b502943c641` with branch head `f4283e79043104dd1c4a3a21771fe2aa8811cd69`.

Required workflows all passed before merge:

- normal CI — PASS;
- `build-delivery` — PASS;
- Windows reproducibility — PASS;
- Windows installed acceptance — PASS;
- DP-WIN-P0.2 installer resilience — PASS.

The machine-readable resilience artifact from pre-merge Windows installed acceptance run `32044762853` reported:

- overall `status`: `PASS`;
- tested installer SHA-256: `d5c5cb9340d67d340a2991a9433272247521d6649ded83a63ec362296e1b87f1`;
- `unicode_reinstall_cycle.status`: `PASS`;
- Unicode install path: `...\Пользователь-Анастасия\AppData\Local\DiscountParser`;
- initial install, in-place reinstall, uninstall, reinstall-after-uninstall and final uninstall: exit code `0`;
- Desktop shortcut launch: valid;
- Start Menu shortcut launch: valid;
- Desktop shortcut removed on uninstall: true;
- `blocked_desktop_shortcut.status`: `PASS`;
- forced Desktop failure observed: true;
- Setup exit code under forced failure: `0`;
- installed payload present after the forced failure: true;
- Start Menu launch path remained valid: true;
- forced Desktop failure classified non-fatal: true;
- scenario uninstall exit code: `0`.

PR #20 was then merged to canonical `main` as `4fa6eb03e4bcdd39e3a4db8e9c45378552c07541`.

### Canonical `main` revalidation

The exact canonical merge commit was rebuilt and re-tested after merge, not merely trusted from the pull-request merge candidate:

- main CI run `32045221339` — PASS;
- main Windows reproducibility run `32045221352` — PASS;
- main Windows installed acceptance run `32045221366` — PASS;
- DP-WIN-P0.2 resilience step inside that installed-acceptance run — PASS.

The canonical-main machine-readable resilience evidence has `source_sha` exactly `4fa6eb03e4bcdd39e3a4db8e9c45378552c07541` and reports:

- overall `status`: `PASS`;
- canonical-main tested installer SHA-256: `290eebaadfa5e2479b301fdc678e5059c8396040d505be453626d7957b8bb31f`;
- `unicode_reinstall_cycle.status`: `PASS`;
- all five install/reinstall/uninstall lifecycle exit codes: `0`;
- Desktop and Start Menu shortcut launches: valid;
- Desktop shortcut cleanup on uninstall: true;
- `blocked_desktop_shortcut.status`: `PASS`;
- forced Desktop shortcut failure observed: true;
- Setup under forced shortcut failure: exit code `0`;
- installed payload retained: true;
- Start Menu launch remained valid: true;
- Desktop failure classified non-fatal: true;
- uninstall exit code: `0`.

## Regression protection

`tests/test_windows_installed_acceptance.py` statically enforces that:

- no Desktop constant appears in `[Icons]`;
- Start Menu remains in `[Icons]`;
- Desktop task selection, executable existence check, `CreateShellLink`, `try..except`, log marker and uninstall cleanup remain present;
- the resilience harness actually launches shortcuts and binds the observed `DiscountParser.exe` process to the expected install path;
- the Windows workflow actually executes and uploads evidence from the resilience gate.

Existing DP-CI-001 reproducibility and DP-CI-002 installed runtime acceptance continue to protect the installer.

## Definition of done

All DP-WIN-P0.2 engineering criteria are satisfied:

1. normal CI passed before and after merge;
2. reproducible Windows build gate passed before and after merge;
3. installed Windows acceptance passed before and after merge;
4. DP-WIN-P0.2 resilience evidence reported `PASS` for both scenarios on canonical `main`;
5. the hotfix was merged to canonical `main`;
6. the hardening roadmap marks DP-WIN-P0.2 COMPLETE.

A new physical customer-machine install remains the later **DP-WIN-001** acceptance gate. It is not a prerequisite for the completed deterministic installer fix.

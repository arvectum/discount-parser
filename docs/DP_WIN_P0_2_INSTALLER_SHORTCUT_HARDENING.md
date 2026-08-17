# DP-WIN-P0.2 — Installer shortcut/rollback hardening

**Priority:** P0 — customer-blocking Windows delivery defect  
**Status:** IMPLEMENTED — native Windows CI acceptance required before merge  
**Customer evidence:** feedback #3, 2026-08-17

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

This directly covers the customer failure boundary because Inno Setup documents `CreateShellLink` as raising an exception when shortcut creation fails. The installer catches that exception instead of allowing it to abort Setup.

## Native Windows regression gate

`scripts/windows_installer_resilience.ps1` is run by `.github/workflows/windows-installed-acceptance.yml` against the actual newly-built `DiscountParser-Setup.exe`.

It adds two scenarios on the GitHub-hosted Windows runner.

### Scenario A — Unicode install path + lifecycle

The application is installed under a path containing Cyrillic components (`Пользователь-Анастасия`), then the gate requires:

1. initial Setup exit code `0`;
2. installed `DiscountParser.exe` and `DiscountParserWorker.exe`;
3. Desktop `.lnk` target and working directory resolve to the installed Unicode path;
4. Start Menu `.lnk` target and working directory resolve to the same executable/path;
5. in-place reinstall succeeds and both links remain valid;
6. uninstall succeeds and removes the product-owned Desktop link;
7. reinstall after uninstall succeeds and recreates valid links;
8. final uninstall succeeds.

This does not rename the GitHub-hosted Windows account, but it exercises the same Unicode filesystem/link-target APIs implicated by a Cyrillic user profile.

### Scenario B — forced Desktop shortcut-save failure

The gate deliberately occupies the exact Desktop `Discount Parser.lnk` pathname with a directory before Setup starts. This forces the Inno `CreateShellLink` call to raise through the same exception boundary as a shell/ACL save failure.

Acceptance requires all of the following simultaneously:

- Setup still exits `0`;
- installed application payload remains present;
- Setup log contains the DP-WIN-P0.2 best-effort failure marker;
- the Start Menu shortcut still exists and points at the installed `DiscountParser.exe`;
- uninstall succeeds after the synthetic blocker is removed.

The test does not depend on the exact HRESULT produced by the synthetic collision; the contract being tested is that **any** `CreateShellLink` exception, including customer `0x80070005`, is non-fatal.

## Regression protection

`tests/test_windows_installed_acceptance.py` statically enforces that:

- no Desktop constant appears in `[Icons]`;
- Start Menu remains in `[Icons]`;
- Desktop task selection, executable existence check, `CreateShellLink`, `try..except`, log marker and uninstall cleanup remain present;
- the Windows workflow actually executes and uploads evidence from the resilience gate.

Existing DP-CI-001 reproducibility and DP-CI-002 installed runtime acceptance continue to run for the same pull request.

## Definition of done

DP-WIN-P0.2 becomes COMPLETE when:

1. normal CI passes;
2. reproducible Windows build gate passes;
3. installed Windows acceptance passes;
4. DP-WIN-P0.2 resilience evidence reports `PASS` for both scenarios;
5. the hotfix is merged to canonical `main`;
6. the hardening roadmap is updated from P0 IN PROGRESS to COMPLETE.

A new physical customer-machine install is the later **DP-WIN-001** acceptance gate, not a prerequisite for merging this deterministic installer fix.

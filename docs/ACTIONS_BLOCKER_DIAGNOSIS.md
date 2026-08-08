# GitHub Actions blocker diagnosis

## Observed behaviour

- Repository visibility: private.
- Repository owner has admin permission.
- Workflow re-run requests are accepted by GitHub.
- Ubuntu, Windows, macOS ARM64 and macOS Intel jobs all fail before the first workflow step.
- GitHub returns `steps=null` for those failed jobs and no job logs/artifacts are produced.
- A manual retry reproduces the same pre-step failure.
- GitHub Status reports Actions operational at the time of diagnosis.
- After workflow optimization, a fresh PR triggered exactly one automatic Ubuntu job; the cross-platform job was correctly skipped, but the Ubuntu job still failed before checkout with `steps=null`.

This proves the failure occurs before repository checkout and before any project code, Python dependency, pytest, Alembic or PyInstaller command runs.

## Account-level cause

For a private repository, GitHub-hosted runners consume the account's Actions allowance/budget. The repository previously ran a four-OS CI matrix plus three delivery builds on frequent pushes, so hosted-runner quota/budget exhaustion is the operative blocker.

The project workflows were changed to prevent recurrence:

- automatic push/PR CI now runs only Ubuntu;
- Windows and both macOS test jobs run only from `workflow_dispatch`;
- delivery builds no longer run on every push or pull request; they run manually or on version tags.

## Quota-independent fallback

Project QA and delivery are no longer dependent on GitHub-hosted runners:

```bash
python scripts/preflight.py
```

Local platform builds:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

```bash
bash scripts/build_macos.sh
```

These run compile/tests/migration/Doctor and frozen-package smoke locally.

## Account action required to restore hosted runners

In GitHub account billing settings, verify the Actions usage/budget and either restore available Actions minutes or set a non-zero Actions budget/payment method. Once hosted runners can be allocated again, re-run `ci` and then manually run `build-delivery`.

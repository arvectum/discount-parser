# Repository-only batch acceptance

Required before merge:

1. `ci` succeeds on all configured operating-system jobs.
2. `build-delivery` succeeds, including Windows installer packaging.
3. Windows reproducibility succeeds.
4. Windows installed acceptance succeeds, including the DP-WIN-P0.2 installer resilience gate.
5. New security, recovery, portability, parser-corpus and data-quality tests all execute in ordinary CI.

After those gates pass, the roadmap may mark DP-SEC-001 through DP-DOC-002 COMPLETE. The next task is physical DP-WIN-001, which is intentionally not executed in GitHub Actions.

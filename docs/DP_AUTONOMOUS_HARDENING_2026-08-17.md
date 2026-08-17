# Autonomous hardening batch — 2026-08-17

This batch executes the repository-only roadmap segment after DP-OBS-001 and before the first physical Windows gate.

Included tasks:

- DP-SEC-001 / issue #23 — local mutation boundary and secret redaction;
- DP-REC-001 / issue #24 — self-service SQLite status/backup/recovery;
- DP-REC-002 / issue #25 — versioned secret-free settings portability;
- DP-QA-001 / issue #26 — versioned offline parser corpus for all five production HTML adapters;
- DP-QA-002 / issue #27 — data-quality regression matrix;
- DP-DOC-001 / issue #28 — Russian customer manual;
- DP-DOC-002 / issue #29 — Russian troubleshooting guide.

The batch is accepted only when normal multi-platform CI, build-delivery, Windows reproducibility and Windows installed acceptance all pass. No physical customer-machine action is part of this batch. The explicit stop point after merge is DP-WIN-001 / issue #31.

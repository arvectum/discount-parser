# R2 — Offer domain + persistence

Статус: **DONE**  
Дата: **2026-08-08**

## Реализовано

- SQLAlchemy 2.x persistence foundation;
- SQLite configuration with WAL, `busy_timeout=30000` and foreign keys;
- `DP_DATABASE_URL`, default `sqlite:///./discount_parser.db`;
- Alembic configuration and initial revision `0001`;
- entities:
  - `Source`;
  - `Offer`;
  - `OfferSourceObservation`;
  - `ParseRun`;
  - `ClassificationRule`;
  - `ManualOverride`;
  - `Publication`;
  - `PublishFilter`;
- offer type/status database constraints;
- parse-run and publication status constraints;
- indexes for status/category/validity/canonical URL/fingerprint;
- exact source observation uniqueness by `source_id + external_id`;
- publication idempotency constraint `offer_id + channel_id`;
- `OfferRepository` CRUD;
- manual override protection against later automatic updates;
- `GET /health/db`;
- persistence regression tests;
- CI workflow with pytest + Alembic smoke gate.

## Database initialization

```bash
alembic upgrade head
```

Schema revision:

```text
0001
```

## R2 gate verification

Locally reproduced persistence smoke covered:

- initial migration into an empty SQLite database;
- expected table set;
- create/read/update Offer;
- manual category override remains intact after automatic update attempt;
- duplicate publication to the same channel is rejected by the DB;
- SQLite runtime reports `journal_mode=wal`;
- foreign keys are enabled;
- busy timeout is 30000 ms.

Automated equivalents are committed in `tests/test_persistence.py` and `.github/workflows/ci.yml`.

## Next

R3 — Source SDK + first end-to-end parser slice.

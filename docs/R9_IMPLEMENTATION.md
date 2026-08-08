# R9 — QA, demo, packaging, delivery

Статус: **IN PROGRESS — automated QA foundation implemented; external live smoke pending**  
Дата: **2026-08-08**

## Automated QA foundation

GitHub Actions CI выполняет:

```text
clean checkout
→ Python 3.11
→ pip install -e .[dev]
→ compileall src/tests
→ pytest
→ Alembic upgrade from empty SQLite
→ database connectivity smoke
→ CLI entrypoint smoke
```

Проверяются CLI-команды:

- root `--help`;
- `parse --help`;
- `maintenance --help`;
- `scheduler --help`;
- `bot --help`.

## Delivery evidence

Добавлен `src.qa.report`:

- `build_smoke_report()`;
- `write_smoke_report()`.

CLI:

```bash
python -m src.cli smoke-report
python -m src.cli smoke-report --output output/smoke_report.json
```

JSON report включает:

- число sources;
- total/ready/needs_review/published/expired offers;
- publication counts;
- ParseRun count;
- latest Telegram message id;
- latest status/last success/last error/counters каждого source.

`tests/test_qa_report.py` проверяет формирование и запись delivery evidence.

## Уже покрытые regression suites

- R1 app/settings/health/logging;
- R2 persistence/migration/WAL/manual override/publication uniqueness;
- R3/R4 source parsing/idempotency/dedup/classification;
- R5 adapter fixtures + source isolation;
- R6 lifecycle + scheduler;
- R7 publication selection/rendering/idempotency/non-ready protection;
- R8 XLSX export/import/rule-memory roundtrip;
- R9 smoke-report generation.

## Что ещё требуется для полного MVP DONE

Эти проверки зависят от реальной runtime-среды и внешних credentials:

1. clean dependency install в CI/целевой машине;
2. полный `python -m pytest` с актуальными dependencies;
3. live smoke всех 5 источников в текущем интернете;
4. реальный Telegram bot polling startup;
5. реальный channel publication;
6. подтверждение сохранённого `telegram_message_id`;
7. live scheduler restart/recovery smoke;
8. финальный `output/smoke_report.json` после live прогона.

До выполнения этих пунктов R9 и общий MVP не помечаются как полностью DONE.

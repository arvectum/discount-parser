# R9 — QA, demo, packaging, delivery

Статус: **FINAL AUTOMATED QA GATE — live external smoke remains credential-dependent**  
Дата: **2026-08-08**

## Automated QA gate

GitHub Actions CI выполняет на Python 3.11:

```text
clean checkout
→ dependency install
→ compileall src/tests
→ full pytest
→ Alembic upgrade from empty SQLite
→ database connectivity smoke
→ CLI entrypoint smoke
```

Обычный test matrix:

- Ubuntu x64;
- Windows x64;
- macOS ARM64;
- macOS Intel.

Проверяются CLI-команды:

- root `--help`;
- `parse --help`;
- `maintenance --help`;
- `scheduler --help`;
- `bot --help`;
- `run --help`;
- `web --help`;
- `smoke-report --help`.

## Delivery build gate

`build-delivery` отдельно собирает frozen packages:

- Windows x64 — PyInstaller + `DiscountParser-Setup.exe`;
- macOS ARM64 — frozen application + installer launcher;
- macOS Intel — frozen application + installer launcher.

Для каждой frozen-сборки выполняется migration smoke через уже собранный executable.

Windows installer создаёт локальную установку и ярлык. macOS update installer сохраняет пользовательские `.env` и `discount_parser.db`.

## Web client surface

Клиентская web-панель включает:

- first-run Telegram setup wizard;
- parser / bot / scheduler controls;
- persisted source enable/disable;
- schedule settings;
- publication filter and queue;
- manual publish/reject;
- XLSX export/import;
- offers browser with filters/search/detail page;
- ParseRun journal and error details.

## Publication safety

Publication ledger обеспечивает conservative at-most-once semantics. Reservation создаётся до Telegram network call со schema-valid статусом `pending`, затем переводится в `published` или `failed`.

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

## Regression coverage

- R1 app/settings/health/logging;
- R2 persistence/migration/WAL/manual override/publication uniqueness;
- R3/R4 source parsing/idempotency/dedup/classification;
- R5 adapter fixtures + source isolation;
- R6 lifecycle + scheduler;
- R7 publication selection/rendering/idempotency/non-ready protection;
- R8 XLSX export/import/rule-memory roundtrip;
- web setup, schedule, source state and management pages;
- R9 smoke-report generation and cross-platform delivery build configuration.

## External live acceptance gate

Следующие проверки невозможно достоверно выполнить без реальных runtime credentials и сетевого окружения заказчика:

1. live HTTP parse всех включённых источников;
2. реальный Telegram bot polling startup;
3. реальная публикация в тестовый Telegram-канал;
4. подтверждение сохранённого `telegram_message_id`;
5. live scheduler/autopost smoke;
6. финальный smoke report после live прогона.

Автоматизированный кодовый/delivery gate и внешний live acceptance считаются разными воротами. R9 можно помечать `CODE/DISTRIBUTION DONE` только после зелёных CI + delivery jobs; полный production acceptance — после внешнего live smoke.

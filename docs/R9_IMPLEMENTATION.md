# R9 — QA, demo, packaging, delivery

Статус: **CODE/DISTRIBUTION IMPLEMENTATION COMPLETE — execution acceptance remains external**  
Дата: **2026-08-08**

## Итог по реализации

Кодовый и клиентский delivery-контур реализован:

- cross-platform Python 3.11 codebase;
- Windows x64 client package + `DiscountParser-Setup.exe`;
- macOS ARM64 package;
- macOS Intel package;
- embedded Python runtime через PyInstaller;
- локальная web-панель и first-run Telegram setup wizard;
- parser / bot / scheduler controls;
- persisted source enable/disable;
- schedule settings;
- publication filters, queue, manual publish/reject;
- XLSX export/import;
- offers browser и ParseRun journal;
- System page с PID, bot/scheduler logs и graceful user-facing shutdown;
- single-instance web launcher;
- DB/settings-preserving update behavior;
- publication ledger reservation использует schema-valid `pending` state.

## Automated QA configuration

GitHub Actions CI настроен на Python 3.11 для:

- Ubuntu x64;
- Windows x64;
- macOS ARM64;
- macOS Intel.

Пайплайн должен выполнять:

```text
clean checkout
→ dependency install
→ compileall src/tests
→ full pytest
→ Alembic upgrade from empty SQLite
→ database connectivity smoke
→ CLI entrypoint smoke
```

Проверяются CLI-команды:

- root `--help`;
- `parse --help`;
- `maintenance --help`;
- `scheduler --help`;
- `bot --help`;
- `run --help`;
- `web --help`;
- `smoke-report --help`.

## Delivery build configuration

`build-delivery` настроен для:

- Windows x64 — PyInstaller `--noconsole` + Inno Setup `DiscountParser-Setup.exe`;
- macOS ARM64 — frozen runtime + install launcher;
- macOS Intel — frozen runtime + install launcher.

Для каждой frozen-сборки предусмотрен migration smoke уже собранным executable.

## Текущий GitHub Actions execution status

Для финального QA был создан PR-gate и реально запущены `ci` и `build-delivery`.

На повторном прогоне все jobs на Windows, Ubuntu, macOS ARM64 и macOS Intel завершились `failure` **до выполнения первого workflow step**. GitHub API возвращает для jobs `steps = null`, а job logs недоступны. Следовательно, текущий красный статус нельзя интерпретировать как падение `pytest`, compilation, migration или PyInstaller: runner не дошёл до `checkout`.

Это внешний Actions execution blocker уровня GitHub runner/account/repository environment. После восстановления исполнения Actions достаточно повторно запустить существующие workflows; дополнительных изменений в самих gate definitions для старта тестов не требуется.

До фактического выполнения workflow нельзя заявлять `CI green` или `delivery build green`.

## Web client surface

Клиентская web-панель включает:

- first-run Telegram setup wizard;
- автоматический запуск bot/scheduler после первого setup в packaged mode;
- parser / bot / scheduler controls;
- persisted source enable/disable;
- schedule settings;
- publication filter and queue;
- manual publish/reject;
- XLSX export/import;
- offers browser with filters/search/detail page;
- ParseRun journal and error details;
- System page с runtime logs и завершением приложения.

Повторный запуск ярлыка не создаёт второй web server: если локальная панель уже работает, приложение просто открывает её в браузере.

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

## Regression suites

В репозитории присутствуют regression tests для:

- R1 app/settings/health/logging;
- R2 persistence/migration/WAL/manual override/publication uniqueness;
- R3/R4 source parsing/idempotency/dedup/classification;
- R5 adapter fixtures + source isolation;
- R6 lifecycle + scheduler;
- R7 publication selection/rendering/idempotency/non-ready protection;
- R8 XLSX export/import/rule-memory roundtrip;
- web setup, schedule, source state, management pages, system page and single-instance launcher;
- R9 smoke-report generation and cross-platform delivery configuration.

## External live acceptance gate

Следующие проверки по определению зависят от реальных credentials и сетевого окружения заказчика:

1. установка готового OS-specific package на чистой целевой машине;
2. first-run web wizard;
3. live HTTP parse всех включённых источников;
4. реальный Telegram bot polling startup;
5. реальная публикация в тестовый Telegram-канал;
6. подтверждение сохранённого `telegram_message_id`;
7. live scheduler/autopost smoke;
8. sleep/resume и повторный запуск приложения;
9. update-over-existing-install с сохранением `.env` и `discount_parser.db`;
10. финальный smoke report после live прогона.

Для macOS отдельным внешним release-пунктом остаётся Apple signing/notarization, если требуется распространение без Gatekeeper warning.

## Определение DONE

- **Implementation:** DONE.
- **Automated workflow configuration:** DONE.
- **Automated workflow execution:** BLOCKED EXTERNALLY before first step; not green/not red-by-code.
- **Live customer-environment acceptance:** PENDING target machine + Telegram credentials + network.

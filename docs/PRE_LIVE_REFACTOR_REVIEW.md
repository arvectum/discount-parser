# Discount Parser — pre-live refactor review

Дата: 2026-08-08

Статус: **CODE REVIEW COMPLETE — READY FOR TARGET-MACHINE LIVE TESTING**

Этот review выполнен перед первым реальным installer/runtime/Telegram smoke на машине пользователя.

## Что было переработано и усилено

### Настройки и first-run

- `.env` теперь сохраняется атомарно через временный файл и replace;
- значения setup wizard валидируются как однострочные;
- закрыта возможность внедрить дополнительную `.env`-строку через web-форму;
- существующие нецелевые `.env`-параметры сохраняются при обновлении настроек;
- настройки Pydantic сбрасываются из cache после успешной записи.

### Local web security

- web server по-прежнему слушает только `127.0.0.1`;
- добавлен TrustedHost guard;
- mutating browser requests с внешним Origin/Referer блокируются;
- управляющие POST не должны приниматься со стороннего сайта;
- single-instance поведение сохранено.

### Preflight diagnostics

Добавлен Doctor:

```bash
python -m src.cli doctor
```

Он проверяет:

- подключение к БД;
- доступность data directory для записи;
- наличие и структуру `sources.yaml`;
- уникальность source keys;
- наличие каждого adapter в registry;
- Telegram configuration как optional pre-first-run check;
- доступность web port при CLI/frozen preflight.

Doctor отображается также на странице `Система` без проверки уже занятого текущей панелью web port.

### Windows packaging

Windows runtime разделён на два процесса:

```text
DiscountParser.exe
  windowed UI launcher, без консольного окна

DiscountParserWorker.exe
  console worker для migrate / doctor / bot / scheduler
```

Это исключает зависимость background jobs от PyInstaller `--noconsole` standard streams и позволяет нормально писать bot/scheduler logs.

`ProcessManager` в frozen Windows выбирает worker executable автоматически.

### Delivery QA

`build-delivery` должен:

1. собрать Windows UI executable;
2. собрать Windows worker executable;
3. собрать macOS ARM64 package;
4. собрать macOS Intel package;
5. выполнить migration smoke уже frozen executable;
6. выполнить Doctor уже frozen executable;
7. собрать `DiscountParser-Setup.exe` на Windows;
8. сохранить OS-specific artifacts.

### Publication safety

Проверено соответствие модели и publisher:

```text
reserve -> pending
success -> published
network failure -> failed
```

Unique `(offer_id, channel_id)` остаётся защитой от повторной публикации.

### Source isolation

Проверено:

- exception adapter collection одного source записывается как failed ParseRun;
- row-level error оборачивается nested transaction;
- ошибки одной записи не откатывают весь source run;
- `run_all` продолжает следующие sources;
- persisted `Source.enabled` используется как runtime override поверх YAML default.

### Scheduler

Проверено:

- collection / maintenance / autopost имеют отдельные jobs;
- `max_instances=1`;
- `coalesce=True`;
- scheduler использует settings после restart из web UI;
- изменение расписания через web UI перезапускает scheduler.

### Update safety

Проверено:

- Windows installer копирует app поверх существующей установки без удаления пользовательской БД;
- macOS installer больше не очищает installation directory перед copy;
- `.env` и `discount_parser.db` сохраняются при update-in-place;
- enabled/disabled source state хранится в SQLite.

## Regression tests, добавленные в финальном refactor

- atomic `.env` persistence;
- preservation unrelated `.env` keys;
- multiline env injection rejection;
- Doctor optional Telegram semantics;
- Doctor missing source config;
- Doctor unknown adapter;
- Doctor JSON report;
- Doctor on System page;
- local Origin guard;
- TrustedHost rejection;
- repeated web launch single-instance behavior;
- Windows worker executable selection.

## Что намеренно не считается проверенным до live запуска

Кодовый review не может заменить следующие проверки:

1. реальные HTTP-ответы всех 5 внешних сайтов;
2. актуальную устойчивость HTML selectors к текущей разметке сайтов;
3. Telegram Bot Token;
4. Telegram polling на реальном аккаунте;
5. права бота в реальном канале;
6. реальную Telegram publication;
7. сохранение фактического `telegram_message_id`;
8. реальный scheduler/autopost cycle;
9. поведение sleep/resume конкретного ноутбука;
10. фактическую frozen build на GitHub runner или локальной build machine.

## GitHub Actions execution blocker

Workflow definitions подготовлены для CI и delivery matrix. Однако в текущем GitHub environment ранее все jobs завершались до первого workflow step (`steps=null`) на Windows/Linux/macOS. Это классифицировано как внешний runner/account execution blocker, а не как pytest/build failure.

До восстановления GitHub Actions зелёный CI заявлять нельзя.

## Следующий этап

Следующий этап — не дальнейшее изменение архитектуры, а последовательный live acceptance по `docs/FINAL_ACCEPTANCE_CHECKLIST.md`:

```text
install
→ Doctor
→ open UI
→ setup wizard
→ one source live parse
→ all sources live parse
→ Telegram polling
→ one manual publication
→ publication ledger verification
→ scheduler/autopost smoke
→ XLSX roundtrip
→ update/sleep-resume checks
→ final smoke report
```

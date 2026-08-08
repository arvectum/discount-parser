# R6 — Offer lifecycle + scheduler

Статус: **DONE**  
Дата: **2026-08-08**

## Реализовано

- APScheduler 3.x;
- отдельный jobs package;
- interval job `collect_sources`;
- cron job `maintenance`, по умолчанию 22:00;
- `max_instances=1` + `coalesce=True` для single-instance idempotency;
- configurable timezone;
- configurable collection interval;
- configurable source config path;
- configurable stale policy;
- явное истечение по `valid_until` без удаления истории;
- conservative stale policy для предложений без даты;
- failed source run сам по себе не переводит offer в stale/expired;
- source run status service;
- `GET /health/sources`;
- CLI `maintenance`;
- CLI `scheduler`;
- ускоряемый background scheduler для тестов.

## Lifecycle policy

### Explicit expiry

Offer со статусом `new`, `ready` или `needs_review` и `valid_until < now` переводится в `expired`.

`published` и `rejected` автоматический expiry job не переписывает.

### Undated/stale offers

Для Offer без `valid_until` используется консервативная политика:

1. `last_seen_at` должен быть старше `DP_STALE_AFTER_DAYS`;
2. для каждого provenance source должен существовать более новый `ParseRun` со статусом `success` или `partial`;
3. только тогда `new/ready` переводится в `needs_review`.

Таким образом, единичный failed fetch не скрывает актуальное предложение.

## Scheduler defaults

```dotenv
DP_SOURCES_CONFIG_PATH=config/sources.yaml
DP_COLLECT_INTERVAL_MINUTES=120
DP_MAINTENANCE_HOUR=22
DP_MAINTENANCE_MINUTE=0
DP_STALE_AFTER_DAYS=7
```

## CLI

```bash
python -m src.cli parse
python -m src.cli maintenance
python -m src.cli scheduler
```

## Tests / gate

`tests/test_lifecycle_scheduler.py` проверяет:

- past active offer → `expired`;
- future offer остаётся active;
- published offer не переписывается maintenance;
- failed source run не вызывает stale transition;
- более свежий successful run переводит пропавший undated offer в `needs_review`;
- accelerated scheduler реально запускает collection job повторно;
- collection/maintenance jobs имеют `max_instances=1`.

Дополнительно `/health/sources` использует сохранённые `ParseRun` и выдаёт last status / last success / last error для каждого Source.

## Gate R6

R6 считается выполненным, когда scheduler может постоянно выполнять parsing + maintenance, повторные parsing runs остаются идемпотентными за счёт R3/R4, explicit expiry работает, а failed fetch не вызывает ложное истечение.

Следующий этап: **R7 — Telegram control plane + publishing**.

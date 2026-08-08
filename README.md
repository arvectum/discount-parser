# discount-parser

Парсер скидок, промокодов, кэшбэка и выгодных предложений с нормализацией, дедупликацией и автоматической публикацией в Telegram-канал.

## Статус

**MVP v1.0 — R1–R8 реализованы. R9 QA-контур реализуется; live Telegram smoke требует настроенных credentials.**

## Документация

- [Техническое задание MVP v1.0](docs/TECHNICAL_SPEC_V1.md)
- [Дорожная карта](docs/ROADMAP.md)
- [R1 implementation](docs/R1_IMPLEMENTATION.md)
- [R2 implementation](docs/R2_IMPLEMENTATION.md)
- [R3 implementation](docs/R3_IMPLEMENTATION.md)
- [R4 implementation](docs/R4_IMPLEMENTATION.md)
- [R5 implementation](docs/R5_IMPLEMENTATION.md)
- [R6 implementation](docs/R6_IMPLEMENTATION.md)
- [R7 implementation](docs/R7_IMPLEMENTATION.md)
- [R8 implementation](docs/R8_IMPLEMENTATION.md)

## Реализовано

- FastAPI application factory, конфигурация `DP_*`, logging;
- `/health`, `/health/db`, `/health/sources`;
- SQLAlchemy 2.x + SQLite WAL + Alembic `0001`;
- Offer/Source/provenance/ParseRun/rules/overrides/publications/filters;
- normalization: canonical URL, benefit values, fingerprint, offer type;
- cross-source dedup: URL, promo code, fingerprint, RapidFuzz;
- deterministic taxonomy + DB rules + manual override priority;
- Source SDK, YAML config, HTTP retries/backoff, source/row failure isolation;
- 5 enabled adapters:
  - `promokood` — promokood.ru;
  - `promokodik` — promokodik.ru;
  - `berikod` — berikod.ru;
  - `promokodi_net_ru` — promokodi.net.ru;
  - `promko` — promko.net;
- повторный parsing run обновляет Offer/observation вместо создания exact duplicate;
- APScheduler: collection + maintenance + autopost;
- lifecycle: explicit expiry и conservative stale review;
- Telegram control bot на aiogram 3;
- deny-by-default admin allowlist;
- `/status`, `/sources`, `/new`, `/queue`, `/filter`, `/autopost`;
- filter по скидке/category/subcategory/type, service-level merchant/source filters;
- preview + publish/skip/reject;
- image → text fallback;
- publication ledger с `telegram_message_id` и защитой от дублей;
- XLSX export/import: `active`, `needs_review`, `published`, `expired`, `sources`;
- `/export` и `/import` в Telegram;
- manual category/subcategory overrides + conservative exact-title rule memory;
- smoke-report generator для delivery evidence;
- CLI parse/maintenance/scheduler/bot/smoke-report;
- deterministic fixtures/tests и GitHub Actions CI configuration.

## Установка для разработки

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
```

## Запуск

API:

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Парсер:

```bash
python -m src.cli parse
python -m src.cli parse --source promokood
```

Maintenance/scheduler:

```bash
python -m src.cli maintenance
python -m src.cli scheduler
```

Telegram control bot:

```bash
python -m src.cli bot
```

Для постоянной работы bot polling и scheduler запускаются как два отдельных процесса.

Delivery/smoke report:

```bash
python -m src.cli smoke-report
python -m src.cli smoke-report --output output/smoke_report.json
```

## Проверки

```bash
python -m compileall -q src tests
python -m pytest
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/db
curl http://127.0.0.1:8000/health/sources
```

Swagger доступен по `/docs`.

## Основная конфигурация

```dotenv
DP_APP_NAME=Discount Parser API
DP_ENV=local
DP_DEBUG=false
DP_HOST=127.0.0.1
DP_PORT=8000
DP_LOG_LEVEL=INFO
DP_LOG_FORMAT=plain
DP_TIMEZONE=Europe/Moscow
DP_DATABASE_URL=sqlite:///./discount_parser.db
DP_SOURCES_CONFIG_PATH=config/sources.yaml
DP_COLLECT_INTERVAL_MINUTES=120
DP_MAINTENANCE_HOUR=22
DP_MAINTENANCE_MINUTE=0
DP_STALE_AFTER_DAYS=7
DP_TELEGRAM_BOT_TOKEN=replace_me
DP_TELEGRAM_CHANNEL_ID=@replace_me
DP_TELEGRAM_ADMIN_IDS=123456789
DP_TELEGRAM_DEFAULT_MIN_DISCOUNT=20
DP_AUTOPOST_INTERVAL_MINUTES=30
```

Источники задаются в `config/sources.yaml`, taxonomy — в `config/taxonomy.yaml`.

## Pipeline

```text
источники
  ↓
source adapters
  ↓
нормализация
  ↓
дедупликация
  ↓
классификация
  ↓
SQLite
  ↓
lifecycle / scheduler
  ↓
filters / queue
  ↓
Telegram bot / autopost
  ↓
Telegram channel
  ↓
publication ledger
  ↓
XLSX correction / rule memory
```

Реализация ведётся по этапам `R1–R9` из дорожной карты.

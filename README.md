# discount-parser

Парсер скидок, промокодов, кэшбэка и выгодных предложений с нормализацией, дедупликацией и автоматической публикацией в Telegram-канал.

## Статус

**MVP v1.0 — R3 Source SDK + first parser slice завершён.**

Следующий этап: **R4 — normalization, deduplication and classification**.

## Документация

- [Техническое задание MVP v1.0](docs/TECHNICAL_SPEC_V1.md)
- [Дорожная карта](docs/ROADMAP.md)
- [R1 implementation](docs/R1_IMPLEMENTATION.md)
- [R2 implementation](docs/R2_IMPLEMENTATION.md)
- [R3 implementation](docs/R3_IMPLEMENTATION.md)

## Реализовано

- FastAPI application factory `src.app.create_app`;
- конфигурация `DP_*`, logging, `/health`, `/health/db`;
- SQLAlchemy 2.x + SQLite WAL + Alembic `0001`;
- Offer/Source/provenance/ParseRun/rules/overrides/publications/filters;
- manual override protection и publication idempotency;
- Source SDK: `RawOffer`, adapter registry, YAML config, HTTP retries/backoff;
- первый реальный adapter `promokood`;
- source runner с isolation ошибок и ParseRun counters;
- повторный parsing run обновляет observation вместо создания exact duplicate;
- CLI для запуска одного или всех источников;
- pytest fixtures/tests и GitHub Actions CI.

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

## Запуск API

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

## Запуск парсера

```bash
python -m src.cli parse
python -m src.cli parse --source promokood
```

## Проверки

```bash
python -m pytest
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/db
```

Swagger доступен по `/docs`.

## Конфигурация

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
```

Источники задаются в `config/sources.yaml`.

## Целевой pipeline

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
фильтры / очередь
  ↓
Telegram bot
  ↓
Telegram channel
```

Реализация ведётся по этапам `R1–R9` из дорожной карты.

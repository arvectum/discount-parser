# discount-parser

Парсер скидок, промокодов, кэшбэка и выгодных предложений с нормализацией, дедупликацией и автоматической публикацией в Telegram-канал.

## Статус

**MVP v1.0 — R2 Offer domain + persistence завершён.**

Следующий этап: **R3 — Source SDK + first end-to-end parser slice**.

## Документация

- [Техническое задание MVP v1.0](docs/TECHNICAL_SPEC_V1.md)
- [Дорожная карта](docs/ROADMAP.md)
- [R1 implementation](docs/R1_IMPLEMENTATION.md)
- [R2 implementation](docs/R2_IMPLEMENTATION.md)

## Реализовано

- FastAPI application factory `src.app.create_app`;
- ASGI entry point `src.main:app`;
- конфигурация `DP_*` через pydantic-settings;
- plain/JSON logging foundation;
- `GET /health` и `GET /health/db`;
- SQLAlchemy 2.x persistence;
- SQLite WAL + foreign keys + busy timeout;
- Alembic schema revision `0001`;
- доменные сущности Offer/Source/provenance/ParseRun/rules/overrides/publications/filters;
- manual override protection;
- publication idempotency constraint;
- pytest persistence tests и GitHub Actions CI.

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

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Проверка:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/db
```

Swagger доступен по `/docs`.

## Тесты

```bash
python -m pytest
```

## Конфигурация

См. `.env.example`. Основные параметры:

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

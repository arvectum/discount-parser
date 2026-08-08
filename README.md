# discount-parser

Парсер скидок, промокодов, кэшбэка и выгодных предложений с нормализацией, дедупликацией и автоматической публикацией в Telegram-канал.

## Статус

**MVP v1.0 — R5 Source pack MVP завершён.**

Следующий этап: **R6 — offer lifecycle + scheduler**.

## Документация

- [Техническое задание MVP v1.0](docs/TECHNICAL_SPEC_V1.md)
- [Дорожная карта](docs/ROADMAP.md)
- [R1 implementation](docs/R1_IMPLEMENTATION.md)
- [R2 implementation](docs/R2_IMPLEMENTATION.md)
- [R3 implementation](docs/R3_IMPLEMENTATION.md)
- [R4 implementation](docs/R4_IMPLEMENTATION.md)
- [R5 implementation](docs/R5_IMPLEMENTATION.md)

## Реализовано

- FastAPI application factory, конфигурация `DP_*`, logging, `/health`, `/health/db`;
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
- CLI для запуска одного или всех источников;
- deterministic HTML fixtures/tests и GitHub Actions CI.

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

Источники задаются в `config/sources.yaml`, taxonomy — в `config/taxonomy.yaml`.

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

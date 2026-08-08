# discount-parser

Парсер скидок, промокодов, кэшбэка и выгодных предложений с нормализацией, дедупликацией и автоматической публикацией в Telegram-канал.

## Статус

**MVP v1.0 — R1 Project foundation завершён.**

Следующий этап: **R2 — Offer domain + persistence**.

## Документация

- [Техническое задание MVP v1.0](docs/TECHNICAL_SPEC_V1.md)
- [Дорожная карта](docs/ROADMAP.md)

## Реализовано в R1

- FastAPI application factory `src.app.create_app`;
- ASGI entry point `src.main:app`;
- конфигурация `DP_*` через pydantic-settings;
- plain/JSON logging foundation;
- `GET /health`;
- pytest setup и базовые тесты;
- структура `src/app`, `src/shared`, `src/modules`.

Persistence, source adapters и Telegram относятся к следующим этапам roadmap.

## Установка для разработки

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

## Запуск

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Проверка:

```bash
curl http://127.0.0.1:8000/health
```

`/health` возвращает `status=ok`. Swagger доступен по `/docs`.

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
```

`DP_LOG_FORMAT` поддерживает `plain` и `json`.

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

## Основные принципы

- подключаемые адаптеры вместо монолитного парсера;
- SQLite является source of truth, XLSX/CSV — экспортом и интерфейсом ручной корректировки;
- истёкшие предложения сохраняются в истории;
- повторный парсинг и повторные jobs должны быть идемпотентными;
- ручные корректировки имеют приоритет над автоматической классификацией;
- ошибка одного источника не останавливает остальные;
- первая версия не зависит от LLM и не пытается обходить CAPTCHA/anti-bot.

Реализация ведётся по этапам `R1–R9` из дорожной карты.

# R1 — Project foundation

Статус: **DONE**  
Дата: **2026-08-08**

## Scope

R1 создаёт минимальный запускаемый каркас приложения без persistence, source adapters, scheduler и Telegram. Эти компоненты остаются в R2+ согласно roadmap.

## Реализовано

- `pyproject.toml` с Python 3.11+, runtime/dev dependencies и pytest config;
- структура `src/app`, `src/shared`, `src/modules`;
- FastAPI application factory `src.app.create_app`;
- ASGI entry point `src.main:app`;
- `pydantic-settings` configuration с prefix `DP_`;
- `.env.example`;
- plain и JSON logging foundation;
- `GET /health`;
- `.gitignore`;
- pytest tests для health/OpenAPI/settings/logging;
- dev-start документация в README.

## Gate evidence

Проверочный R1 snapshot был воспроизведён в чистом временном каталоге с тем же набором исходных файлов и запущен командой:

```bash
python -m pytest -q
```

Результат:

```text
5 passed
```

Покрытые проверки:

1. `/health` возвращает HTTP 200 и `status=ok`;
2. application factory принимает test settings;
3. OpenAPI endpoint доступен;
4. переменные `DP_*` читаются Settings;
5. plain/JSON logging configuration работает.

## Команды пользователя

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m pytest
uvicorn src.main:app --reload
```

После запуска:

- health: `http://127.0.0.1:8000/health`;
- Swagger UI: `http://127.0.0.1:8000/docs`.

## Architectural boundary

В R1 намеренно отсутствуют:

- SQLAlchemy/Alembic;
- SQLite database;
- Offer models;
- source adapters;
- parser runner;
- scheduler;
- Telegram bot.

Это предотвращает смешивание foundation с доменным/persistence-кодом и сохраняет границу R1/R2 из зафиксированной дорожной карты.

## Следующий этап

**R2 — Offer domain + persistence.**

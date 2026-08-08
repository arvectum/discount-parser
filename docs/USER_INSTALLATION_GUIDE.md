# Discount Parser — пользовательская инструкция по установке и запуску

Документ предназначен для пользователя, который получает готовый проект и хочет запустить парсер и Telegram-бот без изменения исходного кода.

## 1. Поддерживаемые операционные системы

Проект рассчитан на:

- Windows 10/11;
- macOS;
- Linux.

Основной код одинаковый для всех систем. Отличаются только команды активации виртуального окружения, копирования `.env` и способ постоянного запуска процессов.

Минимальное требование: Python 3.11 или новее.

Совместимость проекта автоматически проверяется GitHub Actions на трёх окружениях:

- `windows-latest` + Python 3.11;
- `macos-latest` + Python 3.11;
- `ubuntu-latest` + Python 3.11.

На каждой ОС CI выполняет установку зависимостей, `compileall`, весь набор pytest-тестов, Alembic migration smoke и проверку CLI-команд. Это позволяет использовать один и тот же код независимо от ОС заказчика.

## 2. Что необходимо заранее

Перед установкой подготовьте:

1. компьютер или сервер с Windows/macOS/Linux;
2. Python 3.11+;
3. Git;
4. доступ к репозиторию проекта;
5. Telegram-бота, созданного через BotFather;
6. Telegram-канал, куда будут публиковаться предложения;
7. Telegram user ID администратора, который будет управлять ботом.

Telegram-бот должен быть добавлен администратором в канал и иметь право публиковать сообщения.

## 3. Проверка Python и Git

Откройте терминал.

### Windows PowerShell

```powershell
python --version
git --version
```

Если команда `python` не найдена, попробуйте:

```powershell
py --version
```

### macOS / Linux

```bash
python3 --version
git --version
```

Версия Python должна быть 3.11 или выше.

## 4. Скачивание проекта

Перейдите в папку, где хотите хранить программу, и выполните:

```bash
git clone https://github.com/arutyunoveth/discount-parser.git
cd discount-parser
```

Для приватного репозитория GitHub может запросить авторизацию.

## 5. Создание виртуального окружения

### Windows PowerShell

Если используется команда `python`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Если Python запускается командой `py`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

После активации в начале строки PowerShell обычно появляется `(.venv)`.

Если Windows запрещает запуск `Activate.ps1`, для текущего пользователя можно выполнить:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

После этого снова выполните:

```powershell
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

После активации в начале строки терминала обычно появляется `(.venv)`.

## 6. Установка зависимостей

После активации виртуального окружения команда одинакова для Windows, macOS и Linux:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## 7. Создание файла настроек

В корне проекта есть `.env.example`. Нужно создать рядом файл `.env`.

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Откройте `.env` в любом текстовом редакторе.

Основные параметры:

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
DP_TELEGRAM_BOT_TOKEN=PASTE_BOT_TOKEN_HERE
DP_TELEGRAM_CHANNEL_ID=@your_channel
DP_TELEGRAM_ADMIN_IDS=123456789
DP_TELEGRAM_DEFAULT_MIN_DISCOUNT=20
DP_AUTOPOST_INTERVAL_MINUTES=30
```

Замените:

- `PASTE_BOT_TOKEN_HERE` — на токен Telegram-бота;
- `@your_channel` — на username канала или поддерживаемый Telegram chat ID;
- `123456789` — на Telegram user ID администратора.

Не публикуйте файл `.env` и не отправляйте токен бота посторонним.

## 8. Создание базы данных

В активированном виртуальном окружении выполните:

```bash
alembic upgrade head
```

По умолчанию рядом с проектом будет создана SQLite-база:

```text
discount_parser.db
```

Дополнительно проверка базы:

```bash
python -m src.cli smoke-report
```

## 9. Первый запуск парсера

Запустите сбор предложений:

```bash
python -m src.cli parse
```

Парсер обработает все включённые источники из `config/sources.yaml`.

Для запуска только одного источника:

```bash
python -m src.cli parse --source promokood
```

После выполнения данные сохраняются в SQLite.

## 10. Запуск Telegram-бота

Откройте отдельный терминал, перейдите в папку проекта и снова активируйте `.venv`.

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
python -m src.cli bot
```

### macOS / Linux

```bash
source .venv/bin/activate
python -m src.cli bot
```

Терминал с ботом должен оставаться запущенным.

В Telegram доступны основные команды:

- `/status` — состояние базы и очереди;
- `/sources` — состояние источников;
- `/new` — новые предложения;
- `/queue` — предложения, готовые к публикации;
- `/filter` — фильтр публикации;
- `/autopost` — включение/выключение автопостинга;
- `/export` — экспорт XLSX;
- `/import` — импорт исправленного XLSX.

## 11. Запуск автоматического расписания

Для автоматического парсинга, обслуживания базы и автопостинга требуется второй постоянно работающий процесс.

Откройте ещё один терминал и активируйте `.venv`.

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
python -m src.cli scheduler
```

### macOS / Linux

```bash
source .venv/bin/activate
python -m src.cli scheduler
```

Таким образом для полной автоматической работы обычно запущены два процесса:

```text
python -m src.cli bot
python -m src.cli scheduler
```

`bot` отвечает за Telegram-интерфейс. `scheduler` запускает парсинг, maintenance и autopost по расписанию.

## 12. Рекомендуемый первый запуск

Для первого теста не включайте автопостинг сразу.

Последовательность:

```text
1. alembic upgrade head
2. python -m src.cli parse
3. python -m src.cli bot
4. открыть Telegram-бота
5. выполнить /status
6. выполнить /sources
7. выполнить /new или /queue
8. проверить несколько карточек
9. вручную нажать «Опубликовать»
10. проверить сообщение в тестовом канале
11. только после этого включить /autopost
12. запустить python -m src.cli scheduler
```

## 13. Проверка состояния программы

### CLI smoke report

```bash
python -m src.cli smoke-report
```

### API

API необязателен для обычной работы, но удобен для диагностики.

Запуск:

```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Откройте в браузере:

```text
http://127.0.0.1:8000/docs
```

Проверочные endpoints:

```text
/health
/health/db
/health/sources
```

## 14. Работа с Excel

В Telegram выполните:

```text
/export
```

Бот отправит `offers.xlsx`.

Основные листы:

- `active`;
- `needs_review`;
- `published`;
- `expired`;
- `sources`.

Для ручной корректировки изменяйте только поля:

```text
category
subcategory
```

После изменения отправьте файл боту через `/import`.

Ручные изменения сохраняются как manual override и не должны быть затёрты следующим автоматическим парсингом.

## 15. Как остановить программу

В терминале, где работает бот или scheduler, нажмите:

```text
Ctrl+C
```

## 16. Как запустить программу после перезагрузки компьютера

После перезагрузки заново устанавливать зависимости не требуется.

Нужно перейти в папку проекта, активировать `.venv` и запустить процессы.

### Windows PowerShell

```powershell
cd C:\path\to\discount-parser
.\.venv\Scripts\Activate.ps1
python -m src.cli bot
```

Во втором окне:

```powershell
cd C:\path\to\discount-parser
.\.venv\Scripts\Activate.ps1
python -m src.cli scheduler
```

### macOS / Linux

```bash
cd /path/to/discount-parser
source .venv/bin/activate
python -m src.cli bot
```

Во втором окне:

```bash
cd /path/to/discount-parser
source .venv/bin/activate
python -m src.cli scheduler
```

Для промышленного постоянного запуска позже рекомендуется оформить процессы как Windows Service / Task Scheduler на Windows или LaunchAgent/systemd на macOS/Linux.

## 17. Обновление проекта

Остановите бот и scheduler, затем в папке проекта выполните:

```bash
git pull
pip install -e ".[dev]"
alembic upgrade head
```

После этого снова запустите bot и scheduler.

## 18. Типичные проблемы

### `python` не найден

Установите Python 3.11+ и убедитесь, что он добавлен в PATH. На Windows также попробуйте команду `py`.

### `git` не найден

Установите Git и перезапустите терминал.

### `alembic` не найден

Убедитесь, что виртуальное окружение активировано и зависимости установлены:

```bash
pip install -e ".[dev]"
```

### Telegram-бот отвечает «Нет доступа»

Проверьте `DP_TELEGRAM_ADMIN_IDS` в `.env`. Там должен быть Telegram user ID пользователя, который пишет боту.

### Бот запускается, но не публикует в канал

Проверьте:

1. `DP_TELEGRAM_CHANNEL_ID`;
2. что бот добавлен в канал;
3. что бот является администратором;
4. что у него есть право публикации сообщений;
5. что предложение имеет статус `ready`;
6. что предложение ещё не было опубликовано в этот канал.

### `/queue` пуст

Проверьте `/status`, `/sources` и `/filter`. Возможно, предложения находятся в `needs_review`, уже опубликованы или не проходят текущий фильтр.

### Один источник перестал работать

Посмотрите `/sources`. Ошибка одного адаптера не должна останавливать остальные источники. Если сайт изменил HTML, потребуется обновление соответствующего адаптера.

## 19. Что хранится на компьютере

Основные локальные данные:

```text
.env                — секреты и настройки
discount_parser.db  — основная SQLite-база
smoke_report.json   — диагностический отчёт, если он был создан
```

Не удаляйте `discount_parser.db`, если нужно сохранить историю предложений и публикаций.

## 20. Краткая памятка

Первичная установка:

```text
git clone → venv → pip install → .env → alembic upgrade head
```

Первичный тест:

```text
parse → bot → /status → /queue → ручная публикация
```

Постоянная работа:

```text
bot + scheduler
```

Управление:

```text
Telegram-бот
```

Ручная корректировка классификации:

```text
/export → исправить XLSX → /import
```

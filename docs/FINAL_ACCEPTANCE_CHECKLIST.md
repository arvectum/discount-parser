# Discount Parser — финальный acceptance checklist

Этот checklist выполняется на реальной машине заказчика после получения готового OS-specific installer/package.

## 0. Preflight / Doctor

Сразу после установки и до live-парсинга открыть страницу `Система` и проверить блок `Самодиагностика`.

Для технической проверки из исходников:

```bash
python -m src.cli doctor
```

Для packaged Windows QA используется:

```text
DiscountParserWorker.exe doctor
```

Для packaged macOS QA:

```text
./DiscountParser doctor
```

Проверить:

- [ ] database = OK;
- [ ] data_directory = OK;
- [ ] sources_config = OK и все adapters зарегистрированы;
- [ ] web_port не занят до запуска панели;
- [ ] Telegram config после заполнения wizard = OK.

Telegram config до первого запуска может отображаться как `ПРОВЕРИТЬ`; это не блокирует локальную установку.

## 1. Установка

- [ ] Выбран пакет под правильную ОС/архитектуру.
- [ ] Windows: запущен `DiscountParser-Setup.exe`.
- [ ] macOS: выбран ARM64 или Intel package и один раз запущен `install.command`.
- [ ] Установка завершилась без ошибки migration.
- [ ] Появился ярлык `Discount Parser` / `Discount Parser.app`.
- [ ] Python, Git и pip отдельно не устанавливались.

Windows delivery содержит два внутренних executable:

```text
DiscountParser.exe        — локальный web UI без консольного окна
DiscountParserWorker.exe  — migration / doctor / bot / scheduler
```

Заказчик вручную запускает только `DiscountParser.exe` через ярлык.

## 2. Первый запуск

- [ ] Двойной клик открывает браузер на `http://127.0.0.1:8765`.
- [ ] Не открывается лишнее консольное окно при обычной работе.
- [ ] Если настройки отсутствуют, открывается Telegram Setup Wizard.
- [ ] Введены Bot Token, Telegram channel и Telegram user ID администратора.
- [ ] После сохранения открывается dashboard.
- [ ] Bot и scheduler показываются как запущенные либо имеют понятный лог ошибки на странице `Система`.
- [ ] Повторно открыта `Система`: Telegram config в Doctor больше не требует проверки.

## 3. Single-instance и local security

- [ ] Повторный двойной клик по ярлыку не запускает второй экземпляр.
- [ ] Открывается уже работающая локальная панель.
- [ ] Панель доступна только через localhost.
- [ ] Невалидный Host отклоняется.
- [ ] Cross-origin POST к управляющим маршрутам отклоняется.

## 4. Парсер

Сначала тестировать один источник, затем все источники.

- [ ] На главной странице видны все 5 источников.
- [ ] Источник можно выключить и включить.
- [ ] Выключенный источник не запускается при следующем сборе.
- [ ] Выполнен тест одного источника.
- [ ] После него выполнен сбор всех включённых источников.
- [ ] В `Журнале` появились ParseRun.
- [ ] Для успешных источников есть fetched/new/updated counters.
- [ ] Для неуспешных источников виден текст ошибки.
- [ ] Ошибка одного сайта не остановила остальные источники.

## 5. Предложения

- [ ] Страница `Предложения` открывается.
- [ ] Работает поиск.
- [ ] Работают фильтры status/category/type.
- [ ] Открывается карточка Offer.
- [ ] В карточке отображается provenance по источникам.

## 6. Telegram

Сначала проверить polling и команды, только после этого публикацию.

- [ ] Бот отвечает разрешённому admin user ID.
- [ ] `/status` работает.
- [ ] `/sources` работает.
- [ ] `/queue` работает.
- [ ] Выполнена одна ручная публикация тестового предложения.
- [ ] Сообщение появилось в нужном Telegram-канале.
- [ ] Повторная публикация того же Offer не создаёт дубль.
- [ ] В SQLite Publication сохранён `telegram_message_id`.

## 7. Filter/autopost

- [ ] Через web UI сохранён минимальный discount threshold.
- [ ] При необходимости выбраны category/subcategory/type/merchant.
- [ ] Настроен `max_posts_per_cycle`.
- [ ] Включён autopost.
- [ ] Выполнен один реальный autopost cycle.
- [ ] Опубликованы только Offer, проходящие фильтр.

## 8. Расписание

- [ ] Изменён collect interval.
- [ ] Изменён autopost interval.
- [ ] Изменено maintenance time.
- [ ] Если scheduler работал, после сохранения он перезапустился.
- [ ] Новый scheduler cycle использует новое расписание.

## 9. XLSX

- [ ] `offers.xlsx` скачивается из web UI.
- [ ] Изменены только `category`/`subcategory`.
- [ ] XLSX импортируется обратно.
- [ ] Manual override виден в базе/Offer.
- [ ] Следующий parse не стирает manual correction.

## 10. Логи и завершение

- [ ] На странице `Система` видны bot/scheduler PID.
- [ ] `bot.log` и `scheduler.log` читаются через UI.
- [ ] Кнопка очистки лога работает.
- [ ] `Завершить Discount Parser` останавливает web/bot/scheduler.
- [ ] После завершения приложение снова нормально запускается ярлыком.

## 11. Sleep / resume

- [ ] Зафиксировано, что во время sleep автоматические задачи не выполняются.
- [ ] После пробуждения ноутбука приложение/сервисы возвращаются в ожидаемое состояние либо пользователь перезапускает ярлык.
- [ ] Пользователь понимает: для настоящего 24/7 требуется постоянно включённая машина/VPS.

## 12. Update safety

Перед тестом обновления сделать резервную копию:

```text
.env
discount_parser.db
```

Затем:

- [ ] Установлена новая версия поверх существующей.
- [ ] `.env` сохранился.
- [ ] `discount_parser.db` сохранился.
- [ ] История Offer/Publication сохранилась.
- [ ] enabled/disabled state источников сохранился.
- [ ] Alembic migration завершилась успешно.

## 13. Smoke report

После финального live прогона сформировать:

```bash
python -m src.cli smoke-report --output output/smoke_report.json
```

Проверить:

- [ ] source statuses;
- [ ] offer counts;
- [ ] publication counts;
- [ ] ParseRun count;
- [ ] latest successful Telegram message ID.

## 14. Acceptance result

Полный production acceptance считается пройденным только если:

```text
Doctor required checks OK
+ installer/package OK
+ first-run wizard OK
+ live source parse OK
+ Telegram polling OK
+ real channel publish OK
+ telegram_message_id stored
+ scheduler/autopost OK
+ update preserves data
```

До реального запуска на целевой машине этот документ является готовым сценарием приёмки, а не подтверждением live-production результата.

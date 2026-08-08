# Discount Parser — финальный acceptance checklist

Этот checklist выполняется на реальной машине заказчика после получения готового OS-specific installer/package.

## 1. Установка

- [ ] Выбран пакет под правильную ОС/архитектуру.
- [ ] Windows: запущен `DiscountParser-Setup.exe`.
- [ ] macOS: выбран ARM64 или Intel package и один раз запущен `install.command`.
- [ ] Установка завершилась без ошибки migration.
- [ ] Появился ярлык `Discount Parser` / `Discount Parser.app`.
- [ ] Python, Git и pip отдельно не устанавливались.

## 2. Первый запуск

- [ ] Двойной клик открывает браузер на `http://127.0.0.1:8765`.
- [ ] Не открывается лишнее консольное окно при обычной работе.
- [ ] Если настройки отсутствуют, открывается Telegram Setup Wizard.
- [ ] Введены Bot Token, Telegram channel и Telegram user ID администратора.
- [ ] После сохранения открывается dashboard.
- [ ] Bot и scheduler показываются как запущенные либо имеют понятный лог ошибки на странице `Система`.

## 3. Single-instance

- [ ] Повторный двойной клик по ярлыку не запускает второй экземпляр.
- [ ] Открывается уже работающая локальная панель.

## 4. Парсер

- [ ] На главной странице видны все 5 источников.
- [ ] Источник можно выключить и включить.
- [ ] Выключенный источник не запускается при следующем сборе.
- [ ] Нажата кнопка `Запустить сбор сейчас`.
- [ ] В `Журнале` появились ParseRun.
- [ ] Для успешных источников есть fetched/new/updated counters.
- [ ] Для неуспешных источников виден текст ошибки.

## 5. Предложения

- [ ] Страница `Предложения` открывается.
- [ ] Работает поиск.
- [ ] Работают фильтры status/category/type.
- [ ] Открывается карточка Offer.
- [ ] В карточке отображается provenance по источникам.

## 6. Telegram

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

Для packaged acceptance допустимо использовать тот же report service через технический запуск/сборочный QA.

Проверить:

- [ ] source statuses;
- [ ] offer counts;
- [ ] publication counts;
- [ ] ParseRun count;
- [ ] latest successful Telegram message ID.

## 14. Acceptance result

Полный production acceptance считается пройденным только если:

```text
installer/package OK
+ first-run wizard OK
+ live source parse OK
+ Telegram polling OK
+ real channel publish OK
+ telegram_message_id stored
+ scheduler/autopost OK
+ update preserves data
```

До реального запуска на целевой машине этот документ является готовым сценарием приёмки, а не подтверждением live-production результата.

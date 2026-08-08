# R8 — XLSX correction loop + rule memory

Статус: **IMPLEMENTED**  
Дата: **2026-08-08**

## Реализовано

### XLSX export

`export_offers_xlsx()` формирует `offers.xlsx` с листами:

- `active`;
- `needs_review`;
- `published`;
- `expired`;
- `sources`.

В offer sheets выгружаются основные нормализованные поля Offer. Колонки `category` и `subcategory` выделены как редактируемые. Остальные колонки используются как контекст и идентификаторы.

Экспорт отключает автоматическую интерпретацию строк как формул и URL через XlsxWriter options `strings_to_formulas=False` и `strings_to_urls=False`.

### XLSX import

`import_offer_corrections()` читает `.xlsx` через `python-calamine` и применяет только разрешённые изменения:

- `category`;
- `subcategory`.

Изменения сохраняются через `ManualOverride(source="xlsx")`, поэтому последующие parser runs не должны их затирать.

Пустая ячейка трактуется как «не изменять значение», а не как команда очистить поле.

### Status transition

Если Offer находился в `needs_review`, после ручной классификации имеет ненулевую выгоду и категория перестала быть fallback `Другое`, он переводится в `ready`.

### Conservative rule memory

После ручной правки создаётся безопасное правило классификации:

- `match_key = title`;
- `match_value = полный текущий title`;
- category/subcategory из manual correction;
- `source = xlsx_manual`;
- priority `200`.

Одинаковое enabled-rule повторно не создаётся.

### Telegram integration

Добавлен отдельный `xlsx` router:

- `/export` — формирует и отправляет `offers.xlsx`;
- `/import` — инструкция отправить исправленный файл;
- admin `.xlsx` document handler — скачивает, применяет corrections и возвращает ImportReport.

Ограничения Telegram import:

- admin allowlist;
- только `.xlsx`;
- максимум 20 MB;
- временный файл всегда удаляется.

`src.telegram.runner` объединяет control router R7 и XLSX router R8. CLI `python -m src.cli bot` использует именно составной dispatcher.

## Roundtrip tests

`tests/test_xlsx_roundtrip.py` проверяет:

1. создание пяти ожидаемых листов;
2. наличие `id/category/subcategory`;
3. импорт category/subcategory correction;
4. создание двух ManualOverride;
5. перевод `needs_review → ready`;
6. создание одного ClassificationRule;
7. применение сохранённого rule к аналогичному новому входу.

## Gate R8

Кодовый сценарий:

```text
Offer in SQLite
→ XLSX export
→ user edits category/subcategory
→ XLSX import
→ ManualOverride
→ optional exact-title ClassificationRule
→ later classification preserves learned category
```

реализован и покрыт deterministic roundtrip tests.

Следующий этап: **R9 — QA, demo, packaging, delivery**.

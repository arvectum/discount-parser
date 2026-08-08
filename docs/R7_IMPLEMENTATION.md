# R7 — Telegram control plane + publishing

Статус: **IMPLEMENTED, live smoke pending Telegram credentials**  
Дата: **2026-08-08**

## Реализовано

### Control bot

На `aiogram 3` реализованы команды:

- `/start`;
- `/status`;
- `/sources`;
- `/new`;
- `/queue`;
- `/filter`;
- `/autopost`.

Доступ — deny-by-default через `DP_TELEGRAM_ADMIN_IDS`.

### Filters

Сохранённый `PublishFilter` поддерживает:

- минимальную скидку;
- category;
- subcategory;
- offer type;
- merchant;
- source key;
- max posts per cycle.

В Telegram UI доступны:

- 10/20/30/50%;
- тип предложения;
- категории из текущей БД;
- подкатегории выбранной категории.

### Queue / preview

Очередь содержит только `Offer.status == ready`, соответствующие фильтру и ещё не имеющие publication reservation для целевого канала.

Preview использует тот же HTML-renderer, что и channel publisher. Для preview доступны:

- publish;
- skip;
- reject;
- открыть source URL.

### Publication ledger

Перед Telegram API call создаётся уникальная запись `Publication(offer_id, channel_id)` со статусом `sending`.

Это даёт защиту от параллельного/повторного send. После результата:

- success → `published`, сохраняются `telegram_message_id` и `published_at`;
- failure → `failed`, сохраняется error;
- повторная попытка при существующей reservation → `duplicate` без нового send.

Если Offer уже не `ready` (`expired`, `rejected`, `published` и т.д.), publisher возвращает `not_publishable` и не создаёт reservation.

### Image fallback

Если у Offer есть `image_url`, publisher сначала отправляет photo + caption. При ошибке загрузки изображения пробует text message. Если и text send не проходит, Publication фиксируется как `failed`.

### Autopost

Scheduler содержит отдельный `autopost` job:

- период задаётся `DP_AUTOPOST_INTERVAL_MINUTES`;
- job имеет `max_instances=1`, `coalesce=True`;
- работает только если persisted default filter `enabled=true`;
- использует `max_posts_per_cycle`;
- использует тот же publication ledger, что manual publish.

### CLI

```bash
python -m src.cli bot
python -m src.cli scheduler
```

## Telegram settings

```dotenv
DP_TELEGRAM_BOT_TOKEN=replace_me
DP_TELEGRAM_CHANNEL_ID=@replace_me
DP_TELEGRAM_ADMIN_IDS=123456789
DP_TELEGRAM_DEFAULT_MIN_DISCOUNT=20
DP_AUTOPOST_INTERVAL_MINUTES=30
```

## Offline tests

`tests/test_publishing.py` покрывает:

- min-discount filtering;
- exclusion already reserved offer;
- safe HTML escaping;
- successful fake-bot publication;
- persistence of Telegram message id;
- second call returns duplicate and does not send again;
- non-ready Offer cannot be published and does not create Publication.

Scheduler test дополнительно проверяет наличие `autopost` job и `max_instances=1`.

## Live gate

Для полного Gate R7 остаётся только внешний smoke на реальном Telegram:

```text
real parsed ready offer
→ saved filter
→ preview
→ publish callback
→ Telegram channel
→ telegram_message_id in publications
```

Код не содержит bot token/channel credentials; они задаются только через environment.

Следующий этап разработки, не зависящий от live smoke: **R8 — XLSX correction loop + rule memory**.

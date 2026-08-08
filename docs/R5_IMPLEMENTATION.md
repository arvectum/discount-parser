# R5 — Source pack MVP

Статус: **DONE**  
Дата: **2026-08-08**

## Enabled sources

1. `promokood` — `https://promokood.ru/`
2. `promokodik` — `https://promokodik.ru/`
3. `berikod` — `https://berikod.ru/global/ru/`
4. `promokodi_net_ru` — `https://promokodi.net.ru/ru/`
5. `promko` — `https://promko.net/ru`

All are configured in `config/sources.yaml` and registered independently in `src/sources/registry.py`.

## Implementation

- five source adapters;
- shared semantic-card utilities;
- source-specific extraction logic instead of a single universal selector;
- percent and amount extraction;
- promo-code extraction where it is present in public HTML;
- date extraction for `dd.mm.yyyy` sources;
- image URL extraction where available;
- canonical `RawOffer` output for every adapter;
- per-source deterministic HTML fixtures;
- source-level collection failure isolation;
- per-offer DB transaction isolation remains active from R3/R4.

## Current live-shape reconnaissance

During implementation the public pages were checked against their current August 2026 content:

- Promokood exposes compact merchant + benefit cards;
- Promokodik exposes offer text, expiry and `offer_id` activation links;
- Berikod exposes benefit headings and visible promo codes;
- Promokodi.net.ru exposes recent promo offers and merchant/category text;
- PROMKO.NET exposes active merchant discount summaries (`merchant + до N%`).

Default automated tests use committed HTML fixtures instead of live HTTP so CI does not depend on third-party uptime or page changes.

## Regression coverage

`tests/test_source_pack.py` verifies:

- adapter fixture counts;
- Promokodik merchant/discount/date/cashback parsing;
- Berikod promo-code and amount/percent parsing;
- Promokodi.net.ru merchant extraction;
- PROMKO.NET summary parsing.

`tests/test_run_all.py` verifies that one failing source does not prevent a healthy source from being collected and persisted.

## Local semantic smoke

```text
percent parser: PASS
rub amount parser: PASS
DD.MM.YYYY parser: PASS
promo-code token parser: PASS
merchant + до N% summary parser: PASS
```

## Run

```bash
alembic upgrade head
python -m src.cli parse
```

One source:

```bash
python -m src.cli parse --source promokodik
```

## Next

R6 — offer lifecycle + scheduler.

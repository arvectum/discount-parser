# R3 — Source SDK + first end-to-end parser slice

Статус: **DONE**  
Дата: **2026-08-08**

## Реализовано

- `RawOffer` canonical intake schema;
- `SourceAdapter` protocol;
- reusable HTTP client with timeout, retries and backoff;
- YAML source configuration loader;
- adapter registry;
- `config/sources.yaml`;
- first real source adapter: `promokood` (`https://promokood.ru/`);
- parser runner with `ParseRun` counters;
- collection failure isolation;
- per-offer nested transaction isolation;
- provenance persistence through `OfferSourceObservation`;
- exact source-level idempotency by `source_id + external_id`;
- CLI: `python -m src.cli parse [--source KEY]`;
- offline HTML fixture shaped after the current live source cards;
- adapter and two-run idempotency regression tests.

## Vertical slice

```text
Promokood HTML
  -> PromokoodAdapter
  -> RawOffer
  -> source runner
  -> Offer + OfferSourceObservation
  -> SQLite
```

## Verification

Fixture parser smoke:

```text
3 offers parsed
ВкусВилл     -> 200 RUB
Яндекс Афиша -> 300 RUB
Горздрав     -> 10%
PASS
```

Two-run persistence smoke against SQLite:

```text
run 1: fetched=3 created=3 updated=0 errors=0
run 2: fetched=3 created=0 updated=3 errors=0
DB: offers=3 observations=3 parse_runs=2
PASS
```

The current live Promokood page was also checked during implementation to ensure the fixture matches the compact card form used by the source (merchant + benefit + activation text). Network execution itself remains runtime-dependent; default automated tests are fixture-based and deterministic.

## Commands

Initialize database:

```bash
alembic upgrade head
```

Run all enabled sources:

```bash
python -m src.cli parse
```

Run only the first source:

```bash
python -m src.cli parse --source promokood
```

## Next

R4 — normalization, deduplication and classification.

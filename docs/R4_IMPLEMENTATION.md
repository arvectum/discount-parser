# R4 — Normalization, deduplication, classification

Статус: **DONE**  
Дата: **2026-08-08**

## Реализовано

### Normalization

- canonical URL normalization;
- tracking parameter removal (`utm_*`, `yclid`, `gclid`, etc.);
- text normalization;
- Decimal normalization;
- discount calculation from `old_price/new_price`;
- promo code normalization;
- separate discount/cashback/delivery benefit fields;
- deterministic offer type resolution;
- stable SHA-256 fingerprint.

### Deduplication

Matching order:

1. canonical URL;
2. merchant + promo code;
3. exact fingerprint;
4. fuzzy title match for the same merchant using RapidFuzz.

Default fuzzy threshold: `92`.

Benefit mismatch lowers fuzzy score to avoid merging materially different offers from the same merchant.

Cross-source matches attach a new `OfferSourceObservation` to the existing Offer instead of creating a duplicate.

Repeated source observations with the same `external_id` refresh normalized Offer values (including changed discount/price) instead of only refreshing `last_seen_at`.

### Classification

- configurable taxonomy in `config/taxonomy.yaml`;
- DB-backed `ClassificationRule` priority;
- keyword fallback;
- `Другое / Не определено` fallback;
- manual category override has absolute priority;
- unresolved offers are marked `needs_review`;
- resolved `new/needs_review` offers with a benefit can move to `ready`;
- `published/expired/rejected` states are not reopened by normalization.

## Regression coverage

- tracking URL canonicalization;
- discount calculation from prices;
- keyword classification;
- DB classification rule priority;
- manual override priority;
- fuzzy same-offer match;
- different-offer non-match;
- cross-source merge with two provenance records;
- manual override survives cross-source merge;
- stable source external ID refreshes changed discount values.

## Local smoke evidence

```text
canonical URL: PASS
1000 -> 750 => discount_percent=25.00: PASS
same-offer fuzzy score: 100.0
other-offer fuzzy score: 69.23
threshold: 92
PASS
```

## Next

R5 — source pack: at least five live adapters with fixtures and source-level failure isolation.

# R10 — Source Registry & multi-platform collection

Status: **CODE IMPLEMENTED ON FEATURE BRANCH — LOCAL QA/LIVE ACCEPTANCE REQUIRED**

Branch:

```text
feature/source-registry-multiplatform
```

This branch must not be merged into `main` until the local unpushed release-preflight commit is reconciled and the combined tree passes local QA.

## Goal

The parser is no longer limited conceptually to five promo-code aggregators. A persisted source registry now supports known sources from:

- promo aggregators;
- ordinary merchant websites and promotion pages;
- public Telegram channels;
- VK communities via API;
- Dzen public pages;
- Rutube public channel/video metadata;
- future collector types without replacing the existing Offer pipeline.

## Pipeline

Structured legacy promo adapters remain unchanged:

```text
legacy adapter
→ RawOffer
→ normalization
→ deduplication
→ classification
→ Offer
```

New content-oriented sources use:

```text
RegisteredSource
→ SourceCollector
→ SourceItem
→ deterministic OfferSignal
→ RawOffer
→ existing normalization/dedup/classification
→ Offer
```

The registry therefore does not create a second Offer model or parallel persistence pipeline.

## Persisted models

Migration `0002_source_registry` adds:

- `registered_sources`;
- `source_keywords`;
- `source_keyword_links`;
- `source_candidates`;
- `source_items`.

`RegisteredSource` stores management metadata and health state. Credentials are not stored in this table.

`SourceItem` stores platform-level posts/pages before offer extraction, providing idempotency and debugging.

`SourceCandidate` separates discovery from production collection: discovered URLs/channels must be approved before becoming active registered sources.

## Existing promo aggregators

`registry-seed` mirrors the five configured YAML adapters into the registry as `promo_aggregator / legacy_adapter` records.

They are intentionally not fetched through the new registry runner. The established `src.sources.runner` remains authoritative, preventing double collection and preserving existing regression coverage.

## Collectors

Implemented collector contracts:

- `generic_web` — one known merchant/promotion page;
- `telegram_public` — public `t.me/s/<channel>` preview posts, no user credentials;
- `vk_api` — VK wall API, requires optional `DP_VK_ACCESS_TOKEN`;
- `dzen_public` — public-page compatibility collector;
- `rutube_public` — public channel/video metadata compatibility collector;
- `public_page` — generic compatibility fallback.

Collectors have bounded item count, HTTP timeout, redirect handling and response-size limits.

### Telegram limitation

`telegram_public` is not an MTProto history client. It covers channels available through Telegram's public web preview. Private channels, unavailable previews or deeper authenticated history require a future authenticated MTProto collector/session.

Publishing-bot credentials remain independent from collector credentials.

### VK limitation

VK collection is credential-dependent. An enabled `vk_api` source without a token becomes `requires_credentials`; Doctor reports this as an actionable optional warning rather than breaking unrelated sources.

### Dzen / Rutube

Current collectors deliberately use public-page compatibility contracts. Their exact live HTML/API surfaces must be tested on the target network. A stable public JSON/RSS/API endpoint may replace collector internals later without schema changes.

## Discovery

`discover-merchant` implements bounded merchant-page discovery:

- starts from one known merchant homepage;
- same domain only;
- depth 1;
- maximum candidate count;
- searches promo/sale/action/discount/special path/text hints;
- creates `SourceCandidate`, not active sources.

It is intentionally not a general internet crawler.

## Deterministic offer detection

`SourceItem` text is scored by explicit evidence:

- strong discount/promo keywords;
- promo-code pattern;
- discount percentage;
- old/new price pattern;
- cashback/delivery terms;
- negative keywords such as review/unboxing reducing confidence.

No LLM is required.

The threshold is conservative: weak editorial mentions should not automatically become Offers.

## Source management UI

New page:

```text
/sources-registry
```

Supports:

- listing all registered platforms;
- enable/disable;
- test one non-legacy source;
- add source;
- view health/error state;
- approve/reject discovered candidates;
- add/toggle keywords;
- XLSX import/export.

## Registry XLSX

Export file includes sheets:

- `sources`;
- `candidates`;
- `keywords`.

This is the intended mechanism for building and maintaining a large initial source database without hardcoding hundreds of stores into application releases.

## CLI

```bash
python -m src.cli registry-seed
python -m src.cli registry-collect
python -m src.cli registry-collect --source <key>
python -m src.cli registry-export
python -m src.cli registry-import path/to/sources_registry.xlsx
python -m src.cli discover-merchant --merchant "Store" --url https://store.example/
```

## Scheduler

Scheduled collection still runs the five established legacy sources first. It then runs enabled non-legacy registry sources.

Registry-level failure is isolated and cannot prevent the legacy collection job from completing.

## Doctor

Doctor now verifies:

- legacy source config and adapter registry;
- source-registry schema exists;
- registered collector names are valid;
- social credentials required by enabled collectors are present or reported as optional warnings.

## Frozen delivery

Windows/macOS build definitions and local build scripts explicitly include the new registry web modules and collect the `src.modules.source_registry` package.

Migration commands seed the default keywords and mirror legacy sources after upgrading the database.

## Automated regression coverage added

Tests cover:

- registry seed idempotency;
- SourceItem idempotency by platform external ID;
- candidate approval;
- deterministic offer-signal extraction;
- negative keyword behavior;
- collector registry;
- fixture parsing for generic web, Telegram public, Dzen and Rutube;
- source-registry web route registration/precedence;
- Alembic head requiring registry tables.

These tests have been committed remotely but still require execution on the local combined tree because GitHub-hosted Actions quota is exhausted.

## Required local acceptance before merge

The local machine must reconcile its unpushed release-preflight commit with this branch, then run:

```text
compile
full pytest
preflight
fresh Alembic migration
upgrade/migration smoke
Doctor
frozen macOS build
frozen migration
frozen Doctor
```

Then live-test at least:

- one ordinary merchant website;
- one public Telegram channel;
- one Dzen source;
- one Rutube source;
- VK if credentials are available.

The existing four currently reachable promo aggregators should be rerun as regression; `promokodi_net_ru` remains a separately documented HTTP 403 access issue until investigated.

## Merge rule

Do not tag `v1.0.0` from this branch.

Merge only after the local release-preflight changes and R10 are combined and the resulting tree has zero test failures. Full client release still requires Telegram publishing acceptance and packaged UI/fresh-install acceptance.

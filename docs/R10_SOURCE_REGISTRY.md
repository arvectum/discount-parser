# R10 — Source Registry & multi-platform collection

Status: **CODE IMPLEMENTED — CROSS-PLATFORM CI AND DELIVERY GATES AVAILABLE**

Branch:

```text
feature/source-registry-multiplatform
```

The branch remains unmerged only because the developer machine still has the local release-preflight commit `ace21cc` that must be reconciled first. The repository is now public, so GitHub-hosted Actions is usable again.

## Goal

Discount Parser is no longer limited to five promo-code aggregators. A persisted registry supports:

- promo aggregators;
- merchant websites and promotion pages;
- public Telegram channels;
- VK communities via API;
- Dzen public pages;
- Rutube public metadata;
- future collector types without changing the Offer core pipeline.

## Pipelines

Legacy structured sources remain:

```text
legacy adapter → RawOffer → normalization → deduplication → classification → Offer
```

Content-oriented sources use:

```text
RegisteredSource → SourceCollector → SourceItem → deterministic OfferSignal
→ RawOffer → existing normalization/dedup/classification → Offer
```

## Persisted models

Migration `0002_source_registry` adds:

- `registered_sources`;
- `source_keywords`;
- `source_keyword_links`;
- `source_candidates`;
- `source_items`.

Credentials are deliberately not stored in `RegisteredSource`.

## Existing aggregators

`registry-seed` mirrors the five YAML adapters into the registry as `promo_aggregator / legacy_adapter` records. They remain collected by the established legacy runner and are not fetched twice by the registry runner.

## Collectors

Implemented contracts:

- `generic_web`;
- `telegram_public` for `t.me/s/<channel>` previews without credentials;
- `vk_api`, requiring optional `DP_VK_ACCESS_TOKEN`;
- `dzen_public`;
- `rutube_public`;
- `public_page` fallback.

Collectors use bounded item counts, timeouts, redirect handling and maximum response sizes.

### Telegram

Publishing/control-bot credentials are independent from collection credentials. Public Telegram channels require no extra credentials. MTProto API ID/API Hash can be stored by onboarding, but authenticated MTProto session creation is intentionally not claimed as complete yet.

### VK

VK is optional. An enabled `vk_api` source without a token becomes an actionable credential warning instead of breaking unrelated collection.

## Discovery

`discover-merchant` performs bounded same-domain discovery of likely promotion/sale/action pages and writes `SourceCandidate` records. Candidates must be approved before becoming active registered sources.

## Source management UI

```text
/sources-registry
```

Supports listing, add, enable/disable, test-now, candidate approval/rejection, keyword management and XLSX import/export.

## Guided onboarding

Interactive setup now uses:

```text
/onboarding/1 .. /onboarding/5
```

Legacy `GET /setup` redirects to the wizard while legacy `POST /setup` remains backward-compatible.

Wizard steps:

1. Telegram publishing/control bot: Bot Token, optional display name, channel and admin ID. Includes live Bot API connection check without rendering the secret back to the browser.
2. Telegram collection: public mode without credentials, or storage of MTProto API ID/API Hash for later authenticated-session activation.
3. VK: optional token, skip action and API connectivity test.
4. Source capability summary: promo sites, merchant sites, Telegram, VK, Dzen and Rutube.
5. Doctor summary: required versus optional checks and packaged-app start action.

Secrets are stored locally through the existing atomic `.env` writer. New integration fields are single-line validated and are not shown again after saving.

In a frozen client build, completing onboarding starts bot and scheduler best-effort and opens the dashboard. Optional integration failures do not block application startup.

## Registry XLSX

Export contains:

- `sources`;
- `candidates`;
- `keywords`.

This is the intended way to maintain a large source database without hardcoding hundreds of stores in releases.

## CLI

```bash
python -m src.cli registry-seed
python -m src.cli registry-collect
python -m src.cli registry-collect --source <key>
python -m src.cli registry-export
python -m src.cli registry-import path/to/sources_registry.xlsx
python -m src.cli discover-merchant --merchant "Store" --url https://store.example/
```

## Doctor

Doctor verifies legacy source configuration, registry schema, collector names, data directory/database and credential requirements for enabled collectors. Telegram publishing credentials and social credentials remain optional warnings until configured.

## Packaging

Windows and macOS PyInstaller builds explicitly package the source-registry modules and onboarding router. Windows keeps separate `DiscountParser.exe` UI and `DiscountParserWorker.exe` worker executables.

## Automated QA

The feature branch has cross-platform GitHub Actions gates for:

- Ubuntu;
- Windows;
- macOS ARM64;
- macOS Intel.

The normal CI gate runs compile, pytest, Alembic/Doctor and CLI smoke. The delivery gate builds frozen executables, runs frozen migration/Doctor and builds the Windows Inno Setup installer.

Onboarding regression tests cover legacy `/setup` redirection, Telegram setting persistence, secret non-echo, public Telegram mode without credentials, MTProto credential validation, VK skip behavior and the six-platform source summary.

## Remaining external acceptance

Before release, reconcile local commit `ace21cc`, then perform live tests on the combined tree for:

- ordinary merchant website;
- public Telegram channel;
- Dzen;
- Rutube;
- VK when a token is available;
- real Telegram publishing/control bot credentials and one controlled channel publication;
- packaged first-run UI and update-preservation test on the target machine.

`promokodi_net_ru` remains a separately documented HTTP 403 access issue unless a stable public access path is confirmed.

## Merge rule

Do not tag `v1.0.0` until the local release-preflight commit is reconciled and live Telegram/delivery acceptance is complete.

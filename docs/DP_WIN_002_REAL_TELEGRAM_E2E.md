# DP-WIN-002 — Real Telegram E2E

DP-WIN-002 is the physical Windows gate after DP-WIN-001. It must run against an installed Discount Parser build using the real locally configured Telegram bot and channel. Production credentials must not be copied into GitHub, CI logs, issues or support bundles.

## Acceptance command

Run from the installed directory, normally `%LOCALAPPDATA%\DiscountParser`:

```powershell
.\DiscountParserWorker.exe telegram-e2e
```

Optional explicit evidence path:

```powershell
.\DiscountParserWorker.exe telegram-e2e C:\Temp\dp-win-002.json
```

The default evidence file is written to `acceptance\dp-win-002-real-telegram-e2e.json` under the installed runtime directory.

## What the command proves

The command uses the same local `.env`, network-route selection, database and Telegram publisher code as the installed product. It executes the following live sequence:

1. `getMe` with the configured bot token.
2. `getChat` for the configured channel.
3. `getChatMember` for the bot in that channel.
4. Assert administrator/creator status and `can_post_messages` is not false.
5. Create an isolated synthetic `ready` offer and publish it through the product publisher (`manual_publication`).
6. Create a second isolated offer, force the real publisher ledger into `failed`, then retry the same `(offer, channel)` reservation with the real bot and require the same Publication row to become `published` (`failed_retry`).
7. Snapshot the customer's current default publication filter, temporarily replace it with a unique merchant-only filter, create exactly one matching probe offer, run the real `run_autopost_cycle_async()` path and require exactly that one offer to publish (`autopost`).
8. Restore the original filter even on failure.
9. Best-effort delete Telegram probe messages and delete all synthetic database offers/publications.

The temporary autopost filter is deliberately unique so ordinary customer `ready` offers are not selected by this acceptance cycle.

## PASS contract

The process exit code is `0` only when the evidence JSON reports `status: PASS`.

Required evidence fields:

- `telegram_identity.get_me = PASS`;
- `telegram_identity.get_chat = PASS`;
- `telegram_identity.get_chat_member = PASS`;
- administrator/creator membership;
- `manual_publication.status = PASS`;
- `failed_retry.status = PASS`;
- `failed_retry.publication_id_reused = true`;
- `autopost.status = PASS`;
- `autopost.selected_only_probe_offer = true`;
- `filter_restored = true`;
- `database_probe_cleanup = PASS`.

Telegram message deletion is best-effort and is recorded separately because deleting channel posts may require an additional Telegram permission beyond posting.

## Evidence privacy

The acceptance output never serializes the bot token or raw configured channel identifier. The channel is represented by a short SHA-256 fingerprint. Errors pass through application redaction before being stored. Do not attach `.env` to the issue or PR.

## Completion rule

Repository/CI preparation alone does not complete DP-WIN-002. The task is complete only after the command above returns exit code `0` on the physical Windows notebook using the real installed build and the resulting secret-free evidence is reviewed.

After DP-WIN-002 is accepted, the next roadmap action is **DP-WIN-003 — Real source/network sweep**.

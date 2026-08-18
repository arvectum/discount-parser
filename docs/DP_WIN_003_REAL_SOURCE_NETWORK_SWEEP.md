# DP-WIN-003 — Real source/network sweep

## Purpose

`DP-WIN-003` is the physical Windows acceptance gate for the production collection path. It verifies the actually configured sources and the customer network environment using the installed application, without embedding credentials or proxy details in the acceptance evidence.

This gate runs **real collection**. It may create or update normal offers/source items in the production SQLite database. It does not publish acceptance messages to Telegram.

## Prerequisite

`DP-WIN-002 — Real Telegram E2E` must already be complete. The accepted prerequisite was closed with PASS on 2026-08-18.

## Repository preparation

The post-DP-WIN-002 build adds a canonical installed-worker command:

```text
DiscountParserWorker.exe source-network-sweep
```

The command:

1. verifies database integrity before the sweep;
2. creates a recovery backup before any real collection;
3. inventories the actually enabled legacy and registry sources;
4. checks direct/system reachability for every enabled source and proxy reachability when an application proxy is configured;
5. runs the normal production collection path for every enabled source using its effective product network policy;
6. records the route actually remembered by the product network router after collection;
7. validates scheduler cadence and the per-source registry collection interval contract;
8. verifies database integrity again after collection;
9. writes sanitized JSON evidence to `acceptance/dp-win-003-real-source-network-sweep.json` by default.

The sweep deliberately forces each enabled registry source once even when its next scheduled check is not yet due. This is an explicit acceptance action. Normal background collection now honors each registry source's `check_interval_minutes` setting; explicit targeted/manual collection remains immediate.

## Network contract

The application owns four routing policies:

- `auto` — try the available routes and remember a working route per host;
- `direct` — bypass environment/system HTTP proxy variables;
- `proxy` — use the explicitly configured `DP_PROXY_URL`;
- `system` — honor the environment/OS proxy path used by HTTPX.

Loopback (`127.0.0.1`, `localhost`, `::1`) must always remain direct. The sweep also requires these loopback values to be present in the configured `DP_NO_PROXY` contract.

Route probes are reachability diagnostics. The real collection itself still uses the source's effective production network policy, including an operator-defined registry override.

## PASS criteria

The physical Windows gate is PASS only when all of the following are true:

- installed database exists and passes SQLite integrity checks before collection;
- a pre-sweep database backup is created;
- loopback routing/no-proxy invariants pass;
- scheduler collection interval matches `DP_COLLECT_INTERVAL_MINUTES`, with `max_instances=1` and coalescing enabled;
- registry background collection honors each source's `check_interval_minutes` value;
- every actually enabled production source is reachable through its configured/effective route policy;
- every actually enabled source completes a real collection with at least one fetched item and zero collection errors;
- database integrity still passes after the sweep;
- evidence privacy check reports `PASS` and `credentials_embedded=false`.

A source that is intentionally no longer usable should be disabled by the operator rather than silently excluded from this gate.

## Sanitized evidence

The JSON evidence intentionally contains only diagnostics required for acceptance, including source keys, safe origins (`scheme://host[:port]` only), platform/collector type, route names, HTTP status codes, timing, collection counters and PASS/FAIL status.

It must not contain:

- Telegram bot tokens/channel/admin identifiers;
- proxy URL, username or password;
- Telegram collector API/session secrets;
- VK access tokens;
- URL paths/query strings that can carry credentials;
- raw source external identifiers from exception text.

Do not paste `.env`, proxy configuration, bot credentials or unsanitized logs into GitHub issues.

## Physical Windows procedure

Use the installed post-merge build on the Windows notebook that represents the customer runtime/network contour.

Recommended sequence:

```text
DiscountParserWorker.exe doctor
DiscountParserWorker.exe status-json
DiscountParserWorker.exe db-status
DiscountParserWorker.exe source-network-sweep
```

The final command returns exit code `0` only when the JSON evidence status is `PASS`. On failure it returns non-zero and leaves the sanitized evidence file for diagnosis.

If Windows has attached `Zone.Identifier` to newly downloaded delivery files, unblock those files before installation/execution, as already required by the accepted DP-WIN-002 procedure.

## Closure rule

Repository preparation and CI are not sufficient to close issue #33. Close `DP-WIN-003` only after the installed post-merge Windows build runs `source-network-sweep` on the real Windows/customer network contour and produces sanitized `PASS` evidence.

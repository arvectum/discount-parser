from __future__ import annotations

from urllib.parse import unquote

import httpx

from src.shared.network import NetworkRouteError, configured_proxy_url, network_router


class PromkoRevealError(RuntimeError):
    pass


def _client_for_route(route: str, timeout: float) -> httpx.Client:
    selected = route.casefold()
    if selected == "auto":
        selected = network_router.choose_route("https://promko.net", timeout=min(timeout, 6.0))
    if selected == "direct":
        return httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False)
    if selected == "system":
        return httpx.Client(timeout=timeout, follow_redirects=True, trust_env=True)
    if selected == "proxy":
        proxy = configured_proxy_url()
        if not proxy:
            raise NetworkRouteError("proxy route requested but DP_PROXY_URL is empty")
        return httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False, proxy=proxy)
    raise PromkoRevealError(f"unsupported network route: {route}")


def reveal_promko_code(coupon_id: str, *, referer: str, route: str = "auto", timeout: float = 20.0) -> str:
    coupon_id = str(coupon_id).strip()
    if not coupon_id.isdigit():
        raise PromkoRevealError("PROMKO coupon id must be numeric")
    headers = {
        "User-Agent": "DiscountParser/1.0 (+local source monitor)",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Referer": referer,
    }
    with _client_for_route(route, timeout) as client:
        csrf = client.get("https://promko.net/sanctum/csrf-cookie", headers=headers)
        csrf.raise_for_status()
        xsrf = client.cookies.get("XSRF-TOKEN")
        if not xsrf:
            raise PromkoRevealError("PROMKO XSRF token missing")
        response = client.post(
            f"https://promko.net/api/promocodes/{coupon_id}/use",
            headers={**headers, "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest", "X-XSRF-TOKEN": unquote(xsrf)},
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise PromkoRevealError(f"PROMKO reveal {coupon_id}: invalid JSON") from exc
    code = str(payload.get("promocode") or "").strip()
    if not code:
        raise PromkoRevealError(f"PROMKO reveal {coupon_id}: promocode missing")
    return code

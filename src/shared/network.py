from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass
from threading import RLock
from urllib.parse import urlparse

import httpx

from src.shared.config import get_settings

ROUTES = {"auto", "direct", "proxy", "system"}
_LOOPBACK_NAMES = {"localhost"}


class NetworkRouteError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RouteProbe:
    url: str
    route: str
    ok: bool
    status_code: int | None
    elapsed_ms: int
    detail: str


@dataclass(slots=True)
class _RouteCacheEntry:
    route: str
    expires_at: float


def is_loopback_url(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").strip().lower()
    except ValueError:
        return False
    if hostname in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


class NetworkRouter:
    """Application-owned HTTP routing with a hard loopback bypass.

    direct: ignore HTTP(S)_PROXY/ALL_PROXY environment variables.
    proxy: use DP_PROXY_URL explicitly.
    system: let httpx honor environment proxy variables / OS routing.
    auto: try the cached/sensible routes and remember a working route briefly.

    A TUN-only VPN still controls the OS route table. True per-domain split routing
    requires a local HTTP/SOCKS proxy endpoint exposed by the VPN client.
    """

    def __init__(self) -> None:
        self._cache: dict[str, _RouteCacheEntry] = {}
        self._lock = RLock()

    def _configured_mode(self) -> str:
        mode = (get_settings().network_mode or "auto").strip().lower()
        return mode if mode in ROUTES else "auto"

    def _host_key(self, url: str) -> str:
        return (urlparse(url).hostname or url).lower()

    def _client(self, route: str, *, timeout: float, headers: dict[str, str] | None = None) -> httpx.Client:
        settings = get_settings()
        kwargs: dict[str, object] = {
            "timeout": timeout,
            "follow_redirects": True,
            "headers": headers,
        }
        if route == "direct":
            kwargs["trust_env"] = False
        elif route == "system":
            kwargs["trust_env"] = True
        elif route == "proxy":
            proxy_url = (settings.proxy_url or "").strip()
            if not proxy_url:
                raise NetworkRouteError("proxy route requested but DP_PROXY_URL is empty")
            kwargs["trust_env"] = False
            kwargs["proxy"] = proxy_url
        else:
            raise NetworkRouteError(f"unsupported route: {route}")
        return httpx.Client(**kwargs)

    def _candidate_routes(self, url: str, requested: str | None = None) -> list[str]:
        if is_loopback_url(url):
            return ["direct"]
        mode = (requested or self._configured_mode()).strip().lower()
        if mode not in ROUTES:
            mode = "auto"
        if mode != "auto":
            return [mode]

        host = self._host_key(url)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(host)
            if cached and cached.expires_at > now:
                first = cached.route
            else:
                first = "direct"

        candidates = [first]
        if first != "direct":
            candidates.append("direct")
        if (get_settings().proxy_url or "").strip() and "proxy" not in candidates:
            candidates.append("proxy")
        if "system" not in candidates:
            candidates.append("system")
        return candidates

    def request(
        self,
        method: str,
        url: str,
        *,
        route: str | None = None,
        timeout: float = 20.0,
        headers: dict[str, str] | None = None,
        retry_statuses: set[int] | None = None,
        **kwargs,
    ) -> httpx.Response:
        retry_statuses = retry_statuses or set()
        errors: list[str] = []
        for candidate in self._candidate_routes(url, route):
            started = time.monotonic()
            try:
                with self._client(candidate, timeout=timeout, headers=headers) as client:
                    response = client.request(method, url, **kwargs)
                if response.status_code in retry_statuses:
                    errors.append(f"{candidate}: HTTP {response.status_code}")
                    continue
                self.remember(url, candidate)
                return response
            except (httpx.TimeoutException, httpx.ProxyError, httpx.ConnectError, httpx.NetworkError, NetworkRouteError) as exc:
                elapsed = int((time.monotonic() - started) * 1000)
                errors.append(f"{candidate}: {type(exc).__name__} after {elapsed} ms")
        raise NetworkRouteError("; ".join(errors) or "no network route available")

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def remember(self, url: str, route: str, *, ttl_seconds: int = 900) -> None:
        if route not in {"direct", "proxy", "system"} or is_loopback_url(url):
            return
        with self._lock:
            self._cache[self._host_key(url)] = _RouteCacheEntry(route=route, expires_at=time.monotonic() + ttl_seconds)

    def probe(self, url: str, *, route: str, timeout: float = 6.0) -> RouteProbe:
        started = time.monotonic()
        try:
            response = self.request("GET", url, route=route, timeout=timeout)
            elapsed = int((time.monotonic() - started) * 1000)
            # Connectivity is established even when the endpoint itself returns
            # an application-level 4xx such as Telegram's API root.
            ok = response.status_code < 500
            return RouteProbe(url, route, ok, response.status_code, elapsed, f"HTTP {response.status_code}")
        except Exception as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return RouteProbe(url, route, False, None, elapsed, type(exc).__name__)

    def choose_route(self, url: str, *, timeout: float = 6.0) -> str:
        candidates = self._candidate_routes(url, "auto")
        for candidate in candidates:
            probe = self.probe(url, route=candidate, timeout=timeout)
            if probe.ok:
                self.remember(url, candidate)
                return candidate
        raise NetworkRouteError(f"no working route for {url}")


network_router = NetworkRouter()

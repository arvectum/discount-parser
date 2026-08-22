from __future__ import annotations

import ipaddress
import os
import time
from dataclasses import dataclass
from threading import RLock
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

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


def configured_proxy_url() -> str | None:
    settings = get_settings()
    raw = (settings.proxy_url or "").strip()
    if not raw:
        return None
    if not settings.proxy_username:
        return raw
    parts = urlsplit(raw)
    if not parts.scheme or not parts.hostname:
        return raw
    username = quote(settings.proxy_username, safe="")
    password = quote(settings.proxy_password or "", safe="")
    auth = username + (f":{password}" if settings.proxy_password is not None else "")
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit((parts.scheme, f"{auth}@{host}{port}", parts.path, parts.query, parts.fragment))


def _proxy_url_from_windows_value(proxy_server: str | None, target_url: str) -> str | None:
    """Convert the WinINet ProxyServer value into an httpx proxy URL.

    Windows stores either one endpoint (``127.0.0.1:7890``) or a semicolon
    separated map (``http=...;https=...;socks=...``). Chromium/Edge and many
    desktop VPN clients use this setting, while httpx's ``trust_env=True`` does
    not read it. Keeping this conversion in our network layer lets the packaged
    app use the same static system proxy as the customer's browser.
    """
    raw = str(proxy_server or "").strip()
    if not raw:
        return None

    target_scheme = (urlparse(target_url).scheme or "https").casefold()
    selected = raw
    selected_kind = target_scheme
    if "=" in raw:
        mapping: dict[str, str] = {}
        for chunk in raw.split(";"):
            if "=" not in chunk:
                continue
            kind, value = chunk.split("=", 1)
            kind = kind.strip().casefold()
            value = value.strip()
            if kind and value:
                mapping[kind] = value
        if not mapping:
            return None
        if target_scheme == "https":
            order = ("https", "http", "socks", "socks5")
        else:
            order = (target_scheme, "http", "https", "socks", "socks5")
        selected_kind = ""
        selected = ""
        for kind in order:
            if mapping.get(kind):
                selected_kind = kind
                selected = mapping[kind]
                break
        if not selected:
            return None

    if "://" in selected:
        return selected
    prefix = "socks5://" if selected_kind.startswith("socks") else "http://"
    return prefix + selected


def windows_system_proxy_url(target_url: str) -> str | None:
    """Return the current user's enabled static Windows/WinINet proxy.

    This intentionally has no effect outside Windows and does not attempt to
    execute PAC/WPAD scripts. A static proxy is the important missing case for
    the frozen Windows customer build: the browser can work through WinINet
    while raw httpx requests otherwise fail with ConnectError/ProxyError.
    """
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0] or 0)
            if not enabled:
                return None
            proxy_server = str(winreg.QueryValueEx(key, "ProxyServer")[0] or "").strip()
    except (OSError, ValueError, TypeError):
        return None
    return _proxy_url_from_windows_value(proxy_server, target_url)


class NetworkRouter:
    """Application-owned HTTP routing with a hard loopback bypass.

    direct: ignore HTTP(S)_PROXY/ALL_PROXY environment variables.
    proxy: use DP_PROXY_URL explicitly.
    system: on Windows prefer the enabled WinINet system proxy used by browsers;
            otherwise let httpx honor environment proxy variables / OS routing.
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
        """Build a route client while preserving the historical test/extension contract."""
        kwargs: dict[str, object] = {"timeout": timeout, "follow_redirects": True, "headers": headers}
        if route == "direct":
            kwargs["trust_env"] = False
        elif route == "system":
            kwargs["trust_env"] = True
        elif route == "proxy":
            proxy_url = configured_proxy_url()
            if not proxy_url:
                raise NetworkRouteError("proxy route requested but DP_PROXY_URL is empty")
            kwargs["trust_env"] = False
            kwargs["proxy"] = proxy_url
        else:
            raise NetworkRouteError(f"unsupported route: {route}")
        return httpx.Client(**kwargs)

    def _client_for_url(self, route: str, *, url: str, timeout: float, headers: dict[str, str] | None = None) -> httpx.Client:
        if route == "system":
            system_proxy = windows_system_proxy_url(url)
            if system_proxy:
                return httpx.Client(
                    timeout=timeout,
                    follow_redirects=True,
                    headers=headers,
                    trust_env=False,
                    proxy=system_proxy,
                )
        return self._client(route, timeout=timeout, headers=headers)

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
        if configured_proxy_url() and "proxy" not in candidates:
            candidates.append("proxy")
        if "system" not in candidates:
            candidates.append("system")
        return candidates

    def request(self, method: str, url: str, *, route: str | None = None, timeout: float = 20.0, headers: dict[str, str] | None = None, retry_statuses: set[int] | None = None, **kwargs) -> httpx.Response:
        retry_statuses = retry_statuses or set()
        errors: list[str] = []
        for candidate in self._candidate_routes(url, route):
            started = time.monotonic()
            try:
                with self._client_for_url(candidate, url=url, timeout=timeout, headers=headers) as client:
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

    def cached_route(self, url: str) -> str | None:
        """Return the currently remembered route for a host without exposing proxy details."""
        if is_loopback_url(url):
            return "direct"
        host = self._host_key(url)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(host)
            if cached is None:
                return None
            if cached.expires_at <= now:
                self._cache.pop(host, None)
                return None
            return cached.route

    def probe(self, url: str, *, route: str, timeout: float = 6.0) -> RouteProbe:
        started = time.monotonic()
        try:
            response = self.request("GET", url, route=route, timeout=timeout)
            elapsed = int((time.monotonic() - started) * 1000)
            ok = response.status_code < 500
            return RouteProbe(url, route, ok, response.status_code, elapsed, f"HTTP {response.status_code}")
        except Exception as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return RouteProbe(url, route, False, None, elapsed, type(exc).__name__)

    def choose_route(self, url: str, *, timeout: float = 6.0) -> str:
        for candidate in self._candidate_routes(url, "auto"):
            probe = self.probe(url, route=candidate, timeout=timeout)
            if probe.ok:
                self.remember(url, candidate)
                return candidate
        raise NetworkRouteError(f"no working route for {url}")


network_router = NetworkRouter()

from __future__ import annotations

from pathlib import Path

from src.shared import network


ROOT = Path(__file__).resolve().parents[1]


def test_windows_proxy_value_supports_single_endpoint_and_protocol_map() -> None:
    assert network._proxy_url_from_windows_value(
        "127.0.0.1:7890", "https://promokood.ru/travel"
    ) == "http://127.0.0.1:7890"
    assert network._proxy_url_from_windows_value(
        "http=127.0.0.1:8080;https=127.0.0.1:8443;socks=127.0.0.1:1080",
        "https://promokood.ru/travel",
    ) == "http://127.0.0.1:8443"
    assert network._proxy_url_from_windows_value(
        "socks=127.0.0.1:1080", "https://promokood.ru/travel"
    ) == "socks5://127.0.0.1:1080"


def test_system_route_prefers_windows_browser_proxy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(network, "windows_system_proxy_url", lambda url: "http://127.0.0.1:7890")
    monkeypatch.setattr(network.httpx, "Client", FakeClient)

    network.NetworkRouter()._client_for_url(
        "system",
        url="https://promokood.ru/travel",
        timeout=4.0,
        headers={"User-Agent": "test"},
    )

    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["trust_env"] is False


def test_customer_routes_precede_manual_and_legacy_routes() -> None:
    application = (ROOT / "src" / "web" / "application.py").read_text(encoding="utf-8")
    assert "app.include_router(customer_feedback_13_router)" in application
    assert application.index("app.include_router(customer_feedback_13_router)") < application.index(
        "app.include_router(manual_mapping_router)"
    )
    assert application.index("app.include_router(customer_feedback_13_router)") < application.index(
        "app.include_router(source_registry_router)"
    )
    assert 'app.add_api_route("/developer/sources-registry/{source_id}/mapping", mapping_page_v2' in application
    assert '_replace_exact_route("/sources-registry/{source_id}/mapping", "GET", mapping_page_v2)' not in application


def test_customer_existing_source_flow_is_confirm_only() -> None:
    routes = (ROOT / "src" / "web" / "customer_feedback_13_routes.py").read_text(encoding="utf-8")
    page = (ROOT / "src" / "web" / "customer_feedback_13.py").read_text(encoding="utf-8")

    assert "'/sources-registry/{source_id}/analyze-auto'" in routes
    assert "'/sources-registry/{source_id}/confirm-auto'" in routes
    assert "'/sources-registry/{source_id}/mapping'" in routes
    assert "customer_mapping_redirect" in routes
    assert "Перенастроить автоматически" in page
    assert "Ничего копировать из HTML не нужно" in page
    assert "ручная разметка HTML для решения этой ошибки не нужна" in page
    assert "reveal_selector\": None" in page
    assert "reveal_code_attribute\": None" in page

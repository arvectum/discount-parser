from __future__ import annotations

from fastapi.responses import HTMLResponse

from src.web import application, customer_hotfixes, source_registry_routes


def _route_matches(path: str, method: str):
    return [
        route
        for route in application.app.router.routes
        if getattr(route, "path", None) == path
        and method.upper() in set(getattr(route, "methods", set()) or set())
    ]


def test_canonical_application_installs_safe_sources_route() -> None:
    matches = _route_matches("/sources-registry", "GET")

    assert len(matches) == 1
    assert matches[0].endpoint is customer_hotfixes.sources_registry_hotfix


def test_canonical_hotfix_installation_is_idempotent() -> None:
    customer_hotfixes.install_customer_hotfixes(application.app)
    customer_hotfixes.install_customer_hotfixes(application.app)

    sources = _route_matches("/sources-registry", "GET")
    publish = _route_matches("/publish/{offer_id}", "POST")

    assert len(sources) == 1
    assert sources[0].endpoint is customer_hotfixes.sources_registry_hotfix
    assert len(publish) == 1
    assert publish[0].endpoint is customer_hotfixes.web_publish_hotfix


def test_sources_hotfix_contains_legacy_none_render_failure(monkeypatch) -> None:
    monkeypatch.setattr(customer_hotfixes, "_repair_registry_rows_runtime", lambda: None)

    def broken_registry_page(*, message=None, error=None):
        raise AttributeError("'NoneType' object has no attribute 'replace'")

    monkeypatch.setattr(source_registry_routes, "registry_page", broken_registry_page)
    monkeypatch.setattr(
        customer_hotfixes,
        "_fallback_registry_page",
        lambda **kwargs: HTMLResponse("safe sources fallback", status_code=200),
    )

    response = customer_hotfixes.sources_registry_hotfix()

    assert response.status_code == 200
    assert b"safe sources fallback" in response.body

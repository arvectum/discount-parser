from __future__ import annotations

from src.web.application import app


def test_source_registry_routes_are_registered() -> None:
    paths = [route.path for route in app.routes]
    assert "/sources-registry" in paths
    assert "/sources-registry/add" in paths
    assert "/sources-registry/export" in paths
    assert "/sources-registry/import" in paths
    assert "/sources-registry/keywords/add" in paths
    assert "/sources-registry/{source_id}/{action}" in paths


def test_keyword_add_static_route_precedes_dynamic_source_action() -> None:
    paths = [route.path for route in app.routes]
    static_index = paths.index("/sources-registry/keywords/add")
    dynamic_index = paths.index("/sources-registry/{source_id}/{action}")
    assert static_index < dynamic_index

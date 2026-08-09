from __future__ import annotations

from src.web.application import app


def _paths() -> list[str]:
    return [route.path for route in app.routes if hasattr(route, "path")]


def test_source_registry_routes_are_registered() -> None:
    paths = _paths()
    assert "/sources-registry" in paths
    assert "/sources-registry/add" in paths
    assert "/sources-registry/export" in paths
    assert "/sources-registry/import" in paths
    assert "/sources-registry/keywords/add" in paths
    assert "/sources-registry/{source_id}/{action}" in paths


def test_keyword_add_static_route_precedes_dynamic_source_action() -> None:
    paths = _paths()
    static_index = paths.index("/sources-registry/keywords/add")
    dynamic_index = paths.index("/sources-registry/{source_id}/{action}")
    assert static_index < dynamic_index

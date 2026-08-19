from __future__ import annotations

from fastapi.testclient import TestClient

from src.web.application import app


def test_source_registry_routes_are_registered() -> None:
    client = TestClient(app)
    # DP-CUST-007 may serve the safe Sources wrapper directly at middleware
    # level (200) or preserve the first-run setup redirect (303). Either proves
    # that the customer-facing path is handled; a missing route would be 404.
    response = client.get('/sources-registry', follow_redirects=False)
    assert response.status_code in {200, 303}
    if response.status_code == 303:
        assert response.headers['location'] == '/setup'


def test_keyword_add_static_route_precedes_dynamic_source_action() -> None:
    client = TestClient(app)
    response = client.post(
        '/sources-registry/keywords/add',
        data={'keyword': 'скидка', 'kind': 'positive', 'merchant': '', 'priority': '50'},
        follow_redirects=False,
    )
    # Even without an initialized registry DB the static handler converts its
    # service error to a registry redirect. If the dynamic int route captured
    # this URL FastAPI would return validation/404 instead.
    assert response.status_code == 303
    assert response.headers['location'].startswith('/sources-registry?')

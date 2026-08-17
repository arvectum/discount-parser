from __future__ import annotations

from fastapi.testclient import TestClient

from src.web.application import app
from src.web import app as app_module


def test_cross_origin_post_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(app_module, 'is_setup_complete', lambda: True)
    client = TestClient(app)
    response = client.post(
        '/parse',
        headers={'Origin': 'https://evil.example'},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert 'Cross-origin request blocked' in response.text


def test_cross_site_referer_without_origin_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(app_module, 'is_setup_complete', lambda: True)
    client = TestClient(app)
    response = client.post(
        '/parse',
        headers={'Referer': 'https://evil.example/attack'},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert 'Cross-origin request blocked' in response.text


def test_local_origin_post_is_allowed(monkeypatch) -> None:
    monkeypatch.setattr(app_module, 'is_setup_complete', lambda: True)
    monkeypatch.setattr(app_module, '_parse_state', {'running': True, 'last_error': None, 'last_finished': None})
    client = TestClient(app)
    response = client.post(
        '/parse',
        headers={'Origin': 'http://127.0.0.1:8765'},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_localhost_referer_post_is_allowed(monkeypatch) -> None:
    monkeypatch.setattr(app_module, 'is_setup_complete', lambda: True)
    monkeypatch.setattr(app_module, '_parse_state', {'running': True, 'last_error': None, 'last_finished': None})
    client = TestClient(app)
    response = client.post(
        '/parse',
        headers={'Referer': 'http://localhost:8765/home'},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_untrusted_host_is_rejected() -> None:
    client = TestClient(app)
    response = client.get('/', headers={'Host': 'evil.example'})
    assert response.status_code == 400

from fastapi.testclient import TestClient

from src.app import create_app
from src.shared.config import Settings
from src.web.application import app as web_runtime_app


def test_health_returns_ok() -> None:
    app = create_app(Settings(app_name="Discount Parser Test", env="test"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "Discount Parser Test"
    assert payload["env"] == "test"
    assert payload["timestamp"]


def test_openapi_is_available() -> None:
    app = create_app(Settings(env="test"))

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Discount Parser API"


def test_web_runtime_health_is_available_before_onboarding() -> None:
    with TestClient(web_runtime_app) as client:
        response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}

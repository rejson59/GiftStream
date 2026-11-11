from fastapi.testclient import TestClient

from app import main
from app.models import AppConfig


def test_public_config_never_returns_integration_secrets(monkeypatch):
    monkeypatch.setattr(main, "config", AppConfig(minecraft_api_key="mc-private", bridge_webhook_secret="bridge-private"))
    response = TestClient(main.app).get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "minecraft_api_key" not in data
    assert "bridge_webhook_secret" not in data
    assert data["minecraft_has_key"] is True
    assert data["bridge_has_secret"] is True

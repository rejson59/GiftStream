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


def test_download_info_prefers_installer_then_new_and_legacy_launchers(monkeypatch):
    original_cache = main._DOWNLOAD_INFO_CACHE.copy()

    class Response:
        def __init__(self, assets):
            self.payload = {"tag_name": "v0.3.0", "assets": assets}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            import json
            return json.dumps(self.payload).encode()

    assets = [
        {"name": "GiftStream-Setup-win-x64.exe", "browser_download_url": "https://github.com/releases/GiftStream-Setup-win-x64.exe"},
        {"name": "GiftStream.exe", "browser_download_url": "https://github.com/releases/GiftStream.exe"},
        {"name": "TipStream.exe", "browser_download_url": "https://github.com/releases/TipStream.exe"},
    ]
    monkeypatch.setattr(main.urllib.request, "urlopen", lambda *_args, **_kwargs: Response(assets))
    main._DOWNLOAD_INFO_CACHE.update({"expires": 0, "data": None})
    client = TestClient(main.app)
    result = client.get("/api/download-info").json()
    assert result["available"] is True
    assert result["url"].endswith("GiftStream-Setup-win-x64.exe")
    assert result["kind"] == "installer"
    assert result["version"] == "v0.3.0"

    monkeypatch.setattr(main.urllib.request, "urlopen", lambda *_args, **_kwargs: Response(assets[1:]))
    main._DOWNLOAD_INFO_CACHE.update({"expires": 0, "data": None})
    result = client.get("/api/download-info").json()
    assert result["available"] is True
    assert result["url"].endswith("GiftStream.exe")
    assert result["kind"] == "portable"

    monkeypatch.setattr(main.urllib.request, "urlopen", lambda *_args, **_kwargs: Response(assets[2:]))
    main._DOWNLOAD_INFO_CACHE.update({"expires": 0, "data": None})
    result = client.get("/api/download-info").json()
    assert result["available"] is True
    assert result["url"].endswith("TipStream.exe")
    main._DOWNLOAD_INFO_CACHE.update(original_cache)


def test_update_ui_can_only_request_a_published_update(tmp_path):
    from app import update_state

    update_state.clear()
    client = TestClient(main.app)
    assert client.get("/api/updates/status").json()["available"] is False
    assert client.post("/api/updates/apply").status_code == 409

    executable = tmp_path / "GiftStreamApp.exe"
    update_state.publish_update("v0.3.0", executable)
    status = client.get("/api/updates/status").json()
    assert status["available"] is True
    assert status["tag"] == "v0.3.0"
    assert "GiftStream" in status["message"]
    assert client.post("/api/updates/apply").json()["ok"] is True
    assert update_state.take_apply_request() == executable
    update_state.clear()

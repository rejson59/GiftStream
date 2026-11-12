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


def test_download_info_returns_the_single_application_executable(monkeypatch):
    original_cache = main._DOWNLOAD_INFO_CACHE.copy()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            import json
            return json.dumps({"tag_name": "v0.5.0", "assets": [
                {"name": "GiftStream.exe", "browser_download_url": "https://github.com/releases/GiftStream.exe"},
            ]}).encode()

    monkeypatch.setattr(main.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    main._DOWNLOAD_INFO_CACHE.update({"expires": 0, "data": None})
    result = TestClient(main.app).get("/api/download-info").json()
    assert result["available"] is True
    assert result["url"].endswith("GiftStream.exe")
    assert result["kind"] == "application"
    assert result["version"] == "v0.5.0"
    main._DOWNLOAD_INFO_CACHE.update(original_cache)


def test_game_catalog_exposes_ready_modes_without_server_rules():
    result = TestClient(main.app).get("/api/games").json()
    by_id = {game["id"]: game for game in result}
    assert by_id["giftstream-zombie-arena"]["game_url"] == "/game"
    assert by_id["minecraft-parkour"]["status"] == "bridge"
    assert "rules" not in by_id["minecraft-parkour"]
    assert by_id["lethal-company"]["status"] == "idea"


def test_gift_catalog_refresh_endpoint_returns_latest_catalog(monkeypatch):
    monkeypatch.setattr(main, "_refresh_catalog_safely", lambda: 100)
    monkeypatch.setattr(main, "list_gifts", lambda _query="": [{"id": i} for i in range(100)])
    result = TestClient(main.app).post("/api/gifts/refresh").json()
    assert result["ok"] is True
    assert result["count"] == 100
    assert len(result["gifts"]) == 100


def test_live_audio_preferences_are_persisted_without_exposing_secrets(monkeypatch):
    monkeypatch.setattr(main, "config", AppConfig())
    monkeypatch.setattr(main, "save_config", lambda: None)
    response = TestClient(main.app).put("/api/config", json={
        "tts_enabled": True, "tts_voice": "pl-PL", "sound_alerts": True, "sound_volume": 0.7,
    })
    assert response.status_code == 200
    assert response.json()["tts_enabled"] is True
    assert response.json()["sound_alerts"] is True
    assert response.json()["sound_volume"] == 0.7
    invalid = TestClient(main.app).put("/api/config", json={"sound_volume": 1.5})
    assert invalid.status_code == 422


def test_update_check_can_be_requested_and_reports_completion():
    from app import update_state

    update_state.clear()
    client = TestClient(main.app)
    first = client.post("/api/updates/check").json()
    assert first["ok"] is True
    assert first["checking"] is True
    assert first["check_id"] == 1
    second = client.post("/api/updates/check").json()
    assert second["check_id"] == first["check_id"]
    update_state.finish_check("Masz najnowszą wersję.")
    status = client.get("/api/updates/status").json()
    assert status["checking"] is False
    assert status["last_checked"]
    assert status["last_check_message"] == "Masz najnowszą wersję."
    update_state.clear()


def test_update_ui_can_only_request_a_published_update(tmp_path):
    from app import update_state

    update_state.clear()
    client = TestClient(main.app)
    assert client.get("/api/updates/status").json()["available"] is False
    assert client.post("/api/updates/apply").status_code == 409

    executable = tmp_path / "GiftStream.exe"
    update_state.publish_update("v0.3.0", executable)
    status = client.get("/api/updates/status").json()
    assert status["available"] is True
    assert status["tag"] == "v0.3.0"
    assert "GiftStream" in status["message"]
    assert "automatycznie" in status["message"]
    assert client.post("/api/updates/apply").json()["ok"] is True
    assert update_state.take_apply_request() == executable
    update_state.clear()

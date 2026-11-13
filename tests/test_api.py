from fastapi.testclient import TestClient

from app import main
from app.models import AppConfig, Preset, Rule


def test_builtin_parkour_preset_migrates_only_when_untouched(monkeypatch):
    legacy_rules = []
    for rule_id, (name, trigger_type, gift_name, action_type) in main._LEGACY_PARKOUR_RULES.items():
        trigger = {"type": trigger_type}
        if gift_name:
            trigger["gift_name"] = gift_name
        legacy_rules.append(Rule(id=rule_id, name=name, trigger=trigger, action={"type": action_type}))
    old = Preset(id="minecraft-parkour", name="Minecraft: parkour na żywo",
                 description=main._LEGACY_PARKOUR_DESCRIPTION, rules=legacy_rules)
    saved = []
    monkeypatch.setattr(main.preset_store, "get_preset", lambda _id: old)
    monkeypatch.setattr(main.preset_store, "save_preset", lambda preset: saved.append(preset) or preset)
    assert main._migrate_builtin_parkour_preset() is True
    assert saved[0].rules[0].action.type == "parkour_push"
    assert next(r for r in saved[0].rules if r.action.type == "parkour_reset").trigger.min_coins == 1000

    saved.clear()
    old.rules[0].name = "My custom push"
    assert main._migrate_builtin_parkour_preset() is False
    assert saved == []


def test_minecraft_versions_endpoint_returns_official_release_choices(monkeypatch):
    monkeypatch.setattr(main, "minecraft_versions", lambda: {"latest": "26.3", "versions": [{"id": "26.3"}], "map_version": "26.2"})
    response = TestClient(main.app).get("/api/minecraft/versions")
    assert response.status_code == 200
    assert response.json()["latest"] == "26.3"
    assert response.json()["versions"] == [{"id": "26.3"}]


def test_statistics_endpoints_clear_history_or_reset_session_totals(monkeypatch, tmp_path):
    from app import bridge

    monkeypatch.setattr(bridge, "EVENTS_FILE", tmp_path / "events.jsonl")
    main.hub.recent_events[:] = [{"type": "gift"}]
    main.hub.recent_actions[:] = [{"action": "jump"}]
    main.hub.donors.clear()
    main.hub.donors["viewer"] = {"user": "viewer", "diamonds": 12, "gifts": 1, "last": "Rose"}
    main.hub.total_diamonds, main.hub.total_gifts = 12, 1
    main.hub.viewer_count, main.hub.total_likes = 3, 8
    main.engine.stats.update(events=9, actions=4, cooldown_skips=2)
    bridge.EVENTS_FILE.write_text('{"action":"jump"}\\n', encoding="utf-8")
    client = TestClient(main.app)
    assert client.post("/api/stats/clear-activity").status_code == 200
    snapshot = client.get("/api/snapshot").json()
    assert snapshot["recent_events"] == snapshot["recent_actions"] == []
    assert snapshot["total_diamonds"] == 12 and snapshot["total_gifts"] == 1
    assert bridge.EVENTS_FILE.read_text(encoding="utf-8") == ""

    assert client.post("/api/stats/reset").status_code == 200
    snapshot = client.get("/api/snapshot").json()
    assert snapshot["total_diamonds"] == snapshot["total_gifts"] == 0
    assert snapshot["total_likes"] == snapshot["viewer_count"] == 0
    assert snapshot["top_donors"] == []
    assert main.engine.stats == {"events": 0, "actions": 0, "cooldown_skips": 0}
    # Keep shared globals clean for the rest of the suite.
    main.hub.reset_stats()
    main.engine.reset_stats()


def test_public_config_never_returns_webhook_secret(monkeypatch):
    monkeypatch.setattr(main, "config", AppConfig(bridge_webhook_secret="bridge-private"))
    response = TestClient(main.app).get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "bridge_webhook_secret" not in data
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


def test_legacy_game_catalog_is_not_exposed():
    assert TestClient(main.app).get("/api/games").status_code == 404


def test_myinstants_search_endpoint_returns_results_and_caveat(monkeypatch):
    monkeypatch.setattr(main, "search_myinstants", lambda query: [{"name": query, "url": "https://www.myinstants.com/media/sounds/test.mp3"}])
    response = TestClient(main.app).get("/api/sounds/myinstants", params={"q": "hello"})
    assert response.status_code == 200
    assert response.json()["results"][0]["name"] == "hello"
    assert "nieoficjalnego" in response.json()["notice"]


def test_non_parkour_presets_are_not_listed_or_activated():
    client = TestClient(main.app)
    assert client.post("/api/presets").status_code == 405
    assert client.post("/api/presets/default/activate").status_code == 404


def test_supported_actions_are_limited_to_parkour():
    response = TestClient(main.app).get("/api/actions")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {
        "parkour_push", "parkour_level_forward", "parkour_level_back",
        "parkour_jail", "parkour_reset", "parkour_antireset",
    }


def test_gift_catalog_refresh_endpoint_returns_latest_catalog(monkeypatch):
    monkeypatch.setattr(main, "_refresh_catalog_safely", lambda: 100)
    monkeypatch.setattr(main, "list_gifts", lambda _query="": [{"id": i} for i in range(100)])
    result = TestClient(main.app).post("/api/gifts/refresh").json()
    assert result["ok"] is True
    assert result["count"] == 100
    assert len(result["gifts"]) == 100


def test_gift_endpoint_accepts_supported_sort_orders():
    client = TestClient(main.app)
    for order in ("popular", "price_asc", "price_desc"):
        response = client.get("/api/gifts", params={"sort": order})
        assert response.status_code == 200
        assert all("coins" in gift for gift in response.json())
    assert client.get("/api/gifts", params={"sort": "random"}).status_code == 422


def test_earnings_rates_are_saved_and_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(main.earnings_tracker, "SETTINGS_PATH", tmp_path / "earnings.json")
    client = TestClient(main.app)
    assert {key: client.get("/api/earnings/settings").json()[key] for key in ("usd_per_diamond", "usd_to_pln")} == {"usd_per_diamond": 0.005, "usd_to_pln": 4.0}
    saved = client.put("/api/earnings/settings", json={"usd_per_diamond": 0.004, "usd_to_pln": 4.2})
    assert saved.status_code == 200
    assert saved.json()["usd_per_diamond"] == 0.004
    assert saved.json()["usd_to_pln"] == 4.2
    assert client.get("/api/earnings/settings").json() == saved.json()
    assert client.put("/api/earnings/settings", json={"usd_per_diamond": 0, "usd_to_pln": 4}).status_code == 422


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
    assert TestClient(main.app).put("/api/config", json={"sound_url": "http://example.com/alert.mp3"}).status_code == 422
    assert TestClient(main.app).put("/api/config", json={"sound_url": "https://localhost/alert.mp3"}).status_code == 422
    saved_sound = TestClient(main.app).put("/api/config", json={"sound_url": "https://sounds.example.org/alert.mp3"})
    assert saved_sound.status_code == 200
    assert saved_sound.json()["sound_url"] == "https://sounds.example.org/alert.mp3"


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

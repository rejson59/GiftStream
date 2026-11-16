from fastapi.testclient import TestClient

from app import main
from app.models import AppConfig


def test_switching_tiktok_user_clears_every_session_stat_before_start(monkeypatch, tmp_path):
    from app import bridge

    monkeypatch.setattr(bridge, "EVENTS_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(main, "config", AppConfig(mode="tiktok", tiktok_username="PreviousUser"))
    main.hub.recent_events[:] = [{"type": "gift", "user": "old"}]
    main.hub.recent_actions[:] = [{"action": "parkour_push"}]
    main.hub.donors.clear()
    main.hub.donors["old"] = {"user": "old", "diamonds": 17, "gifts": 2, "last": "Rose"}
    main.hub.total_diamonds, main.hub.total_gifts = 17, 2
    main.hub.total_likes, main.hub.viewer_count = 8, 4
    main.engine.stats.update(events=6, actions=3, cooldown_skips=1)
    order = []

    async def stop():
        order.append("stop")

    async def start(mode, username):
        order.append(("start", mode, username))
        assert main.hub.recent_events == []
        assert main.hub.recent_actions == []
        assert main.hub.total_diamonds == main.hub.total_gifts == 0
        assert main.hub.total_likes == main.hub.viewer_count == 0
        assert main.hub.donors == {}
        assert main.engine.stats == {"events": 0, "actions": 0, "cooldown_skips": 0}
        return {"ok": True, "mode": mode}

    monkeypatch.setattr(main.connector, "stop", stop)
    monkeypatch.setattr(main.connector, "start", start)
    monkeypatch.setattr(main.connector, "status", lambda: {"mode": "tiktok", "state": "connecting", "connected": False})
    monkeypatch.setattr(main, "save_config", lambda: None)

    response = TestClient(main.app).post("/api/connect", json={"mode": "tiktok", "username": "@NewUser"})
    assert response.status_code == 200 and response.json()["ok"] is True
    assert order == ["stop", ("start", "tiktok", "NewUser")]
    assert main.config.tiktok_username == "NewUser" and main.config.mode == "tiktok"
    assert main.hub.snapshot()["recent_events"] == []
    main.hub.reset_stats()
    main.engine.reset_stats()


def test_invalid_username_does_not_erase_existing_stats(monkeypatch):
    monkeypatch.setattr(main, "config", AppConfig(mode="tiktok", tiktok_username="ExistingUser"))
    main.hub.total_gifts = 5
    stop_calls = []
    monkeypatch.setattr(main.connector, "stop", lambda: stop_calls.append(True))
    response = TestClient(main.app).post("/api/connect", json={"mode": "tiktok", "username": "bad user"})
    assert response.status_code == 400
    assert main.hub.total_gifts == 5
    assert stop_calls == []
    main.hub.reset_stats()


def test_simulator_and_fake_rule_test_endpoints_are_removed():
    client = TestClient(main.app)
    dashboard = client.get("/").text
    assert 'value="simulator"' not in dashboard
    assert "Szybki test" not in dashboard
    assert client.post("/api/simulate", json={"kind": "gift"}).status_code == 404
    assert client.post("/api/rules/not-a-rule/test").status_code == 404

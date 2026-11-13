import asyncio

from app import main
from app.models import TikTokEvent


def _patch_event_pipeline(monkeypatch):
    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(main, "record_event", lambda _event: None)
    monkeypatch.setattr(main.hub, "publish_event", noop)
    monkeypatch.setattr(main.engine, "handle", noop)


def test_live_comment_is_relayed_only_when_enabled(monkeypatch):
    _patch_event_pipeline(monkeypatch)
    commands = []
    monkeypatch.setattr(main.parkour_server, "settings", lambda: {"chat_relay_enabled": True})
    monkeypatch.setattr(main.parkour_server, "relay_chat", lambda text: commands.append(text))
    original_to_thread = main.asyncio.to_thread

    async def run_direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(main.asyncio, "to_thread", run_direct)
    asyncio.run(main.process_event(TikTokEvent(type="comment", user="viewer", comment='say \\"hi"', source="tiktok")))
    assert commands == ['say \\"hi"']
    monkeypatch.setattr(main.asyncio, "to_thread", original_to_thread)


def test_simulated_comment_is_not_relayed(monkeypatch):
    _patch_event_pipeline(monkeypatch)
    commands = []
    monkeypatch.setattr(main.parkour_server, "settings", lambda: {"chat_relay_enabled": True})
    monkeypatch.setattr(main.parkour_server, "relay_chat", lambda text: commands.append(text))
    asyncio.run(main.process_event(TikTokEvent(type="comment", user="viewer", comment="test", source="test")))
    assert not commands

import asyncio

from app import earnings
from app.bridge import Hub
from app.models import TikTokEvent


def test_estimate_uses_configurable_usd_rate_and_exchange_rate():
    settings = {"usd_per_diamond": 0.005, "usd_to_pln": 4.0}
    assert earnings.estimate_pln(10, settings) == 0.2
    assert earnings.estimate_pln(0, settings) == 0


def test_missing_event_diamonds_can_fall_back_to_cached_gift_metadata(monkeypatch):
    monkeypatch.setattr(earnings, "list_gifts", lambda: [
        {"id": 7, "name": "Rose", "diamonds": 3},
    ])
    assert earnings.resolve_diamonds(7, "Rose", 0) == (3, True)
    assert earnings.resolve_diamonds(99, "Unknown", 0) == (0, False)
    assert earnings.resolve_diamonds(7, "Rose", 9) == (9, False)


def test_session_estimate_counts_completed_streak_once_and_repeats():
    hub = Hub()
    partial = TikTokEvent(type="gift", user="viewer", gift_name="Rose", diamonds=2,
                          repeat_count=2, repeat_end=False)
    final = TikTokEvent(type="gift", user="viewer", gift_name="Rose", diamonds=2,
                        repeat_count=3, repeat_end=True)
    asyncio.run(hub.publish_event(partial))
    assert hub.snapshot()["total_diamonds"] == 0
    asyncio.run(hub.publish_event(final))
    snapshot = hub.snapshot()
    assert snapshot["total_diamonds"] == 6
    assert snapshot["total_gifts"] == 3
    assert snapshot["top_donors"][0]["diamonds"] == 6
    assert snapshot["recent_events"][-1]["earning_diamonds"] == 2

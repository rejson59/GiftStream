import asyncio

from app.engine import Engine
from app.models import Preset, Rule, TikTokEvent


def test_gift_matches_configured_rule():
    engine = Engine()
    engine.active_preset = Preset(id="test", name="test", rules=[
        Rule(id="rose", trigger={"type": "gift", "gift_name": "Rose"},
             action={"type": "spawn_zombie", "params": {"count": 2}})
    ])
    actions = asyncio.run(engine.handle(TikTokEvent(type="gift", user="viewer", gift_name="Rose")))
    assert len(actions) == 1
    assert actions[0].action == "spawn_zombie"
    assert actions[0].params["count"] == 2


def test_gift_name_is_case_insensitive_and_other_gift_does_not_match():
    engine = Engine()
    engine.active_preset = Preset(id="test", name="test", rules=[
        Rule(id="rose", trigger={"type": "gift", "gift_name": "Rose"}, action={"type": "heal"})
    ])
    matched = asyncio.run(engine.handle(TikTokEvent(type="gift", user="viewer", gift_name="rose")))
    ignored = asyncio.run(engine.handle(TikTokEvent(type="gift", user="viewer", gift_name="Lion")))
    assert len(matched) == 1
    assert ignored == []


def test_like_threshold_accumulates_batches():
    engine = Engine()
    engine.active_preset = Preset(id="test", name="test", rules=[
        Rule(id="likes", trigger={"type": "like", "like_threshold": 100}, action={"type": "spawn_zombie"})
    ])
    assert asyncio.run(engine.handle(TikTokEvent(type="like", like_count=55))) == []
    actions = asyncio.run(engine.handle(TikTokEvent(type="like", like_count=50)))
    assert len(actions) == 1


def test_gift_streak_only_triggers_on_final_event():
    engine = Engine()
    engine.active_preset = Preset(id="test", name="test", rules=[
        Rule(id="rose", trigger={"type": "gift", "gift_name": "Rose"}, action={"type": "heal"})
    ])
    partial = asyncio.run(engine.handle(TikTokEvent(type="gift", gift_name="Rose", repeat_count=2, repeat_end=False)))
    final = asyncio.run(engine.handle(TikTokEvent(type="gift", gift_name="Rose", repeat_count=3, repeat_end=True)))
    assert partial == []
    assert len(final) == 1

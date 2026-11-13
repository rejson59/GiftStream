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


def test_selected_rule_sound_is_passed_to_the_action_event():
    engine = Engine()
    sound_url = "/api/sounds/uploads/0123456789abcdef0123456789abcdef.mp3"
    engine.active_preset = Preset(id="test", name="test", rules=[
        Rule(id="rose", trigger={"type": "gift", "gift_name": "Rose"},
             action={"type": "parkour_push"}, sound=sound_url)
    ])
    actions = asyncio.run(engine.handle(TikTokEvent(type="gift", user="viewer", gift_name="Rose")))
    assert actions[0].params["sound"] == sound_url


def test_gift_name_is_case_insensitive_and_other_gift_does_not_match():
    engine = Engine()
    engine.active_preset = Preset(id="test", name="test", rules=[
        Rule(id="rose", trigger={"type": "gift", "gift_name": "Rose"}, action={"type": "heal"})
    ])
    matched = asyncio.run(engine.handle(TikTokEvent(type="gift", user="viewer", gift_name="rose")))
    ignored = asyncio.run(engine.handle(TikTokEvent(type="gift", user="viewer", gift_name="Lion")))
    assert len(matched) == 1
    assert ignored == []


def test_coin_price_tiers_require_explicit_verified_coin_cost(monkeypatch):
    engine = Engine()
    engine.active_preset = Preset(id="test", name="test", rules=[
        Rule(id="push", trigger={"type": "gift", "min_coins": 1, "max_coins": 29}, action={"type": "parkour_push"}),
        Rule(id="level", trigger={"type": "gift", "min_coins": 30, "max_coins": 999}, action={"type": "parkour_level_forward"}),
        Rule(id="reset", trigger={"type": "gift", "min_coins": 1000}, action={"type": "parkour_reset"}),
    ])
    monkeypatch.setattr("app.engine.coin_price_for_gift", lambda *_: (0, True))
    unknown_price = asyncio.run(engine.handle(TikTokEvent(type="gift", gift_name="Rose", diamonds=1)))
    assert unknown_price == []
    estimated_price = asyncio.run(engine.handle(TikTokEvent(type="gift", gift_name="Rose", gift_coins=1,
                                                            gift_coins_estimated=True)))
    assert estimated_price == []
    push = asyncio.run(engine.handle(TikTokEvent(type="gift", gift_name="Rose", gift_coins=1,
                                                  gift_coins_estimated=False)))
    level = asyncio.run(engine.handle(TikTokEvent(type="gift", gift_name="Donut", gift_coins=30,
                                                   gift_coins_estimated=False)))
    reset = asyncio.run(engine.handle(TikTokEvent(type="gift", gift_name="Castle", gift_coins=1000,
                                                   gift_coins_estimated=False)))
    assert [action.action for action in push] == ["parkour_push"]
    assert [action.action for action in level] == ["parkour_level_forward"]
    assert [action.action for action in reset] == ["parkour_reset"]


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

"""Testy akcji „wow” z 0.19.0: globalny próg polubień, ciemność, piorun, disco."""
import asyncio

from app.engine import Engine
from app.games import GAMES
from app.models import KNOWN_ACTIONS, Preset, Rule, TikTokEvent
from app.parkour_server import ParkourServer


def _engine_with(rules):
    engine = Engine()
    engine.active_preset = Preset(id="test", name="test", rules=rules)
    return engine


def _game(game_id):
    return next(game for game in GAMES if game["id"] == game_id)


def test_like_global_counts_likes_from_every_viewer():
    engine = _engine_with([
        Rule(id="taps", trigger={"type": "like", "like_threshold": 1000, "like_global": True},
             action={"type": "parkour_blackout"}),
    ])
    fired = []
    for index in range(1000):
        actions = asyncio.run(engine.handle(TikTokEvent(type="like", user=f"viewer-{index % 25}")))
        fired.extend(actions)
    assert len(fired) == 1, "tysiąc tapów od wielu widzów musi dać dokładnie jedną akcję"
    assert engine.likes_total == 0


def test_like_global_keeps_the_overflow_for_the_next_threshold():
    engine = _engine_with([
        Rule(id="taps", trigger={"type": "like", "like_threshold": 1000, "like_global": True},
             action={"type": "parkour_blackout"}),
    ])
    actions = asyncio.run(engine.handle(TikTokEvent(type="like", like_count=1200)))
    assert len(actions) == 1
    assert engine.likes_total == 200
    assert asyncio.run(engine.handle(TikTokEvent(type="like", like_count=800))) != []


def test_without_the_global_flag_the_engine_keeps_the_old_per_rule_counter():
    engine = _engine_with([
        Rule(id="taps", trigger={"type": "like", "like_threshold": 1000}, action={"type": "parkour_blackout"}),
    ])
    assert asyncio.run(engine.handle(TikTokEvent(type="like", user="a", like_count=999))) == []
    assert asyncio.run(engine.handle(TikTokEvent(type="like", user="b", like_count=1))) != []
    assert engine.likes_total == 0, "licznik globalny rośnie tylko przy włączonej opcji"


def test_blackout_is_longer_and_blinds_the_screen():
    commands = ParkourServer._blackout_commands("Streamer", 15)
    assert "effect give Streamer minecraft:darkness 15 0 true" in commands
    assert "effect give Streamer minecraft:blindness 15 0 true" in commands
    assert "time set midnight" in commands
    assert any(command.startswith("title Streamer actionbar") for command in commands)


def test_follow_action_fires_hearts_and_a_thank_you():
    commands = ParkourServer._heart_commands("Streamer")
    assert any("particle minecraft:heart" in command for command in commands)
    assert any(command.startswith("title Streamer actionbar") for command in commands)


def test_blackout_duration_is_clamped_and_never_negative():
    short = ParkourServer._blackout_commands("Streamer", -5)
    assert "effect give Streamer minecraft:darkness 3 0 true" in short
    long = ParkourServer._blackout_commands("Streamer", 9999)
    assert "effect give Streamer minecraft:darkness 120 0 true" in long


def test_wow_actions_are_known_by_the_api():
    expected = {
        "parkour_blackout", "parkour_lightning", "parkour_disco", "parkour_night", "parkour_heart",
        "dropper_blackout", "dropper_lightning", "dropper_disco", "dropper_heart",
    }
    assert expected.issubset(set(KNOWN_ACTIONS))


def test_parkour_preset_ships_the_wow_rules():
    rules = {rule["id"]: rule for rule in _game("minecraft-parkour")["rules"]}
    darkness = rules["mp-darkness"]
    assert darkness["trigger"] == {"type": "like", "like_threshold": 1000, "like_global": True}
    assert darkness["action"]["type"] == "parkour_blackout"
    assert rules["mp-follow-heart"]["trigger"]["type"] == "follow"
    assert rules["mp-follow-heart"]["action"]["type"] == "parkour_heart"
    assert rules["mp-share-lightning"]["action"]["type"] == "parkour_lightning"
    assert rules["mp-disco"]["trigger"]["keyword"] == "disco"
    assert rules["mp-share-lightning"]["cooldown_sec"] > 0, "piorun nie może lecieć bez przerwy"


def test_dropper_preset_has_no_parkour_actions():
    actions = {rule["action"]["type"] for rule in _game("minecraft-dropper")["rules"]}
    assert actions and all(action.startswith("dropper_") for action in actions)
    assert "dropper_blackout" in actions

from app.games import GAMES, get_game
from app.models import Preset


def test_minecraft_has_ready_preset_mapping():
    game = get_game("minecraft-survival")
    assert game is not None
    assert game["status"] == "bridge"
    assert any(rule["action"]["type"] == "spawn_zombie" for rule in game["rules"])


def test_other_game_cards_are_ideas_not_claimed_integrations():
    ideas = [g for g in GAMES if g["status"] == "idea"]
    assert len(ideas) >= 8
    assert all("rules" not in game for game in ideas)


def test_ready_game_presets_are_complete_and_have_unique_ids():
    ready = [game for game in GAMES if game["status"] == "bridge"]
    assert len(ready) >= 5
    preset_ids = [game["preset_id"] for game in ready]
    assert len(set(preset_ids)) == len(preset_ids)
    assert all(game["rules"] for game in ready)
    assert get_game("giftstream-zombie-arena")["game_url"] == "/game"
    assert get_game("minecraft-parkour")["integration"] == "GiftStream Local Minecraft"
    parkour_rules = get_game("minecraft-parkour")["rules"]
    assert next(rule for rule in parkour_rules if rule["action"]["type"] == "parkour_push")["trigger"]["max_coins"] == 29
    assert next(rule for rule in parkour_rules if rule["action"]["type"] == "parkour_level_forward")["trigger"]["min_coins"] == 30
    assert next(rule for rule in parkour_rules if rule["action"]["type"] == "parkour_reset")["trigger"]["min_coins"] == 1000
    assert next(rule for rule in parkour_rules if rule["action"]["type"] == "parkour_antireset")["trigger"]["min_coins"] == 1000
    assert {rule["action"]["type"] for rule in parkour_rules} >= {
        "parkour_push", "parkour_level_forward", "parkour_level_back", "parkour_jail", "parkour_reset", "parkour_antireset"
    }
    for game in ready:
        preset = Preset(id=game["preset_id"], name=game["title"], rules=game["rules"])
        assert preset.rules

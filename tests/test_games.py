from app.games import GAMES, get_game
from app.models import Preset


def test_only_supported_minecraft_modes_are_exposed():
    assert [game["id"] for game in GAMES] == ["minecraft-parkour", "minecraft-dropper"]
    assert get_game("minecraft-survival") is None
    assert get_game("giftstream-zombie-arena") is None
    assert get_game("minecraft-parkour")["integration"] == "GiftStream Local Minecraft"
    parkour_rules = get_game("minecraft-parkour")["rules"]
    assert next(rule for rule in parkour_rules if rule["action"]["type"] == "parkour_push")["trigger"]["max_coins"] == 29
    assert next(rule for rule in parkour_rules if rule["action"]["type"] == "parkour_level_forward")["trigger"]["min_coins"] == 30
    assert next(rule for rule in parkour_rules if rule["action"]["type"] == "parkour_reset")["trigger"]["min_coins"] == 1000
    assert next(rule for rule in parkour_rules if rule["action"]["type"] == "parkour_antireset")["trigger"]["min_coins"] == 1000
    assert {rule["action"]["type"] for rule in parkour_rules} >= {
        "parkour_push", "parkour_level_forward", "parkour_level_back", "parkour_jail", "parkour_reset", "parkour_antireset"
    }
    game = get_game("minecraft-parkour")
    preset = Preset(id=game["preset_id"], name=game["title"], rules=game["rules"])
    assert preset.rules
    dropper = get_game("minecraft-dropper")
    assert dropper["integration"] == "GiftStream Local Minecraft"
    dropper_actions = {rule["action"]["type"] for rule in dropper["rules"]}
    assert {"dropper_push", "dropper_level_forward", "dropper_level_back", "dropper_reset"}.issubset(dropper_actions)
    assert Preset(id=dropper["preset_id"], name=dropper["title"], rules=dropper["rules"]).rules


def test_level_jump_rules_ship_with_the_parkour_preset():
    rules = {rule["id"]: rule for rule in get_game("minecraft-parkour")["rules"]}
    up, down = rules["mp-jump-forward"], rules["mp-jump-back"]
    assert up["action"] == {"type": "parkour_level_jump_forward", "params": {"levels": 10}}
    assert down["action"] == {"type": "parkour_level_jump_back", "params": {"levels": 10}}
    # Ten levels at once must be a premium gift, well above a single step.
    assert up["trigger"]["min_coins"] >= 1000 and down["trigger"]["min_coins"] >= 1000
    assert up["trigger"]["gift_name"] and down["trigger"]["gift_name"]
    assert up["trigger"]["gift_name"] != down["trigger"]["gift_name"]

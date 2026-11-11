import pytest

from app.minecraft import build_commands, validate_base_url


def test_minecraft_spawn_is_allow_listed_and_bounded():
    commands = build_commands("spawn_enemy", {"entity": "creeper", "count": 100}, "Streamer_1")
    assert len(commands) == 5
    assert all("minecraft:creeper" in command for command in commands)


def test_minecraft_untrusted_entity_falls_back_to_zombie():
    command = build_commands("spawn_enemy", {"entity": "zombie;op Attacker"}, "Streamer_1")[0]
    assert command == "execute at Streamer_1 run summon minecraft:zombie ~ ~ ~"
    assert ";" not in command


def test_minecraft_item_uses_allow_list():
    command = build_commands("give_item", {"item": "command_block", "count": 999}, "Streamer_1")[0]
    assert command == "give Streamer_1 minecraft:diamond 64"


def test_minecraft_player_name_is_validated():
    with pytest.raises(ValueError):
        build_commands("heal", {}, "Player; op")


def test_server_tap_base_url_rejects_credentials_and_url_query():
    with pytest.raises(ValueError):
        validate_base_url("https://user:password@example.com")
    with pytest.raises(ValueError):
        validate_base_url("https://example.com?key=secret")
    assert validate_base_url("https://mc.example.com/") == "https://mc.example.com"

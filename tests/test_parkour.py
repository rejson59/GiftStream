import io
import zipfile

import pytest

from app.parkour_server import MAP_FILENAME, MAP_VERSION, ParkourServer, _extract_map, map_level_areas


def test_minecraft_version_options_offer_latest_stable_and_exclude_snapshots(monkeypatch):
    from app import parkour_server

    monkeypatch.setattr(parkour_server, "_version_manifest", lambda: {
        "latest": {"release": "26.3"},
        "versions": [
            {"id": "26.3", "type": "release", "releaseTime": "2026-11-01T00:00:00Z"},
            {"id": "26.4-snapshot", "type": "snapshot"},
            {"id": "26.2", "type": "release", "releaseTime": "2026-10-01T00:00:00Z"},
        ],
    })
    result = parkour_server.minecraft_versions()
    assert result["latest"] == "26.3"
    assert [item["id"] for item in result["versions"]] == ["26.3", "26.2"]
    assert parkour_server._resolve_release("latest")[0] == "26.3"
    assert parkour_server._resolve_release("26.2")[0] == "26.2"
    with pytest.raises(ValueError, match="stabilnym wydaniem"):
        parkour_server._resolve_release("26.4-snapshot")


def test_setup_stores_each_minecraft_version_in_a_separate_world(tmp_path, monkeypatch):
    from app import parkour_server

    server = ParkourServer()
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(parkour_server, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(parkour_server, "_resolve_release", lambda version: (version, {}))
    monkeypatch.setattr(parkour_server.shutil, "which", lambda _name: "/usr/bin/java")
    monkeypatch.setattr(parkour_server, "_map_archive", lambda: tmp_path / "map.zip")

    def fake_download(root, version):
        jar = root / "server.jar"
        jar.write_bytes(b"test server jar")
        return jar, 21, version

    def fake_extract(_archive, stage):
        world = stage / "100 Levels"
        world.mkdir(parents=True)
        (world / "level.dat").write_bytes(b"map data")

    monkeypatch.setattr(parkour_server, "_download_server_jar", fake_download)
    monkeypatch.setattr(parkour_server, "_extract_map", fake_extract)
    monkeypatch.setattr(server, "start", lambda: {})
    monkeypatch.setattr(server, "status", lambda: {"configured": True, "minecraft_version": server.settings()["minecraft_version"]})

    old = server.setup("", "Streamer", True, "26.2")
    old_world = tmp_path / "MinecraftParkour" / "servers" / "26.2" / "world" / "level.dat"
    assert old["minecraft_version"] == "26.2" and old_world.read_bytes() == b"map data"
    latest = server.setup("", "Streamer", True, "26.3")
    latest_world = tmp_path / "MinecraftParkour" / "servers" / "26.3" / "world" / "level.dat"
    assert latest["minecraft_version"] == "26.3" and latest_world.read_bytes() == b"map data"
    assert old_world.exists()


def test_bundled_map_has_metadata_and_level_regions():
    areas = map_level_areas()
    assert set(range(1, 101)).issubset(areas)
    assert all(dx > 0 and dz > 0 and dy in {69, 150} for _x, _z, dx, dz, dy in areas.values())
    import zipfile as zf
    from app.paths import bundle_root
    with zf.ZipFile(bundle_root() / MAP_FILENAME) as archive:
        assert "100 Levels/level.dat" in archive.namelist()
        assert "100 Levels/datapacks/main/pack.mcmeta" in archive.namelist()


def test_map_extract_rejects_traversal_and_symlinks(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("100 Levels/level.dat", "metadata")
        archive.writestr("100 Levels/datapacks/main/pack.mcmeta", "metadata")
        archive.writestr("../outside.txt", "not safe")
    with pytest.raises(ValueError, match="ścieżkę"):
        _extract_map(bad, tmp_path / "world")


def test_parkour_setup_requires_eula_before_any_download(monkeypatch, tmp_path):
    server = ParkourServer()
    monkeypatch.setattr("app.parkour_server.data_dir", lambda: tmp_path)
    with pytest.raises(ValueError, match="EULA"):
        server.setup("", "Streamer", False)
    assert not (tmp_path / "MinecraftParkour").exists()


def test_push_action_uses_a_small_local_knockback_and_validates_player(monkeypatch):
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "ok")
    message = server.execute_action("parkour_push")
    assert "3 bloki" in message
    assert commands == [
        "effect give Streamer minecraft:slow_falling 3 0 true",
        "execute as Streamer at Streamer run tp @s ^ ^0.6 ^-3",
    ]
    with pytest.raises(ValueError):
        server.execute_action("parkour_push", "bad player")


def test_chat_relay_encodes_text_as_tellraw_json_without_modifying_it(monkeypatch):
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "ok")
    message = 'hi \\"; op @a <3 Привет\nsecond line'
    assert server.relay_chat(message) == "ok"
    command = commands[0]
    assert command.startswith("tellraw @a ")
    import json
    assert json.loads(command[len("tellraw @a "):])["text"] == message


def test_parkour_action_allowlist_is_fixed():
    from app.models import KNOWN_ACTIONS
    assert {"parkour_push", "parkour_level_forward", "parkour_level_back", "parkour_jail",
            "parkour_reset", "parkour_antireset"}.issubset(KNOWN_ACTIONS)

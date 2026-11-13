import io
import json
import zipfile
from pathlib import Path

import pytest

from app.parkour_server import MAP_FILENAME, MAP_VERSION, ParkourServer, _extract_map, map_level_areas


def test_minecraft_version_options_offer_latest_stable_and_exclude_snapshots(monkeypatch):
    from app import parkour_server

    monkeypatch.setattr(parkour_server, "_version_manifest", lambda **_kwargs: {
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
        return jar, 21, version, Path("/usr/bin/java")

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


def test_switching_versions_refuses_to_orphan_a_detached_live_server(monkeypatch, tmp_path):
    from app import parkour_server

    server = ParkourServer()
    old_root = tmp_path / "old-server"
    old_root.mkdir()
    settings = tmp_path / "minecraft_parkour.json"
    settings.write_text(json.dumps({"server_dir": str(old_root), "minecraft_version": "26.2",
                                    "rcon_password": "secret", "rcon_host": "127.0.0.1", "rcon_port": 25575}))
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(parkour_server, "_resolve_release", lambda version: (version, {}))
    monkeypatch.setattr(server, "_rcon", lambda _command: "There are 1 of a max of 8 players online")
    with pytest.raises(RuntimeError, match="Zatrzymaj"):
        server.setup("", "Streamer", True, "26.3")
    assert not (tmp_path / "MinecraftParkour" / "servers" / "26.3").exists()
    assert json.loads(settings.read_text())["server_dir"] == str(old_root)


def test_start_detects_detached_server_after_giftstream_restart(monkeypatch, tmp_path):
    server = ParkourServer()
    root = tmp_path / "server"
    root.mkdir()
    (root / "server.jar").write_bytes(b"jar")
    (root / "eula.txt").write_text("eula=true")
    settings = tmp_path / "minecraft_parkour.json"
    settings.write_text(json.dumps({"server_dir": str(root), "rcon_password": "secret",
                                                   "rcon_host": "127.0.0.1", "rcon_port": 25575}))
    monkeypatch.setattr("app.parkour_server.SETTINGS_PATH", settings)
    commands = []
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "There are 1 of a max of 8 players online: Streamer")
    monkeypatch.setattr("app.parkour_server._running_minecraft_clients", lambda: [])
    monkeypatch.setattr("app.parkour_server.shutil.which", lambda _name: pytest.fail("must not launch duplicate server"))
    status = server.start()
    assert commands == ["list", "list"]
    assert status["ready"] is True and status["players_online"] == 1
    assert status["players"] == ["Streamer"]


def test_running_third_party_launcher_client_is_reported(monkeypatch):
    from app import parkour_server

    monkeypatch.setattr(parkour_server, "_windows_java_processes", lambda: [{
        "path": r"C:\\HorizonLauncher\\runtime\\javaw.exe",
        "command": 'javaw -Dfoo=bar net.minecraft.client.main.Main --version 1.21.11',
        "pid": 123,
    }])
    clients = parkour_server._running_minecraft_clients()
    assert clients == [{"launcher": "Horizon Launcher", "version": "1.21.11", "pid": 123}]


def test_java_major_parser_handles_current_and_legacy_version_formats(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app import parkour_server

    outputs = iter(['openjdk version "21.0.13" 2026-10-15', 'java version "1.8.0_421"'])
    monkeypatch.setattr(parkour_server.subprocess, "run", lambda *_args, **_kwargs:
                        SimpleNamespace(stderr=next(outputs), stdout=""))
    assert parkour_server._java_major(tmp_path / "java.exe") == 21
    assert parkour_server._java_major(tmp_path / "java8.exe") == 8


def test_java_version_detection_and_candidate_selection(monkeypatch, tmp_path):
    from app import parkour_server

    java_21, java_25 = tmp_path / "java21.exe", tmp_path / "java25.exe"
    java_21.touch(); java_25.touch()
    monkeypatch.setattr(parkour_server, "_java_candidates", lambda: [java_21, java_25])
    monkeypatch.setattr(parkour_server, "_java_major", lambda path: 21 if path == java_21 else 25)
    assert parkour_server.find_java(21) == (java_25, 25)
    assert parkour_server.find_java(26) is None


def test_java_runtime_extraction_accepts_a_safe_runtime_zip(tmp_path):
    from app import parkour_server

    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("temurin/bin/java.exe", b"java-runtime")
    executable = parkour_server._safe_extract_java(archive_bytes.getvalue(), tmp_path / "java")
    assert executable == tmp_path / "java" / "temurin" / "bin" / "java.exe"
    assert executable.read_bytes() == b"java-runtime"


def test_java_runtime_extraction_rejects_zip_path_traversal(tmp_path):
    from app import parkour_server

    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("jdk/bin/java.exe", b"java")
        archive.writestr("../outside.txt", b"unsafe")
    with pytest.raises(RuntimeError, match="niebezpieczną ścieżkę"):
        parkour_server._safe_extract_java(archive_bytes.getvalue(), tmp_path / "java")


def test_non_windows_without_compatible_java_gets_actionable_setup_error(monkeypatch):
    from app import parkour_server

    monkeypatch.setattr(parkour_server, "_java_candidates", lambda: [])
    monkeypatch.setattr(parkour_server, "_install_java", lambda _major: (_ for _ in ()).throw(
        RuntimeError("Wymagana jest Java 21+. Zainstaluj ją i uruchom GiftStream ponownie.")))
    with pytest.raises(RuntimeError, match="Java 21"):
        parkour_server.ensure_java(21)


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

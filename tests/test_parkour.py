import io
import json
import zipfile
from pathlib import Path

import pytest

from app.parkour_server import (MAP_FILENAME, MAP_VERSION, ParkourServer, _extract_map,
                                map_level_areas, map_level_spawn_points)


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
    with pytest.raises(ValueError, match="stable release"):
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
        # _extract_map removes the ZIP's top-level "100 Levels" prefix.
        (stage / "level.dat").write_bytes(b"map data")
        glint = stage / "datapacks/main/data/common/item_modifier/training_mode/glint"
        glint.mkdir(parents=True)
        for name in ("disable", "enable"):
            (glint / f"{name}.json").write_text(json.dumps([{
                "function": "minecraft:set_components",
                "components": {"minecraft:enchantment_glint_override": name == "enable"},
            }]), encoding="utf-8")
        timer = stage / "datapacks/main/data/common/function/timer/display.mcfunction"
        timer.parent.mkdir(parents=True)
        timer.write_text('title @s actionbar [{"text":"timer"}]\n', encoding="utf-8")

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
    installed_modifier = json.loads((latest_world.parent / "datapacks/main/data/common/item_modifier/training_mode/glint/enable.json").read_text())
    assert installed_modifier["type"] == "minecraft:set_components" and "function" not in installed_modifier
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


def test_map_level_spawn_points_are_complete_and_inside_stage_bounds():
    areas = map_level_areas()
    points = map_level_spawn_points(areas)

    assert set(points) == set(range(1, 101))
    for level, (x, y, z) in points.items():
        area_x, area_z, dx, dz, dy = areas[level]
        assert area_x <= x < area_x + dx + 1
        assert area_z <= z < area_z + dz + 1
        assert 0 <= y <= dy + 1
    assert points[92] == (-26.5, 32, 276.5)


def test_level_change_teleports_to_the_levels_own_checkpoint(monkeypatch):
    from app.parkour_server import level_checkpoint

    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    def rcon(command, **_kwargs):
        commands.append(command)
        return "Streamer has 10 [level]" if command.startswith("scoreboard players get") else "ok"

    monkeypatch.setattr(server, "_rcon", rcon)
    assert server.execute_action("parkour_level_forward") == \
        "Teleported to the checkpoint of level 11/100 (10 → 11)."
    x, y, z = level_checkpoint(11)
    assert f"tp Streamer {x:.2f} {y:.2f} {z:.2f}" in commands
    assert commands[0] == "scoreboard players get Streamer level"


def test_level_change_falls_back_to_the_position_when_the_scoreboard_is_empty(monkeypatch):
    from app.parkour_server import level_checkpoint

    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    def rcon(command, **_kwargs):
        commands.append(command)
        if command.startswith("scoreboard players get"):
            return "Unknown scoreboard objective 'level'"
        if command.startswith("data get entity"):
            # Standing on the level 41 checkpoint (see app/level_checkpoints.json).
            x, y, z = level_checkpoint(41)
            return f"Streamer has the following entity data: [{x}d, {y}d, {z}d]"
        return "ok"

    monkeypatch.setattr(server, "_rcon", rcon)
    assert server.execute_action("parkour_level_back") == \
        "Teleported to the checkpoint of level 40/100 (41 → 40)."


def test_every_level_checkpoint_is_inside_its_stage_bounds():
    from app.parkour_server import level_checkpoint

    areas = map_level_areas()
    for level in range(1, 101):
        x, y, z = level_checkpoint(level)
        area_x, area_z, dx, dz, dy = areas[level]
        assert area_x - 1 <= x <= area_x + dx + 1
        assert area_z - 1 <= z <= area_z + dz + 1
        assert 0 <= y <= dy + 1


def test_map_extract_strips_archive_root_into_world_directory(tmp_path):
    archive_path = tmp_path / "map.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("100 Levels/level.dat", "metadata")
        archive.writestr("100 Levels/datapacks/main/pack.mcmeta", "metadata")
    destination = tmp_path / ".giftstream-world-stage"
    _extract_map(archive_path, destination)
    assert (destination / "level.dat").read_text() == "metadata"
    assert (destination / "datapacks/main/pack.mcmeta").is_file()
    assert not (destination / "100 Levels").exists()


def test_map_extract_rejects_traversal_and_symlinks(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("100 Levels/level.dat", "metadata")
        archive.writestr("100 Levels/datapacks/main/pack.mcmeta", "metadata")
        archive.writestr("../outside.txt", "not safe")
    with pytest.raises(ValueError, match="unsafe path"):
        _extract_map(bad, tmp_path / "world")


def test_server_diagnostic_tail_includes_jvm_output_and_redacts_secrets(monkeypatch, tmp_path):
    from app import parkour_server

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "giftstream-server.log").write_text(
        "Starting minecraft server\nrcon.password=private-secret\n", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server_dir": str(server_dir)}), encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    lines = ParkourServer().diagnostic_lines()
    assert any("Starting minecraft server" in line for line in lines)
    assert any("rcon.password=[REDACTED]" in line for line in lines)
    assert all("private-secret" not in line for line in lines)


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
    monkeypatch.setattr(server, "_rcon", lambda _command, **_kwargs: "There are 1 of a max of 8 players online")
    with pytest.raises(RuntimeError, match="Stop"):
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
    monkeypatch.setattr(server, "_rcon", lambda command, **_kwargs: commands.append(command) or "There are 1 of a max of 8 players online: Streamer")
    monkeypatch.setattr("app.parkour_server._running_minecraft_clients", lambda: [])
    monkeypatch.setattr("app.parkour_server.shutil.which", lambda _name: pytest.fail("must not launch duplicate server"))
    status = server.start()
    # Daylight is re-asserted on every successful RCON readiness probe.
    assert commands == ["list", "list", "whitelist off",
                        "gamerule doDaylightCycle false", "time set day", "weather clear"]
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
    assert parkour_server.find_java(21) == (java_21, 21)
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
    with pytest.raises(RuntimeError, match="unsafe path"):
        parkour_server._safe_extract_java(archive_bytes.getvalue(), tmp_path / "java")


def test_non_windows_without_compatible_java_gets_actionable_setup_error(monkeypatch):
    from app import parkour_server

    monkeypatch.setattr(parkour_server, "_java_candidates", lambda: [])
    monkeypatch.setattr(parkour_server, "_install_java", lambda _major: (_ for _ in ()).throw(
        RuntimeError("Java 21+ is required. Install it and start GiftStream again.")))
    with pytest.raises(RuntimeError, match="Java 21"):
        parkour_server.ensure_java(21)


def test_push_action_uses_a_strong_sudden_shove_and_validates_player(monkeypatch):
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "ok")
    monkeypatch.setattr("app.parkour_server.secrets.randbelow", lambda _limit: 18000)
    message = server.execute_action("parkour_push")
    assert "Punch II" in message
    assert len(commands) == 1
    # The arrow spawns inside the player hitbox, so a wall can never block it.
    assert "execute as Streamer at @s run summon minecraft:arrow ~ ~1.1 ~" in commands[0]
    assert "positioned ^" not in commands[0] and "rotated" not in commands[0]
    assert "Motion:[0.6500d,0.02d,0.0000d]" in commands[0]
    assert '"minecraft:enchantments":{"minecraft:punch":2}' in commands[0]
    assert "damage:0.5d,pickup:0b" in commands[0]
    with pytest.raises(ValueError):
        server.execute_action("parkour_push", "bad player")


def test_punch_arrow_component_syntax_tracks_minecraft_release(monkeypatch):
    server = ParkourServer()
    monkeypatch.setattr("app.parkour_server.secrets.randbelow", lambda _limit: 18000)

    current = server._punch_arrow_command("Streamer", "26.2")
    legacy_components = server._punch_arrow_command("Streamer", "1.21.4")
    assert '"minecraft:enchantments":{"minecraft:punch":2}' in current
    assert '"minecraft:enchantments":{levels:{"minecraft:punch":2}}' in legacy_components
    with pytest.raises(RuntimeError, match="1.21 or newer"):
        server._punch_arrow_command("Streamer", "1.20.4")


def test_parkour_jail_builds_safe_cell_before_teleport(monkeypatch):
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "ok")

    monkeypatch.setattr(server, "player_position", lambda _player: (-4.5, 90.0, 2.5))
    assert server.execute_action("parkour_jail") == "Player is locked in a cage for 20 seconds."
    # The cage is built around the player, never a teleport to another place.
    # The original blocks are copied to a scratch area first, so the map can be
    # restored exactly when the sentence ends.
    assert commands[0] == "clone -6 89 1 -4 93 3 -6 250 1"
    assert commands[1:4] == [
        "fill -6 89 1 -4 89 3 minecraft:polished_deepslate",
        "fill -6 90 1 -4 92 3 minecraft:glass hollow",
        "fill -6 93 1 -4 93 3 minecraft:glass",
    ]
    assert commands[4] == "tp Streamer -4.5 90.2 2.5"
    assert all("1000" not in command for command in commands)


def test_jail_release_removes_the_cage_and_keeps_the_player_in_place(monkeypatch):
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    monkeypatch.setattr(server, "player_position", lambda _player: (-4.5, 90.0, 2.5))

    def rcon(command, **_kwargs):
        commands.append(command)
        return "ok"

    monkeypatch.setattr(server, "_rcon", rcon)
    monkeypatch.setattr(server, "_rcon_checked", lambda command, **_kwargs: commands.append(command) or "ok")

    server.execute_action("parkour_jail")
    commands.clear()
    server.release_jail("Streamer")
    assert commands[0] == "clone -6 250 1 -4 254 3 -6 89 1"
    assert not any(command.endswith("minecraft:air") for command in commands)
    assert any("FREE!" in command for command in commands)
    assert all(command.startswith("tp") is False for command in commands)


@pytest.mark.parametrize(("action", "commands", "message"), [
    ("parkour_slow", ["effect give Streamer minecraft:slowness 7 1 true"], "Slowed down for 7 seconds!"),
    ("parkour_blind", ["effect give Streamer minecraft:darkness 4 0 true"], "Darkness for 4 seconds!"),
    ("parkour_jump", ["effect give Streamer minecraft:jump_boost 4 2 true",
                       "effect give Streamer minecraft:slow_falling 6 0 true"], "High jump with a safe landing!"),
    ("parkour_shield", ["effect give Streamer minecraft:resistance 6 1 true"], "Damage shield for 6 seconds!"),
    ("parkour_cleanse", ["effect clear Streamer minecraft:slowness", "effect clear Streamer minecraft:darkness",
                         "effect clear Streamer minecraft:blindness", "effect clear Streamer minecraft:nausea",
                         "effect clear Streamer minecraft:weakness"], "Negative effects cleared!"),
])
def test_new_parkour_gameplay_actions_are_bounded_and_rcon_safe(monkeypatch, action, commands, message):
    server = ParkourServer()
    sent = []
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    monkeypatch.setattr(server, "_rcon", lambda command: sent.append(command) or "ok")
    assert server.execute_action(action) == message
    assert sent == commands
    with pytest.raises(ValueError, match="Minecraft player name"):
        server.execute_action(action, "bad player")


def test_rcon_action_rejects_minecraft_command_errors_instead_of_reporting_success(monkeypatch):
    server = ParkourServer()
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    commands = []
    def response(command):
        commands.append(command)
        return "Unknown or incomplete command, see below for error"
    monkeypatch.setattr(server, "_rcon", response)
    with pytest.raises(RuntimeError, match="Minecraft rejected the 'effect' command"):
        server.execute_action("parkour_slow")
    assert commands == ["effect give Streamer minecraft:slowness 7 1 true"]


def test_rcon_action_accepts_success_responses(monkeypatch):
    server = ParkourServer()
    monkeypatch.setattr(server, "settings", lambda: {"player": "Streamer"})
    commands = []
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "Applied effect Slowness II to Streamer")
    assert server.execute_action("parkour_slow") == "Slowed down for 7 seconds!"
    assert len(commands) == 1


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
            "parkour_reset", "parkour_antireset", "parkour_checkpoint", "parkour_slow",
            "parkour_blind", "parkour_jump", "parkour_shield", "parkour_cleanse"}.issubset(KNOWN_ACTIONS)
    # Speed and night were removed for good in 0.21.0.
    assert not {"parkour_speed", "parkour_night", "dropper_speed"}.intersection(KNOWN_ACTIONS)


def test_map_datapack_migration_fixes_modifier_json_and_adds_level_timer_hud(tmp_path):
    from app.parkour_server import _patch_map_datapack

    glint = tmp_path / "datapacks/main/data/common/item_modifier/training_mode/glint"
    glint.mkdir(parents=True)
    original = [{"function": "minecraft:set_components",
                 "components": {"minecraft:enchantment_glint_override": False}}]
    # Repair the exact installed-world format left by 0.10.4: an unwrapped
    # array element which still uses the invalid legacy `function` key.
    (glint / "disable.json").write_text(json.dumps(original[0]), encoding="utf-8")
    original[0]["components"]["minecraft:enchantment_glint_override"] = True
    (glint / "enable.json").write_text(json.dumps(original), encoding="utf-8")
    timer = tmp_path / "datapacks/main/data/common/function/timer/display.mcfunction"
    timer.parent.mkdir(parents=True)
    timer.write_text('title @s actionbar [{"text":"timer"}]\n', encoding="utf-8")

    _patch_map_datapack(tmp_path)
    _patch_map_datapack(tmp_path)  # Reconfiguring an existing installation must not stack HUD prefixes.

    for name in ("disable", "enable"):
        resource = json.loads((glint / f"{name}.json").read_text(encoding="utf-8"))
        assert isinstance(resource, dict)
        assert resource["type"] == "minecraft:set_components"
        assert "function" not in resource
    line = timer.read_text(encoding="utf-8")
    assert line.count('"objective":"level"') == 1
    assert '"text":" / 100  ·  "' in line
    assert '"text":"timer"' in line


def test_stop_is_idempotent_when_tracked_server_process_has_exited(monkeypatch, tmp_path):
    from app import parkour_server

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server_dir": str(tmp_path), "rcon_host": "127.0.0.1",
                                    "rcon_port": 25575, "rcon_password": "secret"}), encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "_running_minecraft_clients", lambda: [])
    server = ParkourServer()

    class ExitedProcess:
        returncode = 0

        @staticmethod
        def poll():
            return 0

    server._process = ExitedProcess()
    monkeypatch.setattr(server, "_rcon", lambda _command: pytest.fail("must not contact RCON for an exited process"))
    result = server.stop()
    assert result["running"] is False
    assert result["ready"] is False
    assert "already stopped" in result["message"]


def test_stop_after_app_restart_treats_refused_rcon_as_already_stopped(monkeypatch, tmp_path):
    from app import parkour_server

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server_dir": str(tmp_path), "rcon_host": "127.0.0.1",
                                    "rcon_port": 25575, "rcon_password": "secret"}), encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "_running_minecraft_clients", lambda: [])
    server = ParkourServer()
    commands = []

    def refused(command, **_kwargs):
        commands.append(command)
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(server, "_rcon", refused)
    result = server.stop()
    assert result["running"] is False and result["ready"] is False
    assert "already stopped" in result["message"]
    assert commands == ["stop", "list"]


def test_exited_startup_process_is_never_reported_as_rcon_ready(monkeypatch, tmp_path):
    from app import parkour_server

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server_dir": str(tmp_path), "minecraft_version": "26.3",
                                    "rcon_host": "127.0.0.1", "rcon_port": 25575,
                                    "rcon_password": "secret"}), encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "_running_minecraft_clients", lambda: [])
    server = ParkourServer()

    class ExitedProcess:
        returncode = 0

        @staticmethod
        def poll():
            return 0

    server._process = ExitedProcess()
    monkeypatch.setattr(server, "_rcon", lambda _command: pytest.fail("dead process must not be queried"))
    result = server.status()
    assert result["running"] is False and result["ready"] is False
    assert "code 0" in result["message"]


def test_concurrent_start_requests_spawn_only_one_server_process(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app import parkour_server

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "server.jar").write_bytes(b"jar")
    (server_dir / "eula.txt").write_text("eula=true")
    java = tmp_path / "java"
    java.touch()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server_dir": str(server_dir), "java_required": 21,
                                    "java_executable": str(java), "rcon_host": "127.0.0.1",
                                    "rcon_port": 25575, "rcon_password": "secret"}), encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "_java_major", lambda _path: 21)
    monkeypatch.setattr(parkour_server, "_patch_map_datapack", lambda _world: None)
    monkeypatch.setattr(parkour_server, "_running_minecraft_clients", lambda: [])
    server = ParkourServer()
    calls = []

    class RunningProcess:
        pid = 456
        returncode = None

        @staticmethod
        def poll():
            return None

    def fake_popen(*_args, **_kwargs):
        calls.append("spawn")
        return RunningProcess()

    def no_rcon(command):
        raise ConnectionRefusedError(f"RCON unavailable for {command}")

    monkeypatch.setattr(server, "_rcon", no_rcon)
    monkeypatch.setattr(parkour_server.subprocess, "Popen", fake_popen)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: server.start(), range(2)))
    assert calls == ["spawn"]
    assert all(result["running"] and not result["ready"] for result in results)


def test_status_keeps_cached_rcon_ready_result_during_poll_cooldown(monkeypatch, tmp_path):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from app import parkour_server

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server_dir": str(tmp_path), "rcon_host": "127.0.0.1",
                                    "rcon_port": 25575, "rcon_password": "secret"}), encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "_running_minecraft_clients", lambda: [])
    server = ParkourServer()
    commands = []
    def fake_rcon(command, **_kwargs):
        commands.append(command)
        time.sleep(0.04)
        return "There are 1 of a max of 8 players online: Streamer"
    monkeypatch.setattr(server, "_rcon", fake_rcon)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _index: server.status(), range(2)))
    assert all(status["ready"] for status in statuses)
    assert all(status["players"] == ["Streamer"] for status in statuses)
    assert commands.count("list") == 1


def test_status_reports_rcon_failure_and_preserves_retry_reason(monkeypatch, tmp_path):
    import time
    from app import parkour_server

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server_dir": str(tmp_path), "rcon_host": "127.0.0.1",
                                    "rcon_port": 25575, "rcon_password": "secret"}), encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "_running_minecraft_clients", lambda: [])
    server = ParkourServer()
    class RunningProcess:
        @staticmethod
        def poll():
            return None
    server._process = RunningProcess()
    server._process_started_at = time.monotonic() - 30
    calls = []
    def fail_rcon(command, **_kwargs):
        calls.append(command)
        raise PermissionError("Serwer odrzucił hasło RCON.")
    monkeypatch.setattr(server, "_rcon", fail_rcon)
    first = server.status()
    second = server.status()
    assert first["running"] and not first["ready"]
    assert "RCON does not answer" in first["message"]
    assert "odrzucił hasło" in second["message"]
    assert calls == ["list"]


def test_status_does_not_probe_rcon_during_server_startup_grace(monkeypatch, tmp_path):
    import time
    from app import parkour_server

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server_dir": str(tmp_path), "rcon_host": "127.0.0.1",
                                    "rcon_port": 25575, "rcon_password": "secret"}), encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "_running_minecraft_clients", lambda: [])
    server = ParkourServer()

    class StartingProcess:
        @staticmethod
        def poll():
            return None

    server._process = StartingProcess()
    server._process_started_at = time.monotonic()
    monkeypatch.setattr(server, "_rcon", lambda *_args, **_kwargs: pytest.fail("RCON must wait during warm-up"))
    status = server.status()
    assert status["running"] is True
    assert status["ready"] is False
    assert "loading the world" in status["message"]


def test_server_properties_and_existing_install_disable_whitelist(tmp_path):
    from app.parkour_server import _disable_server_whitelist, _write_server_properties

    properties = tmp_path / "server.properties"
    _write_server_properties(properties, "secret")
    text = properties.read_text(encoding="utf-8")
    assert "online-mode=false" in text
    assert "white-list=false" in text
    assert "enforce-whitelist=false" in text

    properties.write_text("motd=GiftStream\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\n", encoding="utf-8")
    _disable_server_whitelist(properties)
    text = properties.read_text(encoding="utf-8")
    assert "motd=GiftStream" in text
    assert "online-mode=false" in text
    assert "white-list=false" in text
    assert "enforce-whitelist=false" in text
    assert "online-mode=true" not in text
    assert "white-list=true" not in text


def test_ready_existing_server_has_whitelist_disabled_through_rcon(monkeypatch, tmp_path):
    from app import parkour_server

    settings = tmp_path / "minecraft.json"
    settings.write_text(json.dumps({"server_dir": str(tmp_path), "minecraft_version": "26.3",
                                    "rcon_host": "127.0.0.1", "rcon_port": 25575,
                                    "rcon_password": "secret"}), encoding="utf-8")
    (tmp_path / "server.properties").write_text("white-list=true\n", encoding="utf-8")
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings)
    monkeypatch.setattr(parkour_server, "_running_minecraft_clients", lambda: [])
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "_rcon", lambda command, **_kwargs: commands.append(command) or "There are 0 of a max of 8 players online:")

    status = server.status()
    assert status["ready"] is True
    assert commands == ["list", "whitelist off",
                        "gamerule doDaylightCycle false", "time set day", "weather clear"]
    assert "white-list=false" in (tmp_path / "server.properties").read_text(encoding="utf-8")


def test_dropper_setup_uses_separate_vanilla_world_without_external_map(tmp_path, monkeypatch):
    from app import parkour_server

    server = ParkourServer()
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(parkour_server, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(parkour_server, "_resolve_release", lambda version: (version, {}))
    monkeypatch.setattr(parkour_server.shutil, "which", lambda _name: "/usr/bin/java")
    monkeypatch.setattr(parkour_server, "_map_archive", lambda: (_ for _ in ()).throw(AssertionError("dropper must not need Parkour archive")))
    monkeypatch.setattr(parkour_server, "_extract_map", lambda *_args: (_ for _ in ()).throw(AssertionError("no archive extraction")))

    def fake_download(root, version):
        jar = root / "server.jar"
        jar.write_bytes(b"server")
        return jar, 21, version, Path("/usr/bin/java")

    monkeypatch.setattr(parkour_server, "_download_server_jar", fake_download)
    monkeypatch.setattr(server, "start", lambda: {})
    monkeypatch.setattr(server, "status", lambda: {"configured": True, "game_mode": server.settings()["game_mode"]})
    result = server.setup("", "Streamer", True, "26.2", "dropper")
    root = tmp_path / "MinecraftDropper" / "servers" / "26.2"
    settings = json.loads((tmp_path / "settings.json").read_text())
    assert result["game_mode"] == "dropper"
    assert settings["game_mode"] == "dropper"
    assert settings["map_version"] == "GiftStream Dropper 100 Levels 2.0"
    assert (root / "server.jar").is_file()
    assert not (root / "world" / "level.dat").exists()


def test_dropper_map_generation_is_bounded_and_idempotent(tmp_path, monkeypatch):
    from app import parkour_server

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"game_mode": "dropper", "dropper_map_initialized": False,
                                        "dropper_player_levels": {}}))
    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", settings_path)
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "_rcon", lambda command, **_kwargs: commands.append(command) or "ok")
    server.initialize_dropper_map()
    stored = json.loads(settings_path.read_text())
    assert stored["dropper_map_initialized"] is True
    assert sum(command.startswith("fill ") for command in commands) == 905
    assert sum("minecraft:water" in command for command in commands) == 100
    assert sum(command.endswith("hollow") for command in commands) == 100
    assert any("minecraft:cyan_stained_glass" in command for command in commands)
    assert any("minecraft:green_stained_glass" in command for command in commands)
    assert "dropper_map_version" in stored and stored["dropper_map_version"] == 2
    assert stored["map_version"] == "GiftStream Dropper 100 Levels 2.0"
    server.initialize_dropper_map()
    assert len(commands) == 911


def test_dropper_generation_backs_up_overlapping_world_regions_before_edits(tmp_path, monkeypatch):
    from app import parkour_server

    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", tmp_path / "settings.json")
    server_dir = tmp_path / "MinecraftDropper"
    source = server_dir / "world" / "region" / "r.0.0.mca"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pre-existing-world-region")
    state = {"game_mode": "dropper", "server_dir": str(server_dir),
             "dropper_map_initialized": False, "dropper_player_levels": {}}
    parkour_server._write_parkour_settings(state)
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "_rcon", lambda command, **_kwargs: commands.append(command) or "ok")

    server.initialize_dropper_map()

    backups = list((server_dir / "backups").glob("dropper-map-v2-*/region/r.0.0.mca"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"pre-existing-world-region"
    assert commands.index("save-off") < next(i for i, command in enumerate(commands) if command.startswith("fill "))
    assert commands.index("save-on") < next(i for i, command in enumerate(commands) if command.startswith("fill "))


def test_dropper_has_100_distinct_grid_cells_and_parses_entity_position():
    server = ParkourServer()
    assert server._dropper_lane(-3) == 1
    assert server._dropper_lane(101) == 100
    assert server._dropper_cell(1) == (0, 0)
    assert server._dropper_cell(100) == (144, 144)
    assert server._parse_dropper_position(
        "Streamer has the following entity data: [52.5d, 66.0d, 20.5d]") == (52.5, 66.0, 20.5)
    assert server._parse_dropper_position("No entity data") is None


def test_dropper_water_landing_advances_and_final_stage_records_win(tmp_path, monkeypatch):
    from app import parkour_server

    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", tmp_path / "settings.json")
    server = ParkourServer()
    state = {"dropper_player_levels": {"Streamer": 14}, "dropper_completed_players": {}}
    commands = []
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "ok")

    assert server._dropper_progress(state, "Streamer", (52.5, 66.0, 20.5)) == \
        "Level 14/100 cleared — starting level 15/100!"
    assert state["dropper_player_levels"]["Streamer"] == 15
    assert "tp Streamer 68 127 20" in commands
    assert server._dropper_progress(state, "Streamer", (52.5, 80.0, 20.5)) is None

    state["dropper_player_levels"]["Streamer"] = 100
    final_x, final_z = server._dropper_cell(100)
    result = server._dropper_progress(state, "Streamer", (final_x + 4.5, 66.0, final_z + 4.5))
    assert result == "All 100 Dropper levels completed!"
    assert state["dropper_completed_players"]["Streamer"] is True
    assert any("100 LEVELS COMPLETE!" in command for command in commands)


def test_dropper_push_is_a_sudden_strong_shove(monkeypatch):
    server = ParkourServer()
    commands = []
    monkeypatch.setattr(server, "settings", lambda: {
        "player": "Streamer", "game_mode": "dropper", "dropper_map_initialized": True,
        "dropper_player_levels": {"Streamer": 2},
    })
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "ok")

    monkeypatch.setattr("app.parkour_server.secrets.randbelow", lambda _limit: 0)
    assert "Punch II" in server.execute_action("dropper_push")
    assert len(commands) == 1
    assert "execute as Streamer at @s run summon minecraft:arrow ~ ~1.1 ~" in commands[0]
    assert '"minecraft:enchantments":{"minecraft:punch":2}' in commands[0]


def test_dropper_level_actions_clamp_and_persist_stage(tmp_path, monkeypatch):
    from app import parkour_server

    monkeypatch.setattr(parkour_server, "SETTINGS_PATH", tmp_path / "settings.json")
    server = ParkourServer()
    state = {"game_mode": "dropper", "dropper_map_initialized": True,
             "dropper_player_levels": {"Streamer": 5}, "player": "Streamer"}
    commands = []
    monkeypatch.setattr(server, "settings", lambda: state)
    monkeypatch.setattr(server, "_rcon", lambda command: commands.append(command) or "ok")
    assert "level 6/100" in server.execute_action("dropper_level_forward")
    assert state["dropper_player_levels"]["Streamer"] == 6
    assert "level 5/100" in server.execute_action("dropper_level_back")
    assert state["dropper_player_levels"]["Streamer"] == 5
    assert "tp Streamer 68 127 4" in commands
    assert any('LEVEL 5 / 100' in command for command in commands)

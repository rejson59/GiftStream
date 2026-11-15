"""Local 100 Levels Minecraft server bootstrap and loopback RCON control."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import platform
import re
import secrets
import shutil
import socket
import struct
import subprocess
import time
import tempfile
import threading
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .level_checkpoints_data import CHECKPOINTS
from .paths import bundle_root, data_dir
from . import diagnostics

PLAYER_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
MAP_FILENAME = "100-levels-5229-v1.7.4.zip"
MAP_VERSION = "26.2"  # Version the bundled world was prepared and tested against.
# Stable feet positions inspected from the bundled 100 Levels v1.7.4 world.
# Each location sits directly above a clear, supported map block; the datapack's
# dy=150/69 values are selector ranges, not course elevations.
_MAP_LEVEL_SPAWNS: dict[int, tuple[float, float, float]] = {
    1: (-8.5, 112, 5.5), 2: (-24.5, 112, 5.5), 3: (-39.5, 112, 5.5),
    4: (-53.5, 112, 5.5), 5: (-67.5, 112, 5.5), 6: (-82.5, 112, 5.5),
    7: (-95.5, 112, 5.5), 8: (-109.5, 112, 5.5), 9: (-123.5, 112, 5.5),
    10: (-144.5, 96, 5.5), 11: (-143.5, 96, 17.5), 12: (-143.5, 96, 29.5),
    13: (-144.5, 96, 41.5), 14: (-144.5, 96, 53.5), 15: (-143.5, 96, 68.5),
    16: (-143.5, 96, 82.5), 17: (-143.5, 96, 93.5), 18: (-143.5, 96, 104.5),
    19: (-143.5, 96, 115.5), 20: (-143.5, 96, 128.5), 21: (-143.5, 96, 142.5),
    22: (-130.5, 96, 143.5), 23: (-117.5, 96, 144.5), 24: (-103.5, 96, 143.5),
    25: (-88.5, 96, 144.5), 26: (-76.5, 96, 144.5), 27: (-62.5, 96, 144.5),
    28: (-48.5, 96, 144.5), 29: (-37.5, 96, 143.5), 30: (-24.5, 96, 143.5),
    31: (-9.5, 96, 143.5), 32: (-5.5, 96, 132.5), 33: (-5.5, 80, 120.5),
    34: (-5.5, 80, 109.5), 35: (-5.5, 80, 91.5), 36: (-5.5, 80, 78.5),
    37: (-5.5, 96, 63.5), 38: (-5.5, 96, 51.5), 39: (-5.5, 74, 36.5),
    40: (-5.5, 89, 21.5), 41: (-17.5, 96, 18.5), 42: (-35.5, 96, 18.5),
    43: (-52.5, 96, 18.5), 44: (-63.5, 96, 18.5), 45: (-80.5, 80, 18.5),
    46: (-97.5, 96, 18.5), 47: (-117.5, 85, 20.5), 48: (-130.5, 96, 20.5),
    49: (-130.5, 83, 35.5), 50: (-127.5, 80, 51.5), 51: (-130.5, 96, 65.5),
    52: (-129.5, 96, 79.5), 53: (-130.5, 96, 96.5), 54: (-130.5, 96, 110.5),
    55: (-130.5, 96, 127.5), 56: (-116.5, 96, 130.5), 57: (-100.5, 96, 131.5),
    58: (-75.5, 80, 132.5), 59: (-57.5, 80, 131.5), 60: (-40.5, 96, 131.5),
    61: (-20.5, 96, 131.5), 62: (-17.5, 96, 117.5), 63: (-17.5, 80, 99.5),
    64: (-17.5, 90, 79.5), 65: (-17.5, 80, 64.5), 66: (-18.5, 90, 46.5),
    67: (-17.5, 96, 31.5), 68: (-31.5, 96, 32.5), 69: (-52.5, 96, 31.5),
    70: (-71.5, 84, 31.5), 71: (-88.5, 96, 33.5), 72: (-110.5, 80, 33.5),
    73: (-115.5, 80, 50.5), 74: (-115.5, 96, 67.5), 75: (-115.5, 80, 84.5),
    76: (-115.5, 96, 108.5), 77: (-97.5, 64, 115.5), 78: (-79.5, 48, 115.5),
    79: (-56.5, 80, 115.5), 80: (-34.5, 80, 115.5), 81: (-33.5, 32, 98.5),
    82: (-33.5, 80, 76.5), 83: (-33.5, 64, 52.5), 84: (-54.5, 64, 47.5),
    85: (-78.5, 64, 53.5), 86: (-96.5, 80, 52.5), 87: (-96.5, 64, 72.5),
    88: (-95.5, 80, 94.5), 89: (-76.5, 96, 97.5), 90: (-54.5, 96, 97.5),
    91: (-51.5, 80, 74.5), 92: (-26.5, 32, 276.5), 93: (-46.5, 32, 276.5),
    94: (-69.5, 32, 276.5), 95: (-71.5, 32, 296.5), 96: (-71.5, 32, 318.5),
    97: (-49.5, 32, 319.5), 98: (-26.5, 32, 320.5), 99: (-26.5, 32, 296.5),
    100: (-74.5, 96, 74.5),
}
VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
SETTINGS_PATH = data_dir() / "minecraft_parkour.json"
MAX_SERVER_JAR_BYTES = 300 * 1024 * 1024
_VERSION_CACHE: tuple[float, dict[str, Any]] | None = None
_VERSION_CACHE_TTL = 600
_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_RCON_COMMAND_ERROR = re.compile(
    r"(?i)(unknown or incomplete command|unknown command|incorrect argument|"
    r"no entity was found|no player was found|could not find (?:player|entity)|"
    r"unknown (?:effect|scoreboard objective|game ?rule)|"
    r"expected .{1,120} at position)"
)
_WINDOWS_PROCESS_CACHE: tuple[float, list[dict[str, Any]]] = (0.0, [])
_START_LOCK = threading.Lock()
_SERVER_STARTUP_GRACE_SEC = 8.0


def _write_parkour_settings(state: dict[str, Any]) -> None:
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_PATH.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, SETTINGS_PATH)
    server_dir = str(state.get("server_dir", ""))
    if server_dir:
        try:
            root = Path(server_dir).resolve()
            snapshot = root / ".giftstream-state.json"
            staged = root / ".giftstream-state.json.tmp"
            staged.write_text(payload, encoding="utf-8")
            os.replace(staged, snapshot)
        except OSError as exc:
            diagnostics.warning("Could not save the Minecraft world settings backup: %s", exc)


def _map_archive() -> Path:
    for path in (bundle_root() / "assets" / MAP_FILENAME, bundle_root() / MAP_FILENAME):
        if path.is_file():
            return path
    raise FileNotFoundError("The bundled 100 Levels map could not be found.")


def map_level_areas(archive: Path | None = None) -> dict[int, tuple[int, int, int, int, int]]:
    """Read level bounds from the bundled map datapack; values are x,z,dx,dz,dy."""
    with zipfile.ZipFile(archive or _map_archive()) as zf:
        text = zf.read("100 Levels/datapacks/main/data/game/function/level/setlevel.mcfunction").decode("utf-8")
    result = {}
    pattern = re.compile(r"@s\[x=(-?\d+),y=0,z=(-?\d+),dx=(\d+),dy=(\d+),dz=(\d+)\].*? level (\d+)$")
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            x, z, dx, dy, dz, level = map(int, match.groups())
            result[level] = (x, z, dx, dz, dy)
    # The datapack runs every selector in this file each tick, in order, so the
    # last matching line decides the level score. Level 100 simply has two areas
    # (the course stage and the final arena).
    _LEVEL_AREA_ORDER[:] = [
        (int(match.group(6)), int(match.group(1)), int(match.group(2)),
         int(match.group(3)), int(match.group(5)), int(match.group(4)))
        for match in (pattern.search(line) for line in text.splitlines()) if match
    ]
    if len(result) < 90 or not {1, 50, 100}.issubset(result):
        raise ValueError("Could not read the level bounds from the parkour map.")
    return result


# (level, x, z, dx, dz, dy) in the exact order the datapack applies them.
_LEVEL_AREA_ORDER: list[tuple[int, int, int, int, int, int]] = []


def _level_score_at(x: int, y: int, z: int) -> int | None:
    """The ``level`` score the datapack would give this block position.

    Every ``setlevel`` line is a selector for its own level and they are applied
    in file order, so overlapping areas are resolved the same way the map does
    it: the last matching line wins. Level 100 has two areas (course stage and
    final arena) which overlap nothing, but level 52's box is partly covered by
    later lines — that is why a plain "closest centre" guess teleported players
    to the wrong level.
    """
    if not _LEVEL_AREA_ORDER:
        map_level_areas()
    score = None
    for level, ax, az, dx, dz, dy in _LEVEL_AREA_ORDER:
        if ax <= x <= ax + dx and az <= z <= az + dz and 0 <= y <= dy:
            score = level
    if score is not None:
        return score
    # The final levels declare a height limit (dy=69) while their arena extends
    # higher, so a player finishing the map up there would otherwise look "off
    # the map". Fall back to the same horizontal boxes, ignoring the height.
    for level, ax, az, dx, dz, _dy in _LEVEL_AREA_ORDER:
        if ax <= x <= ax + dx and az <= z <= az + dz:
            score = level
    return score


def map_level_spawn_points(areas: dict[int, tuple[int, int, int, int, int]] | None = None
                           ) -> dict[int, tuple[float, float, float]]:
    """Return verified, deterministic landing positions within each map stage."""
    areas = areas if areas is not None else map_level_areas()
    if set(_MAP_LEVEL_SPAWNS) != set(range(1, 101)):
        raise ValueError("A landing point is missing for one of the parkour levels.")
    for level, (px, py, pz) in _MAP_LEVEL_SPAWNS.items():
        if level not in areas:
            raise ValueError(f"The map has no bounds for level {level}.")
        x, z, dx, dz, dy = areas[level]
        if not (x <= px < x + dx + 1 and z <= pz < z + dz + 1 and 0 <= py <= dy + 1):
            raise ValueError(f"The landing point of level {level} falls outside its map area.")
    return dict(_MAP_LEVEL_SPAWNS)


_checkpoint_cache: dict[int, tuple[float, float, float]] | None = None


def level_checkpoints() -> dict[int, tuple[float, float, float]]:
    """Real start points of every 100 Levels level (the player's feet).

    The table lives in :mod:`app.level_checkpoints_data`, i.e. inside the Python
    code, so it is always present in the packaged application. (A separate JSON
    file was not bundled by PyInstaller, which is why level changes failed with
    "no stored checkpoint" in the released .exe.) Each entry was generated from
    the real map blocks by ``tools/build_level_checkpoints.py``.
    """
    global _checkpoint_cache
    if _checkpoint_cache is None:
        _checkpoint_cache = {int(level): (float(spot[0]), float(spot[1]), float(spot[2]))
                             for level, spot in CHECKPOINTS.items()}
    return dict(_checkpoint_cache)


def level_checkpoint(level: int) -> tuple[float, float, float]:
    """Feet position of a level's own checkpoint; clamped to 1..100."""
    points = level_checkpoints()
    level = max(1, min(int(level), 100))
    spot = points.get(level)
    if spot is None:
        raise RuntimeError(f"The bundled map has no checkpoint for level {level}.")
    return spot


def _windows_java_processes() -> list[dict[str, Any]]:
    """Inspect running Java processes without terminating or modifying them."""
    global _WINDOWS_PROCESS_CACHE
    if os.name != "nt":
        return []
    if _WINDOWS_PROCESS_CACHE[0] > time.monotonic():
        return [dict(item) for item in _WINDOWS_PROCESS_CACHE[1]]
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return []
    script = (
        "$items = @(Get-CimInstance Win32_Process -Filter \"Name='java.exe' OR Name='javaw.exe'\" "
        "| ForEach-Object { [pscustomobject]@{ name=$_.Name; path=$_.ExecutablePath; "
        "command=$_.CommandLine; pid=$_.ProcessId } }); "
        "ConvertTo-Json -InputObject $items -Compress"
    )
    try:
        result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, timeout=3, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        value = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else []
        processes = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
    except (OSError, subprocess.SubprocessError, ValueError):
        processes = []
    _WINDOWS_PROCESS_CACHE = (time.monotonic() + 15, processes)
    return [dict(item) for item in processes]


def _launcher_label(path: str) -> str:
    value = path.casefold()
    for key, label in (("horizon", "Horizon Launcher"), ("prism", "Prism Launcher"),
                       ("multimc", "MultiMC"), ("lunar", "Lunar Client"),
                       ("feather", "Feather Launcher"), ("minecraft", "Minecraft Launcher")):
        if key in value:
            return label
    return "Launcher Minecraft Java"


def _running_minecraft_clients() -> list[dict[str, Any]]:
    results = []
    markers = ("net.minecraft.client.main.main", "net.minecraft.launchwrapper.launch",
               "net.fabricmc.loader.impl.launch.knot.knotclient", "cpw.mods.modlauncher.launcher",
               "--gamedir", "--assetsdir")
    for proc in _windows_java_processes():
        command = str(proc.get("command") or "")
        path = str(proc.get("path") or "")
        if not any(marker in command.casefold() for marker in markers):
            continue
        version_match = re.search(r"(?:--version[ =]|-version[ =])([0-9][0-9A-Za-z.+_-]*)", command)
        results.append({"launcher": _launcher_label(path + " " + command),
                        "version": version_match.group(1) if version_match else None,
                        "pid": int(proc.get("pid") or 0)})
    return results


def _java_candidates():
    """Yield likely Java installations in priority order without crawling every root first."""
    seen: set[Path] = set()
    executable_name = "java.exe" if os.name == "nt" else "java"

    def normalize(value: str | Path | None) -> Path | None:
        if not value:
            return None
        path = Path(value).expanduser()
        if path.name.casefold() == "javaw.exe":
            path = path.with_name("java.exe")
        if path.is_dir():
            path = path / "bin" / executable_name
        try:
            path = path.resolve()
        except OSError:
            return None
        return path if path.is_file() and path not in seen else None

    def emit(value: str | Path | None):
        path = normalize(value)
        if path is not None:
            seen.add(path)
            return path
        return None

    quick = emit(shutil.which("java"))
    if quick:
        yield quick
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = emit(Path(java_home) / "bin" / executable_name)
        if candidate:
            yield candidate

    # A running launcher often exposes its exact, already-compatible Java path.
    if os.name == "nt":
        for proc in _windows_java_processes():
            candidate = emit(proc.get("path"))
            if candidate:
                yield candidate

        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        program_files = [Path(os.environ[name]) for name in ("ProgramFiles", "ProgramW6432") if os.environ.get(name)]
        roots = [appdata / ".minecraft" / "runtime", appdata / "Horizon", appdata / "HorizonLauncher",
                 appdata / "PrismLauncher", appdata / "MultiMC", local / "Horizon", local / "HorizonLauncher",
                 local / "PrismLauncher", local / "Programs" / "Horizon Launcher"]
        roots.extend(root / sub for root in program_files for sub in ("Eclipse Adoptium", "Java", "Microsoft"))
        checked = 0
        for root in roots:
            if not root.is_dir():
                continue
            try:
                # rglob is lazy; the first usable runtime returns immediately rather
                # than testing up to 100 executables with a fresh `java -version`.
                for path in root.rglob(executable_name):
                    candidate = emit(path)
                    if candidate:
                        yield candidate
                        checked += 1
                        if checked >= 100:
                            return
            except OSError:
                continue


def _java_major(executable: Path) -> int | None:
    try:
        result = subprocess.run([str(executable), "-version"], capture_output=True,
                                text=True, timeout=6, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = (result.stderr or "") + (result.stdout or "")
        match = re.search(r'version\s+"(?:1\.)?(\d+)', output)
        return int(match.group(1)) if match else None
    except (OSError, subprocess.SubprocessError):
        return None


def find_java(required_major: int) -> tuple[Path, int] | None:
    for executable in _java_candidates():
        major = _java_major(executable)
        if major is not None and major >= required_major:
            return executable, major
    return None


def _safe_extract_java(payload: bytes, destination: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        if len(infos) > 30000 or sum(item.file_size for item in infos) > 800 * 1024 * 1024:
            raise RuntimeError("Archiwum Java przekracza dozwolony rozmiar.")
        root = destination.resolve()
        for item in infos:
            member = PurePosixPath(item.filename.replace("\\", "/"))
            if member.is_absolute() or ".." in member.parts or not member.parts:
                raise RuntimeError("The Java archive contains an unsafe path.")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError("Archiwum Java zawiera niedozwolony link symboliczny.")
            target = (destination / Path(*member.parts)).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("Archiwum Java wychodzi poza katalog instalacji.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
        java_files = list(destination.rglob("java.exe"))
        if not java_files:
            raise RuntimeError("The downloaded Java package does not contain java.exe.")
        return java_files[0]


def _install_java(required_major: int) -> Path:
    """Install an official Adoptium JRE per-user, with no admin rights required."""
    if os.name != "nt":
        raise RuntimeError(f"Java {required_major}+ is required. Install it and start GiftStream again.")
    architecture = platform.machine().casefold()
    arch = "aarch64" if architecture in {"arm64", "aarch64"} else "x64"
    repository = f"adoptium/temurin{required_major}-binaries"
    api_url = f"https://api.github.com/repos/{repository}/releases/latest"
    request = urllib.request.Request(api_url, headers={"User-Agent": "GiftStream/1", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            release_data = response.read(12 * 1024 * 1024 + 1)
    except Exception as exc:
        raise RuntimeError(f"Could not download the Java {required_major} installer from Adoptium: {exc}") from exc
    if len(release_data) > 12 * 1024 * 1024:
        raise RuntimeError("The Java catalog response exceeds the allowed size.")
    release = json.loads(release_data.decode("utf-8"))
    assets = release.get("assets", [])
    wanted = re.compile(rf"^OpenJDK{required_major}U-(?:jre|jdk)_{arch}_windows_hotspot_.*\.zip$", re.IGNORECASE)
    asset = next((item for item in assets if wanted.fullmatch(str(item.get("name", "")))
                  and "jre_" in str(item.get("name", "")).casefold()), None)
    if not asset:
        asset = next((item for item in assets if wanted.fullmatch(str(item.get("name", "")))), None)
    if not asset:
        raise RuntimeError(f"No official Java {required_major} package found for Windows/{arch}.")
    url = str(asset.get("browser_download_url", ""))
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or not parsed.path.startswith(f"/{repository}/releases/download/"):
        raise RuntimeError("Adoptium returned an invalid Java installer URL.")
    request = urllib.request.Request(url, headers={"User-Agent": "GiftStream/1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read(400 * 1024 * 1024 + 1)
    if len(payload) > 400 * 1024 * 1024:
        raise RuntimeError("Instalator Java przekracza dozwolony rozmiar.")
    expected_digest = str(asset.get("digest", ""))
    if expected_digest.startswith("sha256:"):
        expected_digest = expected_digest.split(":", 1)[1]
    if not expected_digest:
        checksum_asset = next((item for item in assets if str(item.get("name", "")) in
                               {str(asset.get("name", "")) + ".sha256.txt", str(asset.get("name", "")) + ".sha256"}), None)
        if checksum_asset:
            checksum_url = str(checksum_asset.get("browser_download_url", ""))
            checksum_parsed = urllib.parse.urlparse(checksum_url)
            if checksum_parsed.scheme == "https" and checksum_parsed.hostname == "github.com" and checksum_parsed.path.startswith(f"/{repository}/releases/download/"):
                checksum_request = urllib.request.Request(checksum_url, headers={"User-Agent": "GiftStream/1"})
                with urllib.request.urlopen(checksum_request, timeout=20) as response:
                    checksum_text = response.read(4096).decode("ascii", errors="replace")
                match = re.search(r"\b([a-fA-F0-9]{64})\b", checksum_text)
                expected_digest = match.group(1) if match else ""
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_digest):
        raise RuntimeError("No valid SHA-256 checksum for the Java installer.")
    if hashlib.sha256(payload).hexdigest().casefold() != expected_digest.casefold():
        raise RuntimeError("The SHA-256 checksum of the Java package is invalid.")

    install_root = data_dir() / "runtime" / f"temurin-{required_major}"
    install_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="java-install-", dir=install_root.parent) as temporary:
        staging = Path(temporary) / "extract"
        staging.mkdir()
        extracted_java = _safe_extract_java(payload, staging)
        java_home = extracted_java.parent.parent
        if install_root.exists():
            shutil.rmtree(install_root)
        shutil.copytree(java_home, install_root)
    executable = install_root / "bin" / "java.exe"
    if not executable.is_file() or (_java_major(executable) or 0) < required_major:
        shutil.rmtree(install_root, ignore_errors=True)
        raise RuntimeError("The automatically installed Java does not meet the Minecraft requirements.")
    return executable


def ensure_java(required_major: int) -> tuple[Path, int]:
    found = find_java(required_major)
    if found:
        diagnostics.info("Found a compatible Java %s: %s.", found[1], found[0])
        return found
    diagnostics.info("Java %s+ was not found; starting the Adoptium runtime installation.", required_major)
    executable = _install_java(required_major)
    actual_major = _java_major(executable) or 0
    if actual_major < required_major:
        raise RuntimeError(f"The installed Java {actual_major} is too old; Java {required_major}+ is required.")
    diagnostics.info("Zainstalowano Java %s: %s.", actual_major, executable)
    return executable, actual_major

def _version_manifest(force: bool = False) -> dict[str, Any]:
    """Fetch/cache Mojang's authoritative release manifest (stable releases only)."""
    global _VERSION_CACHE
    now = time.monotonic()
    if not force and _VERSION_CACHE and _VERSION_CACHE[0] > now:
        return _VERSION_CACHE[1]
    request = urllib.request.Request(VERSION_MANIFEST_URL, headers={"User-Agent": "GiftStream/1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise RuntimeError("Manifest wersji Minecraft przekracza dozwolony rozmiar.")
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("versions"), list):
        raise RuntimeError("Mojang returned an invalid Minecraft version manifest.")
    _VERSION_CACHE = (now + _VERSION_CACHE_TTL, manifest)
    return manifest


def minecraft_versions() -> dict[str, Any]:
    manifest = _version_manifest()
    releases = [
        {"id": str(entry.get("id", "")), "release_time": str(entry.get("releaseTime", ""))}
        for entry in manifest["versions"]
        if isinstance(entry, dict) and entry.get("type") == "release"
        and _VERSION_RE.fullmatch(str(entry.get("id", "")))
    ]
    latest = str(manifest.get("latest", {}).get("release", ""))
    if not any(item["id"] == latest for item in releases):
        raise RuntimeError("Could not determine the newest stable Minecraft version.")
    # A manageable selector: newest 40 releases, always including the bundled-map version.
    choices = releases[:40]
    if not any(item["id"] == MAP_VERSION for item in choices):
        bundled = next((item for item in releases if item["id"] == MAP_VERSION), None)
        if bundled:
            choices.append(bundled)
    return {"latest": latest, "versions": choices, "map_version": MAP_VERSION}


def _resolve_release(requested_version: str = "latest") -> tuple[str, dict[str, Any]]:
    # Revalidate the moving "latest" alias at setup time; a chosen numbered release
    # can use the short-lived manifest cache populated by the version selector.
    manifest = _version_manifest(force=requested_version == "latest")
    selected = str(manifest.get("latest", {}).get("release", "")) if requested_version == "latest" else requested_version
    if not _VERSION_RE.fullmatch(selected):
        raise ValueError("The Minecraft version must be a stable release, e.g. 1.21.11.")
    version = next((entry for entry in manifest["versions"]
                    if isinstance(entry, dict) and entry.get("id") == selected and entry.get("type") == "release"), None)
    if not version:
        raise ValueError(f"Minecraft version {selected} is not available in the official release catalog.")
    return selected, version


def _release_details(version: dict[str, Any]) -> dict[str, Any]:
    version_url = str(version.get("url", ""))
    version_host = urllib.parse.urlparse(version_url).hostname or ""
    if not version_url.startswith("https://") or not (version_host == "piston-meta.mojang.com" or version_host.endswith(".piston-meta.mojang.com")):
        raise RuntimeError("The Minecraft manifest returned an invalid release URL.")
    with urllib.request.urlopen(version_url, timeout=15) as response:
        info = json.loads(response.read().decode("utf-8"))
    if not isinstance(info, dict):
        raise RuntimeError("Mojang returned invalid Minecraft release details.")
    return info


def _download_server_jar(server_dir: Path, requested_version: str = "latest") -> tuple[Path, int, str, Path]:
    """Download a selected official release server jar and verify Mojang's SHA-1."""
    selected, version = _resolve_release(requested_version)
    diagnostics.info("The Mojang manifest chose stable Minecraft %s; downloading the release details.", selected)
    version_info = _release_details(version)
    required_java = int(version_info.get("javaVersion", {}).get("majorVersion", 0))
    if required_java < 1:
        raise RuntimeError(f"Could not read the Java requirements for Minecraft {selected}.")
    diagnostics.info("Minecraft %s wymaga Java %s+.", selected, required_java)
    java_executable, _installed_java = ensure_java(required_java)
    server = version_info.get("downloads", {}).get("server", {})
    url = str(server.get("url", ""))
    host = urllib.parse.urlparse(url).hostname or ""
    if not url.startswith("https://") or not (host == "piston-data.mojang.com" or host.endswith(".piston-data.mojang.com")):
        raise RuntimeError("The Minecraft manifest returned an invalid server URL.")
    request = urllib.request.Request(url, headers={"User-Agent": "GiftStream/1"})
    diagnostics.info("Pobieram plik serwera Minecraft %s z oficjalnego hosta Mojang.", selected)
    with urllib.request.urlopen(request, timeout=90) as response:
        jar = response.read(MAX_SERVER_JAR_BYTES + 1)
    if len(jar) < 1024 or len(jar) > MAX_SERVER_JAR_BYTES:
        raise RuntimeError("The downloaded Minecraft server file has an invalid size.")
    expected_sha1 = str(server.get("sha1", "")).lower()
    if not expected_sha1 or hashlib.sha1(jar).hexdigest() != expected_sha1:
        raise RuntimeError("The SHA-1 checksum of the Minecraft server is invalid or does not match.")
    destination = server_dir / "server.jar"
    temporary = destination.with_suffix(".jar.new")
    temporary.write_bytes(jar)
    os.replace(temporary, destination)
    diagnostics.info("Minecraft server %s downloaded and verified (SHA-1), size %s bytes.", selected, len(jar))
    return destination, required_java, selected, java_executable


def _patch_map_datapack(world: Path) -> None:
    """Adapt known 100 Levels resources to current datapack JSON and add a compact HUD."""
    for name in ("disable", "enable"):
        modifier = world / "datapacks/main/data/common/item_modifier/training_mode/glint" / f"{name}.json"
        try:
            value = json.loads(modifier.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Could not read the map modifier {modifier.name}: {exc}") from exc
        # Minecraft 26.3 expects a typed object resource. The bundled map
        # stores a one-element loot-function array with the old `function` key;
        # simply unwrapping it is insufficient (26.3 reports "No key type").
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            value = value[0]
        if not isinstance(value, dict):
            raise ValueError(f"Unknown map modifier format {modifier.name}; it cannot be migrated safely.")
        modifier_type = value.pop("function", value.get("type"))
        if modifier_type != "minecraft:set_components":
            raise ValueError(f"Unknown map modifier format {modifier.name}; it cannot be migrated safely.")
        value["type"] = modifier_type
        modifier.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # The map already renders its timer in the actionbar. Add the player's
    # scoreboard level to those same actionbar messages (rather than replacing
    # the timer or taking over the map's optional sidebar scoreboard).
    timer_display = world / "datapacks/main/data/common/function/timer/display.mcfunction"
    try:
        lines = timer_display.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"The map timer display function is missing: {exc}") from exc
    updated = []
    hud = [
        {"text": "LEVEL ", "color": "yellow", "bold": True},
        {"score": {"objective": "level", "name": "@s"}, "color": "yellow", "bold": True},
        {"text": " / 100  ·  ", "color": "dark_gray"},
    ]
    for line in lines:
        if " actionbar " not in line:
            updated.append(line)
            continue
        command, payload = line.split(" actionbar ", 1)
        try:
            components = json.loads(payload)
        except ValueError as exc:
            raise ValueError("Could not update the map timer display.") from exc
        if not isinstance(components, list):
            raise ValueError("Unknown map timer display format.")
        if not any(isinstance(component, dict)
                   and component.get("score", {}).get("objective") == "level"
                   for component in components):
            components = hud + components
        updated.append(command + " actionbar " + json.dumps(components, ensure_ascii=False, separators=(",", ":")))
    if not any(" actionbar " in line for line in updated):
        raise ValueError("The map timer actionbar display was not found.")
    timer_display.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _extract_map(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        infos = [item for item in zf.infolist() if not item.is_dir()]
        total = sum(item.file_size for item in infos)
        if total > 100 * 1024 * 1024 or len(infos) > 5000:
            raise ValueError("The map archive exceeds the allowed size.")
        required = {"100 Levels/level.dat", "100 Levels/datapacks/main/pack.mcmeta"}
        if not required.issubset({item.filename for item in infos}):
            raise ValueError("The archive does not contain a valid Minecraft 100 Levels map.")
        for item in infos:
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "100 Levels":
                raise ValueError("The map archive contains an unsafe path.")
            # Reject Unix symlinks so extraction cannot escape the selected server folder.
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("The map archive contains a forbidden symbolic link.")
            relative = Path(*path.parts[1:])
            target = (destination / relative).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError("A map file path leaves the world directory.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(item) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def _world_copy_signature(world: Path) -> str:
    """Signature of the current world: the map plus any local edit keeps it stable."""
    digest = hashlib.sha256(b"giftstream-map-reset-v1")
    top_level = [world / "level.dat", world / "datapacks/main/pack.mcmeta"]
    for path in top_level:
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
    region_dir = world / "region"
    if region_dir.is_dir():
        for path in sorted(region_dir.glob("*.mca")):
            digest.update(path.name.encode("utf-8"))
            try:
                digest.update(path.stat().st_mtime_ns.to_bytes(8, "little", signed=False))
                digest.update(str(path.stat().st_size).encode("ascii"))
            except OSError:
                digest.update(b"<unreadable>")
    return digest.hexdigest()


def _archive_marker(marker: Path, signature: str) -> None:
    try:
        marker.write_text(json.dumps({"signature": signature, "map": MAP_FILENAME,
                                      "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                                     indent=1), encoding="utf-8")
    except OSError as exc:
        diagnostics.warning("Could not write the map reset marker: %s", exc)


def _replace_world_with_bundled_map(root: Path, backup_stage: Path) -> str:
    """Install a pristine copy of the bundled map, replacing the current world.

    Called on every start so a streamer can never face a world they changed by
    accident (broken command blocks, a hole in the course, leftover jail blocks).
    The new map is unpacked next to the world first; only then is it swapped in,
    so an interrupted extraction leaves the old world untouched. Space is not
    doubled: the previous world is deleted right after a successful swap.
    """
    world = root / "world"
    staged = root / ".giftstream-world-stage"
    shutil.rmtree(staged, ignore_errors=True)
    shutil.rmtree(backup_stage, ignore_errors=True)  # leftovers from a killed reset
    staged.mkdir(parents=True, exist_ok=True)
    try:
        _extract_map(_map_archive(), staged)
        _patch_map_datapack(staged)
        if not (staged / "level.dat").is_file():
            raise FileNotFoundError("The unpacked map has no level.dat.")
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    previous = None
    if world.exists():
        previous = backup_stage
        try:
            shutil.rmtree(previous, ignore_errors=True)
            # shutil.move copes with a server folder on another drive (a user-picked
            # path may sit on D: while %LOCALAPPDATA% is on C:); os.replace would fail
            # there with EXDEV.
            shutil.move(str(world), str(previous))
        except OSError as exc:
            diagnostics.warning("Could not move the old world aside (%s); replacing it directly.", exc)
            shutil.rmtree(world, ignore_errors=True)
            previous = None
    try:
        shutil.move(str(staged), str(world))
    except OSError:
        # Restore the previous world instead of leaving the installation empty.
        if previous is not None and not world.exists():
            shutil.move(str(previous), str(world))
        raise
    marker = root / ".giftstream-map-reset.json"
    _archive_marker(marker, _world_copy_signature(world))
    if previous is not None:
        shutil.rmtree(previous, ignore_errors=True)
    diagnostics.info("The bundled 100 Levels map was restored in %s before the server start.", world)
    return _world_copy_signature(world)


def _write_server_properties(path: Path, password: str) -> None:
    values = {
        "motd": "GiftStream · Parkour 100 Levels",
        "level-name": "world",
        "server-ip": "127.0.0.1",
        "server-port": "25565",
        "enable-rcon": "true",
        "rcon.port": "25575",
        "rcon.password": password,
        # This server is loopback-only; avoid Mojang session-server throttling for local joins.
        "online-mode": "false",
        "white-list": "false",
        "enforce-whitelist": "false",
        "gamemode": "adventure",
        "difficulty": "normal",
        "max-players": "8",
        "view-distance": "8",
        "simulation-distance": "6",
        "spawn-protection": "0",
        "allow-flight": "true",
        "enable-command-block": "true",
    }
    path.write_text("# GiftStream local parkour server settings\n" + "\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")


def _disable_server_whitelist(properties: Path) -> None:
    """Keep the private localhost server joinable without online authentication or a whitelist."""
    try:
        lines = properties.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    overrides = {"online-mode": "false", "white-list": "false", "enforce-whitelist": "false"}
    seen: set[str] = set()
    updated: list[str] = []
    for line in lines:
        key, sep, _value = line.partition("=")
        if sep and key.strip() in overrides:
            if key.strip() not in seen:
                updated.append(f"{key.strip()}=false")
                seen.add(key.strip())
        else:
            updated.append(line)
    for key, value in overrides.items():
        if key not in seen:
            updated.append(f"{key}={value}")
    if updated == lines:
        return
    temporary = properties.with_suffix(properties.suffix + ".tmp")
    temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
    os.replace(temporary, properties)


def _recv_packet(sock: socket.socket) -> tuple[int, int, str]:
    header = _recv_exact(sock, 4)
    length = struct.unpack("<i", header)[0]
    if length < 10 or length > 1_000_000:
        raise ConnectionError("RCON returned an invalid packet")
    payload = _recv_exact(sock, length)
    packet_id, packet_type = struct.unpack("<ii", payload[:8])
    text = payload[8:-2].decode("utf-8", errors="replace")
    return packet_id, packet_type, text


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        part = sock.recv(count - len(chunks))
        if not part:
            raise ConnectionError("The Minecraft server closed the RCON connection")
        chunks.extend(part)
    return bytes(chunks)


def _send_packet(sock: socket.socket, packet_id: int, packet_type: int, text: str) -> None:
    body = struct.pack("<ii", packet_id, packet_type) + text.encode("utf-8") + b"\0\0"
    sock.sendall(struct.pack("<i", len(body)) + body)


class ParkourServer:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._process_started_at = 0.0
        self._next_rcon_probe_at = 0.0
        self._rcon_retry_delay = 1.0
        self._last_status_ready: bool | None = None
        self._last_status_snapshot: dict[str, Any] | None = None
        # Active jail cages: player -> cage position and size (for cleanup).
        self._cages: dict[str, dict[str, int]] = {}
        self._last_daylight_check = 0.0
        self._status_lock = threading.RLock()
        self._last_logged_exit: int | None = None

    def settings(self) -> dict[str, Any]:
        try:
            value = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return {}
            if value.get("server_dir") and "game_mode" not in value:
                # Migrate existing Parkour installs before users create/switch modes,
                # preserving their RCON credentials and world location per server.
                value["game_mode"] = "parkour"
                _write_parkour_settings(value)
            return value
        except (OSError, ValueError, TypeError):
            return {}

    def save_settings(self, state: dict[str, Any]) -> None:
        _write_parkour_settings(state)

    def _server_log_path(self) -> Path | None:
        server_dir = str(self.settings().get("server_dir", ""))
        return Path(server_dir) / "giftstream-server.log" if server_dir else None

    def diagnostic_lines(self, limit: int = 100) -> list[str]:
        """Return a safe, bounded tail of the JVM log for the copyable app diagnostics."""
        log_path = self._server_log_path()
        if log_path is None:
            return []
        try:
            # Server logs may grow for the entire stream; seek from the end instead
            # of loading the whole file whenever the dashboard refreshes diagnostics.
            with log_path.open("rb") as file:
                file.seek(0, os.SEEK_END)
                size = file.tell()
                file.seek(max(0, size - 256 * 1024), os.SEEK_SET)
                tail = file.read().decode("utf-8", errors="replace")
            lines = tail.splitlines()[-max(1, min(limit, 200)):]
        except OSError:
            return []
        return [f"[MINECRAFT] {diagnostics.redact(line)}" for line in lines]

    def clear_diagnostic_logs(self) -> None:
        log_path = self._server_log_path()
        if log_path is None or not log_path.exists():
            return
        try:
            log_path.write_text("", encoding="utf-8")
        except OSError as exc:
            diagnostics.warning("Could not clear the Minecraft log file %s: %s", log_path, exc)

    def setup(self, server_dir: str, player: str, eula_accepted: bool, version: str = "latest",
              game_mode: str = "parkour") -> dict[str, Any]:
        if not eula_accepted:
            raise ValueError("Accept the Minecraft EULA before creating the server.")
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Enter a Minecraft nickname: 3–16 letters, digits or underscores.")
        if game_mode not in {"parkour", "dropper"}:
            raise ValueError("Unsupported Minecraft mode.")
        selected_version, _version_info = _resolve_release(version)
        if server_dir.strip():
            root = Path(server_dir).expanduser().resolve()
        else:
            folder = "MinecraftDropper" if game_mode == "dropper" else "MinecraftParkour"
            root = (data_dir() / folder / "servers" / selected_version).resolve()
        if root == Path(root.anchor) or root == data_dir().resolve():
            raise ValueError("Choose a separate folder for the local Minecraft server.")
        state = self.settings()
        if self._process is not None and self._process.poll() is None:
            if (state.get("server_dir") != str(root) or state.get("minecraft_version") != selected_version
                    or state.get("game_mode", "parkour") != game_mode):
                raise RuntimeError("Stop the running server before switching the Minecraft mode or version.")
            return self.status()
        if state and (state.get("server_dir") != str(root) or state.get("minecraft_version") != selected_version
                      or state.get("game_mode", "parkour") != game_mode):
            try:
                self._rcon("list", log_failure=False)
            except Exception:
                pass
            else:
                raise RuntimeError("A server running in the background was detected. Stop it before switching versions so you do not lose RCON control.")
        root.mkdir(parents=True, exist_ok=True)
        if (state.get("server_dir") != str(root) or state.get("minecraft_version") != selected_version
                or state.get("game_mode", "parkour") != game_mode):
            snapshot = root / ".giftstream-state.json"
            try:
                saved_state = json.loads(snapshot.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                saved_state = {}
            world_ready = game_mode == "dropper" or (root / "world" / "level.dat").is_file()
            if (saved_state.get("server_dir") == str(root)
                    and saved_state.get("minecraft_version") == selected_version
                    and saved_state.get("game_mode", "parkour") == game_mode
                    and (root / "server.jar").is_file() and (root / "eula.txt").is_file() and world_ready):
                _write_parkour_settings(saved_state)
                if game_mode == "parkour":
                    _patch_map_datapack(root / "world")
                diagnostics.info("Restored the saved Minecraft %s server from its world directory.", game_mode)
                self.start()
                return self.status()
        if (state.get("server_dir") == str(root) and state.get("minecraft_version") == selected_version
                and state.get("game_mode", "parkour") == game_mode and (root / "server.jar").is_file()
                and (game_mode == "dropper" or (root / "world" / "level.dat").is_file())):
            if game_mode == "parkour":
                _patch_map_datapack(root / "world")
            self.start()
            return self.status()
        if any(root.iterdir()):
            raise FileExistsError("The selected version folder is not empty. World data is protected — choose another folder or version.")

        password = secrets.token_urlsafe(24)
        map_stage = root / ".giftstream-world-stage"
        phase = "checking the map"
        diagnostics.info("Starting Minecraft %s (%s) setup for player %s in %s.",
                         game_mode, selected_version, player, root)
        try:
            if game_mode == "parkour":
                _map_archive()  # Fail before downloading server files if the bundled world is absent.
            phase = "pobieranie serwera i przygotowanie Java"
            diagnostics.info("Pobieram oficjalny serwer Minecraft %s i sprawdzam wymagania Java.", selected_version)
            jar, required_java, installed_version, java_executable = _download_server_jar(root, selected_version)
            diagnostics.info("Server downloaded and verified; using Java %s (%s).", required_java, java_executable)
            if game_mode == "parkour":
                phase = "unpacking the Parkour map"
                map_stage.mkdir()
                _extract_map(_map_archive(), map_stage)
                _patch_map_datapack(map_stage)
                staged_level = map_stage / "level.dat"
                if not staged_level.is_file():
                    raise FileNotFoundError(f"The file {staged_level} is missing after unpacking the map.")
                os.replace(map_stage, root / "world")
                diagnostics.info("The 100 Levels map is unpacked and installed as %s/world.", root)
            else:
                diagnostics.info("The Dropper Arena will be generated in a vanilla world through controlled RCON commands after start.")
            phase = "zapisywanie konfiguracji serwera"
            (root / "eula.txt").write_text("# Accepted in GiftStream setup\neula=true\n", encoding="ascii")
            _write_server_properties(root / "server.properties", password)
            state = {"server_dir": str(root), "player": player,
                     "rcon_host": "127.0.0.1", "rcon_port": 25575,
                     "server_address": "localhost:25565", "minecraft_version": installed_version,
                     "map_version": MAP_VERSION if game_mode == "parkour" else "GiftStream Dropper 100 Levels 2.0",
                     "game_mode": game_mode, "dropper_map_initialized": False,
                     "java_required": required_java, "java_executable": str(java_executable), "server_jar": str(jar)}
            _write_parkour_settings({**state, "rcon_password": password})
            diagnostics.info("Server configuration and EULA consent saved in %s.", root)
        except Exception as exc:
            diagnostics.error("Minecraft setup (%s) failed during the '%s' stage: %s",
                              game_mode, phase, exc, exc_info=exc)
            shutil.rmtree(map_stage, ignore_errors=True)
            if game_mode == "parkour":
                shutil.rmtree(root / "world", ignore_errors=True)
            for generated in (root / "server.jar", root / "server.jar.new", root / "eula.txt", root / "server.properties"):
                try:
                    generated.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    diagnostics.warning("Could not clean up the file %s: %s", generated, cleanup_error)
            raise
        shutil.rmtree(map_stage, ignore_errors=True)
        diagnostics.info("Setup finished; starting the Minecraft server %s.", installed_version)
        self.start()
        return self.status()

    def reset_world(self) -> dict[str, Any]:
        """Restore the bundled map on demand (the server has to be stopped first).

        Every start already does this automatically; the endpoint exists so a
        streamer can recover mid-session without hunting for the Run button.
        """
        state = self.settings()
        if not state.get("server_dir"):
            raise RuntimeError("Create the local Minecraft server first.")
        if state.get("game_mode", "parkour") != "parkour":
            raise RuntimeError("The map reset only applies to the Parkour mode.")
        if self._process is not None and self._process.poll() is None:
            raise RuntimeError("Stop the Minecraft server before resetting the map.")
        if state.get("last_launch_failed"):
            # A previous launch died before the world was loaded, so any answer on
            # the RCON port comes from another server and must not block the reset.
            diagnostics.warning("The last Minecraft launch failed; skipping the RCON liveness check.")
        else:
            try:
                self._rcon("list", log_failure=False)
            except Exception:
                pass
            else:
                raise RuntimeError("Stop the Minecraft server before resetting the map.")
        root = Path(str(state["server_dir"]))
        backup = root / ".giftstream-world-before-reset"
        state["world_reset_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state["world_reset_signature"] = _replace_world_with_bundled_map(root, backup)
        self.save_settings(state)
        return {**self.status(), "message": "The 100 Levels map was restored from the bundled copy."}

    def start(self) -> dict[str, Any]:
        # Serialize startup requests so rapid clicks/API retries cannot spawn two JVMs.
        with _START_LOCK:
            return self._start_once()

    def _start_once(self) -> dict[str, Any]:
        state = self.settings()
        root = Path(str(state.get("server_dir", "")))
        diagnostics.info("Request to start the Minecraft server (version %s, directory %s).",
                         state.get("minecraft_version", "nieznana"), root)
        jar = root / "server.jar"
        if not jar.is_file() or not (root / "eula.txt").is_file():
            raise RuntimeError("Create the local parkour server first.")
        _disable_server_whitelist(root / "server.properties")
        if self._process is not None and self._process.poll() is None:
            return self.status()
        # The server is deliberately detached from the dashboard process. After a
        # GiftStream restart, discover an already-running instance through loopback
        # RCON instead of launching a duplicate on the same port.
        try:
            self._rcon("list", log_failure=False)
            diagnostics.info("A running local Minecraft server was already detected via RCON; not starting a duplicate.")
            return self.status()
        except Exception:
            pass
        if state.get("game_mode", "parkour") == "parkour":
            # Every start begins on a pristine copy of the bundled map: a streamer who
            # changed something (or a session that left blocks behind) can never end up
            # with a broken course. The previous world is kept until the new one is in
            # place, so an interrupted reset cannot destroy the installation.
            previous = root / ".giftstream-world-before-reset"
            try:
                state["world_reset_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                state["world_reset_signature"] = _replace_world_with_bundled_map(root, previous)
                _write_parkour_settings(state)
            except Exception as exc:
                diagnostics.error("Could not restore the 100 Levels map before the start: %s",
                                  exc, exc_info=exc)
                raise RuntimeError(f"Could not restore the 100 Levels map: {exc}") from exc
        try:
            required_java = int(state.get("java_required") or 0)
            if required_java < 1:
                legacy_version = str(state.get("minecraft_version") or state.get("map_version") or MAP_VERSION)
                _version_id, version_entry = _resolve_release(legacy_version)
                version_details = _release_details(version_entry)
                required_java = int(version_details.get("javaVersion", {}).get("majorVersion", 0))
                if required_java < 1:
                    raise RuntimeError(f"Could not determine the Java requirements for Minecraft {legacy_version}.")
                state["java_required"] = required_java
            configured_java = Path(str(state.get("java_executable", "")))
            if configured_java.is_file() and (_java_major(configured_java) or 0) >= required_java:
                java = configured_java
            else:
                java, _major = ensure_java(required_java)
                state["java_executable"] = str(java)
                _write_parkour_settings(state)
        except Exception as exc:
            raise RuntimeError(f"Could not prepare Java for the Minecraft server: {exc}") from exc
        log = (root / "giftstream-server.log").open("ab")
        kwargs: dict[str, Any] = {"cwd": str(root), "stdin": subprocess.DEVNULL,
                                  "stdout": log, "stderr": subprocess.STDOUT, "close_fds": True}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        else:
            kwargs["start_new_session"] = True
        try:
            self._process = subprocess.Popen([
                java, "-Xms512M", "-Xmx2G", "-XX:+UseG1GC",
                "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=150",
                "-jar", str(jar), "nogui",
            ], **kwargs)
            self._process_started_at = time.monotonic()
            self._last_status_snapshot = None
            self._next_rcon_probe_at = self._process_started_at + _SERVER_STARTUP_GRACE_SEC
            self._rcon_retry_delay = 1.0
            self._last_logged_exit = None
            self._last_status_ready = None
            if state.get("last_launch_failed"):
                state.pop("last_launch_failed", None)
                _write_parkour_settings(state)
            diagnostics.info("Minecraft server process started (PID %s); stdout/stderr goes to %s.",
                             self._process.pid, root / "giftstream-server.log")
        except Exception as exc:
            diagnostics.error("Could not start the Minecraft server process: %s", exc, exc_info=exc)
            raise
        finally:
            log.close()
        return self.status()

    def _rcon(self, command: str, *, log_failure: bool = True) -> str:
        state = self.settings()
        host = str(state.get("rcon_host", "127.0.0.1"))
        port = int(state.get("rcon_port", 25575))
        password = str(state.get("rcon_password", ""))
        if host != "127.0.0.1" or not password or not (1 <= port <= 65535):
            raise RuntimeError("No secure RCON configuration on localhost.")
        command_kind = command.split(maxsplit=1)[0] if command else "<empty>"
        try:
            with socket.create_connection((host, port), timeout=3) as sock:
                sock.settimeout(3)
                _send_packet(sock, 1, 3, password)
                packet_id, _packet_type, _ = _recv_packet(sock)
                if packet_id == -1:
                    raise PermissionError("The server rejected the RCON password.")
                if packet_id != 1:
                    _recv_packet(sock)
                _send_packet(sock, 2, 2, command)
                response_id, _response_type, text = _recv_packet(sock)
                if response_id != 2:
                    raise ConnectionError("Invalid RCON response.")
                return text.strip()
        except Exception as exc:
            # Log only the command verb: chat payloads, player data and secrets
            # must not leak into the copyable diagnostics.
            if log_failure:
                diagnostics.warning("The RCON command '%s' failed: %s", command_kind, exc)
            raise

    def _rcon_checked(self, command: str, *, log_success: bool = True) -> str:
        """Reject vanilla error responses; RCON otherwise returns syntax/target errors as text."""
        result = self._rcon(command)
        if _RCON_COMMAND_ERROR.search(result):
            command_kind = command.split(maxsplit=1)[0] if command else "<empty>"
            diagnostics.error("Minecraft rejected the RCON command '%s': %s", command_kind, result[:500])
            raise RuntimeError(f"Minecraft rejected the '{command_kind}' command: {result[:500]}")
        if log_success:
            diagnostics.info("Minecraft answered RCON '%s': %s", command.split(maxsplit=1)[0], result[:300])
        return result

    def status(self) -> dict[str, Any]:
        # Polls can arrive from the dashboard and action endpoints concurrently.
        # Serialize probe/backoff/cache updates so a slow stale poll cannot overwrite
        # a newer successful RCON result.
        with self._status_lock:
            return self._read_status()

    def _read_status(self) -> dict[str, Any]:
        state = self.settings()
        clients = _running_minecraft_clients()
        client_info = {"minecraft_client_running": bool(clients), "minecraft_clients": clients}
        if not state:
            self._last_status_snapshot = None
            return {"configured": False, "running": False, "ready": False,
                    "server_address": "localhost:25565", "players_online": 0, "players": [],
                    **client_info,
                    "message": "Create the local server and import the 100 Levels map."}
        _disable_server_whitelist(Path(str(state.get("server_dir", ""))) / "server.properties")
        stage_map = state.get("dropper_player_levels", {})
        stage_value = stage_map.get(str(state.get("player", "")), 1) if isinstance(stage_map, dict) else 1
        response = {"configured": True, "running": False, "ready": False,
                    "server_address": state.get("server_address", "localhost:25565"),
                    "server_dir": state.get("server_dir", ""), "player": state.get("player", ""),
                    "minecraft_version": state.get("minecraft_version", MAP_VERSION),
                    "map_version": state.get("map_version", MAP_VERSION),
                    "game_mode": state.get("game_mode", "parkour"),
                    "dropper_completed": bool(state.get("dropper_completed_players", {}).get(str(state.get("player", "")))),
                    "dropper_stage": self._dropper_lane(stage_value) if state.get("game_mode") == "dropper" else None,
                    "java_required": state.get("java_required"),
                    "security_warning": "Offline mode does not verify Microsoft accounts. The server is meant for local connections only — do not expose ports 25565/25575 to the internet.",
                    "chat_relay_enabled": bool(state.get("chat_relay_enabled", False)),
                    "world_reset_at": state.get("world_reset_at"),
                    "world_reset_on_start": True,
                    "players_online": 0, "players": [], **client_info,
                    "message": "The server is starting — the first launch may take a moment."}
        if self._process is not None and self._process.poll() is not None:
            code = int(self._process.returncode or 0)
            response["message"] = f"The server exited (code {code}). Check giftstream-server.log."
            if self._last_logged_exit != code:
                diagnostics.error("The Minecraft server process exited with code %s. JVM log: %s",
                                  code, Path(str(state.get("server_dir", ""))) / "giftstream-server.log")
                self._last_logged_exit = code
                # Remember it: a world reset must not be blocked by an RCON answer
                # coming from some other server on this machine.
                if state.get("server_dir"):
                    state["last_launch_failed"] = True
                    _write_parkour_settings(state)
            self._last_status_ready = False
            self._last_status_snapshot = None
            return response
        now = time.monotonic()
        process_running = self._process is not None and self._process.poll() is None
        if process_running:
            response["running"] = True
        # The vanilla server spends its first seconds loading registries/world data.
        # Do not block setup or hammer an unopened RCON socket during warm-up.
        if process_running and now - self._process_started_at < _SERVER_STARTUP_GRACE_SEC:
            response["message"] = "Minecraft is loading the world and registries…"
            return response
        if now < self._next_rcon_probe_at:
            # Keep the last authoritative RCON result during the short poll interval.
            # Otherwise a dashboard polling every two seconds can repeatedly land just
            # before the next probe and display a false "waiting for RCON" state.
            if self._last_status_snapshot is not None:
                return {**self._last_status_snapshot, **client_info}
            retry_in = max(1, int(self._next_rcon_probe_at - now + 0.999))
            response["message"] = f"Minecraft is configured; RCON will be checked again in {retry_in} s."
            return response
        try:
            listing = self._rcon("list", log_failure=False)
            if state.get("game_mode") == "dropper" and not state.get("dropper_map_initialized"):
                self.initialize_dropper_map()
                state = self.settings()
            if self._last_status_ready is not True:
                # Existing servers can retain whitelist=true from older properties.
                # RCON runs as console, so disable it once they become reachable.
                try:
                    self._rcon("whitelist off", log_failure=False)
                    diagnostics.info("The Parkour server whitelist was disabled; the server is local and needs no allow list.")
                except Exception as exc:
                    diagnostics.warning("Could not disable the whitelist via RCON: %s", exc)
            player_match = re.search(r"There are (\d+) of a max of \d+ players online:(.*)", listing, re.IGNORECASE)
            players = [name.strip() for name in (player_match.group(2) if player_match else "").split(",") if name.strip()]
            response.update({"running": True, "ready": True,
                             "players_online": int(player_match.group(1)) if player_match else len(players),
                             "players": players,
                             "message": "Minecraft gotowy · " + (listing or "RCON connected")})
            if (state.get("game_mode") == "dropper"
                    and any(name.casefold() == str(state.get("player", "")).casefold() for name in players)):
                player = str(state.get("player", ""))
                try:
                    position_output = self._rcon(f"data get entity {player} Pos", log_failure=False)
                    position = self._parse_dropper_position(position_output)
                    if position:
                        self._dropper_progress(state, player, position)
                except Exception as exc:
                    diagnostics.warning("Could not check the Dropper landing: %s", exc)
                state = self.settings()
                stage_map = state.get("dropper_player_levels", {})
                response["dropper_stage"] = self._dropper_lane(stage_map.get(player, 1)) if isinstance(stage_map, dict) else 1
                response["dropper_completed"] = bool(state.get("dropper_completed_players", {}).get(player))
            self._detect_level_from_position(response)
            self._enforce_daylight_periodically()
            self._rcon_retry_delay = 1.0
            # The dashboard polls more often than this; serve the cached ready result
            # between probes to avoid opening a fresh RCON socket on every refresh.
            self._next_rcon_probe_at = now + 4.0
            if self._last_status_ready is not True:
                diagnostics.info("The Minecraft server is ready and answers over RCON (%s).", state.get("server_address", "localhost:25565"))
            self._last_status_ready = True
            self._last_status_snapshot = dict(response)
        except Exception as exc:
            response["running"] = process_running
            self._next_rcon_probe_at = now + self._rcon_retry_delay
            retry_in = max(1, int(self._rcon_retry_delay + 0.999))
            self._rcon_retry_delay = min(8.0, self._rcon_retry_delay * 1.7)
            response["message"] = f"The server is running but RCON does not answer; retrying in {retry_in} s. ({exc})"
            if self._last_status_ready is not False:
                diagnostics.warning("The Minecraft server is not ready over RCON yet: %s", exc)
            self._last_status_ready = False
            self._last_status_snapshot = dict(response)
        return response

    def stop(self) -> dict[str, Any]:
        if not self.settings():
            diagnostics.warning("A Minecraft stop was requested, but the server is not configured.")
            return self.status()
        if self._process is not None and self._process.poll() is not None:
            code = int(self._process.returncode or 0)
            diagnostics.info("The Minecraft server was already stopped (process code %s); skipping the RCON stop.", code)
            self._last_status_ready = False
            return {**self.status(), "message": f"The server is already stopped (code {code}); RCON is not needed."}

        diagnostics.info("Sending a safe stop command to the local Minecraft server.")
        try:
            self._rcon("stop")
        except Exception as exc:
            if self._process is not None and self._process.poll() is None:
                diagnostics.error("Could not stop Minecraft via RCON: %s", exc, exc_info=exc)
                raise RuntimeError(f"Could not stop the server via RCON: {exc}") from exc
            # After a GiftStream restart there may be no tracked Popen handle. A
            # refused connection plus a non-ready status is an idempotent stop,
            # not an API error that encourages repeated stop/start attempts.
            current = self.status()
            if not current.get("running") and not current.get("ready"):
                diagnostics.info("RCON is unreachable and the server is not running; treating the stop as complete.")
                return {**current, "message": "The server is already stopped or does not answer via RCON."}
            diagnostics.error("Could not stop Minecraft via RCON: %s", exc, exc_info=exc)
            raise RuntimeError(f"Could not stop the server via RCON: {exc}") from exc
        self._last_status_ready = False
        self._last_status_snapshot = None
        return {**self.status(), "message": "A safe shutdown command was sent to the server."}

    def command(self, command: str) -> str:
        return self._rcon_checked(command)

    def relay_chat(self, message: str) -> str:
        """Relay plain TikTok chat text to Minecraft without interpreting it as a command."""
        if not isinstance(message, str) or not message:
            raise ValueError("The chat message is empty.")
        if len(message) > 2000:
            raise ValueError("The chat message exceeds the safe limit of 2000 characters.")
        # Tellraw's JSON text component safely encodes quotes, slashes and command
        # characters as data. Preserve the message text (including punctuation and
        # Unicode) exactly; never prepend a username or pass it through RCON raw.
        component = json.dumps({"text": message}, ensure_ascii=False, separators=(",", ":"))
        return self._rcon_checked(f"tellraw @a {component}")

    @staticmethod
    def _dropper_lane(stage: int) -> int:
        return max(1, min(100, int(stage)))

    @staticmethod
    def _dropper_cell(stage: int) -> tuple[int, int]:
        stage = ParkourServer._dropper_lane(stage) - 1
        return (stage % 10) * 16, (stage // 10) * 16

    def _dropper_teleport(self, player: str, stage: int) -> None:
        stage = self._dropper_lane(stage)
        x0, z0 = self._dropper_cell(stage)
        self._rcon_checked(f"tp {player} {x0 + 4} 127 {z0 + 4}")
        title = json.dumps({"text": f"LEVEL {stage} / 100", "color": "aqua", "bold": True},
                           ensure_ascii=False, separators=(",", ":"))
        self._rcon_checked(f"title {player} actionbar {title}")

    @staticmethod
    def _parse_dropper_position(output: str) -> tuple[float, float, float] | None:
        number = r"(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)[dDfF]?"
        match = re.search(rf"\[\s*{number}\s*,\s*{number}\s*,\s*{number}\s*\]", output)
        return tuple(map(float, match.groups())) if match else None

    def _dropper_progress(self, state: dict[str, Any], player: str,
                          position: tuple[float, float, float]) -> str | None:
        """Auto-advance only when the configured player lands in their current water pool."""
        levels = state.setdefault("dropper_player_levels", {})
        stage = self._dropper_lane(levels.get(player, 1))
        completed = state.setdefault("dropper_completed_players", {})
        if completed.get(player):
            return None
        x, y, z = position
        x0, z0 = self._dropper_cell(stage)
        if not (65.5 <= y <= 68.5 and x0 - 0.25 <= x <= x0 + 9.25
                and z0 - 0.25 <= z <= z0 + 9.25):
            return None
        if stage >= 100:
            completed[player] = True
            _write_parkour_settings(state)
            title = json.dumps({"text": "100 LEVELS COMPLETE!", "color": "gold", "bold": True},
                               ensure_ascii=False, separators=(",", ":"))
            self._rcon_checked(f"title {player} title {title}")
            diagnostics.info("Player %s finished the 100-level Dropper map.", player)
            return "All 100 Dropper levels completed!"
        next_stage = stage + 1
        self._dropper_teleport(player, next_stage)
        levels[player] = next_stage
        completed.pop(player, None)
        _write_parkour_settings(state)
        diagnostics.info("Player %s cleared Dropper level %s/100.", player, stage)
        return f"Level {stage}/100 cleared — starting level {next_stage}/100!"

    def initialize_dropper_map(self) -> None:
        """Generate a bounded, replayable 100-stage vanilla Dropper with no third-party plugins."""
        state = self.settings()
        if (state.get("game_mode") != "dropper"
                or (state.get("dropper_map_initialized") and state.get("dropper_map_version") == 2)):
            return
        diagnostics.info("Building the vanilla Dropper 100 Levels map (100 cells, 3 obstacles each).")
        def build(command: str) -> str:
            return self._rcon_checked(command, log_success=False)
        # Snapshot the small set of existing world region files touched by the
        # migration/generator before issuing any block edits. If a backup cannot
        # be made, fail closed rather than risk overwriting a user's local builds.
        server_dir = Path(str(state.get("server_dir", "")))
        world_dir = server_dir / "world"
        region_ids = {f"{rx}.{rz}" for rx in (-1, 0) for rz in (-1, 0)}
        backup_sources = [world_dir / directory / f"r.{region_id}.mca"
                          for directory in ("region", "entities", "poi")
                          for region_id in region_ids]
        existing_sources = [path for path in backup_sources if path.is_file()]
        if existing_sources:
            try:
                self._rcon_checked("save-all flush", log_success=False)
                self._rcon_checked("save-off", log_success=False)
                backup_dir = server_dir / "backups" / f"dropper-map-v2-{time.strftime('%Y%m%d-%H%M%S')}"
                try:
                    for source in existing_sources:
                        destination = backup_dir / source.relative_to(world_dir)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, destination)
                    (backup_dir / "README.txt").write_text(
                        "Pre-migration backup of Minecraft world region files that overlap the generated Dropper 100 Levels arena.\n"
                        "Original world files remain in ../world; this snapshot is retained for manual recovery.\n",
                        encoding="utf-8")
                    diagnostics.info("Backed up %s world region files before generating the Dropper: %s",
                                     len(existing_sources), backup_dir)
                finally:
                    self._rcon_checked("save-on", log_success=False)
            except Exception as exc:
                diagnostics.error("Could not back up the regions before generating the Dropper: %s", exc)
                raise RuntimeError("Could not protect the Minecraft world; the Dropper map was not changed.") from exc
        # Remove the former five-lane arena only in its documented bounds; preserve
        # every other part of the user's local world before replacing the minigame.
        for old_lane in range(5):
            old_x = old_lane * 18
            build(f"fill {old_x - 1} 65 -1 {old_x + 9} 126 9 minecraft:air")
        glass_colors = ("cyan_stained_glass", "orange_stained_glass", "magenta_stained_glass",
                        "lime_stained_glass", "purple_stained_glass", "yellow_stained_glass",
                        "light_blue_stained_glass", "red_stained_glass", "pink_stained_glass",
                        "green_stained_glass")
        obstacle_colors = ("light_gray_stained_glass", "blue_stained_glass", "orange_stained_glass",
                           "magenta_stained_glass", "lime_stained_glass")
        for stage in range(1, 101):
            x0, z0 = self._dropper_cell(stage)
            color = glass_colors[(stage - 1) // 10]
            build(
                f"fill {x0 - 1} 65 {z0 - 1} {x0 + 9} 126 {z0 + 9} minecraft:{color} hollow")
            # A 3×3 entrance lets the player drop from the checkpoint above the shaft.
            build(f"fill {x0 + 3} 126 {z0 + 3} {x0 + 5} 126 {z0 + 5} minecraft:air")
            build(f"fill {x0} 66 {z0} {x0 + 8} 66 {z0 + 8} minecraft:water")
            for layer, y in enumerate((110, 92, 74)):
                # Deterministic pseudo-random routes make all 100 stages distinct
                # and reproducible when migrating an older local Dropper world.
                hole_size = 3 if stage <= 20 else 2
                hole_x = (stage * 3 + layer * 4) % (10 - hole_size)
                hole_z = (stage * 5 + layer * 2) % (10 - hole_size)
                obstacle = obstacle_colors[(stage + layer) % len(obstacle_colors)]
                build(
                    f"fill {x0} {y} {z0} {x0 + 8} {y} {z0 + 8} minecraft:{obstacle}")
                build(
                    f"fill {x0 + hole_x} {y} {z0 + hole_z} "
                    f"{x0 + hole_x + hole_size - 1} {y} {z0 + hole_z + hole_size - 1} minecraft:air")
            if stage % 10 == 0:
                diagnostics.info("Wygenerowano szyby Droppera %s/100.", stage)
        # Same rule rename as the daylight lock: 26.x wants snake_case names.
        if self._rules_are_snake_case(str(state.get("minecraft_version", MAP_VERSION))):
            keep_inventory, no_mobs = "gamerule keep_inventory true", "gamerule spawn_mobs false"
        else:
            keep_inventory, no_mobs = "gamerule keepInventory true", "gamerule doMobSpawning false"
        for command in (keep_inventory, no_mobs,
                        *self.daylight_commands(str(state.get("minecraft_version", MAP_VERSION))),
                        "setworldspawn 4 127 4"):
            build(command)
        levels = state.get("dropper_player_levels", {})
        state["dropper_map_initialized"] = True
        state["dropper_map_version"] = 2
        state["map_version"] = "GiftStream Dropper 100 Levels 2.0"
        state["dropper_player_levels"] = ({str(player): self._dropper_lane(stage)
                                          for player, stage in levels.items()}
                                         if isinstance(levels, dict) else {})
        state["dropper_completed_players"] = {}
        _write_parkour_settings(state)
        player = str(state.get("player", ""))
        if PLAYER_RE.fullmatch(player):
            try:
                self._rcon("list", log_failure=False)
                self._dropper_teleport(player, state["dropper_player_levels"].get(player, 1))
            except Exception:
                # The map is ready even if the streamer has not joined the server yet.
                pass
        diagnostics.info("Dropper 100 Levels v2 ready: 100 routes, 3 obstacles per level, water checkpoints.")

    def get_player_level(self, player: str) -> int:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        output = self._rcon_checked(f"scoreboard players get {player} level")
        match = re.search(r"has\s+(-?\d+)\s+\[level\]", output) or re.search(r"(-?\d+)", output)
        if not match:
            raise RuntimeError(f"Could not read the map level: {output or 'the player may be off the map'}")
        return int(match.group(1))

    def player_position(self, player: str) -> tuple[float, float, float] | None:
        """The player's current position from RCON; ``None`` when the player is offline."""
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        output = self._rcon(f"data get entity {player} Pos", log_failure=False)
        match = re.search(r"\[(-?[\d.]+)d?,?\s+(-?[\d.]+)d?,?\s+(-?[\d.]+)d?\]", output)
        if not match:
            return None
        return tuple(float(value) for value in match.groups())

    def level_at_position(self, position: tuple[float, float, float] | None) -> int | None:
        """Which level the player stands in, using the map's own area rules.

        The datapack resolves overlapping boxes by applying its ``setlevel``
        lines in order, so a plain "closest area centre" guess could answer
        level 52 for a player who is really on 74/75, and could answer level 100
        for the final arena while the player was still on the last course stage.
        Here the very same rule is applied, and the map checkpoint floors are
        only used as a sanity check for positions far outside the stages.
        """
        if not position:
            return None
        x, y, z = math.floor(position[0]), math.floor(position[1]), math.floor(position[2])
        score = _level_score_at(x, y, z)
        if score is not None:
            return score
        # Not inside any stage box (e.g. the lobby or a fall below the course):
        # fall back to the vertically nearest checkpoint of a box we are above.
        points = level_checkpoints()
        candidates: list[tuple[float, int]] = []
        for level, (ax, az, dx, dz, _dy) in map_level_areas().items():
            if not (ax - 2 <= x <= ax + dx + 2 and az - 2 <= z <= az + dz + 2):
                continue
            floor = points.get(level)
            if floor is None:
                continue
            candidates.append((abs(y - floor[1]), level))
        if not candidates:
            return None
        distance, level = min(candidates)
        return level if distance <= 24 else None

    def get_player_level_or_position(self, player: str) -> int:
        """Player level: the real position first, then the map scoreboard.

        The datapack only writes the ``level`` score while the player stands
        inside a stage box, so the stored score can be stale (it kept the old
        value after a teleport). The position is therefore the primary source
        and the scoreboard is only a fallback.
        """
        position = self.player_position(player)
        detected = self.level_at_position(position)
        if detected is not None:
            return detected
        if position is not None:
            # The position is known but it is outside every stage (lobby, spectator,
            # below the course). The stored score is usually stale there — trusting it
            # is what teleported players to level 100 while they stood in the lobby.
            raise RuntimeError(
                "The player is not on a parkour stage (lobby or off the course), so the "
                "current level is unknown. Walk onto a checkpoint first.")
        try:
            return self.get_player_level(player)
        except (RuntimeError, ValueError):
            raise RuntimeError(
                "Cannot tell which level the player is on — make sure they stand on the map, "
                "not in the lobby or below the course.") from None

    # The arrow is spawned one block away from the player and flies back through
    # their hitbox. The spawn spot is probed with `execute if block ... #minecraft:air`
    # first, so the arrow never starts inside a wall — that was the reason Punch II
    # sometimes did not connect on the tight 1-block corridors of the map.
    PUNCH_DIRECTIONS = 8
    PUNCH_OFFSET = 1.0

    def _punch_arrow_command(self, player: str, minecraft_version: str = MAP_VERSION,
                             direction: int | None = None) -> str:
        """Shoot an arrow *into* the player, so Punch II always lands.

        The arrow starts one block in front of the player's chest and flies back
        into their hitbox. That way it visibly flies *at* the runner (0.21.0
        spawned it inside them, so it looked like it flew away) and Punch II
        knockback — which only happens on a real hit — always triggers. The spawn
        spot is outside the player's block, so a wall behind them cannot block it,
        and :meth:`punch_player` checks the block first so the arrow never starts
        inside a wall either.
        """
        version_match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?$", minecraft_version)
        version = tuple(map(int, version_match.groups(default="0"))) if version_match else (0, 0, 0)
        if version < (1, 21, 0):
            raise RuntimeError("The Punch II arrow requires Minecraft 1.21 or newer. Change the server version.")
        enchantments = ('{"minecraft:punch":2}' if version >= (1, 21, 5)
                        else '{levels:{"minecraft:punch":2}}')
        if direction is None:
            direction = secrets.randbelow(self.PUNCH_DIRECTIONS)
        angle = math.radians(direction * (360 / self.PUNCH_DIRECTIONS)
                             + (secrets.randbelow(3600) / 10 if direction is None else 0))
        # `or 0.0` turns -0.0 into 0.0, so the commands read cleanly.
        offset_x = round(math.cos(angle) * self.PUNCH_OFFSET, 4) or 0.0
        offset_z = round(math.sin(angle) * self.PUNCH_OFFSET, 4) or 0.0
        # The knockback direction is the arrow's flight direction: straight back
        # through the player, with a little push so the shove is always visible.
        motion_x = -offset_x * 0.4
        motion_z = -offset_z * 0.4
        return (
            f"execute as {player} at @s run summon minecraft:arrow "
            f"~{offset_x:.4f} ~1.0 ~{offset_z:.4f} "
            f'{{Motion:[{motion_x:.4f}d,0.0d,{motion_z:.4f}d],damage:0.5d,pickup:0b,'
            f'crit:0b,weapon:{{id:"minecraft:bow",count:1,components:{{"minecraft:enchantments":{enchantments}}}}}}}'
        )

    def _arrow_spot_is_free(self, player: str, direction: int) -> bool:
        """Is the block one step out (at chest height) free for the arrow?"""
        angle = math.radians(direction * (360 / self.PUNCH_DIRECTIONS))
        offset_x = round(math.cos(angle) * self.PUNCH_OFFSET, 4) or 0.0
        offset_z = round(math.sin(angle) * self.PUNCH_OFFSET, 4) or 0.0
        # World-axis `~` offsets, exactly like the summon: mixing `^` (player-local)
        # here would probe a different direction than the arrow is spawned in.
        output = self._rcon(
            f"execute as {player} at @s if block ~{offset_x:.4f} ~1.0 ~{offset_z:.4f} "
            f"#minecraft:air run data get entity {player} Pos", log_failure=False)
        return "failed" not in output.casefold() and bool(output)

    def punch_player(self, player: str, minecraft_version: str = MAP_VERSION) -> str:
        """Fire the Punch II arrow from the first free spot around the player."""
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        start = secrets.randbelow(self.PUNCH_DIRECTIONS)
        for step in range(self.PUNCH_DIRECTIONS):
            direction = (start + step) % self.PUNCH_DIRECTIONS
            if not self._arrow_spot_is_free(player, direction):
                continue
            self._rcon_checked(self._punch_arrow_command(player, minecraft_version, direction))
            return "A Punch II arrow flew at the player."
        # Every direction is solid — a fully sealed box. The arrow would start
        # inside a block and never connect, so report it instead of pretending.
        raise RuntimeError("There is no free space around the player for the Punch II arrow "
                           "(the player seems to be sealed in).")

    @staticmethod
    def _heart_commands(player: str) -> list[str]:
        """Follow → hearts and a short ovation (no speed: it would disturb the run)."""
        return [
            f"execute at {player} run particle minecraft:heart ~ ~2 ~ 1.2 1 1.2 0.05 40 force",
            f"execute at {player} run particle minecraft:happy_villager ~ ~2 ~ 1 1 1 0.05 30 force",
            f"title {player} actionbar "
            + json.dumps({"text": "THANK YOU FOR THE FOLLOW!", "color": "light_purple", "bold": True},
                         separators=(",", ":")),
        ]

    @staticmethod
    def _disco_commands(player: str) -> list[str]:
        return [
            f"execute at {player} run particle minecraft:end_rod ~ ~2 ~ 1.5 1 1.5 0.2 120 force",
            f"execute at {player} run particle minecraft:note ~ ~2 ~ 1 1 1 0.1 60 force",
        ]

    @staticmethod
    def _blackout_commands(player: str, seconds: int = 15) -> list[str]:
        """“So dark you can barely see” — darkness + blindness, with daylight kept on.

        Darkness alone dims the screen, but in a bright environment the map is
        still readable. Blindness cuts the view down to a few blocks, so the
        effect really lands on stream. The world time is never changed.
        """
        seconds = max(3, min(int(seconds), 120))
        return [
            f"effect give {player} minecraft:darkness {seconds} 0 true",
            f"effect give {player} minecraft:blindness {seconds} 0 true",
            f"title {player} actionbar "
            + json.dumps({"text": f"BLACKOUT · {seconds} s", "color": "dark_purple", "bold": True},
                         separators=(",", ":")),
        ]

    def _detect_level_from_position(self, response: dict[str, Any]) -> None:
        """Fills ``response['level']`` from the player's real position.

        The map scoreboard is sometimes empty (e.g. after a teleport or when the
        player stands between areas), so the level is also computed from the
        position — the same method the “next/previous level” actions use.
        """
        player = str(response.get("player") or "")
        if response.get("game_mode") == "dropper" or not PLAYER_RE.fullmatch(player):
            return
        try:
            position = self.player_position(player)
        except Exception as exc:
            diagnostics.warning("Could not read the player position: %s", exc)
            return
        if position is None:
            return
        response["position"] = ["%.2f" % value for value in position]
        detected = self.level_at_position(position)
        if detected is not None:
            response["level"] = detected
        elif response.get("level") is None:
            response["level"] = None

    def _enforce_daylight_periodically(self) -> None:
        """The map always looks like daytime — even after /time from another source."""
        now = time.monotonic()
        if now - self._last_daylight_check < 60:
            return
        self._last_daylight_check = now
        self.keep_daylight()

    @staticmethod
    def _level_jump(action: str, params: dict[str, Any], current: int) -> tuple[int, int]:
        """Resolve a fixed-distance level jump ("10 levels up/down") into a target level.

        Returns ``(target, requested)``; ``requested`` is the signed distance so the
        caller can report an edge case honestly instead of silently doing nothing.
        """
        forward = action.endswith("forward")
        step = 1 if forward else -1
        raw = params.get("levels", 10)
        try:
            distance = abs(int(raw))
        except (TypeError, ValueError):
            raise ValueError("The level jump needs a whole number of levels.") from None
        if distance < 1:
            raise ValueError("A level jump needs at least one level.")
        distance = min(distance, 99)
        target = max(1, min(100, current + step * distance))
        return target, step * distance

    def execute_action(self, action: str, player: str | None = None,
                       params: dict[str, Any] | None = None) -> str:
        state = self.settings()
        player = player or str(state.get("player", ""))
        params = params or {}
        diagnostics.info("Running Minecraft action '%s' for player %s.", action, player or "unset")
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Set the Minecraft player name first.")
        if action.startswith("dropper_"):
            if state.get("game_mode") != "dropper":
                raise RuntimeError("Switch to Dropper mode to use this action.")
            if not state.get("dropper_map_initialized"):
                raise RuntimeError("The Dropper map is still being prepared — try again in a moment.")
            levels = state.setdefault("dropper_player_levels", {})
            stage = self._dropper_lane(levels.get(player, 1))
            if action == "dropper_push":
                message = self.punch_player(player, str(state.get("minecraft_version", MAP_VERSION)))
                return message + " Inside the shaft."
            if action in {"dropper_level_forward", "dropper_level_back",
                          "dropper_level_jump_forward", "dropper_level_jump_back"}:
                if "jump" in action:
                    target, _requested = self._level_jump(action, params, stage)
                else:
                    target = self._dropper_lane(stage + (1 if action.endswith("forward") else -1))
                levels[player] = target
                state.setdefault("dropper_completed_players", {}).pop(player, None)
                self._dropper_teleport(player, target)
                _write_parkour_settings(state)
                if "jump" in action:
                    return f"Moved the player to level {target}/100 ({stage} → {target})."
                return f"Moved the player to level {target}/100."
            if action == "dropper_reset":
                levels[player] = 1
                state.setdefault("dropper_completed_players", {}).pop(player, None)
                self._dropper_teleport(player, 1)
                _write_parkour_settings(state)
                return "Back to the first Dropper level."
            effects = {
                "dropper_slow": ([f"effect give {player} minecraft:slowness 7 1 true"],
                                 "Slowed down for 7 seconds!"),
                "dropper_blind": ([f"effect give {player} minecraft:darkness 4 0 true"],
                                  "Darkness for 4 seconds!"),
                "dropper_blackout": (self._blackout_commands(player, 15),
                                     "Blackout: you can barely see for 15 seconds!"),
                "dropper_lightning": ([f"execute at {player} run summon minecraft:lightning_bolt ~ ~ ~"],
                                      "Lightning strikes the player!"),
                "dropper_disco": (self._disco_commands(player), "Disco!"),
                "dropper_heart": (self._heart_commands(player), "Thanks for the follow!"),
                "dropper_jump": ([f"effect give {player} minecraft:jump_boost 4 2 true",
                                  f"effect give {player} minecraft:slow_falling 6 0 true"],
                                 "High jump with a safe landing!"),
                "dropper_shield": ([f"effect give {player} minecraft:resistance 6 1 true"],
                                   "Damage shield for 6 seconds!"),
                "dropper_cleanse": ([f"effect clear {player} minecraft:slowness",
                                     f"effect clear {player} minecraft:darkness",
                                     f"effect clear {player} minecraft:blindness",
                                     f"effect clear {player} minecraft:nausea",
                                     f"effect clear {player} minecraft:weakness"],
                                    "Negative effects cleared!"),
            }
            if action in effects:
                commands, message = effects[action]
                for command in commands:
                    self._rcon_checked(command)
                self.keep_daylight()
                return message
            raise ValueError("Unsupported Dropper action.")
        if action == "parkour_push":
            self.punch_player(player, str(state.get("minecraft_version", MAP_VERSION)))
            diagnostics.info("Punch II arrow sent to %s.", player)
            self.keep_daylight()
            return "A Punch II arrow flew at the player."
        if action in {"parkour_level_forward", "parkour_level_back",
                      "parkour_level_jump_forward", "parkour_level_jump_back"}:
            current = self.get_player_level_or_position(player)
            if "jump" in action:
                # "10 levels up/down at once" — one rule, fixed distance (params).
                target, requested = self._level_jump(action, params, current)
            else:
                requested = 1 if action.endswith("forward") else -1
                target = max(1, min(100, current + requested))
            if target == current:
                edge = "last" if requested > 0 else "first"
                return f"Player is already on the {edge} level ({current}/100)."
            if "jump" in action:
                self.teleport_to_checkpoint(player, target)
                diagnostics.info("Jumped %s by %s levels: %s → level %s.",
                                 player, abs(requested), current, target)
                distance = abs(target - current)
                note = "" if distance == abs(requested) else f" (shortened by the map edge from {abs(requested)})"
                return f"Teleported {distance} levels to the checkpoint of level {target}/100 ({current} → {target}){note}."
            self.teleport_to_checkpoint(player, target)
            diagnostics.info("Teleported %s to the checkpoint of level %s (was %s).", player, target, current)
            return f"Teleported to the checkpoint of level {target}/100 ({current} → {target})."
        if action == "parkour_checkpoint":
            level = self.get_player_level_or_position(player)
            self.teleport_to_checkpoint(player, level)
            return f"Sent back to the checkpoint of level {level}/100."
        effects = {
            "parkour_slow": ([f"effect give {player} minecraft:slowness 7 1 true"],
                             "Slowed down for 7 seconds!"),
            "parkour_blind": ([f"effect give {player} minecraft:darkness 4 0 true"],
                              "Darkness for 4 seconds!"),
            "parkour_blackout": (self._blackout_commands(player, 15),
                                 "Blackout: you can barely see for 15 seconds!"),
            "parkour_heart": (self._heart_commands(player), "Thanks for the follow!"),
            "parkour_lightning": ([f"execute at {player} run summon minecraft:lightning_bolt ~ ~ ~"],
                                  "Lightning strikes the player!"),
            "parkour_disco": (self._disco_commands(player), "Disco!"),
            "parkour_jump": ([f"effect give {player} minecraft:jump_boost 4 2 true",
                              f"effect give {player} minecraft:slow_falling 6 0 true"],
                             "High jump with a safe landing!"),
            "parkour_shield": ([f"effect give {player} minecraft:resistance 6 1 true"],
                               "Damage shield for 6 seconds!"),
            "parkour_cleanse": ([f"effect clear {player} minecraft:slowness",
                                 f"effect clear {player} minecraft:darkness",
                                 f"effect clear {player} minecraft:blindness",
                                 f"effect clear {player} minecraft:nausea",
                                 f"effect clear {player} minecraft:weakness"],
                                "Negative effects cleared!"),
        }
        if action in effects:
            commands, message = effects[action]
            for command in commands:
                self._rcon_checked(command)
            diagnostics.info("Applied Parkour effect '%s' to %s.", action, player)
            self.keep_daylight()
            return message
        if action == "parkour_jail":
            seconds = int(params.get("seconds", 20) or 20)
            return self.jail_player(player, seconds=seconds)
        if action in {"parkour_reset", "parkour_antireset"}:
            raise RuntimeError("The reset countdown is coordinated by GiftStream.")
        raise ValueError("Unsupported parkour action.")

    # -- mapa: checkpointy i poziom -----------------------------------------
    def teleport_to_checkpoint(self, player: str, level: int) -> str:
        """Teleport exactly onto the level's own checkpoint from the map data."""
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        x, y, z = level_checkpoint(level)
        # `spawnpoint` keeps the map's own "back to checkpoint" working after a fall,
        # and a short slow-fall keeps a mid-air checkpoint from hurting the player.
        self._rcon_checked(f"tp {player} {x:.2f} {y:.2f} {z:.2f}")
        self._rcon(f"execute as {player} at @s run spawnpoint {player} ~ ~ ~", log_failure=False)
        self._rcon(f"effect give {player} minecraft:slow_falling 3 0 true", log_failure=False)
        self._rcon_checked(
            f"title {player} actionbar "
            + json.dumps({"text": f"LEVEL {level}/100", "color": "gold", "bold": True},
                         separators=(",", ":")))
        return f"Teleported to level {level}."

    # -- permanent daylight --------------------------------------------------
    @staticmethod
    def _rules_are_snake_case(minecraft_version: str = MAP_VERSION) -> bool:
        """Java 1.21.11 (and 26.x) moved game rules into a registry with new names."""
        version_match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?$", minecraft_version)
        major, minor, patch = (tuple(map(int, version_match.groups(default="0")))
                               if version_match else (0, 0, 0))
        return (major, minor, patch) >= (1, 21, 11) or major > 1

    @staticmethod
    def daylight_commands(minecraft_version: str = MAP_VERSION) -> tuple[str, ...]:
        """Commands that lock the world to a bright, rain-free day.

        Java 1.21.11 moved every game rule into a registry and renamed them to
        snake_case: ``doDaylightCycle`` became ``advance_time`` (and
        ``doWeatherCycle`` became ``advance_weather``). On those versions the old
        names are rejected, which is why the daylight lock silently did nothing.
        """
        if ParkourServer._rules_are_snake_case(minecraft_version):
            return ("gamerule advance_time false", "time set day",
                    "gamerule advance_weather false", "weather clear")
        return ("gamerule doDaylightCycle false", "time set day",
                "gamerule doWeatherCycle false", "weather clear")

    def keep_daylight(self) -> None:
        """The stream must always look like day — no night, no weather changes."""
        state = self.settings()
        version = str(state.get("minecraft_version", MAP_VERSION))
        commands = self.daylight_commands(version)
        for command in commands:
            try:
                result = self._rcon(command, log_failure=False)
            except Exception as exc:
                diagnostics.warning("Could not enforce daylight: %s", exc)
                return
            if _RCON_COMMAND_ERROR.search(result or ""):
                # A rule name the server does not know: retry with the other naming
                # scheme instead of silently leaving the night running.
                swapped = self._swap_rule_name(command)
                if swapped is None:
                    continue
                try:
                    retry = self._rcon(swapped, log_failure=False)
                except Exception as exc:
                    diagnostics.warning("Could not enforce daylight with %r: %s", swapped, exc)
                    continue
                if _RCON_COMMAND_ERROR.search(retry or ""):
                    diagnostics.warning("The server accepted neither %r nor %r.", command, swapped)

    @staticmethod
    def _swap_rule_name(command: str) -> str | None:
        """Map a game rule command between the pre-1.21.11 and 26.x names."""
        pairs = (("doDaylightCycle", "advance_time"), ("doWeatherCycle", "advance_weather"),
                 ("keepInventory", "keep_inventory"), ("doMobSpawning", "spawn_mobs"))
        for old, new in pairs:
            for source, target in ((old, new), (new, old)):
                if source in command:
                    return command.replace(source, target)
        return None

    # -- jail: a temporary glass cage above the player ------------------------
    JAIL_RADIUS = 1          # 3 x 3 footprint
    JAIL_HEIGHT = 4          # two blocks of wall plus the roof
    JAIL_LIFT = 2            # the cage floor floats 2 blocks above the ground
    JAIL_MATERIAL = "minecraft:iron_bars"   # see-through cage walls
    JAIL_FLOOR = "minecraft:glass"          # floor and roof

    def jail_player(self, player: str, seconds: int = 20) -> str:
        """Build a small floating cage around the player, for a few seconds.

        The cage hovers above the ground the player stands on, so it is clear of
        the course. Every block is placed with ``keep``, which only fills space
        that is still air: the cage can therefore never overwrite — let alone
        destroy — a map block, not even on a 1-block corridor where a wall sits
        exactly on the cage edge. Releasing it only replaces the cage material
        back with air (``replace`` filter), so the world is left untouched.
        """
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        position = self.player_position(player)
        if not position:
            raise RuntimeError("The player is not on the server, so there is nothing to cage.")
        block_x, block_z = math.floor(position[0]), math.floor(position[2])
        # The block under the feet: feet on a block boundary (y = 90.0) means the
        # player stands on block 89, otherwise they are above block 90.
        ground_y = math.floor(position[1]) - (0 if position[1] % 1 else 1)
        floor_y = ground_y + 1 + self.JAIL_LIFT
        x0, z0 = block_x - self.JAIL_RADIUS, block_z - self.JAIL_RADIUS
        x1, z1 = block_x + self.JAIL_RADIUS, block_z + self.JAIL_RADIUS
        wall_top = floor_y + self.JAIL_HEIGHT - 1
        self._cages[player] = {"x0": x0, "z0": z0, "x1": x1, "z1": z1,
                               "y0": floor_y, "y1": wall_top,
                               "return": (block_x + 0.5, ground_y + 1.2, block_z + 0.5)}
        material = self.JAIL_MATERIAL
        commands = [
            # Floor and roof.
            f"fill {x0} {floor_y} {z0} {x1} {floor_y} {z1} {self.JAIL_FLOOR} keep",
            f"fill {x0} {wall_top} {z0} {x1} {wall_top} {z1} {self.JAIL_FLOOR} keep",
            # Four walls, each one a 3-wide, 2-high slab of bars.
            f"fill {x0} {floor_y + 1} {z0} {x1} {wall_top - 1} {z0} {material} keep",
            f"fill {x0} {floor_y + 1} {z1} {x1} {wall_top - 1} {z1} {material} keep",
            f"fill {x0} {floor_y + 1} {z0} {x0} {wall_top - 1} {z1} {material} keep",
            f"fill {x1} {floor_y + 1} {z0} {x1} {wall_top - 1} {z1} {material} keep",
            f"tp {player} {block_x + 0.5} {floor_y + 0.1} {block_z + 0.5}",
            f"effect give {player} minecraft:resistance {min(seconds + 2, 120)} 4 true",
            f"effect give {player} minecraft:slow_falling {min(seconds + 2, 120)} 0 true",
            f"title {player} actionbar "
            + json.dumps({"text": f"JAILED · {seconds} s", "color": "red", "bold": True},
                         separators=(",", ":")),
        ]
        for command in commands:
            self._rcon_checked(command, log_success=False)
        diagnostics.info("Caged %s in the air above %s/%s/%s for %s s.",
                         player, block_x, ground_y, block_z, seconds)
        return f"Player is locked in a flying glass cage for {seconds} seconds."

    def release_jail(self, player: str) -> str:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        cage = self._cages.pop(player, None)
        if cage:
            region = (f"{cage['x0']} {cage['y0']} {cage['z0']} "
                      f"{cage['x1']} {cage['y1']} {cage['z1']}")
            return_x, return_y, return_z = cage["return"]
            for command in (
                # `replace` touches the cage material only: the map is never edited.
                f"fill {region} minecraft:air replace {self.JAIL_MATERIAL}",
                f"fill {region} minecraft:air replace {self.JAIL_FLOOR}",
                f"tp {player} {return_x:.2f} {return_y:.2f} {return_z:.2f}",
                f"effect clear {player} minecraft:resistance",
                f"effect clear {player} minecraft:slow_falling",
                f"title {player} actionbar "
                + json.dumps({"text": "FREE!", "color": "green", "bold": True},
                             separators=(",", ":")),
            ):
                try:
                    self._rcon_checked(command, log_success=False)
                except Exception as exc:
                    diagnostics.warning("Could not fully release %s from the cage: %s", player, exc)
        else:
            self._rcon(f"effect clear {player} minecraft:slow_falling", log_failure=False)
        self.keep_daylight()
        return "Released from jail."

    def start_reset(self, player: str) -> str:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        self._rcon_checked(f"title {player} title {{\"text\":\"RESET IN 60 SECONDS\",\"color\":\"gold\"}}")
        self._rcon_checked(f"title {player} subtitle {{\"text\":\"Send the anti-reset gift to cancel\",\"color\":\"white\"}}")
        return "Started the 60-second reset countdown."

    def update_reset_countdown(self, player: str, remaining: int) -> None:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        remaining = max(0, min(60, int(remaining)))
        self._rcon_checked(f"title {player} actionbar {{\"text\":\"RESET IN {remaining} s · send anti-reset to cancel\",\"color\":\"gold\"}}")

    def finish_reset(self, player: str) -> str:
        return self._rcon_checked(f"execute as {player} run trigger restart set 1")

    def cancel_reset(self, player: str) -> str:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Invalid player name.")
        self._rcon_checked(f"title {player} clear")
        self._rcon_checked(f"title {player} actionbar {{\"text\":\"RESET CANCELLED\",\"color\":\"green\"}}")
        return "Reset cancelled by the anti-reset gift."


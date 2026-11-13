"""Local 100 Levels Minecraft server bootstrap and loopback RCON control."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .paths import bundle_root, data_dir

PLAYER_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
MAP_FILENAME = "100-levels-5229-v1.7.4.zip"
MAP_VERSION = "26.2"  # Version the bundled world was prepared and tested against.
VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
SETTINGS_PATH = data_dir() / "minecraft_parkour.json"
MAX_SERVER_JAR_BYTES = 300 * 1024 * 1024
_VERSION_CACHE: tuple[float, dict[str, Any]] | None = None
_VERSION_CACHE_TTL = 600
_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def _map_archive() -> Path:
    for path in (bundle_root() / "assets" / MAP_FILENAME, bundle_root() / MAP_FILENAME):
        if path.is_file():
            return path
    raise FileNotFoundError("Wbudowana mapa 100 Levels nie została znaleziona.")


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
    if len(result) < 90 or not {1, 50, 100}.issubset(result):
        raise ValueError("Nie udało się odczytać zakresów poziomów z mapy parkour.")
    return result


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
        raise RuntimeError("Mojang zwrócił nieprawidłowy manifest wersji Minecraft.")
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
        raise RuntimeError("Nie udało się ustalić najnowszej stabilnej wersji Minecraft.")
    # A manageable selector: newest 40 releases, always including the bundled-map version.
    choices = releases[:40]
    if not any(item["id"] == MAP_VERSION for item in choices):
        bundled = next((item for item in releases if item["id"] == MAP_VERSION), None)
        if bundled:
            choices.append(bundled)
    return {"latest": latest, "versions": choices, "map_version": MAP_VERSION}


def _resolve_release(requested_version: str = "latest") -> tuple[str, dict[str, Any]]:
    manifest = _version_manifest()
    selected = str(manifest.get("latest", {}).get("release", "")) if requested_version == "latest" else requested_version
    if not _VERSION_RE.fullmatch(selected):
        raise ValueError("Wersja Minecraft musi być stabilnym wydaniem, np. 1.21.11.")
    version = next((entry for entry in manifest["versions"]
                    if isinstance(entry, dict) and entry.get("id") == selected and entry.get("type") == "release"), None)
    if not version:
        raise ValueError(f"Wersja Minecraft {selected} nie jest dostępna w oficjalnym katalogu wydań.")
    return selected, version


def _download_server_jar(server_dir: Path, requested_version: str = "latest") -> tuple[Path, int, str]:
    """Download a selected official release server jar and verify Mojang's SHA-1."""
    selected, version = _resolve_release(requested_version)
    version_url = str(version.get("url", ""))
    version_host = urllib.parse.urlparse(version_url).hostname or ""
    if not version_url.startswith("https://") or not (version_host == "piston-meta.mojang.com" or version_host.endswith(".piston-meta.mojang.com")):
        raise RuntimeError("Manifest Minecraft zwrócił nieprawidłowy adres wydania.")
    with urllib.request.urlopen(version_url, timeout=15) as response:
        version_info = json.loads(response.read().decode("utf-8"))
    required_java = int(version_info.get("javaVersion", {}).get("majorVersion", 0))
    if required_java < 1:
        raise RuntimeError(f"Nie udało się odczytać wymagań Java dla Minecraft {selected}.")
    java_output = subprocess.run([shutil.which("java") or "java", "-version"], capture_output=True,
                                 text=True, timeout=5, check=False)
    java_text = (java_output.stderr or "") + (java_output.stdout or "")
    java_match = re.search(r'version\s+"(?:1\.)?(\d+)', java_text)
    if not java_match:
        raise RuntimeError("Nie udało się rozpoznać zainstalowanej wersji Java.")
    installed_java = int(java_match.group(1))
    if installed_java < required_java:
        raise RuntimeError(f"Minecraft {selected} wymaga Java {required_java} lub nowszej; wykryto Java {installed_java}.")
    server = version_info.get("downloads", {}).get("server", {})
    url = str(server.get("url", ""))
    host = urllib.parse.urlparse(url).hostname or ""
    if not url.startswith("https://") or not (host == "piston-data.mojang.com" or host.endswith(".piston-data.mojang.com")):
        raise RuntimeError("Minecraft manifest zwrócił nieprawidłowy adres serwera.")
    request = urllib.request.Request(url, headers={"User-Agent": "GiftStream/1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        jar = response.read(MAX_SERVER_JAR_BYTES + 1)
    if len(jar) < 1024 or len(jar) > MAX_SERVER_JAR_BYTES:
        raise RuntimeError("Pobrany plik serwera Minecraft ma nieprawidłowy rozmiar.")
    expected_sha1 = str(server.get("sha1", "")).lower()
    if not expected_sha1 or hashlib.sha1(jar).hexdigest() != expected_sha1:
        raise RuntimeError("Suma SHA-1 serwera Minecraft jest nieprawidłowa lub nie zgadza się.")
    destination = server_dir / "server.jar"
    temporary = destination.with_suffix(".jar.new")
    temporary.write_bytes(jar)
    os.replace(temporary, destination)
    return destination, required_java, selected


def _extract_map(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        infos = [item for item in zf.infolist() if not item.is_dir()]
        total = sum(item.file_size for item in infos)
        if total > 100 * 1024 * 1024 or len(infos) > 5000:
            raise ValueError("Archiwum mapy przekracza dozwolony rozmiar.")
        required = {"100 Levels/level.dat", "100 Levels/datapacks/main/pack.mcmeta"}
        if not required.issubset({item.filename for item in infos}):
            raise ValueError("Archiwum nie zawiera poprawnej mapy Minecraft 100 Levels.")
        for item in infos:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "100 Levels":
                raise ValueError("Archiwum mapy zawiera niebezpieczną ścieżkę.")
            # Reject Unix symlinks so extraction cannot escape the selected server folder.
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archiwum mapy zawiera niedozwolony link symboliczny.")
            relative = Path(*path.parts[1:])
            target = (destination / relative).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError("Ścieżka pliku mapy wychodzi poza katalog świata.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(item) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def _write_server_properties(path: Path, password: str) -> None:
    values = {
        "motd": "GiftStream · Parkour 100 Levels",
        "level-name": "world",
        "server-ip": "127.0.0.1",
        "server-port": "25565",
        "enable-rcon": "true",
        "rcon.port": "25575",
        "rcon.password": password,
        "online-mode": "true",
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


def _recv_packet(sock: socket.socket) -> tuple[int, int, str]:
    header = _recv_exact(sock, 4)
    length = struct.unpack("<i", header)[0]
    if length < 10 or length > 1_000_000:
        raise ConnectionError("RCON zwrócił nieprawidłowy pakiet")
    payload = _recv_exact(sock, length)
    packet_id, packet_type = struct.unpack("<ii", payload[:8])
    text = payload[8:-2].decode("utf-8", errors="replace")
    return packet_id, packet_type, text


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        part = sock.recv(count - len(chunks))
        if not part:
            raise ConnectionError("Serwer Minecraft zamknął połączenie RCON")
        chunks.extend(part)
    return bytes(chunks)


def _send_packet(sock: socket.socket, packet_id: int, packet_type: int, text: str) -> None:
    body = struct.pack("<ii", packet_id, packet_type) + text.encode("utf-8") + b"\0\0"
    sock.sendall(struct.pack("<i", len(body)) + body)


class ParkourServer:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None

    def settings(self) -> dict[str, Any]:
        try:
            value = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def setup(self, server_dir: str, player: str, eula_accepted: bool, version: str = "latest") -> dict[str, Any]:
        if not eula_accepted:
            raise ValueError("Zaznacz akceptację EULA Minecraft przed utworzeniem serwera.")
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Wpisz nick Minecraft: 3–16 liter, cyfr lub podkreśleń.")
        if not shutil.which("java"):
            raise RuntimeError("Nie znaleziono Java. Zainstaluj wersję wymaganą przez serwer Minecraft i spróbuj ponownie.")
        selected_version, _version_info = _resolve_release(version)
        if server_dir.strip():
            root = Path(server_dir).expanduser().resolve()
        else:
            root = (data_dir() / "MinecraftParkour" / "servers" / selected_version).resolve()
        if root == Path(root.anchor) or root == data_dir().resolve():
            raise ValueError("Wybierz osobny folder na lokalny serwer Minecraft.")
        state = self.settings()
        if self._process is not None and self._process.poll() is None:
            if state.get("server_dir") != str(root) or state.get("minecraft_version") != selected_version:
                raise RuntimeError("Zatrzymaj działający serwer przed przełączeniem wersji Minecraft.")
            return self.status()
        root.mkdir(parents=True, exist_ok=True)
        if (state.get("server_dir") == str(root) and state.get("minecraft_version") == selected_version
                and (root / "server.jar").is_file() and (root / "world" / "level.dat").is_file()):
            self.start()
            return self.status()
        if any(root.iterdir()):
            raise FileExistsError("Folder wybranej wersji nie jest pusty. Dane świata są chronione — wybierz inny folder lub wersję.")

        password = secrets.token_urlsafe(24)
        map_stage = root / ".giftstream-world-stage"
        try:
            _map_archive()  # Fail before downloading server files if the bundled world is absent.
            jar, required_java, installed_version = _download_server_jar(root, selected_version)
            map_stage.mkdir()
            _extract_map(_map_archive(), map_stage)
            os.replace(map_stage / "100 Levels", root / "world")
            (root / "eula.txt").write_text("# Accepted in GiftStream setup\neula=true\n", encoding="ascii")
            _write_server_properties(root / "server.properties", password)
            state = {"server_dir": str(root), "player": player,
                     "rcon_host": "127.0.0.1", "rcon_port": 25575,
                     "server_address": "localhost:25565", "minecraft_version": installed_version,
                     "map_version": MAP_VERSION, "java_required": required_java, "server_jar": str(jar)}
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = SETTINGS_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({**state, "rcon_password": password}, indent=2), encoding="utf-8")
            os.replace(tmp, SETTINGS_PATH)
        except Exception:
            shutil.rmtree(map_stage, ignore_errors=True)
            shutil.rmtree(root / "world", ignore_errors=True)
            for generated in (root / "server.jar", root / "server.jar.new", root / "eula.txt", root / "server.properties"):
                try:
                    generated.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        shutil.rmtree(map_stage, ignore_errors=True)
        self.start()
        return self.status()

    def start(self) -> dict[str, Any]:
        state = self.settings()
        root = Path(str(state.get("server_dir", "")))
        jar = root / "server.jar"
        if not jar.is_file() or not (root / "eula.txt").is_file():
            raise RuntimeError("Najpierw utwórz lokalny serwer parkour.")
        if self._process is not None and self._process.poll() is None:
            return self.status()
        java = shutil.which("java")
        if not java:
            raise RuntimeError("Nie znaleziono Java wymaganej przez serwer Minecraft.")
        log = (root / "giftstream-server.log").open("ab")
        kwargs: dict[str, Any] = {"cwd": str(root), "stdin": subprocess.DEVNULL,
                                  "stdout": log, "stderr": subprocess.STDOUT, "close_fds": True}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        else:
            kwargs["start_new_session"] = True
        try:
            self._process = subprocess.Popen([java, "-Xms1G", "-Xmx2G", "-jar", str(jar), "nogui"], **kwargs)
        finally:
            log.close()
        return self.status()

    def _rcon(self, command: str) -> str:
        state = self.settings()
        host = str(state.get("rcon_host", "127.0.0.1"))
        port = int(state.get("rcon_port", 25575))
        password = str(state.get("rcon_password", ""))
        if host != "127.0.0.1" or not password or not (1 <= port <= 65535):
            raise RuntimeError("Brak bezpiecznej konfiguracji RCON na localhost.")
        with socket.create_connection((host, port), timeout=3) as sock:
            sock.settimeout(3)
            _send_packet(sock, 1, 3, password)
            packet_id, _packet_type, _ = _recv_packet(sock)
            if packet_id == -1:
                raise PermissionError("Serwer odrzucił hasło RCON.")
            if packet_id != 1:
                _recv_packet(sock)
            _send_packet(sock, 2, 2, command)
            response_id, _response_type, text = _recv_packet(sock)
            if response_id != 2:
                raise ConnectionError("Niepoprawna odpowiedź RCON.")
            return text.strip()

    def status(self) -> dict[str, Any]:
        state = self.settings()
        if not state:
            return {"configured": False, "running": False, "ready": False,
                    "server_address": "localhost:25565", "players_online": 0, "players": [],
                    "message": "Utwórz lokalny serwer i zaimportuj mapę 100 Levels."}
        response = {"configured": True, "running": False, "ready": False,
                    "server_address": state.get("server_address", "localhost:25565"),
                    "server_dir": state.get("server_dir", ""), "player": state.get("player", ""),
                    "minecraft_version": state.get("minecraft_version", MAP_VERSION),
                    "map_version": state.get("map_version", MAP_VERSION),
                    "java_required": state.get("java_required"),
                    "chat_relay_enabled": bool(state.get("chat_relay_enabled", False)),
                    "players_online": 0, "players": [],
                    "message": "Serwer startuje — pierwsze uruchomienie może potrwać chwilę."}
        if self._process is not None and self._process.poll() is not None:
            response["message"] = f"Serwer zakończył pracę (kod {self._process.returncode}). Zajrzyj do giftstream-server.log."
            return response
        try:
            listing = self._rcon("list")
            player_match = re.search(r"There are (\d+) of a max of \d+ players online:(.*)", listing, re.IGNORECASE)
            players = [name.strip() for name in (player_match.group(2) if player_match else "").split(",") if name.strip()]
            response.update({"running": True, "ready": True,
                             "players_online": int(player_match.group(1)) if player_match else len(players),
                             "players": players,
                             "message": "Minecraft gotowy · " + (listing or "RCON połączony")})
        except Exception:
            if self._process is not None and self._process.poll() is None:
                response["running"] = True
        return response

    def stop(self) -> dict[str, Any]:
        if not self.settings():
            return self.status()
        try:
            self._rcon("stop")
        except Exception as exc:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError(f"Nie udało się zatrzymać serwera przez RCON: {exc}") from exc
        return {**self.status(), "message": "Wysłano polecenie bezpiecznego zamknięcia serwera."}

    def command(self, command: str) -> str:
        return self._rcon(command)

    def relay_chat(self, message: str) -> str:
        """Relay plain TikTok chat text to Minecraft without interpreting it as a command."""
        if not isinstance(message, str) or not message:
            raise ValueError("Wiadomość czatu jest pusta.")
        if len(message) > 2000:
            raise ValueError("Wiadomość czatu przekracza bezpieczny limit 2000 znaków.")
        # Tellraw's JSON text component safely encodes quotes, slashes and command
        # characters as data. Preserve the message text (including punctuation and
        # Unicode) exactly; never prepend a username or pass it through RCON raw.
        component = json.dumps({"text": message}, ensure_ascii=False, separators=(",", ":"))
        return self._rcon(f"tellraw @a {component}")

    def get_player_level(self, player: str) -> int:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Niepoprawny nick gracza.")
        output = self._rcon(f"scoreboard players get {player} level")
        match = re.search(r"has\s+(-?\d+)\s+\[level\]", output) or re.search(r"(-?\d+)", output)
        if not match:
            raise RuntimeError(f"Nie udało się odczytać poziomu mapy: {output or 'gracz może być poza mapą'}")
        return int(match.group(1))

    def execute_action(self, action: str, player: str | None = None) -> str:
        state = self.settings()
        player = player or str(state.get("player", ""))
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Najpierw ustaw nick gracza Minecraft.")
        if action == "parkour_push":
            commands = [f"effect give {player} minecraft:slow_falling 3 0 true",
                        f"execute as {player} at {player} run tp @s ^ ^0.6 ^-3"]
            for command in commands:
                self._rcon(command)
            return "Delikatnie odrzucono gracza o 3 bloki do tyłu."
        if action in {"parkour_level_forward", "parkour_level_back"}:
            areas = map_level_areas()
            current = self.get_player_level(player)
            target = max(1, min(100, current + (1 if action.endswith("forward") else -1)))
            if target not in areas:
                raise RuntimeError(f"Mapa nie ma zakresu dla poziomu {target}.")
            x, z, dx, dz, dy = areas[target]
            # Drop into the region from above its declared vertical bound while
            # slow-falling, allowing the map's own course geometry to catch the player.
            y = dy + 3
            commands = [f"effect give {player} minecraft:slow_falling 30 0 true",
                        f"tp {player} {x + dx / 2:.1f} {y} {z + dz / 2:.1f}"]
            for command in commands:
                self._rcon(command)
            return f"Przeniesiono gracza na obszar poziomu {target}."
        if action == "parkour_jail":
            commands = [f"tp {player} 1001 101 1001",
                        "fill 1000 100 1000 1002 100 1002 minecraft:stone",
                        "fill 1000 101 1000 1002 104 1002 minecraft:glass hollow",
                        f"effect give {player} minecraft:slowness 20 255 true",
                        f"title {player} actionbar {{\"text\":\"WIĘZIENIE · 20 s\",\"color\":\"red\"}}"]
            for command in commands:
                self._rcon(command)
            return "Gracz trafił na 20 sekund do lobby-więzienia."
        if action in {"parkour_reset", "parkour_antireset"}:
            raise RuntimeError("Reset z odliczaniem jest koordynowany przez GiftStream.")
        raise ValueError("Nieobsługiwana akcja parkour.")

    def start_reset(self, player: str) -> str:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Niepoprawny nick gracza.")
        self._rcon(f"title {player} title {{\"text\":\"RESET ZA 60 SEKUND\",\"color\":\"gold\"}}")
        self._rcon(f"title {player} subtitle {{\"text\":\"Wyślij prezent przypisany do Anty-resetu, aby anulować\",\"color\":\"white\"}}")
        return "Rozpoczęto 60-sekundowe odliczanie resetu."

    def update_reset_countdown(self, player: str, remaining: int) -> None:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Niepoprawny nick gracza.")
        remaining = max(0, min(60, int(remaining)))
        self._rcon(f"title {player} actionbar {{\"text\":\"RESET ZA {remaining} s · podaruj Anty-reset, aby anulować\",\"color\":\"gold\"}}")

    def finish_reset(self, player: str) -> str:
        return self._rcon(f"execute as {player} run trigger restart set 1")

    def cancel_reset(self, player: str) -> str:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Niepoprawny nick gracza.")
        self._rcon(f"title {player} clear")
        self._rcon(f"title {player} actionbar {{\"text\":\"RESET ANULOWANY\",\"color\":\"green\"}}")
        return "Reset anulowany przez anty-reset."

    def release_jail(self, player: str) -> str:
        if not PLAYER_RE.fullmatch(player or ""):
            raise ValueError("Niepoprawny nick gracza.")
        self._rcon(f"effect clear {player} minecraft:slowness")
        return self._rcon(f"tp {player} -4 89 1")

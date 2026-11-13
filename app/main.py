"""GiftStream — API i serwer webowy."""
from __future__ import annotations

import asyncio
import json
import ipaddress
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import presets as preset_store
from . import earnings as earnings_tracker
from .bridge import Hub
from .engine import Engine
from .gifts import coin_price_for_gift, list_gifts, record_event, refresh_tiktok_catalog
from .games import GAMES, get_game
from .minecraft import ServerTapClient, validate_base_url
from .parkour_server import ParkourServer
from .models import AppConfig, GameAction, Preset, TikTokEvent
from .paths import bundle_root, data_dir, installed_release_tag
from .tiktok_connector import TikTokConnector
from .version import VERSION
from . import update_state

load_dotenv()
ROOT = bundle_root()
DATA = data_dir()
WEB = ROOT / "web"
CONFIG_PATH = DATA / "config.json"
GITHUB_RELEASES_URL = "https://github.com/rejson59/GiftStream/releases"
_DOWNLOAD_INFO_CACHE: dict[str, Any] = {"expires": 0.0, "data": None}

app = FastAPI(title="GiftStream", version=VERSION,
              description="Prezenty z TikTok LIVE sterują grą")
connector: TikTokConnector
config = AppConfig()


class ConnectRequest(BaseModel):
    mode: str = "simulator"
    username: str = ""


class SimulateRequest(BaseModel):
    kind: str = "gift"
    gift_name: str | None = None
    user: str = "viewer"
    diamonds: int = 1
    comment: str | None = None


class PresetCopyRequest(BaseModel):
    new_id: str
    new_name: str


class EarningsSettingsRequest(BaseModel):
    usd_per_diamond: float = Field(gt=0, le=1)
    usd_to_pln: float | None = Field(default=None, gt=0, le=100)


class MinecraftSettingsRequest(BaseModel):
    base_url: str = ""
    api_key: str = ""
    player: str = ""
    enabled: bool = False


class ParkourSetupRequest(BaseModel):
    server_dir: str = ""
    player: str
    eula_accepted: bool = False


class ParkourActionRequest(BaseModel):
    action: str
    player: str | None = None


async def publish_game_action(action: GameAction) -> None:
    await hub.publish_action(action)
    if action.action.startswith("parkour_"):
        try:
            await _run_parkour_action(action)
        except Exception as exc:
            await hub.publish_status({"parkour_result": {"ok": False, "message": str(exc)}})
    if config.minecraft_enabled and not action.action.startswith("parkour_"):
        try:
            result = await minecraft_bridge.send(action.action, action.params)
            await hub.publish_status({"minecraft_result": result})
        except Exception as exc:
            await hub.publish_status({"minecraft_result": {"ok": False, "message": str(exc)}})


hub = Hub()
minecraft_bridge = ServerTapClient()
parkour_server = ParkourServer()
parkour_reset_task: asyncio.Task | None = None
parkour_reset_player = ""
parkour_jail_tasks: dict[str, asyncio.Task] = {}


async def _run_parkour_action(action: GameAction) -> None:
    global parkour_reset_task, parkour_reset_player
    settings = parkour_server.settings()
    if not settings.get("enabled"):
        return
    player = str(action.params.get("player") or settings.get("player") or "")
    if action.action == "parkour_reset":
        if parkour_reset_task and not parkour_reset_task.done():
            parkour_reset_task.cancel()
        await asyncio.to_thread(parkour_server.start_reset, player)
        parkour_reset_player = player
        async def countdown() -> None:
            global parkour_reset_task, parkour_reset_player
            try:
                for remaining in range(60, 0, -1):
                    await hub.publish_status({"parkour_reset_countdown": remaining, "parkour_player": player})
                    try:
                        await asyncio.to_thread(parkour_server.update_reset_countdown, player, remaining)
                    except Exception:
                        # Preserve the countdown if the player is temporarily offline.
                        pass
                    await asyncio.sleep(1)
                result = await asyncio.to_thread(parkour_server.finish_reset, player)
                await hub.publish_status({"parkour_reset_countdown": 0, "parkour_result": result})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await hub.publish_status({"parkour_reset_countdown": None, "parkour_result": str(exc)})
            finally:
                parkour_reset_task = None
        parkour_reset_task = asyncio.create_task(countdown())
        return
    if action.action == "parkour_antireset":
        if parkour_reset_task and not parkour_reset_task.done():
            parkour_reset_task.cancel()
            parkour_reset_task = None
            result = await asyncio.to_thread(parkour_server.cancel_reset, parkour_reset_player or player)
            await hub.publish_status({"parkour_reset_countdown": None, "parkour_result": result})
        return
    if action.action == "parkour_jail":
        result = await asyncio.to_thread(parkour_server.execute_action, action.action, player)
        previous = parkour_jail_tasks.pop(player, None)
        if previous and not previous.done():
            previous.cancel()
        async def release_jail() -> None:
            try:
                await asyncio.sleep(20)
                released = await asyncio.to_thread(parkour_server.release_jail, player)
                await hub.publish_status({"parkour_result": released})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await hub.publish_status({"parkour_result": str(exc)})
            finally:
                parkour_jail_tasks.pop(player, None)
        parkour_jail_tasks[player] = asyncio.create_task(release_jail())
        await hub.publish_status({"parkour_result": result, "parkour_jail_seconds": 20})
        return
    if action.action.startswith("parkour_"):
        result = await asyncio.to_thread(parkour_server.execute_action, action.action, player)
        await hub.publish_status({"parkour_result": result})


engine = Engine(on_action=publish_game_action)


async def process_event(ev: TikTokEvent) -> None:
    if ev.viewer_count:
        hub.viewer_count = ev.viewer_count
    if ev.type == "gift":
        if ev.diamonds <= 0:
            resolved, from_catalog = earnings_tracker.resolve_diamonds(ev.gift_id, ev.gift_name, ev.diamonds)
            if resolved > 0:
                ev.diamonds = resolved
                ev.diamonds_estimated = from_catalog
        if ev.gift_coins <= 0 or ev.gift_coins_estimated:
            coins, estimated = coin_price_for_gift(ev.gift_id, ev.gift_name)
            if coins > 0:
                ev.gift_coins = coins
                ev.gift_coins_estimated = estimated
    record_event(ev)
    await hub.publish_event(ev)
    await engine.handle(ev)


connector = TikTokConnector(process_event)
_catalog_refresh_task: asyncio.Task | None = None
_catalog_refresh_started = False
_gift_refresh_loop_task: asyncio.Task | None = None
_currency_refresh_task: asyncio.Task | None = None


async def _currency_refresh_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(earnings_tracker.refresh_usd_to_pln)
        except Exception:
            # Keep the last successful NBP rate and never delay application startup.
            pass
        await asyncio.sleep(12 * 60 * 60)


async def _gift_catalog_refresh_loop() -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            await asyncio.to_thread(_refresh_catalog_safely)
        except Exception:
            # Retain the last cached gift catalog if TikTok or the network is unavailable.
            pass


def read_config() -> AppConfig:
    if CONFIG_PATH.exists():
        try:
            return AppConfig(**json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return AppConfig()


def save_config() -> None:
    CONFIG_PATH.write_text(json.dumps(config.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def public_config() -> dict:
    data = config.model_dump()
    data.pop("minecraft_api_key", None)
    data.pop("bridge_webhook_secret", None)
    data["minecraft_has_key"] = bool(config.minecraft_api_key)
    data["bridge_has_secret"] = bool(config.bridge_webhook_secret or os.getenv("GIFTSTREAM_BRIDGE_WEBHOOK_SECRET", ""))
    return data


def sync_minecraft_client() -> None:
    minecraft_bridge.base_url = config.minecraft_servertap_url
    minecraft_bridge.api_key = config.minecraft_api_key
    minecraft_bridge.player = config.minecraft_player


def _refresh_catalog_safely() -> int:
    try:
        return refresh_tiktok_catalog()
    except Exception:
        # Keep the last valid catalog and let the local gallery work offline.
        return 0


_LEGACY_PARKOUR_DESCRIPTION = "Gotowe akcje dla dołączonej mapy 100 Levels: przesuwanie poziomu, więzienie, reset z 60-sekundowym odliczaniem i anty-reset. Wymaga lokalnego serwera GiftStream."
_LEGACY_PARKOUR_RULES = {
    "mp-rose": ("Róża → następny poziom", "gift", "Rose", "parkour_level_forward"),
    "mp-tiktok": ("TikTok → poprzedni poziom", "gift", "TikTok", "parkour_level_back"),
    "mp-follow": ("Follow → więzienie", "follow", None, "parkour_jail"),
    "mp-donut": ("Donut → awans o poziom", "gift", "Donut", "parkour_level_forward"),
    "mp-dragon": ("Smok → reset za 60 s", "gift", "Dragon", "parkour_reset"),
    "mp-antireset": ("Anty-reset → anuluj reset", "gift", "Panda", "parkour_antireset"),
}


def _migrate_builtin_parkour_preset() -> bool:
    """Update only the untouched built-in v0.6.4 parkour preset, never user-edited rules."""
    old = preset_store.get_preset("minecraft-parkour")
    if old is None or old.description != _LEGACY_PARKOUR_DESCRIPTION or len(old.rules) != len(_LEGACY_PARKOUR_RULES):
        return False
    for rule in old.rules:
        expected = _LEGACY_PARKOUR_RULES.get(rule.id)
        actual = (rule.name, rule.trigger.type, rule.trigger.gift_name, rule.action.type)
        if expected is None or actual != expected or rule.trigger.min_coins is not None or rule.trigger.max_coins is not None:
            return False
    game = get_game("minecraft-parkour")
    if game is None:
        return False
    preset_store.save_preset(Preset(id=game["preset_id"], name=game["title"],
                                    description=game["description"], rules=game["rules"]))
    return True


@app.on_event("startup")
async def startup() -> None:
    global config, _catalog_refresh_task, _catalog_refresh_started, _currency_refresh_task, _gift_refresh_loop_task
    preset_store.ensure_default()
    config = read_config()
    sync_minecraft_client()
    _migrate_builtin_parkour_preset()
    engine.load_preset(config.active_preset_id)
    # TikTok's public catalog is loaded once in the background; the panel remains usable offline.
    if not _catalog_refresh_started:
        _catalog_refresh_started = True
        _catalog_refresh_task = asyncio.create_task(asyncio.to_thread(_refresh_catalog_safely))
    if _gift_refresh_loop_task is None or _gift_refresh_loop_task.done():
        _gift_refresh_loop_task = asyncio.create_task(_gift_catalog_refresh_loop())
    if _currency_refresh_task is None or _currency_refresh_task.done():
        _currency_refresh_task = asyncio.create_task(_currency_refresh_loop())
    if config.mode == "simulator":
        await connector.start("simulator")


@app.on_event("shutdown")
async def shutdown() -> None:
    await connector.stop()
    global parkour_reset_task
    if parkour_reset_task and not parkour_reset_task.done():
        parkour_reset_task.cancel()
    for task in parkour_jail_tasks.values():
        if not task.done():
            task.cancel()
    if parkour_server.settings():
        try:
            await asyncio.to_thread(parkour_server.stop)
        except Exception:
            pass
    if _currency_refresh_task and not _currency_refresh_task.done():
        _currency_refresh_task.cancel()
    if _gift_refresh_loop_task and not _gift_refresh_loop_task.done():
        _gift_refresh_loop_task.cancel()


# -- Web app ---------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard() -> Any:
    return FileResponse(WEB / "index.html")

@app.get("/game", response_class=HTMLResponse)
async def game() -> Any:
    return FileResponse(WEB / "game.html")

@app.get("/overlay", response_class=HTMLResponse)
async def overlay() -> Any:
    return FileResponse(WEB / "overlay.html")

@app.get("/docs/minecraft")
async def minecraft_docs() -> Any:
    return FileResponse(ROOT / "docs" / "MINECRAFT.md", media_type="text/markdown")

@app.get("/docs/games")
async def games_docs() -> Any:
    return FileResponse(ROOT / "docs" / "GAME_IDEAS.md", media_type="text/markdown")

app.mount("/static", StaticFiles(directory=WEB), name="static")


# -- API -------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "app": "GiftStream", "version": installed_release_tag()}

@app.get("/api/updates/status")
async def updates_status() -> dict:
    return update_state.status()

@app.post("/api/updates/check")
async def check_for_updates() -> dict:
    queued = update_state.request_check()
    status = update_state.status()
    return {"ok": True, "checking": True, "check_id": status["check_id"],
            "message": "Sprawdzanie aktualizacji rozpoczęte." if queued else "Sprawdzanie aktualizacji jest już w toku."}

@app.post("/api/updates/apply")
async def apply_downloaded_update() -> dict:
    if not update_state.request_apply():
        raise HTTPException(409, "Nie ma pobranej aktualizacji do zastosowania.")
    return {"ok": True, "message": "GiftStream uruchomi się ponownie z pobraną aktualizacją."}

@app.get("/api/download-info")
async def download_info() -> dict:
    """Return the single GiftStream executable download URL."""
    now = time.time()
    if _DOWNLOAD_INFO_CACHE["data"] is not None and now < _DOWNLOAD_INFO_CACHE["expires"]:
        return _DOWNLOAD_INFO_CACHE["data"]
    fallback = {"available": False, "url": GITHUB_RELEASES_URL,
                "releases_url": GITHUB_RELEASES_URL,
                "message": "Wydanie GiftStream dla Windows nie jest obecnie dostępne."}

    def check_github_release() -> dict:
        request = urllib.request.Request(
            "https://api.github.com/repos/rejson59/GiftStream/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "GiftStream/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                release = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return fallback
            raise
        assets = {asset.get("name"): asset for asset in release.get("assets", [])}
        asset = assets.get("GiftStream.exe")
        asset_url = str((asset or {}).get("browser_download_url", ""))
        if asset and asset_url.startswith("https://github.com/"):
            version = release.get("tag_name", "")
            return {"available": True, "kind": "application", "url": asset_url,
                    "releases_url": GITHUB_RELEASES_URL, "version": version,
                    "message": f"Pobierz GiftStream {version} dla Windows."}
        return fallback

    try:
        result = await asyncio.to_thread(check_github_release)
    except Exception:
        result = {**fallback, "message": "Nie udało się sprawdzić wydań. Otwórz stronę wydań GiftStream."}
    _DOWNLOAD_INFO_CACHE.update({"data": result, "expires": now + (300 if result["available"] else 60)})
    return result

@app.get("/api/status")
async def status() -> dict:
    return {
        "connector": connector.status(),
        "preset": engine.active_preset.model_dump() if engine.active_preset else None,
        "stats": engine.stats,
        "viewer_count": hub.viewer_count,
        "total_likes": hub.total_likes,
        "mode": config.mode,
        "tiktok_username": config.tiktok_username,
    }

@app.get("/api/snapshot")
async def snapshot() -> dict:
    return {**hub.snapshot(), "connector": connector.status(),
            "preset": engine.active_preset.model_dump() if engine.active_preset else None,
            "stats": engine.stats, "config": public_config()}

@app.get("/api/config")
async def get_config() -> dict:
    return public_config()

@app.put("/api/config")
async def update_config(data: dict[str, Any]) -> dict:
    global config
    if "sound_url" in data:
        url = str(data["sound_url"] or "").strip()
        if url:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower().rstrip(".")
            try:
                ip = ipaddress.ip_address(hostname)
                unsafe_ip = ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            except ValueError:
                unsafe_ip = False
            if (len(url) > 2048 or parsed.scheme != "https" or not hostname or
                    parsed.username or parsed.password or unsafe_ip or
                    hostname in {"localhost", "metadata.google.internal"} or
                    hostname.endswith((".localhost", ".local", ".internal"))):
                raise HTTPException(422, "Dźwięk musi wskazywać publiczny adres HTTPS bez danych logowania ani adresu lokalnego.")
        data["sound_url"] = url
    merged = {**config.model_dump(), **data}
    try:
        config = AppConfig(**merged)
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors()) from exc
    sync_minecraft_client()
    save_config()
    return public_config()

@app.get("/api/gifts")
async def gifts(q: str = "", sort: Literal["popular", "price_asc", "price_desc"] = "price_asc") -> list[dict]:
    return list_gifts(q, sort)

@app.post("/api/gifts/refresh")
async def refresh_gifts() -> dict:
    count = await asyncio.to_thread(_refresh_catalog_safely)
    return {"ok": count > 0, "count": count, "gifts": list_gifts()}

@app.get("/api/earnings/settings")
async def get_earnings_settings() -> dict[str, Any]:
    return earnings_tracker.get_settings()

@app.put("/api/earnings/settings")
async def update_earnings_settings(req: EarningsSettingsRequest) -> dict[str, Any]:
    return earnings_tracker.save_settings(req.usd_per_diamond, req.usd_to_pln)

@app.post("/api/earnings/refresh-rate")
async def refresh_earnings_rate() -> dict[str, Any]:
    try:
        return {"ok": True, "settings": await asyncio.to_thread(earnings_tracker.refresh_usd_to_pln)}
    except Exception as exc:
        return {"ok": False, "settings": earnings_tracker.get_settings(),
                "message": f"Nie udało się pobrać najnowszego kursu NBP: {exc}"}

@app.get("/api/games")
async def games() -> list[dict]:
    return [{key: value for key, value in game.items() if key != "rules"} for game in GAMES]

@app.post("/api/games/{game_id}/preset")
async def create_game_preset(game_id: str) -> dict:
    global config
    game = get_game(game_id)
    if game is None:
        raise HTTPException(404, "Nie znaleziono gry")
    if not game.get("rules"):
        raise HTTPException(400, "Ten pomysł nie ma jeszcze gotowego presetu — użyj go jako inspiracji.")
    preset_id = game["preset_id"]
    preset = Preset(id=preset_id, name=game["title"], description=game["description"], rules=game["rules"])
    if preset_store.get_preset(preset_id) is None:
        preset_store.save_preset(preset)
    engine.load_preset(preset_id)
    config.active_preset_id = preset_id
    save_config()
    return {"ok": True, "preset": engine.active_preset.model_dump()}

@app.get("/api/integrations/minecraft")
async def minecraft_status() -> dict:
    return {"enabled": config.minecraft_enabled, "configured": minecraft_bridge.configured,
            "base_url": config.minecraft_servertap_url, "player": config.minecraft_player,
            "has_key": bool(config.minecraft_api_key), "integration": "ServerTap"}

@app.put("/api/integrations/minecraft")
async def update_minecraft_settings(req: MinecraftSettingsRequest) -> dict:
    global config
    try:
        base_url = validate_base_url(req.base_url) if req.base_url.strip() else ""
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    player = req.player.strip()
    if req.enabled and (not base_url or not (req.api_key.strip() or config.minecraft_api_key) or not player):
        raise HTTPException(400, "Aby włączyć integrację, podaj adres ServerTap, klucz API i nick gracza.")
    merged = config.model_dump()
    merged.update({"minecraft_servertap_url": base_url,
                   "minecraft_player": player,
                   "minecraft_enabled": req.enabled})
    if req.api_key.strip():
        merged["minecraft_api_key"] = req.api_key.strip()
    config = AppConfig(**merged)
    sync_minecraft_client()
    save_config()
    return await minecraft_status()

@app.post("/api/integrations/minecraft/test")
async def test_minecraft_connection() -> dict:
    try:
        return await minecraft_bridge.check()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.RequestError as exc:
        return {"ok": False, "message": f"Nie udało się połączyć z ServerTap: {exc}"}

@app.get("/api/minecraft/parkour")
async def parkour_status() -> dict[str, Any]:
    status = await asyncio.to_thread(parkour_server.status)
    status["enabled"] = bool(parkour_server.settings().get("enabled"))
    return status

@app.post("/api/minecraft/parkour/setup")
async def parkour_setup(req: ParkourSetupRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(parkour_server.setup, req.server_dir, req.player, req.eula_accepted)
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc

@app.post("/api/minecraft/parkour/start")
async def parkour_start() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(parkour_server.start)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc

@app.post("/api/minecraft/parkour/stop")
async def parkour_stop() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(parkour_server.stop)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc

@app.put("/api/minecraft/parkour/enabled")
async def parkour_enabled(request: dict[str, bool]) -> dict[str, Any]:
    state = parkour_server.settings()
    if not state.get("server_dir"):
        raise HTTPException(400, "Najpierw skonfiguruj lokalny serwer parkour.")
    state["enabled"] = bool(request.get("enabled", False))
    path = DATA / "minecraft_parkour.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)
    return {**await asyncio.to_thread(parkour_server.status), "enabled": state["enabled"]}

@app.post("/api/minecraft/parkour/action")
async def parkour_test_action(req: ParkourActionRequest) -> dict[str, Any]:
    allowed = {"parkour_push", "parkour_level_forward", "parkour_level_back", "parkour_jail", "parkour_reset", "parkour_antireset"}
    if req.action not in allowed:
        raise HTTPException(400, "Nieznana akcja parkour.")
    await _run_parkour_action(GameAction(action=req.action, params={"player": req.player} if req.player else {}))
    return {"ok": True, "message": f"Akcja parkour wysłana: {req.action}"}

@app.get("/api/actions")
async def actions() -> list[dict]:
    from .models import KNOWN_ACTIONS
    labels = {"spawn_zombie":"Przywołaj zombie", "spawn_enemy":"Przywołaj przeciwnika",
              "spawn_boss":"Przywołaj bossa", "boss_raid":"Fala bossów", "heal":"Ulecz gracza",
              "drop_diamond":"Upuść diament", "drop_item":"Upuść przedmiot", "give_item":"Daj przedmiot",
              "move_left":"Ruch w lewo", "move_right":"Ruch w prawo", "jump":"Skok", "shield":"Tarcza",
              "speed_boost":"Przyspieszenie", "teleport":"Teleport", "spawn_wall":"Stwórz przeszkodę",
              "change_weather":"Zmień pogodę", "change_time":"Zmień porę dnia", "screen_shake":"Trzęsienie ekranu",
              "confetti":"Konfetti", "vote":"Głosowanie", "custom":"Akcja własna"}
    labels.update({"parkour_push":"Parkour: delikatny push", "parkour_level_forward":"Parkour: kolejny poziom", "parkour_level_back":"Parkour: poprzedni poziom",
                   "parkour_jail":"Parkour: więzienie", "parkour_reset":"Parkour: reset za 60 s",
                   "parkour_antireset":"Parkour: anty-reset"})
    return [{"id": x, "label": labels.get(x, x.replace("_", " ").title())} for x in KNOWN_ACTIONS]

@app.get("/api/presets")
async def list_presets() -> list[dict]:
    return [p.model_dump() for p in preset_store.list_presets()]

@app.post("/api/presets")
async def create_preset(preset: Preset) -> dict:
    if preset_store.get_preset(preset.id):
        raise HTTPException(409, "Preset ID już istnieje")
    return preset_store.save_preset(preset).model_dump()

@app.get("/api/presets/{preset_id}")
async def get_preset(preset_id: str) -> dict:
    p = preset_store.get_preset(preset_id)
    if p is None:
        raise HTTPException(404, "Nie znaleziono presetu")
    return p.model_dump()

@app.put("/api/presets/{preset_id}")
async def update_preset(preset_id: str, preset: Preset) -> dict:
    if preset.id != preset_id:
        raise HTTPException(400, "ID w URL i body muszą być takie same")
    saved = preset_store.save_preset(preset)
    if engine.active_preset and engine.active_preset.id == preset_id:
        engine.load_preset(preset_id)
    return saved.model_dump()

@app.delete("/api/presets/{preset_id}")
async def remove_preset(preset_id: str) -> dict:
    if preset_id == "default":
        raise HTTPException(400, "Nie można usunąć domyślnego presetu")
    if not preset_store.delete_preset(preset_id):
        raise HTTPException(404, "Nie znaleziono presetu")
    if engine.active_preset and engine.active_preset.id == preset_id:
        engine.load_preset("default")
        config.active_preset_id = "default"
        save_config()
    return {"ok": True}

@app.post("/api/presets/{preset_id}/activate")
async def activate_preset(preset_id: str) -> dict:
    preset = engine.load_preset(preset_id)
    if preset is None:
        raise HTTPException(404, "Nie znaleziono presetu")
    config.active_preset_id = preset_id
    save_config()
    await hub.publish_status({"active_preset_id": preset_id, "active_preset_name": preset.name})
    return {"ok": True, "preset": preset.model_dump()}

@app.post("/api/presets/{preset_id}/duplicate")
async def duplicate_preset(preset_id: str, req: PresetCopyRequest) -> dict:
    if preset_store.get_preset(req.new_id):
        raise HTTPException(409, "Preset ID już istnieje")
    p = preset_store.duplicate_preset(preset_id, req.new_id, req.new_name)
    if p is None:
        raise HTTPException(404, "Nie znaleziono presetu")
    return p.model_dump()

@app.post("/api/rules/{rule_id}/test")
async def test_rule(rule_id: str) -> dict:
    action = await engine.test_rule(rule_id)
    if action is None:
        raise HTTPException(404, "Nie znaleziono reguły")
    return action.model_dump()

@app.post("/api/connect")
async def connect(req: ConnectRequest) -> dict:
    global config
    result = await connector.start(req.mode, req.username)
    if result.get("ok"):
        config.mode = req.mode  # type: ignore[assignment]
        config.tiktok_username = req.username.lstrip("@")
        save_config()
    await hub.publish_status(connector.status())
    return result

@app.post("/api/disconnect")
async def disconnect() -> dict:
    await connector.stop()
    await hub.publish_status(connector.status())
    return {"ok": True, "message": "Rozłączono"}

@app.post("/api/simulate")
async def simulate(req: SimulateRequest) -> dict:
    if req.gift_name:
        gift = next((g for g in list_gifts() if g["name"].lower() == req.gift_name.lower()), None)
        ev = TikTokEvent(type="gift", user=req.user, nickname=req.user,
                         gift_name=req.gift_name, gift_id=gift["id"] if gift else None,
                         gift_image_url=gift.get("image_url") if gift else None,
                         diamonds=req.diamonds or (gift["diamonds"] if gift else 1), source="test")
    elif req.kind == "comment":
        ev = TikTokEvent(type="comment", user=req.user, nickname=req.user,
                         comment=req.comment or "boss", source="test")
    elif req.kind == "like":
        ev = TikTokEvent(type="like", user=req.user, nickname=req.user,
                         like_count=max(req.diamonds, 1), source="test")
    else:
        ev = TikTokEvent(type=req.kind if req.kind in ("gift", "follow", "share", "join", "subscribe") else "gift",
                         user=req.user, nickname=req.user,
                         gift_name="Rose" if req.kind == "gift" else None,
                         diamonds=req.diamonds, source="test")
    await process_event(ev)
    return {"ok": True, "event": ev.model_dump()}

@app.post("/api/bridge/event")
async def bridge_event(ev: TikTokEvent, x_giftstream_secret: str | None = Header(default=None)) -> dict:
    secret = config.bridge_webhook_secret or os.getenv("GIFTSTREAM_BRIDGE_WEBHOOK_SECRET", "")
    if secret and not secrets.compare_digest(x_giftstream_secret or "", secret):
        raise HTTPException(401, "Invalid or missing X-GiftStream-Secret")
    await process_event(ev)
    return {"ok": True}

@app.post("/api/bridge/action")
async def bridge_action(data: dict) -> dict:
    """Game -> GiftStream (e.g. report score/state); forwarded to dashboard/overlay."""
    data.setdefault("ts", __import__("time").time())
    await hub.publish_status({"game": data})
    return {"ok": True}


# -- WebSockets ------------------------------------------------------------
async def _ws_client(websocket: WebSocket, group: set[WebSocket]) -> None:
    await websocket.accept()
    group.add(websocket)
    await websocket.send_json({"kind": "snapshot", "data": hub.snapshot()})
    try:
        while True:
            # keepalive or client commands; all commands are intentionally inert
            await websocket.receive_text()
    except WebSocketDisconnect:
        group.discard(websocket)
    except Exception:
        group.discard(websocket)

@app.websocket("/ws/feed")
async def ws_feed(websocket: WebSocket) -> None:
    await _ws_client(websocket, hub.feed_clients)

@app.websocket("/ws/game")
async def ws_game(websocket: WebSocket) -> None:
    await _ws_client(websocket, hub.game_clients)

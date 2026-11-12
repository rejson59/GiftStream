"""GiftStream — API i serwer webowy."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import presets as preset_store
from .bridge import Hub
from .engine import Engine
from .gifts import list_gifts, record_event, refresh_tiktok_catalog
from .games import GAMES, get_game
from .minecraft import ServerTapClient, validate_base_url
from .models import AppConfig, GameAction, Preset, TikTokEvent
from .paths import bundle_root, data_dir, installed_release_tag
from .tiktok_connector import TikTokConnector
from . import update_state

load_dotenv()
ROOT = bundle_root()
DATA = data_dir()
WEB = ROOT / "web"
CONFIG_PATH = DATA / "config.json"
GITHUB_RELEASES_URL = "https://github.com/rejson59/GiftStream/releases"
_DOWNLOAD_INFO_CACHE: dict[str, Any] = {"expires": 0.0, "data": None}

app = FastAPI(title="GiftStream", version="0.4.1",
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


class MinecraftSettingsRequest(BaseModel):
    base_url: str = ""
    api_key: str = ""
    player: str = ""
    enabled: bool = False


async def publish_game_action(action: GameAction) -> None:
    await hub.publish_action(action)
    if config.minecraft_enabled:
        try:
            result = await minecraft_bridge.send(action.action, action.params)
            await hub.publish_status({"minecraft_result": result})
        except Exception as exc:
            await hub.publish_status({"minecraft_result": {"ok": False, "message": str(exc)}})


hub = Hub()
minecraft_bridge = ServerTapClient()
engine = Engine(on_action=publish_game_action)


async def process_event(ev: TikTokEvent) -> None:
    if ev.viewer_count:
        hub.viewer_count = ev.viewer_count
    record_event(ev)
    await hub.publish_event(ev)
    await engine.handle(ev)


connector = TikTokConnector(process_event)
_catalog_refresh_task: asyncio.Task | None = None
_catalog_refresh_started = False


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
    data["bridge_has_secret"] = bool(config.bridge_webhook_secret or os.getenv("BRIDGE_WEBHOOK_SECRET", ""))
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


@app.on_event("startup")
async def startup() -> None:
    global config, _catalog_refresh_task, _catalog_refresh_started
    preset_store.ensure_default()
    config = read_config()
    sync_minecraft_client()
    engine.load_preset(config.active_preset_id)
    # TikTok's public catalog is loaded once in the background; the panel remains usable offline.
    if not _catalog_refresh_started:
        _catalog_refresh_started = True
        _catalog_refresh_task = asyncio.create_task(asyncio.to_thread(_refresh_catalog_safely))
    if config.mode == "simulator":
        await connector.start("simulator")


@app.on_event("shutdown")
async def shutdown() -> None:
    await connector.stop()


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

@app.post("/api/updates/apply")
async def apply_downloaded_update() -> dict:
    if not update_state.request_apply():
        raise HTTPException(409, "Nie ma pobranej aktualizacji do zastosowania.")
    return {"ok": True, "message": "GiftStream uruchomi się ponownie z pobraną aktualizacją."}

@app.get("/api/download-info")
async def download_info() -> dict:
    """Returns the latest Windows launcher URL when a release has been published."""
    now = time.time()
    if _DOWNLOAD_INFO_CACHE["data"] is not None and now < _DOWNLOAD_INFO_CACHE["expires"]:
        return _DOWNLOAD_INFO_CACHE["data"]
    fallback = {"available": False, "url": GITHUB_RELEASES_URL,
                "releases_url": GITHUB_RELEASES_URL,
                "message": "Wydanie GiftStream dla Windows nie jest obecnie dostępne."}
    def check_github_release() -> dict:
        request = urllib.request.Request(
            "https://api.github.com/repos/rejson59/GiftStream/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "GiftStream-Preview/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                release = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return fallback
            raise
        assets = {a.get("name"): a for a in release.get("assets", [])}
        installer = assets.get("GiftStream-Setup-win-x64.exe")
        asset = installer or assets.get("GiftStream.exe") or assets.get("TipStream.exe")
        asset_url = str((asset or {}).get("browser_download_url", ""))
        if asset and asset_url.startswith("https://github.com/"):
            download_kind = "instalator" if installer else "wersję przenośną"
            return {"available": True, "kind": "installer" if installer else "portable",
                    "url": asset_url, "releases_url": GITHUB_RELEASES_URL,
                    "version": release.get("tag_name", ""),
                    "message": f"Pobierz {download_kind} GiftStream {release.get('tag_name', '')} dla Windows."}
        return fallback

    try:
        result = await asyncio.to_thread(check_github_release)
    except Exception:
        result = {**fallback, "message": "Nie udało się sprawdzić wydań. Otwórz stronę GitHub Releases."}
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
    merged = {**config.model_dump(), **data}
    config = AppConfig(**merged)
    sync_minecraft_client()
    save_config()
    return public_config()

@app.get("/api/gifts")
async def gifts(q: str = "") -> list[dict]:
    return list_gifts(q)

@app.post("/api/gifts/refresh")
async def refresh_gifts() -> dict:
    count = await asyncio.to_thread(_refresh_catalog_safely)
    return {"ok": count > 0, "count": count, "gifts": list_gifts()}

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
async def bridge_event(ev: TikTokEvent, x_tipstream_secret: str | None = Header(default=None)) -> dict:
    secret = config.bridge_webhook_secret or os.getenv("BRIDGE_WEBHOOK_SECRET", "")
    if secret and not secrets.compare_digest(x_tipstream_secret or "", secret):
        raise HTTPException(401, "Invalid or missing X-TipStream-Secret")
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

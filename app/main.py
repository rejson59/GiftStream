"""GiftStream — API i serwer webowy."""
from __future__ import annotations

import asyncio
import json
import ipaddress
import os
import re
import secrets
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import presets as preset_store
from . import earnings as earnings_tracker
from .bridge import Hub
from .engine import Engine
from .gifts import coin_price_for_gift, list_gifts, record_event, refresh_tiktok_catalog
from .games import get_game
from .parkour_server import ParkourServer, minecraft_versions
from .models import AppConfig, GameAction, Preset, Rule, TikTokEvent
from .paths import bundle_root, data_dir, installed_release_tag
from .tiktok_connector import TikTokConnector
from .version import VERSION
from . import update_state
from . import diagnostics
from .myinstants import search as search_myinstants
from . import audio as audio_tools

load_dotenv()
ROOT = bundle_root()
DATA = data_dir()
WEB = ROOT / "web"
CONFIG_PATH = DATA / "config.json"
GITHUB_RELEASES_URL = "https://github.com/rejson59/GiftStream/releases"
_DOWNLOAD_INFO_CACHE: dict[str, Any] = {"expires": 0.0, "data": None}

app = FastAPI(title="GiftStream", version=VERSION,
              description="TikTok LIVE gifts control the game")


@app.middleware("http")
async def log_http_failures(request: Request, call_next):
    """Capture failed routes without logging query strings, bodies, or credentials."""
    try:
        response = await call_next(request)
    except Exception as exc:
        diagnostics.error("Unhandled HTTP exception %s %s: %s",
                          request.method, request.url.path, exc, exc_info=exc)
        raise
    if response.status_code >= 500:
        diagnostics.error("HTTP %s %s finished with status %s.",
                          request.method, request.url.path, response.status_code)
    elif response.status_code >= 400:
        diagnostics.warning("HTTP %s %s finished with status %s.",
                            request.method, request.url.path, response.status_code)
    return response


connector: TikTokConnector
config = AppConfig()


class ConnectRequest(BaseModel):
    mode: Literal["tiktok", "managed"] = "tiktok"
    username: str = ""


class EarningsSettingsRequest(BaseModel):
    usd_per_diamond: float = Field(gt=0, le=1)
    usd_to_pln: float | None = Field(default=None, gt=0, le=100)


class ParkourSetupRequest(BaseModel):
    server_dir: str = ""
    player: str
    eula_accepted: bool = False
    version: str = "latest"
    game_mode: Literal["parkour", "dropper"] = "parkour"


class ParkourActionRequest(BaseModel):
    action: str
    player: str | None = None


class ParkourChatRelayRequest(BaseModel):
    enabled: bool = False


class ClientDiagnosticRequest(BaseModel):
    source: str = Field(default="browser", max_length=80)
    message: str = Field(min_length=1, max_length=1500)


class BrowserEventRequest(BaseModel):
    event: TikTokEvent
    trigger_actions: bool = False


async def publish_game_action(action: GameAction) -> None:
    trigger = action.triggered_by
    trigger_hint = f" po zdarzeniu {trigger.type}" if trigger else ""
    diagnostics.info("Matched rule '%s': action '%s'%s.",
                     action.rule_name or "unnamed", action.action, trigger_hint)
    action_id = await hub.publish_action(action)
    if not action.action.startswith(("parkour_", "dropper_")):
        await hub.update_action(action_id, "sent", "Sent to the local bridge; the game has not confirmed execution.")
        return
    try:
        result = await _run_parkour_action(action)
        if result is None:
            await hub.update_action(
                action_id, "sent",
                "The local bridge received the action; local Minecraft control is disabled, so execution is not confirmed.")
        else:
            await hub.update_action(action_id, "succeeded", result)
    except Exception as exc:
        diagnostics.error("Parkour action '%s' from rule '%s' failed: %s",
                          action.action, action.rule_name, exc, exc_info=exc)
        await hub.update_action(action_id, "failed", str(exc))
        await hub.publish_status({"parkour_result": {"ok": False, "message": str(exc)}})


hub = Hub()
parkour_server = ParkourServer()
parkour_reset_task: asyncio.Task | None = None
parkour_reset_player = ""
parkour_jail_tasks: dict[str, asyncio.Task] = {}


async def _run_parkour_action(action: GameAction, *, allow_disabled: bool = False) -> str | None:
    global parkour_reset_task, parkour_reset_player
    settings = parkour_server.settings()
    if not settings.get("enabled") and not allow_disabled:
        diagnostics.warning("Parkour action '%s' skipped: local game control is disabled or the server is not configured.",
                            action.action)
        return
    player = str(action.params.get("player") or settings.get("player") or "")
    if action.action == "parkour_reset":
        if parkour_reset_task and not parkour_reset_task.done():
            parkour_reset_task.cancel()
        await asyncio.to_thread(parkour_server.start_reset, player)
        diagnostics.info("Started the Parkour reset with a 60-second countdown for %s.", player)
        parkour_reset_player = player
        countdown_update_failed = False
        async def countdown() -> None:
            global parkour_reset_task, parkour_reset_player
            nonlocal countdown_update_failed
            try:
                for remaining in range(60, 0, -1):
                    await hub.publish_status({"parkour_reset_countdown": remaining, "parkour_player": player})
                    try:
                        await asyncio.to_thread(parkour_server.update_reset_countdown, player, remaining)
                    except Exception as exc:
                        # Preserve the countdown if the player is temporarily offline,
                        # but capture the first RCON failure in diagnostics.
                        if not countdown_update_failed:
                            diagnostics.warning("Could not update the reset countdown through RCON: %s", exc)
                            countdown_update_failed = True
                    await asyncio.sleep(1)
                result = await asyncio.to_thread(parkour_server.finish_reset, player)
                diagnostics.info("Countdown finished; Parkour reset sent for %s.", player)
                await hub.publish_status({"parkour_reset_countdown": 0, "parkour_result": result})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                diagnostics.error("The Parkour reset countdown failed: %s", exc, exc_info=exc)
                await hub.publish_status({"parkour_reset_countdown": None, "parkour_result": str(exc)})
            finally:
                parkour_reset_task = None
        parkour_reset_task = asyncio.create_task(countdown())
        return "Started the 60-second reset countdown."
    if action.action == "parkour_antireset":
        if parkour_reset_task and not parkour_reset_task.done():
            parkour_reset_task.cancel()
            parkour_reset_task = None
            result = await asyncio.to_thread(parkour_server.cancel_reset, parkour_reset_player or player)
            diagnostics.info("Cancelled the Parkour reset for %s.", parkour_reset_player or player)
            await hub.publish_status({"parkour_reset_countdown": None, "parkour_result": result})
            return result
        diagnostics.info("Anti-reset received, but no countdown was running.")
        return "There is no reset countdown to cancel."
    if action.action == "parkour_jail":
        result = await asyncio.to_thread(parkour_server.execute_action, action.action, player, action.params)
        previous = parkour_jail_tasks.pop(player, None)
        if previous and not previous.done():
            previous.cancel()
        jail_seconds = max(3, min(120, int((action.params or {}).get("seconds", 20) or 20)))
        async def release_jail() -> None:
            try:
                await asyncio.sleep(jail_seconds)
                released = await asyncio.to_thread(parkour_server.release_jail, player)
                diagnostics.info("Released %s from the parkour cage.", player)
                await hub.publish_status({"parkour_result": released})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                diagnostics.error("Could not release player %s from parkour jail: %s", player, exc, exc_info=exc)
                await hub.publish_status({"parkour_result": str(exc)})
            finally:
                parkour_jail_tasks.pop(player, None)
        parkour_jail_tasks[player] = asyncio.create_task(release_jail())
        await hub.publish_status({"parkour_result": result, "parkour_jail_seconds": jail_seconds})
        return result
    if action.action.startswith(("parkour_", "dropper_")):
        result = await asyncio.to_thread(parkour_server.execute_action, action.action, player, action.params)
        await hub.publish_status({"parkour_result": result})
        return result


engine = Engine(on_action=publish_game_action)


async def process_event(ev: TikTokEvent, *, trigger_actions: bool = True) -> None:
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
                ev.gift_coins_source = "catalog"
    now = time.monotonic()
    gift_label = (ev.gift_name or "")[:100] if ev.type == "gift" else ""
    event_key = (ev.source[:40], ev.type, gift_label)
    if now - _event_diag_times.get(event_key, 0.0) >= 15:
        _event_diag_times[event_key] = now
        if len(_event_diag_times) > 1000:
            _event_diag_times.pop(next(iter(_event_diag_times)))
        diagnostics.info("Odebrano zdarzenie: source=%s type=%s%s%s.",
                         ev.source[:40], ev.type,
                         f" gift={gift_label!r}" if gift_label else "",
                         f" count={ev.repeat_count}" if ev.type == "gift" else "")
    try:
        record_event(ev)
        await hub.publish_event(ev)
        if (ev.type == "comment" and ev.source == "tiktok" and ev.comment
                and parkour_server.settings().get("chat_relay_enabled")):
            try:
                await asyncio.to_thread(parkour_server.relay_chat, ev.comment)
                diagnostics.info("LIVE comment relayed to the Minecraft chat (content omitted from the log).")
            except Exception as exc:
                diagnostics.error("Could not relay the LIVE comment to Minecraft: %s", exc, exc_info=exc)
                await hub.publish_status({"parkour_chat_relay_error": str(exc)})
        if trigger_actions:
            await engine.handle(ev)
    except Exception as exc:
        diagnostics.error("Error while processing the event source=%s type=%s: %s",
                          ev.source, ev.type, exc, exc_info=exc)
        raise


connector = TikTokConnector(process_event)
_catalog_refresh_task: asyncio.Task | None = None
_catalog_refresh_started = False
_gift_refresh_loop_task: asyncio.Task | None = None
_currency_refresh_task: asyncio.Task | None = None
_event_diag_times: dict[tuple[str, str, str], float] = {}


async def _currency_refresh_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(earnings_tracker.refresh_usd_to_pln)
        except Exception as exc:
            # Keep the last successful NBP rate and never delay application startup.
            diagnostics.warning("Could not refresh the NBP rate; keeping the last saved rate: %s", exc)
        await asyncio.sleep(12 * 60 * 60)


async def _gift_catalog_refresh_loop() -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            await asyncio.to_thread(_refresh_catalog_safely)
        except Exception as exc:
            # Retain the last cached gift catalog if TikTok or the network is unavailable.
            diagnostics.warning("Could not refresh the gift catalog; keeping the cache: %s", exc)


def read_config() -> AppConfig:
    if CONFIG_PATH.exists():
        try:
            result = AppConfig(**json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
            diagnostics.info("Loaded the GiftStream configuration from %s.", CONFIG_PATH)
            return result
        except Exception as exc:
            diagnostics.error("Could not load the configuration %s: %s; using defaults.",
                              CONFIG_PATH, exc, exc_info=exc)
    return AppConfig()


def save_config() -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        diagnostics.info("GiftStream configuration saved.")
    except Exception as exc:
        diagnostics.error("Could not save the GiftStream configuration: %s", exc, exc_info=exc)
        raise


def public_config() -> dict:
    data = config.model_dump()
    data.pop("bridge_webhook_secret", None)
    data["bridge_has_secret"] = bool(config.bridge_webhook_secret or os.getenv("GIFTSTREAM_BRIDGE_WEBHOOK_SECRET", ""))
    return data


def _refresh_catalog_safely() -> int:
    try:
        count = refresh_tiktok_catalog()
        diagnostics.info("TikTok gift catalog refreshed; available entries: %s.", count)
        return count
    except Exception as exc:
        # Keep the last valid catalog and let the local gallery work offline.
        diagnostics.warning("Could not refresh the TikTok gift catalog; keeping the cache: %s", exc)
        return 0


_LEGACY_PARKOUR_DESCRIPTION = "Ready-made actions for the bundled 100 Levels map: pushing, level changes, a temporary jail, a 60-second reset countdown and anti-reset. Requires the local GiftStream server."
_LEGACY_PARKOUR_RULES = {
    "mp-rose": ("Rose → next level", "gift", "Rose", "parkour_level_forward"),
    "mp-tiktok": ("TikTok → previous level", "gift", "TikTok", "parkour_level_back"),
    "mp-follow": ("Follow → jail", "follow", None, "parkour_jail"),
    "mp-donut": ("Donut → climb one level", "gift", "Donut", "parkour_level_forward"),
    "mp-dragon": ("Dragon → reset in 60 s", "gift", "Dragon", "parkour_reset"),
    "mp-antireset": ("Anti-reset → cancel reset", "gift", "Panda", "parkour_antireset"),
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


WOW_RULE_PREFIXES = ("mp-", "md-")
WOW_RULE_IDS = {
    "mp-darkness", "mp-follow-heart", "mp-share-lightning", "mp-disco", "mp-checkpoint",
    "md-darkness", "md-share-lightning", "md-disco", "md-slow", "md-jump",
}


RETIRED_ACTIONS = {"parkour_speed", "dropper_speed", "parkour_night"}


def _retire_removed_actions() -> list[str]:
    """0.21.0 removes the speed and night actions.

    Rules that used them are migrated to a harmless effect instead of silently
    breaking: speed → jump boost, night → blackout. The coin prices are kept so
    the streamer is not surprised by a price change.
    """
    replacements = {"parkour_speed": "parkour_jump", "dropper_speed": "dropper_jump",
                    "parkour_night": "parkour_blackout"}
    changed: list[str] = []
    for game_id in ("minecraft-parkour", "minecraft-dropper"):
        saved = preset_store.get_preset(game_id)
        if saved is None:
            continue
        touched = False
        for rule in saved.rules:
            if rule.action.type in RETIRED_ACTIONS:
                rule.action.type = replacements[rule.action.type]
                touched = True
                changed.append(rule.id)
        if touched:
            preset_store.save_preset(saved)
            diagnostics.info("Migrated %d rules away from removed speed/night actions.", len(changed))
    return changed


def _add_missing_wow_rules() -> list[str]:
    """Appends the new “wow” rules to presets that are already saved (0.19.0).

    An update must never delete rules configured by the streamer, so only the
    missing identifiers are appended at the end — the existing order and coin
    prices stay untouched.
    """
    added: list[str] = []
    for game_id in ("minecraft-parkour", "minecraft-dropper"):
        game = get_game(game_id)
        saved = preset_store.get_preset(game["preset_id"]) if game else None
        if not game or saved is None:
            continue
        known = {rule.id for rule in saved.rules}
        missing = [rule for rule in game["rules"]
                   if rule["id"] in WOW_RULE_IDS and rule["id"] not in known]
        if not missing:
            continue
        saved.rules.extend(Rule(**rule) for rule in missing)
        preset_store.save_preset(saved)
        added.extend(rule["id"] for rule in missing)
        diagnostics.info("Added %d “wow” rules to preset '%s'.", len(missing), saved.name)
    return added


@app.on_event("startup")
async def startup() -> None:
    global config, _catalog_refresh_task, _catalog_refresh_started, _currency_refresh_task, _gift_refresh_loop_task
    diagnostics.info("Starting GiftStream %s; user data: %s.", VERSION, DATA)
    config = read_config()
    if config.mode == "simulator":
        # Older builds persisted the demo as the startup mode, which generated
        # fabricated viewers/events on every launch. Migrate to an inert state.
        config.mode = "disconnected"
        save_config()
        diagnostics.info("The legacy simulator mode is disabled; GiftStream waits for a manual TikTok LIVE connection.")
    if config.tiktok_username:
        connector.username = config.tiktok_username
    for game_id in ("minecraft-parkour", "minecraft-dropper"):
        game = get_game(game_id)
        if game and preset_store.get_preset(game["preset_id"]) is None:
            preset_store.save_preset(Preset(id=game["preset_id"], name=game["title"],
                                            description=game["description"], rules=game["rules"]))
    _migrate_builtin_parkour_preset()
    _add_missing_wow_rules()
    _retire_removed_actions()
    if config.active_preset_id not in preset_store.PRESET_IDS:
        config.active_preset_id = "minecraft-parkour"
        save_config()
    engine.load_preset(config.active_preset_id)
    diagnostics.info("Loaded preset '%s'; source mode: %s.", config.active_preset_id, config.mode)
    # TikTok's public catalog is loaded once in the background; the panel remains usable offline.
    if not _catalog_refresh_started:
        _catalog_refresh_started = True
        _catalog_refresh_task = asyncio.create_task(asyncio.to_thread(_refresh_catalog_safely))
    if _gift_refresh_loop_task is None or _gift_refresh_loop_task.done():
        _gift_refresh_loop_task = asyncio.create_task(_gift_catalog_refresh_loop())
    if _currency_refresh_task is None or _currency_refresh_task.done():
        _currency_refresh_task = asyncio.create_task(_currency_refresh_loop())
    if config.mode == "tiktok" and config.tiktok_username:
        # Restore the last explicitly selected public LIVE channel after an app restart.
        result = await connector.start("tiktok", config.tiktok_username)
        if not result.get("ok"):
            diagnostics.warning("Automatic TikTok LIVE resume failed: %s", result.get("message", "error"))


@app.on_event("shutdown")
async def shutdown() -> None:
    diagnostics.info("Shutting GiftStream down; cleaning up tasks and connections.")
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
        except Exception as exc:
            diagnostics.warning("Could not stop local Minecraft while shutting GiftStream down: %s", exc)
    if _currency_refresh_task and not _currency_refresh_task.done():
        _currency_refresh_task.cancel()
    if _gift_refresh_loop_task and not _gift_refresh_loop_task.done():
        _gift_refresh_loop_task.cancel()


# -- Web app ---------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard() -> Any:
    return FileResponse(WEB / "index.html")

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
_TIKTOK_IMAGE_HOSTS = ("tiktokcdn.com", "tiktokcdn-us.com", "tiktokcdn-eu.com")
_SOUND_UPLOAD_DIR = DATA / "uploads" / "sounds"
_SOUND_UPLOAD_LIMIT = 10 * 1024 * 1024
_SOUND_MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
               ".m4a": "audio/mp4", ".aac": "audio/aac", ".flac": "audio/flac"}
_SOUND_FILE_RE = re.compile(r"^[a-f0-9]{32}\.(?:mp3|wav|ogg|m4a|aac|flac)$")


def _trusted_tiktok_image_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (parsed.scheme == "https" and parsed.port in (None, 443) and
                not parsed.username and not parsed.password and
                any(host == domain or host.endswith("." + domain) for domain in _TIKTOK_IMAGE_HOSTS))
    except ValueError:
        return False


class _TikTokImageRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        if not _trusted_tiktok_image_url(target):
            raise urllib.error.HTTPError(target, code, "TikTok CDN redirected outside its trusted hosts", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _download_tiktok_image(url: str) -> tuple[bytes, str]:
    if not _trusted_tiktok_image_url(url):
        raise ValueError("Unsupported TikTok artwork URL.")
    request = urllib.request.Request(url, headers={"User-Agent": "GiftStream/1", "Referer": "https://www.tiktok.com/"})
    opener = urllib.request.build_opener(_TikTokImageRedirect())
    with opener.open(request, timeout=8) as response:
        if not _trusted_tiktok_image_url(response.geturl()):
            raise ValueError("The artwork redirect left the TikTok CDN.")
        media_type = response.headers.get_content_type().lower()
        if media_type not in {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}:
            raise ValueError("The TikTok CDN did not return a supported raster image.")
        payload = response.read(4 * 1024 * 1024 + 1)
    if not payload or len(payload) > 4 * 1024 * 1024:
        raise ValueError("The artwork is empty or exceeds the 4 MB limit.")
    return payload, media_type


@app.get("/api/gifts/image")
async def gift_image(url: str) -> Response:
    if not _trusted_tiktok_image_url(url):
        raise HTTPException(400, "The artwork URL must belong to a trusted TikTok CDN.")
    try:
        payload, media_type = await asyncio.to_thread(_download_tiktok_image, url)
    except Exception as exc:
        # Missing CDN art is expected for gifts that TikTok no longer serves;
        # return a cacheable non-server error so a long feed cannot flood diagnostics.
        raise HTTPException(404, f"Artwork unavailable from the TikTok CDN: {exc}",
                            headers={"Cache-Control": "public, max-age=300"}) from exc
    return Response(payload, media_type=media_type,
                    headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})


@app.post("/api/sounds/upload")
async def upload_sound(request: Request, filename: str = "") -> dict[str, Any]:
    safe_name = Path(filename.replace("\\", "/")).name[:160]
    suffix = Path(safe_name).suffix.lower()
    media_type = _SOUND_MIME.get(suffix)
    if not media_type:
        raise HTTPException(415, "Choose an MP3, WAV, OGG, M4A, AAC or FLAC file.")
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        content_length = 0
    if content_length > _SOUND_UPLOAD_LIMIT:
        raise HTTPException(413, "The audio file exceeds the 10 MB limit.")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > _SOUND_UPLOAD_LIMIT:
            raise HTTPException(413, "The audio file exceeds the 10 MB limit.")
        chunks.append(chunk)
    payload = b"".join(chunks)
    signatures = {".wav": lambda b: len(b) > 12 and b[:4] == b"RIFF" and b[8:12] == b"WAVE",
                  ".ogg": lambda b: b.startswith(b"OggS"), ".flac": lambda b: b.startswith(b"fLaC"),
                  ".m4a": lambda b: len(b) > 8 and b[4:8] == b"ftyp",
                  ".aac": lambda b: len(b) > 2 and b[0] == 0xff and (b[1] & 0xf6) == 0xf0,
                  ".mp3": lambda b: b.startswith(b"ID3") or (len(b) > 1 and b[0] == 0xff and (b[1] & 0xe0) == 0xe0)}
    if not payload or not signatures[suffix](payload):
        raise HTTPException(415, "The file does not look like audio matching its extension.")
    _SOUND_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    asset = f"{uuid.uuid4().hex}{suffix}"
    (_SOUND_UPLOAD_DIR / asset).write_bytes(payload)
    diagnostics.info("Saved the user's local sound (%s, %s bytes).", suffix, len(payload))
    return {"url": f"/api/sounds/uploads/{asset}", "name": safe_name, "size": len(payload), "content_type": media_type}


def _save_sound_asset(payload: bytes, suffix: str) -> str:
    _SOUND_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    asset = f"{uuid.uuid4().hex}{suffix}"
    (_SOUND_UPLOAD_DIR / asset).write_bytes(payload)
    return asset


def _wav_duration_seconds(path: Path) -> float | None:
    "WAV file duration; compressed formats are measured by the panel in the browser."""
    if path.suffix.lower() != ".wav":
        return None
    try:
        return audio_tools.wav_info(path.read_bytes())["duration"]
    except (OSError, audio_tools.AudioError):
        return None


@app.get("/api/sounds/uploads")
async def list_uploaded_sounds() -> dict[str, Any]:
    "Uploaded audio files — reusable without uploading them again."""
    items: list[dict[str, Any]] = []
    if _SOUND_UPLOAD_DIR.is_dir():
        for path in sorted(_SOUND_UPLOAD_DIR.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if not _SOUND_FILE_RE.fullmatch(path.name):
                continue
            stat = path.stat()
            items.append({"url": f"/api/sounds/uploads/{path.name}", "name": path.name,
                          "size": stat.st_size, "modified": int(stat.st_mtime),
                          "duration": _wav_duration_seconds(path)})
    return {"files": items[:200], "limit": _SOUND_UPLOAD_LIMIT}


_AUDIO_DOWNLOAD_LIMIT = 10 * 1024 * 1024
_AUDIO_MIME_EXT = {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
                   "audio/wave": ".wav", "audio/vnd.wave": ".wav", "audio/ogg": ".ogg",
                   "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac", "audio/flac": ".flac",
                   "audio/x-flac": ".flac"}
_AUDIO_URL_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}


def _unsafe_host(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
        return True
    return (not hostname or hostname in {"localhost", "metadata.google.internal"} or
            hostname.endswith((".localhost", ".local", ".internal")))


def _public_audio_url(value: str, what: str = "Sound", allow_local: bool = False) -> str:
    """Accepts only public HTTPS (or a file uploaded to GiftStream)."""
    if allow_local and value.startswith("/api/sounds/uploads/"):
        return value
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (len(value) > 2048 or parsed.scheme != "https" or not hostname or parsed.username or
            parsed.password or _unsafe_host(hostname)):
        raise HTTPException(422, f"{what} must be a public HTTPS link or an uploaded local file.")
    return value


@app.post("/api/sounds/fetch")
async def fetch_sound(data: dict[str, Any]) -> dict[str, Any]:
    """Downloads a sound from a public link into a local file so it can be trimmed.

    The browser cannot read bytes from a foreign server (CORS), so GiftStream
    performs the controlled download: HTTPS only, 10 MB limit, the file type is
    verified and the file is stored locally. Thanks to that, trimming also works
    for MyInstants results.
    """
    url = _public_audio_url(str(data.get("url") or "").strip(), "Sound link")
    try:
        downloaded, _media_type = await asyncio.to_thread(_download_audio, url)
    except Exception as exc:
        raise HTTPException(502, f"Could not download the sound from the link: {exc}") from exc
    suffix = downloaded["suffix"]
    asset = _save_sound_asset(downloaded["payload"], suffix)
    name = str(data.get("name") or Path(urlparse(url).path).name or "sound")[:100]
    diagnostics.info("Downloaded the linked sound into a local file (%s, %s bytes).", suffix, len(downloaded["payload"]))
    return {"url": f"/api/sounds/uploads/{asset}", "name": name, "size": len(downloaded["payload"]),
            "content_type": downloaded["content_type"], "source": "download"}


class _AudioRedirect(urllib.request.HTTPRedirectHandler):
    """Blocks redirects outside public HTTPS — otherwise a link could point to
    localhost or the streamer's LAN (SSRF)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        try:
            _public_audio_url(target)
        except HTTPException as exc:
            raise urllib.error.HTTPError(target, code, str(exc.detail), headers, fp) from exc
        return super().redirect_request(req, fp, code, msg, headers, target)


def _download_audio(url: str) -> tuple[dict[str, Any], str]:
    request = urllib.request.Request(url, headers={"User-Agent": "GiftStream/1 (sound fetch)",
                                                   "Accept": "audio/*,application/octet-stream"})
    opener = urllib.request.build_opener(_AudioRedirect())
    with opener.open(request, timeout=10) as response:
        final = response.geturl()
        _public_audio_url(final, "Sound link")
        raw_type = (response.headers.get_content_type() or "").lower()
        length = response.headers.get("Content-Length")
        if length and int(length) > _AUDIO_DOWNLOAD_LIMIT:
            raise ValueError("The sound exceeds the 10 MB limit.")
        payload = response.read(_AUDIO_DOWNLOAD_LIMIT + 1)
    if not payload or len(payload) > _AUDIO_DOWNLOAD_LIMIT:
        raise ValueError("The sound is empty or exceeds the 10 MB limit.")
    suffix = _AUDIO_MIME_EXT.get(raw_type) or Path(urlparse(final).path).suffix.lower()
    if suffix not in _AUDIO_URL_EXT:
        raise ValueError("The link does not point to a supported audio file (MP3, WAV, OGG, M4A, AAC, FLAC).")
    signatures = {".wav": lambda b: len(b) > 12 and b[:4] == b"RIFF" and b[8:12] == b"WAVE",
                  ".ogg": lambda b: b.startswith(b"OggS"), ".flac": lambda b: b.startswith(b"fLaC"),
                  ".m4a": lambda b: len(b) > 8 and b[4:8] == b"ftyp",
                  ".aac": lambda b: len(b) > 2 and b[0] == 0xff and (b[1] & 0xf6) == 0xf0,
                  ".mp3": lambda b: b.startswith(b"ID3") or (len(b) > 1 and b[0] == 0xff and (b[1] & 0xe0) == 0xe0)}
    if not signatures[suffix](payload):
        raise ValueError("The downloaded file does not look like audio matching its extension.")
    return ({"payload": payload, "suffix": suffix,
             "content_type": _SOUND_MIME.get(suffix, raw_type or "application/octet-stream")},
            raw_type)


@app.post("/api/sounds/info")
async def sound_info(request: Request, filename: str = "") -> dict[str, Any]:
    "Sound parameters: duration, channels, sample rate and the waveform."""
    payload = await request.body()
    if not payload or len(payload) > _SOUND_UPLOAD_LIMIT:
        raise HTTPException(413, "The audio file is empty or exceeds the 10 MB limit.")
    try:
        info = await asyncio.to_thread(audio_tools.wav_info, payload)
        peaks = await asyncio.to_thread(audio_tools.wav_peaks, payload, 180)
    except audio_tools.AudioError as exc:
        raise HTTPException(415, str(exc)) from exc
    return {**info, "name": Path(filename.replace("\\", "/")).name[:160], "peaks": peaks}


@app.post("/api/sounds/trim")
async def trim_sound(request: Request, start: float = 0, end: float | None = None,
                     fade_in_ms: int = 0, fade_out_ms: int = 0,
                     filename: str = "") -> dict[str, Any]:
    "Cuts a WAV fragment (with soft fade in/out) and saves it as a new sound."""
    payload = await request.body()
    if not payload or len(payload) > _SOUND_UPLOAD_LIMIT:
        raise HTTPException(413, "The audio file is empty or exceeds the 10 MB limit.")
    if start < 0 or (end is not None and end <= start):
        raise HTTPException(422, "The trim range is invalid.")
    try:
        clipped, info = await asyncio.to_thread(
            audio_tools.trim_wav, payload, start, end, fade_in_ms, fade_out_ms)
    except audio_tools.AudioError as exc:
        raise HTTPException(415, str(exc)) from exc
    asset = _save_sound_asset(clipped, ".wav")
    stem = Path(Path(filename.replace("\\", "/")).name).stem[:80] or "fragment"
    label = f"{stem} · {info['start']:.2f}–{info['end']:.2f} s"[:160]
    diagnostics.info("Trimmed the sound to %.2f s (fade %s/%s ms).", info["duration"], fade_in_ms, fade_out_ms)
    return {"url": f"/api/sounds/uploads/{asset}", "name": label, "size": len(clipped),
            "content_type": "audio/wav", **info}


@app.get("/api/sounds/uploads/{filename}")
async def uploaded_sound(filename: str) -> FileResponse:
    if not _SOUND_FILE_RE.fullmatch(filename):
        raise HTTPException(404, "Audio file not found.")
    path = _SOUND_UPLOAD_DIR / filename
    if not path.is_file():
        raise HTTPException(404, "Audio file not found.")
    return FileResponse(path, media_type=_SOUND_MIME[path.suffix],
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@app.get("/api/sounds/myinstants")
async def myinstants_search(q: str = "") -> dict[str, Any]:
    if len(q) > 100:
        raise HTTPException(400, "The search phrase can be at most 100 characters.")
    if not q.strip():
        return {"results": [], "notice": "The MyInstants search is unofficial and may stop working from time to time."}
    try:
        results = await asyncio.to_thread(search_myinstants, q)
    except Exception as exc:
        raise HTTPException(502, f"Could not load the MyInstants results: {exc}") from exc
    return {"results": results, "notice": "Results come from the unofficial MyInstants search; file availability may change."}

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
            "message": "Update check started." if queued else "An update check is already running."}

@app.post("/api/updates/apply")
async def apply_downloaded_update() -> dict:
    if not update_state.request_apply():
        raise HTTPException(409, "There is no downloaded update to apply.")
    return {"ok": True, "message": "GiftStream will restart with the downloaded update."}

@app.get("/api/download-info")
async def download_info() -> dict:
    """Return the single GiftStream executable download URL."""
    now = time.time()
    if _DOWNLOAD_INFO_CACHE["data"] is not None and now < _DOWNLOAD_INFO_CACHE["expires"]:
        return _DOWNLOAD_INFO_CACHE["data"]
    fallback = {"available": False, "url": GITHUB_RELEASES_URL,
                "releases_url": GITHUB_RELEASES_URL,
                "message": "The GiftStream Windows release is not available right now."}

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
                    "message": f"Download GiftStream {version} for Windows."}
        return fallback

    try:
        result = await asyncio.to_thread(check_github_release)
    except Exception:
        result = {**fallback, "message": "Could not check the releases. Open the GiftStream releases page."}
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

@app.post("/api/stats/clear-activity")
async def clear_activity() -> dict[str, Any]:
    hub.clear_activity()
    diagnostics.info("The user cleared the activity feed; counters were left unchanged.")
    await hub.broadcast_snapshot()
    return {"ok": True, "message": "Activity feed cleared. Statistics counters were left unchanged."}

@app.post("/api/stats/reset")
async def reset_stats() -> dict[str, Any]:
    hub.reset_stats()
    engine.reset_stats()
    diagnostics.info("The user reset all statistics of the current session.")
    await hub.broadcast_snapshot()
    await hub.publish_status({"stats_reset": True})
    return {"ok": True, "message": "All statistics of the current session were reset."}

@app.get("/api/config")
async def get_config() -> dict:
    return public_config()

@app.put("/api/config")
async def update_config(data: dict[str, Any]) -> dict:
    global config
    if "sound_url" in data:
        url = str(data["sound_url"] or "").strip()
        if url.startswith("/api/sounds/uploads/"):
            filename = url.rsplit("/", 1)[-1]
            if not _SOUND_FILE_RE.fullmatch(filename) or not (_SOUND_UPLOAD_DIR / filename).is_file():
                raise HTTPException(422, "No uploaded audio file was found.")
        elif url:
            _public_audio_url(url)
        data["sound_url"] = url
    merged = {**config.model_dump(), **data}
    try:
        config = AppConfig(**merged)
    except ValidationError as exc:
        raise HTTPException(422, detail=jsonable_encoder(exc.errors())) from exc
    save_config()
    diagnostics.info("Zaktualizowano ustawienia panelu GiftStream.")
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
                "message": f"Could not download the latest NBP rate: {exc}"}

@app.get("/api/minecraft/versions")
async def minecraft_version_options() -> dict[str, Any]:
    try:
        versions = await asyncio.to_thread(minecraft_versions)
        diagnostics.info("Downloaded the list of stable Minecraft versions; latest=%s.", versions.get("latest"))
        return versions
    except Exception as exc:
        diagnostics.error("Could not download the Minecraft version manifest: %s", exc, exc_info=exc)
        raise HTTPException(502, f"Could not download the Minecraft version from the Mojang manifest: {exc}") from exc

@app.get("/api/minecraft/parkour")
async def parkour_status() -> dict[str, Any]:
    settings = parkour_server.settings()
    status = await asyncio.to_thread(parkour_server.status)
    status["enabled"] = bool(settings.get("enabled"))
    status["chat_relay_enabled"] = bool(settings.get("chat_relay_enabled"))
    return status

@app.post("/api/minecraft/parkour/setup")
async def parkour_setup(req: ParkourSetupRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(parkour_server.setup, req.server_dir, req.player, req.eula_accepted, req.version, req.game_mode)
    except (ValueError, FileExistsError) as exc:
        diagnostics.warning("Minecraft setup was rejected: %s", exc)
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        diagnostics.error("The Minecraft setup endpoint returned an error: %s", exc, exc_info=exc)
        raise HTTPException(502, str(exc)) from exc

@app.post("/api/minecraft/parkour/start")
async def parkour_start() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(parkour_server.start)
    except Exception as exc:
        diagnostics.error("Could not start the Minecraft server through the API: %s", exc, exc_info=exc)
        raise HTTPException(400, str(exc)) from exc

@app.post("/api/minecraft/parkour/reset-map")
async def parkour_reset_map() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(parkour_server.reset_world)
    except Exception as exc:
        diagnostics.warning("Could not reset the Minecraft map through the API: %s", exc)
        raise HTTPException(400, str(exc)) from exc

@app.post("/api/minecraft/parkour/stop")
async def parkour_stop() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(parkour_server.stop)
    except Exception as exc:
        diagnostics.error("Could not stop the Minecraft server through the API: %s", exc, exc_info=exc)
        raise HTTPException(400, str(exc)) from exc

@app.put("/api/minecraft/parkour/enabled")
async def parkour_enabled(request: dict[str, bool]) -> dict[str, Any]:
    state = parkour_server.settings()
    if not state.get("server_dir"):
        raise HTTPException(400, "Najpierw skonfiguruj lokalny serwer parkour.")
    state["enabled"] = bool(request.get("enabled", False))
    await asyncio.to_thread(parkour_server.save_settings, state)
    diagnostics.info("Sterowanie zdarzeniami w lokalnym Parkour %s.", "enabled" if state["enabled"] else "disabled")
    return {**await asyncio.to_thread(parkour_server.status),
            "enabled": state["enabled"],
            "chat_relay_enabled": bool(state.get("chat_relay_enabled"))}

@app.put("/api/minecraft/parkour/chat-relay")
async def parkour_chat_relay(req: ParkourChatRelayRequest) -> dict[str, Any]:
    state = parkour_server.settings()
    if not state.get("server_dir"):
        raise HTTPException(400, "Najpierw skonfiguruj lokalny serwer parkour.")
    state["chat_relay_enabled"] = req.enabled
    await asyncio.to_thread(parkour_server.save_settings, state)
    diagnostics.info("Przekazywanie komentarzy LIVE do Minecraft %s.", "enabled" if req.enabled else "disabled")
    return {"ok": True, "chat_relay_enabled": req.enabled}

@app.post("/api/minecraft/parkour/action")
async def parkour_test_action(req: ParkourActionRequest) -> dict[str, Any]:
    from .models import KNOWN_ACTIONS
    state = parkour_server.settings()
    mode = state.get("game_mode", "parkour")
    prefix = "dropper_" if mode == "dropper" else "parkour_"
    if req.action not in KNOWN_ACTIONS or not req.action.startswith(prefix):
        raise HTTPException(400, f"This action does not match the active mode {mode}.")
    if not state.get("server_dir"):
        raise HTTPException(409, "Najpierw skonfiguruj lokalny serwer Minecraft.")
    status = await asyncio.to_thread(parkour_server.status)
    if not status.get("ready"):
        raise HTTPException(409, status.get("message") or "The Minecraft server is not ready over RCON yet.")
    player = req.player or str(state.get("player", ""))
    if not player or player.casefold() not in {str(name).casefold() for name in status.get("players", [])}:
        raise HTTPException(409, f"Player {player or '(not set)'} is not online on the Minecraft server.")
    try:
        # A manual test is intentionally independent of the LIVE automation toggle.
        # That toggle controls incoming gifts; this endpoint is an explicit user action.
        message = await _run_parkour_action(
            GameAction(action=req.action, params={"player": player}), allow_disabled=True)
    except Exception as exc:
        diagnostics.warning("Minecraft action test '%s' failed: %s", req.action, exc)
        raise HTTPException(502, f"Could not run the Minecraft action: {exc}") from exc
    return {"ok": True, "message": message or f"Action {req.action} sent for {player}."}

@app.get("/api/actions")
async def actions() -> list[dict]:
    from .models import KNOWN_ACTIONS
    labels = {
        "parkour_push": "Parkour: Punch II arrow",
        "parkour_level_forward": "Parkour: next level",
        "parkour_level_back": "Parkour: previous level",
        "parkour_checkpoint": "Parkour: back to checkpoint",
        "parkour_jail": "Parkour: jail for 20 s",
        "parkour_reset": "Parkour: reset in 60 s",
        "parkour_antireset": "Parkour: cancel reset",
        "parkour_slow": "Parkour: slowness · 7 s",
        "parkour_blind": "Parkour: darkness · 4 s",
        "parkour_blackout": "Parkour: blackout · 15 s (barely visible)",
        "parkour_lightning": "Parkour: lightning",
        "parkour_disco": "Parkour: disco",
        "parkour_heart": "Parkour: hearts + ovation (follow)",
        "parkour_jump": "Parkour: high jump · 4 s",
        "parkour_shield": "Parkour: shield · 6 s",
        "parkour_cleanse": "Parkour: clear negative effects",
        "dropper_push": "Dropper: Punch II arrow",
        "dropper_level_forward": "Dropper: next level",
        "dropper_level_back": "Dropper: previous level",
        "dropper_reset": "Dropper: back to the start",
        "dropper_slow": "Dropper: slowness · 7 s",
        "dropper_blind": "Dropper: darkness · 4 s",
        "dropper_blackout": "Dropper: blackout · 15 s (barely visible)",
        "dropper_lightning": "Dropper: lightning",
        "dropper_disco": "Dropper: disco",
        "dropper_heart": "Dropper: hearts + ovation (follow)",
        "dropper_jump": "Dropper: high jump",
        "dropper_shield": "Dropper: shield · 6 s",
        "dropper_cleanse": "Dropper: clear negative effects",
    }
    return [{"id": action, "label": labels[action]} for action in KNOWN_ACTIONS]

@app.get("/api/presets")
async def list_presets() -> list[dict]:
    return [preset.model_dump() for preset_id in sorted(preset_store.PRESET_IDS)
            if (preset := preset_store.get_preset(preset_id)) is not None]

@app.get("/api/presets/{preset_id}")
async def get_preset(preset_id: str) -> dict:
    if preset_id not in preset_store.PRESET_IDS:
        raise HTTPException(404, "Preset not found")
    p = preset_store.get_preset(preset_id)
    if p is None:
        raise HTTPException(404, "Preset not found")
    return p.model_dump()

def _validate_rule_sound_url(url: str) -> None:
    if url.startswith("/api/sounds/uploads/"):
        filename = url.rsplit("/", 1)[-1]
        if not _SOUND_FILE_RE.fullmatch(filename) or not (_SOUND_UPLOAD_DIR / filename).is_file():
            raise HTTPException(422, "No uploaded audio file assigned to the rule was found.")
        return
    _public_audio_url(url, "Rule sound", allow_local=True)


@app.put("/api/presets/{preset_id}")
async def update_preset(preset_id: str, preset: Preset) -> dict:
    if preset_id not in preset_store.PRESET_IDS:
        raise HTTPException(404, "Preset not found")
    if preset.id != preset_id:
        raise HTTPException(400, "The IDs in the URL and the body must match")
    for rule in preset.rules:
        if rule.sound:
            _validate_rule_sound_url(rule.sound)
    saved = preset_store.save_preset(preset)
    if engine.active_preset and engine.active_preset.id == preset_id:
        engine.load_preset(preset_id)
    diagnostics.info("Saved the Parkour preset '%s' (%s rules).", saved.name, len(saved.rules))
    return saved.model_dump()

@app.post("/api/presets/{preset_id}/activate")
async def activate_preset(preset_id: str) -> dict:
    if preset_id not in preset_store.PRESET_IDS:
        raise HTTPException(404, "Preset not found")
    preset = engine.load_preset(preset_id)
    if preset is None:
        raise HTTPException(404, "Preset not found")
    config.active_preset_id = preset_id
    save_config()
    await hub.publish_status({"active_preset_id": preset_id, "active_preset_name": preset.name})
    diagnostics.info("Aktywowano preset Parkour '%s'.", preset.name)
    return {"ok": True, "preset": preset.model_dump()}

@app.get("/api/logs")
async def get_diagnostics(limit: int = 300) -> dict[str, Any]:
    lines = diagnostics.get_logs(limit)
    minecraft_lines = await asyncio.to_thread(parkour_server.diagnostic_lines, min(max(limit, 1), 150))
    return {"lines": lines + minecraft_lines}

@app.post("/api/logs/client")
async def report_client_diagnostic(req: ClientDiagnosticRequest) -> dict[str, bool]:
    diagnostics.error("UI error (%s): %s", req.source, req.message)
    return {"ok": True}

@app.post("/api/logs/clear")
async def clear_diagnostics() -> dict[str, bool]:
    diagnostics.clear_logs()
    await asyncio.to_thread(parkour_server.clear_diagnostic_logs)
    diagnostics.info("Dziennik aplikacji i log Minecraft wyczyszczono z panelu GiftStream.")
    return {"ok": True}

@app.post("/api/connect")
async def connect(req: ConnectRequest) -> dict:
    global config
    username = req.username.strip().lstrip("@").strip()
    if req.mode == "tiktok" and not re.fullmatch(r"[A-Za-z0-9._]{2,24}", username):
        raise HTTPException(400, "Podaj poprawny @username TikTok LIVE (bez spacji).")

    previous_username = config.tiktok_username.strip().lstrip("@").casefold()
    new_tiktok_user = req.mode == "tiktok" and username.casefold() != previous_username
    if new_tiktok_user:
        # Stop old-user events first, then clear every counter/history before the
        # new connector is allowed to receive data. This prevents mixed LIVE stats.
        await connector.stop()
        hub.reset_stats()
        engine.reset_stats()
        config.mode = "disconnected"
        config.tiktok_username = username
        save_config()
        await hub.broadcast_snapshot()
        await hub.publish_status({"stats_reset": True})
        diagnostics.info("New TikTok LIVE channel @%s; statistics were reset before connecting.", username)
    try:
        result = await connector.start(req.mode, username)
    except Exception as exc:
        diagnostics.error("Connector start error (%s): %s", req.mode, exc, exc_info=exc)
        raise HTTPException(500, "Could not start the connection. Details are in the log panel.") from exc
    if result.get("ok"):
        config.mode = req.mode
        config.tiktok_username = username if req.mode == "tiktok" else config.tiktok_username
        save_config()
    await hub.publish_status(connector.status())
    return result

@app.post("/api/disconnect")
async def disconnect() -> dict:
    global config
    await connector.stop()
    config.mode = "disconnected"
    save_config()
    await hub.publish_status(connector.status())
    diagnostics.info("The connection was stopped manually; automatic resume disabled.")
    return {"ok": True, "message": "Disconnected"}

@app.post("/api/bridge/event")
async def bridge_event(ev: TikTokEvent, x_giftstream_secret: str | None = Header(default=None)) -> dict:
    secret = config.bridge_webhook_secret or os.getenv("GIFTSTREAM_BRIDGE_WEBHOOK_SECRET", "")
    if secret and not secrets.compare_digest(x_giftstream_secret or "", secret):
        raise HTTPException(401, "Invalid or missing X-GiftStream-Secret")
    await process_event(ev)
    return {"ok": True}

@app.post("/api/browser/event")
async def browser_event(req: BrowserEventRequest, request: Request) -> dict[str, Any]:
    """Accept normalized events from a local browser helper; never expose a public ingest."""
    remote = request.client.host if request.client else ""
    try:
        is_loopback = ipaddress.ip_address(remote).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(403, "The browser relay accepts events only from this computer.")
    ev = req.event
    if ev.type == "system":
        raise HTTPException(422, "The browser relay does not accept system events.")
    if (len(ev.user) > 64 or len(ev.nickname) > 100 or len(ev.comment or "") > 1000
            or len(ev.gift_name or "") > 128 or len(ev.gift_image_url or "") > 2048
            or ev.repeat_count < 1 or ev.repeat_count > 1000
            or ev.like_count < 0 or ev.like_count > 10_000_000
            or ev.diamonds < 0 or ev.diamonds > 10_000_000):
        raise HTTPException(422, "The browser event exceeds the allowed size or range.")
    normalized = ev.model_copy(update={"source": "browser"})
    await process_event(normalized, trigger_actions=req.trigger_actions)
    return {"ok": True, "received": normalized.type,
            "trigger_actions": req.trigger_actions,
            "events_received": hub.browser_event_count}


@app.get("/api/browser/status")
async def browser_status(request: Request) -> dict[str, Any]:
    remote = request.client.host if request.client else ""
    try:
        is_loopback = ipaddress.ip_address(remote).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(403, "The browser relay is available locally only.")
    return {"events_received": hub.browser_event_count,
            "last_event_at": hub.browser_last_event_at or None}


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

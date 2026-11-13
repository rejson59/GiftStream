"""GiftStream — konektor TikTok Live.

Tryby:
  1. "tiktok"    — nieoficjalna biblioteka TikTokLive (isaackogan/TikTokLive).
                   Darmowa, łączy się po @username. Wymaga: pip install TikTokLive
  2. "simulator" — generuje fałszywe eventy (prezenty, lajki, komentarze).
                   Do testów bez TikToka i na produkcji jako fallback.
  3. "managed"   — adapter pod płatne API (TikTool / EulerStream).
                   Wypełnij klucze w .env — szkielet gotowy, patrz docs/TIKTOK.md.

Wszystkie tryby emitują znormalizowane TikTokEvent -> Engine -> gra.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import threading
import time
from collections.abc import Awaitable, Callable

from .models import GIFT_CATALOG, TikTokEvent
from . import diagnostics

OnEvent = Callable[[TikTokEvent], Awaitable[None]]

SIM_USERS = ["fan_kasia", "gamer_marek", "ola_live", "tomek_gra", "zuzia_tt",
             "piotr_stream", "maja_pl", "kuba_plays", "ania_watch", "dawid_live"]
SIM_COMMENTS = ["GG!", "boss!!", "dawaj!", "lecz się", "skacz w lewo", "heal pls",
                "to jest super", "jeszcze jeden!", "OMG", "🔥🔥🔥", "boss", "pomocy"]


def _is_signing_rate_limit(exc: Exception) -> bool:
    """Whether TikTokLive's upstream signing service explicitly rate-limited us."""
    return (type(exc).__name__ == "SignatureRateLimitError"
            or "rate_limit_account_hour" in str(exc).casefold())


def _is_user_offline(exc: BaseException) -> bool:
    """TikTokLive uses this expected signal when the creator is not LIVE."""
    return type(exc).__name__ == "UserOfflineError"


def _retry_delay(attempt: int, *, user_offline: bool = False) -> float:
    """Back off further for an offline room, without polling it every few seconds."""
    if user_offline:
        return min(300.0, 120.0 * max(attempt, 1)) + random.uniform(0.0, 20.0)
    delay = min(60.0, float(2 ** min(attempt, 6)))
    return delay + random.uniform(0.0, min(5.0, delay / 4))


async def _disconnect_tiktok_client(client, close_http: bool = False) -> None:  # noqa: ANN001
    """Disconnect on the client's loop, safely draining its task without nested loop runners."""
    websocket = getattr(client, "_ws", None)
    if websocket is not None:
        await websocket.disconnect()
    event_task = getattr(client, "_event_loop_task", None)
    if event_task is not None:
        await asyncio.gather(event_task, return_exceptions=True)
        client._event_loop_task = None
    video = getattr(getattr(client, "_web", None), "fetch_video_data", None)
    if video is not None and getattr(video, "is_recording", False):
        video.stop()
    for name in ("_room_id", "_room_info", "_gift_info"):
        if hasattr(client, name):
            setattr(client, name, None)
    if close_http:
        web_client = getattr(client, "_web", None)
        close = getattr(web_client, "close", None)
        if close is not None:
            await close()


class TikTokConnector:
    def __init__(self, on_event: OnEvent):
        self.on_event = on_event
        self.mode = "simulator"
        self.username = ""
        self.connected = False
        self._task: asyncio.Task | None = None
        self._thread: threading.Thread | None = None
        self._stop = asyncio.Event()
        self._tt_stop = threading.Event()
        self.connection_state = "disconnected"
        self.last_error = ""
        self.retry_attempt = 0
        self.retry_in = 0.0

    # ------------------------------------------------------------------
    async def start(self, mode: str, username: str = "") -> dict:
        normalized_username = username.strip().lstrip("@").strip()
        # Avoid a button click restarting an already connected/retrying client.
        if (mode == "tiktok" and self.mode == mode and self.username.casefold() == normalized_username.casefold()
                and self._thread is not None and self._thread.is_alive() and not self._tt_stop.is_set()):
            return {"ok": True, "mode": mode, "message": f"Połączenie z @{self.username} już działa lub ponawia próbę.", **self.status()}
        await self.stop()
        if self._thread is not None and self._thread.is_alive():
            return {"ok": False, "message": "Poprzednia sesja TikTokLive nadal się zamyka. Poczekaj chwilę i sprawdź logi."}
        self.mode = mode
        self.username = normalized_username
        self._stop = asyncio.Event()
        self._tt_stop = threading.Event()
        self._tt_connect_task = None
        self._tt_ws_task = None
        self.last_error = ""
        self.retry_attempt = 0
        self.retry_in = 0.0
        if mode == "simulator":
            self._task = asyncio.create_task(self._simulator_loop())
            self.connected = True
            self.connection_state = "connected"
            diagnostics.info("Symulator zdarzeń został uruchomiony.")
            return {"ok": True, "mode": mode, "message": "Symulator uruchomiony"}
        if mode == "tiktok":
            if not self.username or not re.fullmatch(r"[A-Za-z0-9._]{2,24}", self.username):
                self.connection_state = "error"
                self.last_error = "Podaj poprawny @username TikTok LIVE (bez spacji)."
                diagnostics.warning(self.last_error)
                return {"ok": False, "message": self.last_error, **self.status()}
            return await self._start_tiktoklive()
        if mode == "managed":
            return await self._start_managed()
        self.connection_state = "error"
        self.last_error = f"Nieznany tryb: {mode}"
        diagnostics.error(self.last_error)
        return {"ok": False, "message": self.last_error}

    async def stop(self) -> None:
        was_active = self.connected or self.connection_state not in {"disconnected", "error"}
        self.connected = False
        self.connection_state = "stopping" if self._thread and self._thread.is_alive() else "disconnected"
        self._stop.set()
        self._tt_stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

        client = getattr(self, "_tt_client", None)
        thread = self._thread
        loop = getattr(client, "_owned_asyncio_loop", None) if client is not None else None
        connect_task = getattr(self, "_tt_connect_task", None)
        websocket_task = getattr(self, "_tt_ws_task", None)
        # The worker owns TikTokLive's loop. Disconnect a running websocket or
        # cancel an in-progress HTTP/start request; never nest run_until_complete.
        if loop is not None and not loop.is_closed() and loop.is_running():
            try:
                if websocket_task is not None:
                    future = asyncio.run_coroutine_threadsafe(
                        _disconnect_tiktok_client(client, close_http=False), loop)
                    await asyncio.wait_for(asyncio.wrap_future(future), timeout=8)
                elif connect_task is not None:
                    loop.call_soon_threadsafe(connect_task.cancel)
            except Exception as exc:
                diagnostics.warning("Nie udało się zatrzymać zadania TikTokLive: %s", exc)
        if thread is not None and thread.is_alive():
            await asyncio.to_thread(thread.join, 8)
        elif client is not None and loop is not None and not loop.is_closed() and not loop.is_running():
            # A client without a live worker can be safely cleaned up here.
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(loop.run_until_complete, _disconnect_tiktok_client(client, True)),
                    timeout=8,
                )
                loop.close()
            except Exception as exc:
                diagnostics.warning("Zamykanie TikTokLive zakończyło się z błędem: %s", exc)
        if thread is None or not thread.is_alive():
            self._thread = None
            self._tt_client = None
            self._tt_connect_task = None
            self.connection_state = "disconnected"
            self.retry_in = 0.0
            if was_active:
                diagnostics.info("Połączenie TikTok LIVE zostało zatrzymane przez użytkownika.")
        else:
            self.connection_state = "stopping"
            diagnostics.warning("TikTokLive nadal zamyka połączenie; nie uruchamiam drugiej sesji równolegle.")

    def status(self) -> dict:
        retry_in = max(0, round(self.retry_in - time.monotonic())) if self.retry_in else 0
        return {"mode": self.mode, "username": self.username, "connected": self.connected,
                "state": self.connection_state, "last_error": self.last_error,
                "retry_attempt": self.retry_attempt, "retry_in": retry_in}

    # ------------------------------------------------------------------
    # Symulator
    # ------------------------------------------------------------------
    async def _simulator_loop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(random.uniform(1.5, 4.5))
            if self._stop.is_set():
                break
            roll = random.random()
            user = random.choice(SIM_USERS)
            if roll < 0.45:
                gift = random.choice(GIFT_CATALOG)
                ev = TikTokEvent(type="gift", user=user, nickname=user,
                                 gift_name=gift["name"], gift_id=gift["id"],
                                 diamonds=gift["diamonds"], source="simulator")
            elif roll < 0.70:
                ev = TikTokEvent(type="like", user=user, nickname=user,
                                 like_count=random.randint(1, 10), source="simulator")
            elif roll < 0.85:
                ev = TikTokEvent(type="comment", user=user, nickname=user,
                                 comment=random.choice(SIM_COMMENTS), source="simulator")
            elif roll < 0.93:
                ev = TikTokEvent(type="follow", user=user, nickname=user, source="simulator")
            else:
                ev = TikTokEvent(type="join", user=user, nickname=user, source="simulator")
            await self.on_event(ev)

    async def simulate_once(self, kind: str = "gift") -> TikTokEvent:
        """Ręczny test: jeden event na żądanie (przyciski w dashboardzie)."""
        user = random.choice(SIM_USERS)
        if kind == "gift":
            gift = random.choice(GIFT_CATALOG)
            ev = TikTokEvent(type="gift", user=user, nickname=user, gift_name=gift["name"],
                             gift_id=gift["id"], diamonds=gift["diamonds"], source="test")
        elif kind == "like":
            ev = TikTokEvent(type="like", user=user, nickname=user, like_count=10, source="test")
        elif kind == "follow":
            ev = TikTokEvent(type="follow", user=user, nickname=user, source="test")
        else:
            ev = TikTokEvent(type="comment", user=user, nickname=user,
                             comment=random.choice(SIM_COMMENTS), source="test")
        await self.on_event(ev)
        return ev

    # ------------------------------------------------------------------
    # TikTokLive (nieoficjalna biblioteka)
    # ------------------------------------------------------------------
    async def _start_tiktoklive(self) -> dict:
        if not self.username:
            return {"ok": False, "message": "Podaj @username streamera"}
        try:
            from TikTokLive import TikTokLiveClient  # type: ignore
            from TikTokLive.events import (  # type: ignore
                CommentEvent, ConnectEvent, DisconnectEvent, FollowEvent,
                GiftEvent, JoinEvent, LikeEvent, RoomUserSeqEvent, ShareEvent,
                SubNotifyEvent,
            )
        except ImportError as exc:
            self.connection_state = "error"
            self.last_error = "Brak biblioteki TikTokLive w tej instalacji."
            diagnostics.error("Nie można połączyć z TikTok LIVE: biblioteka TikTokLive nie jest zainstalowana.", exc_info=exc)
            return {"ok": False,
                    "message": "Brak biblioteki TikTokLive. Zaktualizuj GiftStream albo zainstaluj TikTokLive."}

        diagnostics.attach_logger("TikTokLive")
        client = TikTokLiveClient(unique_id=self.username)
        self._tt_client = client
        self.connection_state = "connecting"
        diagnostics.info("Rozpoczynam połączenie TikTok LIVE z @%s.", self.username)
        loop = asyncio.get_running_loop()

        def emit(ev: TikTokEvent) -> None:
            if loop.is_closed():
                return
            future = asyncio.run_coroutine_threadsafe(self.on_event(ev), loop)
            def report_result(done):
                try:
                    exc = done.exception()
                    if exc:
                        diagnostics.error("Błąd przetwarzania zdarzenia TikTok LIVE: %s", exc, exc_info=exc)
                except Exception:
                    pass
            future.add_done_callback(report_result)

        @client.on(ConnectEvent)
        async def _on_connect(event):  # noqa: ANN001
            self.connected = True
            self.connection_state = "connected"
            self.retry_attempt = 0
            self.retry_in = 0.0
            self.last_error = ""
            diagnostics.info("Połączono z TikTok LIVE: @%s.", self.username)
            # TikTokLive pobiera katalog przy fetch_gift_info=True przed startem streamu.
            try:
                from .gifts import record_metadata
                catalog = client.gift_info or {}
                entries = catalog.get("gifts", []) if isinstance(catalog, dict) else []
                if isinstance(entries, dict):
                    entries = entries.values()
                for entry in entries:
                    record_metadata(entry)
            except Exception:
                pass

        @client.on(DisconnectEvent)
        async def _on_disconnect(event):  # noqa: ANN001
            self.connected = False
            if not self._tt_stop.is_set():
                self.connection_state = "reconnecting"
                diagnostics.warning("TikTok LIVE rozłączył websocket; konektor podejmie ponowną próbę.")

        @client.on(GiftEvent)
        async def _on_gift(event):  # noqa: ANN001
            gift = getattr(event, "gift", None)
            if gift is None:
                return
            streaking = getattr(event, "streaking", False)
            image = getattr(gift, "image", None) or getattr(gift, "icon", None)
            image_urls = getattr(image, "url_list", None) or []
            image_url = next((u for u in image_urls if isinstance(u, str) and u.startswith("https://")), None)
            try:
                from .gifts import record_metadata
                record_metadata(gift)
            except Exception:
                pass
            emit(TikTokEvent(
                type="gift",
                user=getattr(event.user, "unique_id", "unknown"),
                nickname=getattr(event.user, "nickname", ""),
                gift_name=getattr(gift, "name", None),
                gift_id=getattr(gift, "id", None),
                gift_image_url=image_url,
                diamonds=getattr(gift, "diamond_count", 0) or 0,
                repeat_count=getattr(event, "repeat_count", 1) or 1,
                repeat_end=not streaking,
                source="tiktok",
            ))

        @client.on(CommentEvent)
        async def _on_comment(event):  # noqa: ANN001
            emit(TikTokEvent(type="comment",
                             user=getattr(event.user, "unique_id", "unknown"),
                             nickname=getattr(event.user, "nickname", ""),
                             comment=getattr(event, "comment", ""), source="tiktok"))

        @client.on(LikeEvent)
        async def _on_like(event):  # noqa: ANN001
            emit(TikTokEvent(type="like",
                             user=getattr(event.user, "unique_id", "unknown"),
                             nickname=getattr(event.user, "nickname", ""),
                             like_count=getattr(event, "count", 1) or 1,
                             total_likes=getattr(event, "total", 0) or 0, source="tiktok"))

        @client.on(FollowEvent)
        async def _on_follow(event):  # noqa: ANN001
            emit(TikTokEvent(type="follow",
                             user=getattr(event.user, "unique_id", "unknown"),
                             nickname=getattr(event.user, "nickname", ""), source="tiktok"))

        @client.on(JoinEvent)
        async def _on_join(event):  # noqa: ANN001
            user = getattr(event, "user", None)
            emit(TikTokEvent(type="join",
                             user=getattr(user, "unique_id", "unknown"),
                             nickname=getattr(user, "nickname", ""), source="tiktok"))

        @client.on(ShareEvent)
        async def _on_share(event):  # noqa: ANN001
            user = getattr(event, "user", None)
            emit(TikTokEvent(type="share",
                             user=getattr(user, "unique_id", "unknown"),
                             nickname=getattr(user, "nickname", ""), source="tiktok"))

        @client.on(SubNotifyEvent)
        async def _on_subscribe(event):  # noqa: ANN001
            user = getattr(event, "user", None)
            emit(TikTokEvent(type="subscribe",
                             user=getattr(user, "unique_id", "unknown"),
                             nickname=getattr(user, "nickname", ""), source="tiktok"))

        @client.on(RoomUserSeqEvent)
        async def _on_viewers(event):  # noqa: ANN001
            emit(TikTokEvent(type="join", user="system", nickname="",
                             viewer_count=getattr(event, "viewer_count", 0) or 0, source="tiktok"))

        def _run() -> None:
            # Keep TikTokLive's asyncio loop owned by this worker thread. Calling
            # client.run() hides its connect task, so drive start() explicitly to
            # let Stop cancel it safely without nested run_until_complete calls.
            owned_loop = client._asyncio_loop
            while not self._tt_stop.is_set():
                self.connected = False
                self.connection_state = "connecting" if self.retry_attempt == 0 else "reconnecting"
                self.last_error = ""
                self.retry_in = 0.0
                rate_limited = False
                user_offline = False

                async def _connect_once():
                    if self._tt_stop.is_set():
                        return
                    self._tt_connect_task = asyncio.current_task()
                    if self._tt_stop.is_set():
                        return
                    try:
                        task = await client.start(fetch_gift_info=True, fetch_live_check=True)
                        self._tt_ws_task = task
                        await task
                    finally:
                        self._tt_connect_task = None
                        self._tt_ws_task = None

                try:
                    owned_loop.run_until_complete(_connect_once())
                    if not self._tt_stop.is_set():
                        raise ConnectionError("TikTokLive zakończył pętlę websocket bez rozłączenia użytkownika.")
                except asyncio.CancelledError:
                    self.connected = False
                    if not self._tt_stop.is_set():
                        self.last_error = "Zadanie połączenia TikTok LIVE zostało nieoczekiwanie anulowane."
                        self.connection_state = "reconnecting"
                        diagnostics.warning(self.last_error)
                except Exception as exc:
                    self.connected = False
                    if _is_user_offline(exc) and not self._tt_stop.is_set():
                        # Offline is a normal LIVE state, not a connection crash.
                        # Recheck less often and do not emit repeated tracebacks.
                        user_offline = True
                        self.connection_state = "offline"
                        self.last_error = (
                            f"Kanał @{self.username} jest obecnie offline. GiftStream będzie "
                            "automatycznie sprawdzać transmisję co 2–5 minut."
                        )
                        diagnostics.warning("TikTok LIVE potwierdził, że @%s jest offline; ponowię sprawdzenie później.",
                                            self.username)
                    elif not self._tt_stop.is_set() and _is_signing_rate_limit(exc):
                        # This is an account-level signing quota, not a transient
                        # websocket failure. Reconnecting immediately only repeats
                        # the rejected request and can consume more quota.
                        rate_limited = True
                        self.last_error = (
                            "Serwer podpisujący EulerStream odrzucił połączenie z powodu limitu "
                            "połączeń na godzinę (rate_limit_account_hour). Automatyczne próby "
                            "wstrzymano. Skonfiguruj SIGN_API_KEY z EulerStream albo spróbuj "
                            "ponownie po odnowieniu limitu."
                        )
                        self.connection_state = "error"
                        self.retry_in = 0.0
                        diagnostics.error("%s Szczegóły odpowiedzi: %s", self.last_error, exc)
                    elif not self._tt_stop.is_set():
                        self.last_error = f"{type(exc).__name__}: {exc}"
                        self.connection_state = "reconnecting"
                        diagnostics.error("Połączenie TikTok LIVE nie powiodło się: %s", self.last_error, exc_info=exc)
                finally:
                    self._tt_connect_task = None
                    if not owned_loop.is_closed() and not owned_loop.is_running():
                        try:
                            owned_loop.run_until_complete(_disconnect_tiktok_client(client, close_http=False))
                        except Exception as cleanup_error:
                            if not self._tt_stop.is_set():
                                diagnostics.warning("Sprzątanie sesji TikTokLive: %s", cleanup_error)
                if self._tt_stop.is_set() or rate_limited:
                    break
                self.retry_attempt += 1
                delay = _retry_delay(self.retry_attempt, user_offline=user_offline)
                self.retry_in = time.monotonic() + delay
                if user_offline:
                    self.connection_state = "offline"
                    diagnostics.info("Następne sprawdzenie statusu LIVE za około %s s.", round(delay))
                else:
                    self.connection_state = "reconnecting"
                    diagnostics.warning("Ponowna próba TikTok LIVE nr %s za około %s s.",
                                        self.retry_attempt, round(delay))
                self._tt_stop.wait(delay)
            self.connected = False
            if self.connection_state not in {"error", "offline"}:
                self.connection_state = "disconnected"
            self.retry_in = 0.0
            if not owned_loop.is_closed() and not owned_loop.is_running():
                try:
                    owned_loop.run_until_complete(_disconnect_tiktok_client(client, close_http=True))
                except Exception as cleanup_error:
                    diagnostics.warning("Końcowe zamykanie sesji TikTokLive: %s", cleanup_error)
                finally:
                    owned_loop.close()
            diagnostics.info("Zakończono wątek TikTokLive dla @%s.", self.username)

        self.connection_state = "connecting"
        self._thread = threading.Thread(target=_run, name="GiftStream-TikTokLive", daemon=True)
        self._thread.start()
        return {"ok": True, "mode": "tiktok",
                "message": f"Łączenie z @{self.username}. Bieżący stan i błędy są widoczne w logach."}

    # ------------------------------------------------------------------
    # Managed API (TikTool / EulerStream) — adapter
    # ------------------------------------------------------------------
    async def _start_managed(self) -> dict:
        """Płatne API: TikTool WebSocket (wss://api.tik.tools).

        Wymaga klucza w .env: TIKTOOL_API_KEY. Jeśli klucz jest, łączymy
        się przez WebSocket i mapujemy eventy na TikTokEvent.
        Bez klucza zwracamy instrukcję (fallback: symulator).
        """
        api_key = os.getenv("TIKTOOL_API_KEY", "")
        if not api_key:
            self.connection_state = "error"
            self.last_error = "Brak TIKTOOL_API_KEY w .env."
            diagnostics.warning(self.last_error)
            return {"ok": False,
                    "message": "Brak TIKTOOL_API_KEY w .env. Ustaw klucz albo użyj trybu "
                               "'tiktok' (TikTokLive) / 'simulator'."}
        if not self.username:
            return {"ok": False, "message": "Podaj @username streamera"}
        try:
            import websockets  # type: ignore
        except ImportError as exc:
            self.connection_state = "error"
            self.last_error = "Brak pakietu websockets."
            diagnostics.error(self.last_error, exc_info=exc)
            return {"ok": False, "message": "Brak pakietu websockets"}
        self._task = asyncio.create_task(self._managed_loop(api_key))
        self.connected = True
        self.connection_state = "connected"
        diagnostics.info("Uruchomiono zewnętrzne API dla @%s.", self.username)
        return {"ok": True, "mode": "managed", "message": f"Managed API: @{self.username}"}

    async def _managed_loop(self, api_key: str) -> None:
        import json
        import websockets  # type: ignore

        uri = f"wss://api.tik.tools?uniqueId={self.username}&apiKey={api_key}"
        async with websockets.connect(uri) as ws:
            async for raw in ws:
                if self._stop.is_set():
                    break
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                data = msg.get("data", msg)
                kind = msg.get("event", "")
                user = (data.get("user") or {}).get("uniqueId", "unknown")
                if kind == "gift":
                    ev = TikTokEvent(type="gift", user=user,
                                     gift_name=data.get("giftName"),
                                     gift_id=data.get("giftId"),
                                     gift_image_url=data.get("giftPictureUrl") or data.get("imageUrl"),
                                     diamonds=data.get("diamondCount", 0) or 0,
                                     repeat_count=data.get("repeatCount", 1) or 1,
                                     repeat_end=data.get("repeatEnd", 1) == 1,
                                     source="tiktok")
                elif kind == "chat":
                    ev = TikTokEvent(type="comment", user=user,
                                     comment=data.get("comment", ""), source="tiktok")
                elif kind == "like":
                    ev = TikTokEvent(type="like", user=user,
                                     like_count=data.get("likeCount", 1) or 1,
                                     total_likes=data.get("totalLikes", 0) or 0, source="tiktok")
                elif kind in ("follow", "social"):
                    ev = TikTokEvent(type="follow", user=user, source="tiktok")
                elif kind == "roomUserSeq":
                    ev = TikTokEvent(type="join", user="system",
                                     viewer_count=data.get("viewerCount", 0) or 0, source="tiktok")
                else:
                    continue
                await self.on_event(ev)

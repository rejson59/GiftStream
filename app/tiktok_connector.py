"""TipStream — konektor TikTok Live.

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
import os
import random
import threading
from collections.abc import Awaitable, Callable

from .models import GIFT_CATALOG, TikTokEvent

OnEvent = Callable[[TikTokEvent], Awaitable[None]]

SIM_USERS = ["fan_kasia", "gamer_marek", "ola_live", "tomek_gra", "zuzia_tt",
             "piotr_stream", "maja_pl", "kuba_plays", "ania_watch", "dawid_live"]
SIM_COMMENTS = ["GG!", "boss!!", "dawaj!", "lecz się", "skacz w lewo", "heal pls",
                "to jest super", "jeszcze jeden!", "OMG", "🔥🔥🔥", "boss", "pomocy"]


class TikTokConnector:
    def __init__(self, on_event: OnEvent):
        self.on_event = on_event
        self.mode = "simulator"
        self.username = ""
        self.connected = False
        self._task: asyncio.Task | None = None
        self._thread: threading.Thread | None = None
        self._stop = asyncio.Event()

    # ------------------------------------------------------------------
    async def start(self, mode: str, username: str = "") -> dict:
        await self.stop()
        self.mode = mode
        self.username = username.lstrip("@")
        self._stop = asyncio.Event()
        if mode == "simulator":
            self._task = asyncio.create_task(self._simulator_loop())
            self.connected = True
            return {"ok": True, "mode": mode, "message": "Symulator uruchomiony"}
        if mode == "tiktok":
            return await self._start_tiktoklive()
        if mode == "managed":
            return await self._start_managed()
        return {"ok": False, "message": f"Nieznany tryb: {mode}"}

    async def stop(self) -> None:
        self.connected = False
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # TikTokLive działa w wątku — odłączamy przez flagę (best-effort)
        client = getattr(self, "_tt_client", None)
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass
            self._tt_client = None

    def status(self) -> dict:
        return {"mode": self.mode, "username": self.username, "connected": self.connected}

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
                GiftEvent, LikeEvent, RoomUserSeqEvent,
            )
        except ImportError:
            return {"ok": False,
                    "message": "Brak biblioteki TikTokLive. Zainstaluj: pip install TikTokLive"}

        client = TikTokLiveClient(unique_id=f"@{self.username}")
        self._tt_client = client
        loop = asyncio.get_running_loop()

        def emit(ev: TikTokEvent) -> None:
            asyncio.run_coroutine_threadsafe(self.on_event(ev), loop)

        @client.on(ConnectEvent)
        async def _on_connect(event):  # noqa: ANN001
            self.connected = True
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

        @client.on(RoomUserSeqEvent)
        async def _on_viewers(event):  # noqa: ANN001
            emit(TikTokEvent(type="join", user="system", nickname="",
                             viewer_count=getattr(event, "viewer_count", 0) or 0, source="tiktok"))

        def _run() -> None:
            try:
                client.run(fetch_gift_info=True)
            except Exception:
                self.connected = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        # Daj chwili na połączenie
        await asyncio.sleep(1.0)
        return {"ok": True, "mode": "tiktok",
                "message": f"Łączenie z @{self.username}… (sprawdź status)"}

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
            return {"ok": False,
                    "message": "Brak TIKTOOL_API_KEY w .env. Ustaw klucz albo użyj trybu "
                               "'tiktok' (TikTokLive) / 'simulator'."}
        if not self.username:
            return {"ok": False, "message": "Podaj @username streamera"}
        try:
            import websockets  # type: ignore
        except ImportError:
            return {"ok": False, "message": "Brak pakietu websockets"}
        self._task = asyncio.create_task(self._managed_loop(api_key))
        self.connected = True
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

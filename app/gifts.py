"""Lokalna biblioteka giftów: przykładowe wpisy + metadane z LIVE.

Oryginalne grafiki nie są kopiowane ani hostowane przez GiftStream. Gdy
TikTokLive zwróci adres CDN grafiki prezentu, zapisujemy adres źródłowy,
aby można go użyć na nakładce OBS.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import GIFT_CATALOG, TikTokEvent
from .paths import data_dir

CACHE_PATH = data_dir() / "gift_catalog.json"
LABEL_PL = {"Rose":"Róża", "Rosa":"Róża", "Dragon":"Smok", "Lion":"Lew",
            "Doughnut":"Donut", "Donut":"Donut", "Ice Cream":"Lody",
            "Finger Heart":"Serduszko z palców", "Sunglasses":"Okulary",
            "Money Gun":"Pistolet na pieniądze", "TikTok Universe":"Wszechświat TikToka"}

# First entries are familiar, frequently used gifts. The rest of the 100-card
# showcase is filled from TikTok's current public catalog, favoring accessible gifts.
POPULAR_GIFT_NAMES = (
    "rose", "tiktok", "finger heart", "donut", "doughnut", "ice cream", "gg", "perfume",
    "heart me", "love you", "cap", "sunglasses", "paper crane", "hand hearts",
    "galaxy", "lion", "universe", "money gun", "swan", "fireworks", "dragon",
)
POPULAR_GIFT_LIMIT = 100


def label_pl(name: str) -> str:
    return LABEL_PL.get(name, name)


def _load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        cache = {str(x.get("id")): x for x in data if isinstance(x, dict) and x.get("id") is not None}
        # Older releases filled viewer Coins from creator diamonds. Keep only explicit
        # coin prices; invalidate stale estimated values as unknown, never as 0 Coins.
        for gift in cache.values():
            try:
                coins = int(gift.get("coins", 0) or 0)
            except (TypeError, ValueError):
                coins = 0
            if gift.get("coins_estimated") is not False or coins <= 0:
                gift["coins"] = 0
                gift["coins_estimated"] = True
            else:
                gift["coins"] = coins
        return cache
    except (OSError, ValueError, TypeError):
        return {}


_seen = _load_cache()
_cache_lock = threading.RLock()
_refresh_lock = threading.Lock()


def _save() -> None:
    try:
        CACHE_PATH.write_text(json.dumps(list(_seen.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _safe_tiktok_image(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value)
        host = parsed.hostname or ""
        if parsed.scheme == "https" and (host.endswith(".tiktokcdn.com") or host.endswith(".tiktokcdn-us.com") or host.endswith(".tiktokcdn-eu.com")):
            return value
    except Exception:
        pass
    return None


def record_event(event: TikTokEvent) -> None:
    if event.type != "gift" or not event.gift_name:
        return
    key = str(event.gift_id) if event.gift_id is not None else f"name:{event.gift_name.casefold()}"
    with _cache_lock:
        old = _seen.get(key, {})
        entry = {**old,
                 "id": event.gift_id,
                 "name": event.gift_name,
                 "label_pl": label_pl(event.gift_name),
                 "diamonds": event.diamonds or old.get("diamonds", 0),
                 "coins": (event.gift_coins if event.gift_coins > 0 and not event.gift_coins_estimated
                           else old.get("coins", 0) if old.get("coins_estimated") is False else 0),
                 "coins_estimated": (False if event.gift_coins > 0 and not event.gift_coins_estimated
                                     else old.get("coins_estimated") is not False),
                 "image_url": _safe_tiktok_image(event.gift_image_url) or old.get("image_url"),
                 "source": "tiktok-live" if event.source in {"tiktok", "managed"} else event.source,
                 "streakable": old.get("streakable", False)}
        _seen[key] = entry
        _save()


def record_metadata(gift: Any, source: str = "tiktok-live", save: bool = True) -> None:
    """Cache metadata from TikTokLive's protobuf objects or gift-list dictionaries."""
    if gift is None:
        return

    def field(obj: Any, *names: str, default: Any = None) -> Any:
        for name in names:
            value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
            if value is not None:
                return value
        return default

    gift_id = field(gift, "id", "gift_id")
    name = field(gift, "name", "gift_name")
    if not name:
        return
    img = field(gift, "image", "icon")
    urls = field(img, "url_list", "urlList", default=[]) or []
    image_url = next((safe for u in urls if isinstance(u, str) if (safe := _safe_tiktok_image(u))), None)
    try:
        diamonds = int(field(gift, "diamond_count", "diamondCount", "diamond_count_value", default=0) or 0)
    except (TypeError, ValueError):
        diamonds = 0
    explicit_coins = field(gift, "coin_count", "coinCount", "coins")
    try:
        coins = max(0, int(explicit_coins)) if explicit_coins is not None else 0
    except (TypeError, ValueError):
        coins = 0
        explicit_coins = None
    coins_estimated = explicit_coins is None or coins <= 0
    if coins_estimated:
        coins = 0
    try:
        gift_type = field(gift, "type", default=0)
        streakable = bool(field(gift, "streakable", default=gift_type == 1))
    except Exception:
        streakable = False
    key = str(gift_id) if gift_id is not None else f"name:{str(name).casefold()}"
    with _cache_lock:
        previous = _seen.get(key, {})
        _seen[key] = {"id": gift_id, "name": str(name), "label_pl": label_pl(str(name)),
                      "diamonds": diamonds, "coins": coins, "coins_estimated": coins_estimated,
                      "image_url": image_url or previous.get("image_url"),
                      "source": source, "streakable": streakable}
        if save:
            _save()


def _popular_rank(gift: Any) -> tuple[int, int, str]:
    name = str(gift.get("name", "")).casefold()
    rank = next((i for i, candidate in enumerate(POPULAR_GIFT_NAMES) if candidate in name), len(POPULAR_GIFT_NAMES))
    try:
        coins = int(gift.get("coins", 0) or 0)
    except (TypeError, ValueError):
        coins = 0
    # Unknown prices sort after explicitly priced gifts within the same rank.
    return rank, coins if coins > 0 and gift.get("coins_estimated") is False else 2**31, name


def record_catalog(entries: Any) -> int:
    """Cache up to 100 current TikTok gifts that include verified CDN artwork."""
    if isinstance(entries, dict):
        entries = entries.get("gifts", [])
    if not isinstance(entries, (list, tuple)):
        return 0
    candidates: list[tuple[tuple[int, int, str], Any]] = []
    for gift in entries:
        if not isinstance(gift, dict):
            continue
        image = gift.get("image") or gift.get("icon") or {}
        urls = image.get("url_list", image.get("urlList", [])) if isinstance(image, dict) else []
        if not any(_safe_tiktok_image(url) for url in urls if isinstance(url, str)):
            continue
        name = gift.get("name") or gift.get("gift_name")
        if not name:
            continue
        try:
            diamonds = int(gift.get("diamond_count", gift.get("diamondCount", 0)) or 0)
        except (TypeError, ValueError):
            diamonds = 0
        candidates.append(((0, diamonds, str(name).casefold()), gift))
    # Put known crowd favorites first, then fill with lower-price catalog entries.
    candidates.sort(key=lambda pair: _popular_rank({"name": pair[1].get("name", ""),
                                                    "diamonds": pair[1].get("diamond_count", 0)}))
    selected = candidates[:POPULAR_GIFT_LIMIT]
    if not selected:
        return 0
    with _cache_lock:
        for key in [key for key, value in _seen.items() if value.get("source") == "tiktok-catalog"]:
            _seen.pop(key, None)
        for _rank, gift in selected:
            record_metadata(gift, source="tiktok-catalog", save=False)
        _save()
    return len(selected)


def refresh_tiktok_catalog() -> int:
    """Fetch TikTok's public gift list (no room connection or credentials needed)."""
    import asyncio
    from TikTokLive import TikTokLiveClient  # type: ignore

    async def fetch() -> int:
        client = TikTokLiveClient(unique_id="@giftstream_catalog")
        try:
            result = await client.web.fetch_gift_list()
            return record_catalog(result)
        finally:
            close = getattr(client.web, "close", None)
            if close is not None:
                await close()

    with _refresh_lock:
        return asyncio.run(fetch())


def coin_price_for_gift(gift_id: int | None, gift_name: str | None) -> tuple[int, bool]:
    """Return cached viewer coin cost and whether that cost is an estimate.

    Never substitute creator diamonds for viewer coins: price gates can require only
    values explicitly supplied as coin_count/coinCount/coins by catalog metadata.
    """
    entries = list_gifts()
    match = next((gift for gift in entries if gift_id is not None and str(gift.get("id")) == str(gift_id)), None)
    if match is None and gift_name:
        match = next((gift for gift in entries if str(gift.get("name", "")).casefold() == gift_name.casefold()), None)
    if match is None:
        return 0, True
    try:
        coins = max(0, int(match.get("coins", 0) or 0))
    except (TypeError, ValueError):
        return 0, True
    return coins, bool(match.get("coins_estimated", True))


def list_gifts(query: str = "", sort: str = "price_asc") -> list[dict[str, Any]]:
    """Combine gift sources and sort by TikTok gift prominence or viewer coin cost."""
    merged: dict[str, dict[str, Any]] = {}
    with _cache_lock:
        seen = {key: dict(gift) for key, gift in _seen.items()}
    has_real_catalog = sum(1 for gift in seen.values() if gift.get("source") == "tiktok-catalog" and gift.get("image_url")) >= 80
    if not has_real_catalog:
        for gift in GIFT_CATALOG:
            merged[f"name:{gift['name'].casefold()}"] = dict(gift)
    for key, gift in seen.items():
        gift = {**gift, "label_pl": label_pl(str(gift.get("name", "")))}
        merged[key] = dict(gift)
        # Same name variant/sample should pick up latest real ID, image and price.
        name_key = f"name:{str(gift.get('name', '')).casefold()}"
        if name_key in merged:
            merged.pop(name_key, None)
    entries = list(merged.values())
    for gift in entries:
        # A missing explicit viewer coin price is unknown, not an estimate from diamonds.
        try:
            coins = max(0, int(gift.get("coins", 0) or 0))
        except (TypeError, ValueError):
            coins = 0
        verified = gift.get("coins_estimated") is False and coins > 0
        gift["coins_estimated"] = not verified
        gift["coins"] = coins if verified else 0
    if query.strip():
        q = query.strip().casefold()
        entries = [g for g in entries if q in str(g.get("name", "")).casefold()
                   or q in str(g.get("label_pl", "")).casefold()]
    if sort == "popular":
        return sorted(entries, key=_popular_rank)
    if sort == "price_desc":
        return sorted(entries, key=lambda g: (g["coins"] <= 0, -g["coins"], str(g.get("name", "")).casefold()))
    return sorted(entries, key=lambda g: (g["coins"] <= 0, g["coins"], str(g.get("name", "")).casefold()))

"""Lokalna biblioteka giftów: przykładowe wpisy + metadane z LIVE.

Oryginalne grafiki nie są kopiowane ani hostowane przez TipStream. Gdy
TikTokLive zwróci adres CDN grafiki prezentu, zapisujemy adres źródłowy,
aby można go użyć na nakładce OBS.
"""
from __future__ import annotations

import json
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


def label_pl(name: str) -> str:
    return LABEL_PL.get(name, name)


def _load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return {str(x.get("id")): x for x in data if x.get("id") is not None}
    except (OSError, ValueError, TypeError):
        return {}


_seen = _load_cache()


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
    old = _seen.get(key, {})
    entry = {**old,
             "id": event.gift_id,
             "name": event.gift_name,
             "label_pl": label_pl(event.gift_name),
             "diamonds": event.diamonds or old.get("diamonds", 0),
             "image_url": _safe_tiktok_image(event.gift_image_url) or old.get("image_url"),
             "source": "tiktok-live" if event.source in {"tiktok", "managed"} else event.source,
             "streakable": old.get("streakable", False)}
    _seen[key] = entry
    _save()


def record_metadata(gift: Any) -> None:
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
    try:
        gift_type = field(gift, "type", default=0)
        streakable = bool(field(gift, "streakable", default=gift_type == 1))
    except Exception:
        streakable = False
    key = str(gift_id) if gift_id is not None else f"name:{str(name).casefold()}"
    _seen[key] = {"id": gift_id, "name": str(name), "label_pl": label_pl(str(name)),
                  "diamonds": diamonds, "image_url": image_url,
                  "source": "tiktok-live", "streakable": streakable}
    _save()


def list_gifts(query: str = "") -> list[dict[str, Any]]:
    """Combine examples with observed gift data; observed IDs win."""
    merged: dict[str, dict[str, Any]] = {}
    for gift in GIFT_CATALOG:
        merged[f"name:{gift['name'].casefold()}"] = dict(gift)
    for key, gift in _seen.items():
        gift = {**gift, "label_pl": label_pl(str(gift.get("name", "")))}
        merged[key] = dict(gift)
        # Same name variant/sample should pick up latest real ID, image and price.
        name_key = f"name:{str(gift.get('name', '')).casefold()}"
        if name_key in merged:
            merged.pop(name_key, None)
    entries = list(merged.values())
    if query.strip():
        q = query.strip().casefold()
        entries = [g for g in entries if q in str(g.get("name", "")).casefold()
                   or q in str(g.get("label_pl", "")).casefold()]
    return sorted(entries, key=lambda g: (int(g.get("diamonds") or 0), str(g.get("name", "")).casefold()))

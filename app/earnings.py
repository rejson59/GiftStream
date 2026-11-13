"""Transparent estimates of creator-side gift rewards (not TikTok payout statements)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .gifts import list_gifts
from .paths import data_dir

SETTINGS_PATH = data_dir() / "earnings_settings.json"
_DEFAULTS = {"usd_per_diamond": 0.005, "usd_to_pln": 4.0}
_lock = threading.RLock()


def get_settings() -> dict[str, float]:
    with _lock:
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            saved = {}
        result = {}
        for key, fallback in _DEFAULTS.items():
            try:
                value = float(saved.get(key, fallback))
                result[key] = value if 0 < value <= (100 if key == "usd_to_pln" else 1) else fallback
            except (TypeError, ValueError):
                result[key] = fallback
        return result


def save_settings(usd_per_diamond: float, usd_to_pln: float) -> dict[str, float]:
    settings = {"usd_per_diamond": usd_per_diamond, "usd_to_pln": usd_to_pln}
    with _lock:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return settings


def resolve_diamonds(gift_id: int | None, gift_name: str | None, diamonds: int) -> tuple[int, bool]:
    """Use event diamonds first; if missing, fall back to cached gift metadata."""
    if diamonds > 0:
        return diamonds, False
    gifts = list_gifts()
    match = next((g for g in gifts if gift_id is not None and str(g.get("id")) == str(gift_id)), None)
    if match is None and gift_name:
        match = next((g for g in gifts if str(g.get("name", "")).casefold() == gift_name.casefold()), None)
    value = int((match or {}).get("diamonds") or 0)
    return value, bool(value)


def estimate_pln(diamonds: int | float, settings: dict[str, Any] | None = None) -> float:
    rates = settings or get_settings()
    return max(0.0, float(diamonds)) * float(rates["usd_per_diamond"]) * float(rates["usd_to_pln"])

"""Transparent creator reward estimates and automatically refreshed NBP FX rates."""
from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from typing import Any

from .gifts import list_gifts
from .paths import data_dir

SETTINGS_PATH = data_dir() / "earnings_settings.json"
_NBP_USD_URL = "https://api.nbp.pl/api/exchangerates/rates/a/usd/?format=json"
_DEFAULTS: dict[str, Any] = {
    "usd_per_diamond": 0.005,
    "usd_to_pln": 4.0,
    "usd_to_pln_updated": "",
    "rate_source": "Kurs domyślny (NBP niedostępny)",
}
_lock = threading.RLock()


def _read_settings() -> dict[str, Any]:
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return {**_DEFAULTS, **saved}
    except (OSError, ValueError, TypeError):
        return dict(_DEFAULTS)


def get_settings() -> dict[str, Any]:
    with _lock:
        saved = _read_settings()
        try:
            usd_per_diamond = float(saved["usd_per_diamond"])
            if not 0 < usd_per_diamond <= 1:
                raise ValueError
        except (TypeError, ValueError):
            usd_per_diamond = float(_DEFAULTS["usd_per_diamond"])
        try:
            usd_to_pln = float(saved["usd_to_pln"])
            if not 0 < usd_to_pln <= 100:
                raise ValueError
        except (TypeError, ValueError):
            usd_to_pln = float(_DEFAULTS["usd_to_pln"])
        return {"usd_per_diamond": usd_per_diamond, "usd_to_pln": usd_to_pln,
                "usd_to_pln_updated": str(saved.get("usd_to_pln_updated") or ""),
                "rate_source": str(saved.get("rate_source") or _DEFAULTS["rate_source"])}


def _write_settings(values: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(values, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_PATH)


def save_settings(usd_per_diamond: float, usd_to_pln: float | None = None) -> dict[str, Any]:
    """Save the assumed creator USD-per-diamond rate; normally retain NBP FX."""
    with _lock:
        old = get_settings()
        if usd_to_pln is not None:  # support older local clients without breaking settings
            old["usd_to_pln"] = usd_to_pln
            old["rate_source"] = "Kurs ustawiony ręcznie"
        values = {**old, "usd_per_diamond": usd_per_diamond}
        _write_settings(values)
    return get_settings()


def refresh_usd_to_pln() -> dict[str, Any]:
    """Fetch the latest official NBP Table A USD mid-rate (network call, off the UI thread)."""
    request = urllib.request.Request(_NBP_USD_URL, headers={"Accept": "application/json", "User-Agent": "GiftStream/1"})
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rate_entry = payload["rates"][0]
    rate = float(rate_entry["mid"])
    if not 0.1 <= rate <= 20:
        raise ValueError("NBP returned an implausible USD/PLN rate")
    with _lock:
        values = {**get_settings(), "usd_to_pln": rate,
                  "usd_to_pln_updated": str(rate_entry.get("effectiveDate") or ""),
                  "rate_source": "NBP · kurs średni USD/PLN"}
        _write_settings(values)
    return get_settings()


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

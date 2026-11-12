"""Paths for GiftStream resources and user data."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "GiftStream"


def bundle_root() -> Path:
    """Directory containing resources bundled by PyInstaller or the checkout."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Persistent settings and update directory outside the one-file executable."""
    override = os.environ.get("GIFTSTREAM_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif getattr(sys, "frozen", False):
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        else:
            root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path = root / APP_NAME
    else:
        path = bundle_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def installed_release_tag() -> str:
    metadata = data_dir() / "current.json"
    try:
        value = json.loads(metadata.read_text(encoding="utf-8"))
        return str(value.get("tag", "dev"))
    except (OSError, ValueError, TypeError):
        return "dev"

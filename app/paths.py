"""Ścieżki zasobów aplikacji i lokalnych danych użytkownika."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Keep the legacy directory so existing TipStream users retain settings and update state.
APP_NAME = "TipStream"


def bundle_root() -> Path:
    """Katalog zasobów dołączonych do aplikacji (PyInstaller lub checkout)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Trwały katalog ustawień, presetów i historii, poza one-file EXE."""
    override = os.environ.get("TIPSTREAM_DATA_DIR")
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

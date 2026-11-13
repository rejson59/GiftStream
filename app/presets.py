"""Local JSON persistence for the single supported Minecraft Parkour preset."""
from __future__ import annotations

import json
from pathlib import Path

from .models import Preset
from .paths import data_dir

PRESETS_DIR = data_dir() / "presets"
PRESET_ID = "minecraft-parkour"


def _path() -> Path:
    return PRESETS_DIR / f"{PRESET_ID}.json"


def get_preset(preset_id: str) -> Preset | None:
    if preset_id != PRESET_ID:
        return None
    path = _path()
    if not path.is_file():
        return None
    try:
        return Preset(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def save_preset(preset: Preset) -> Preset:
    if preset.id != PRESET_ID:
        raise ValueError("GiftStream udostępnia wyłącznie preset Minecraft Parkour.")
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    path = _path()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(preset.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return preset

"""GiftStream — magazyn presetów (JSON na dysku + opcjonalnie Supabase).

Preset = nazwana lista reguł "gift -> akcja". Streamer może przełączać
presety w trakcie streama (jak w StreamToEarn).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .models import Preset, Rule
from .paths import data_dir

PRESETS_DIR = data_dir() / "presets"
PRESETS_DIR.mkdir(parents=True, exist_ok=True)


def _path(preset_id: str) -> Path:
    return PRESETS_DIR / f"{preset_id}.json"


def list_presets() -> list[Preset]:
    out: list[Preset] = []
    for p in sorted(PRESETS_DIR.glob("*.json")):
        try:
            out.append(Preset(**json.loads(p.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


def get_preset(preset_id: str) -> Preset | None:
    p = _path(preset_id)
    if not p.exists():
        return None
    return Preset(**json.loads(p.read_text(encoding="utf-8")))


def save_preset(preset: Preset) -> Preset:
    _path(preset.id).write_text(
        json.dumps(preset.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return preset


def delete_preset(preset_id: str) -> bool:
    p = _path(preset_id)
    if p.exists():
        p.unlink()
        return True
    return False


def duplicate_preset(preset_id: str, new_id: str, new_name: str) -> Preset | None:
    src = get_preset(preset_id)
    if src is None:
        return None
    data = src.model_dump()
    data["id"] = new_id
    data["name"] = new_name
    return save_preset(Preset(**data))


def ensure_default() -> None:
    """Tworzy preset startowy i łagodnie aktualizuje jego stare etykiety."""
    existing = get_preset("default")
    if existing is not None:
        if existing.name in {"Default — Zombie Survival", "Zombie: przetrwanie"}:
            existing.name = "Zombie: przetrwanie"
            existing.description = "Startowy zestaw reguł do testowania interakcji widzów."
            translations = {
                "Rose → Spawn zombie": "Róża → przywołaj zombie",
                "TikTok → Heal": "TikTok → ulecz gracza",
                "Donut → Drop diamond": "Donut → upuść diament",
                "Panda → Shield": "Panda → tarcza",
                "Dragon → Boss raid": "Smok → fala bossów",
                "Lion → Boss raid (interrupt)": "Lew → fala bossów (priorytet)",
                "Co 100 lajków → spawn zombie": "100 polubień → zombie",
                "Follow → heal": "Nowa obserwacja → leczenie",
                "Komentarz 'boss' → boss": "Komentarz „boss” → boss",
            }
            alerts = {
                "🌹 Rose = zombie!": "🌹 Róża — zombie nadchodzi!",
                "🎵 TikTok = heal!": "🎵 TikTok — leczenie!",
                "🍩 Donut = diamond!": "🍩 Donut — diament dla gracza!",
                "🐼 Panda = shield!": "🐼 Panda — tarcza!",
                "🐉 DRAGON = BOSS RAID!": "🐉 SMOK — NADCHODZI BOSS!",
                "🦁 LION = BOSS RAID!": "🦁 LEW — FALA BOSSÓW!",
                "❤️ Nowy follow = heal!": "❤️ Nowa obserwacja — leczenie!",
            }
            for rule in existing.rules:
                if rule.name in translations:
                    rule.name = translations[rule.name]
                if rule.alert_text in alerts:
                    rule.alert_text = alerts[rule.alert_text]
            save_preset(existing)
        return
    rules = [
        Rule(id="r1", name="Róża → przywołaj zombie", trigger={"type": "gift", "gift_name": "Rose"},
             action={"type": "spawn_zombie", "params": {"count": 1}},
             alert_text="🌹 Róża — zombie nadchodzi!"),
        Rule(id="r2", name="TikTok → ulecz gracza", trigger={"type": "gift", "gift_name": "TikTok"},
             action={"type": "heal", "params": {"amount": 20}},
             alert_text="🎵 TikTok — leczenie!"),
        Rule(id="r3", name="Donut → upuść diament", trigger={"type": "gift", "gift_name": "Donut"},
             action={"type": "drop_diamond", "params": {"count": 1}},
             alert_text="🍩 Donut — diament dla gracza!"),
        Rule(id="r4", name="Panda → tarcza", trigger={"type": "gift", "gift_name": "Panda"},
             action={"type": "shield", "params": {"duration_sec": 10}},
             alert_text="🐼 Panda — tarcza!"),
        Rule(id="r5", name="Smok → fala bossów", trigger={"type": "gift", "gift_name": "Dragon"},
             action={"type": "boss_raid", "params": {"boss": "dragon"}},
             interrupt=True, alert_text="🐉 SMOK — NADCHODZI BOSS!"),
        Rule(id="r6", name="Lew → fala bossów (priorytet)", trigger={"type": "gift", "gift_name": "Lion"},
             action={"type": "boss_raid", "params": {"boss": "lion"}},
             interrupt=True, alert_text="🦁 LEW — FALA BOSSÓW!"),
        Rule(id="r7", name="100 polubień → zombie", trigger={"type": "like", "like_threshold": 100},
             action={"type": "spawn_zombie", "params": {"count": 1}}),
        Rule(id="r8", name="Nowa obserwacja → leczenie", trigger={"type": "follow"},
             action={"type": "heal", "params": {"amount": 5}},
             alert_text="❤️ Nowa obserwacja — leczenie!"),
        Rule(id="r9", name="Komentarz „boss” → boss", trigger={"type": "comment", "keyword": "boss"},
             action={"type": "spawn_boss", "params": {"boss": "golem"}}),
    ]
    save_preset(Preset(id="default", name="Zombie: przetrwanie",
                       description="Startowy zestaw reguł do testowania interakcji widzów.",
                       rules=rules))


def now() -> float:
    return time.time()

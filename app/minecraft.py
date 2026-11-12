"""Bezpieczny adapter do serwera Minecraft przez ServerTap.

Komendy są składane wyłącznie z jawnej listy akcji. Żadne pole z czatu
ani parametr klienta nie jest wykonywany jako dowolna komenda.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

PLAYER_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def validate_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parts = urlparse(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
        raise ValueError("Podaj prawidłowy adres ServerTap zaczynający się od http:// lub https://")
    if parts.query or parts.fragment:
        raise ValueError("Adres ServerTap nie może zawierać parametrów ani fragmentu URL")
    return value


def build_commands(action: str, params: dict, player: str) -> list[str] | None:
    if not PLAYER_RE.fullmatch(player or ""):
        raise ValueError("Ustaw poprawny nick gracza Minecraft (3–16 znaków: litery, cyfry, _).")

    # Ograniczenia wartości z presetów. To nie jest interpreter komend.
    count = max(1, min(int(params.get("count", 1)), 5))
    if action in {"spawn_zombie", "spawn_enemy"}:
        entity = params.get("entity", "zombie")
        allowed = {"zombie", "skeleton", "creeper", "spider", "slime", "witch"}
        if entity not in allowed:
            entity = "zombie"
        offsets = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
        return [f"execute at {player} run summon minecraft:{entity} ~{dx if dx else ''} ~ ~{dz if dz else ''}" for dx, dz in offsets[:count]]
    if action in {"spawn_boss", "boss_raid"}:
        boss = params.get("boss", "wither")
        entity = {"wither": "wither", "dragon": "ender_dragon", "warden": "warden", "ravager": "ravager"}.get(boss, "wither")
        return [f"execute at {player} run summon minecraft:{entity} ~ ~ ~"]
    if action == "heal":
        duration = max(1, min(int(params.get("duration", 5)), 30))
        amplifier = max(0, min(int(params.get("amplifier", 1)), 4))
        return [f"effect give {player} minecraft:regeneration {duration} {amplifier} true"]
    if action == "shield":
        duration = max(1, min(int(params.get("duration_sec", 10)), 60))
        return [f"effect give {player} minecraft:resistance {duration} 1 true"]
    if action == "speed_boost":
        duration = max(1, min(int(params.get("duration_sec", 10)), 60))
        return [f"effect give {player} minecraft:speed {duration} 1 true"]
    if action == "jump":
        duration = max(1, min(int(params.get("duration_sec", 6)), 30))
        amplifier = max(0, min(int(params.get("amplifier", 1)), 3))
        return [f"effect give {player} minecraft:jump_boost {duration} {amplifier} true"]
    if action in {"drop_diamond", "drop_item", "give_item"}:
        # W MVP typ przedmiotu jest celowo ograniczony do allow-listy.
        item = params.get("item", "diamond")
        allowed_items = {"diamond", "gold_ingot", "iron_ingot", "bread", "apple", "golden_apple", "arrow", "emerald"}
        if item not in allowed_items:
            item = "diamond"
        amount = max(1, min(int(params.get("count", 1)), 64))
        return [f"give {player} minecraft:{item} {amount}"]
    if action == "change_time":
        time = params.get("time", "day")
        return [f"time set {'night' if time == 'night' else 'day'}"]
    if action == "change_weather":
        weather = params.get("weather", "clear")
        return [f"weather {'thunder' if weather == 'thunder' else 'rain' if weather == 'rain' else 'clear'}"]
    if action == "confetti":
        return [f"execute at {player} run particle minecraft:happy_villager ~ ~2 ~ 1 1 1 0.1 30 force"]
    return None


class ServerTapClient:
    def __init__(self, base_url: str = "", api_key: str = "", player: str = ""):
        self.base_url = base_url
        self.api_key = api_key
        self.player = player

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.player)

    async def check(self) -> dict:
        if not self.base_url or not self.api_key:
            return {"ok": False, "message": "Wpisz adres ServerTap i klucz API."}
        url = validate_base_url(self.base_url)
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/v1/server", headers={"key": self.api_key})
        if response.is_error:
            return {"ok": False, "message": f"ServerTap zwrócił HTTP {response.status_code}. Sprawdź adres, wtyczkę i klucz."}
        try:
            info = response.json()
        except ValueError:
            info = {}
        return {"ok": True, "message": "Połączenie z Minecraftem działa.",
                "server": {"name": info.get("name", "Minecraft"), "version": info.get("version", "")}}

    async def send(self, action: str, params: dict) -> dict:
        if not self.configured:
            return {"ok": False, "skipped": True, "message": "Minecraft ServerTap nie jest skonfigurowany."}
        commands = build_commands(action, params, self.player)
        if not commands:
            return {"ok": False, "skipped": True, "message": f"Akcja {action} nie ma jeszcze mapowania Minecraft."}
        url = validate_base_url(self.base_url)
        async with httpx.AsyncClient(timeout=5.0) as client:
            for command in commands:
                response = await client.post(f"{url}/v1/server/exec", headers={"key": self.api_key}, data={"command": command})
                if response.is_error:
                    return {"ok": False, "message": f"ServerTap zwrócił HTTP {response.status_code}.", "commands": commands}
        return {"ok": True, "message": "Akcja wysłana do Minecrafta.", "commands": commands}

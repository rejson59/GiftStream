"""Built-in ready-to-run Minecraft game modes supported by GiftStream."""
from __future__ import annotations


def _rule(rule_id: str, name: str, trigger: dict, action: dict, alert: str = "", interrupt: bool = False) -> dict:
    return {
        "id": rule_id,
        "name": name,
        "enabled": True,
        "trigger": trigger,
        "action": action,
        "alert_text": alert or name,
        "interrupt": interrupt,
        "cooldown_sec": 0,
    }


def _wow_rule(rule_id: str, name: str, trigger: dict, action: dict, alert: str,
              cooldown: float = 0, once: bool = False) -> dict:
    """Dodatkowe akcje „wow” — bez wymuszania ceny, z cooldownem, żeby nie spamować."""
    rule = _rule(rule_id, name, trigger, action, alert)
    rule["cooldown_sec"] = cooldown
    if once:
        rule["first_time_only"] = True
    return rule


GAMES = [
    {
        "id": "minecraft-parkour",
        "title": "Minecraft: parkour na żywo",
        "category": "Parkour",
        "status": "bridge",
        "integration": "GiftStream Local Minecraft",
        "icon": "🧗",
        "tagline": "100 poziomów parkour sterowanych przez widzów.",
        "description": "Gotowe akcje dla mapy 100 Levels. Push jest najtańszy (1–29 monet); awans i cofnięcie poziomu wymagają prezentu 30–999 monet; reset i anty-reset — co najmniej 1000 monet. Ceny monet są weryfikowane z katalogu TikToka, bez przeliczania diamentów.",
        "ideas": [
            "Róża · 1–29 monet → push",
            "Donut · 30–999 monet → następny poziom",
            "Ice Cream · 30–999 monet → poprzedni poziom",
            "Castle · 1000+ monet → reset",
            "Lion · 1000+ monet → anty-reset",
            "1000 tapów → ciemność, follow → owacja",
        ],
        "preset_id": "minecraft-parkour",
        "rules": [
            _rule("mp-push", "Róża · 1–29 monet → push", {"type": "gift", "gift_name": "Rose", "min_coins": 1, "max_coins": 29}, {"type": "parkour_push"}, "🌹 Push streamera!"),
            _rule("mp-forward", "Donut · 30–999 monet → następny poziom", {"type": "gift", "gift_name": "Donut", "min_coins": 30, "max_coins": 999}, {"type": "parkour_level_forward"}, "🍩 Awans o poziom!"),
            _rule("mp-back", "Lody · 30–999 monet → poprzedni poziom", {"type": "gift", "gift_name": "Ice Cream", "min_coins": 30, "max_coins": 999}, {"type": "parkour_level_back"}, "↩ Cofnij streamera!"),
            _rule("mp-follow", "Follow → więzienie na 20 s", {"type": "follow"}, {"type": "parkour_jail"}, "🔒 Do więzienia!"),
            _rule("mp-reset", "Castle · 1000+ monet → reset za 60 s", {"type": "gift", "gift_name": "Castle", "min_coins": 1000}, {"type": "parkour_reset"}, "🏰 Reset za 60 sekund!", True),
            _rule("mp-antireset", "Lion · 1000+ monet → anty-reset", {"type": "gift", "gift_name": "Lion", "min_coins": 1000}, {"type": "parkour_antireset"}, "🦁 Reset uratowany!", True),
            # Eventy „wow”: ciemność za 1000 tapów, follow, udostępnienie, komentarz
            _wow_rule("mp-darkness", "1000 tapów → ciemność 15 s",
                      {"type": "like", "like_threshold": 1000, "like_global": True},
                      {"type": "parkour_blackout"}, "🌑 1000 tapów — gasną światła!", cooldown=30),
            _wow_rule("mp-follow-heart", "Follow → serduszko + owacja",
                      {"type": "follow"}, {"type": "parkour_heart"}, "💚 Dziękujemy za obserwację!", once=True),
            _wow_rule("mp-share-lightning", "Udostępnienie → piorun",
                      {"type": "share"}, {"type": "parkour_lightning"}, "⚡ Piorun za udostępnienie!", cooldown=20),
            _wow_rule("mp-disco", "Komentarz „disco” → disco",
                      {"type": "comment", "keyword": "disco"}, {"type": "parkour_disco"}, "🪩 DISCO!", cooldown=45),
        ],
    },
    {
        "id": "minecraft-dropper",
        "title": "Minecraft: Dropper",
        "category": "Dropper",
        "status": "bridge",
        "integration": "GiftStream Local Minecraft",
        "icon": "🪂",
        "tagline": "100 poziomów Droppera sterowanych przez widzów.",
        "description": "GiftStream generuje lokalnie 100 kolorowych poziomów Droppera z różnymi przeszkodami, wodnymi checkpointami i automatycznym awansem po lądowaniu. Widzowie mogą wystrzelić strzałę Punch II, pominąć lub cofnąć poziom, albo zresetować próbę. Nie wymaga pluginów ani modów.",
        "ideas": ["Róża → Punch II", "Donut → następny poziom", "Ice Cream → poprzedni poziom", "Castle → reset"],
        "preset_id": "minecraft-dropper",
        "rules": [
            _rule("md-push", "Róża → push", {"type": "gift", "gift_name": "Rose"}, {"type": "dropper_push"}, "🌹 Push w szybie!"),
            _rule("md-forward", "Donut → wyższy poziom", {"type": "gift", "gift_name": "Donut"}, {"type": "dropper_level_forward"}, "🍩 Wyższy szyb!"),
            _rule("md-back", "Ice Cream → niższy poziom", {"type": "gift", "gift_name": "Ice Cream"}, {"type": "dropper_level_back"}, "↩ Niższy szyb!"),
            _rule("md-reset", "Castle → powrót na start", {"type": "gift", "gift_name": "Castle"}, {"type": "dropper_reset"}, "🏰 Powrót na górę!", True),
            _wow_rule("md-darkness", "1000 tapów → ciemność 15 s",
                      {"type": "like", "like_threshold": 1000, "like_global": True},
                      {"type": "dropper_blackout"}, "🌑 1000 tapów — gasną światła!", cooldown=30),
            _wow_rule("md-share-lightning", "Udostępnienie → piorun",
                      {"type": "share"}, {"type": "dropper_lightning"}, "⚡ Piorun za udostępnienie!", cooldown=20),
            _wow_rule("md-disco", "Komentarz „disco” → disco",
                      {"type": "comment", "keyword": "disco"}, {"type": "dropper_disco"}, "🪩 DISCO!", cooldown=45),
            _rule("md-follow", "Follow → spowolnienie", {"type": "follow"}, {"type": "dropper_slow"}, "🐢 Spowolnienie w locie!"),
            _rule("md-jump", "Panda → wysoki skok", {"type": "gift", "gift_name": "Panda"}, {"type": "dropper_jump"}, "⬆ Wysoki skok!"),
        ],
    },
]


def get_game(game_id: str) -> dict | None:
    return next((game for game in GAMES if game["id"] == game_id), None)

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
    """Extra “wow” actions — no price required, with a cooldown so they do not spam."""
    rule = _rule(rule_id, name, trigger, action, alert)
    rule["cooldown_sec"] = cooldown
    if once:
        rule["first_time_only"] = True
    return rule


GAMES = [
    {
        "id": "minecraft-parkour",
        "title": "Minecraft: live parkour",
        "category": "Parkour",
        "status": "bridge",
        "integration": "GiftStream Local Minecraft",
        "icon": "🧗",
        "tagline": "100 parkour levels controlled by your viewers.",
        "description": "Ready-made actions for the 100 Levels map. Push is the cheapest (1–29 coins); next and previous level cost 30–999 coins; reset and anti-reset need 1000+ coins. Coin prices come from the TikTok catalog — diamonds are never converted.",
        "ideas": [
            "Rose · 1–29 coins → push",
            "Donut · 30–999 coins → next level",
            "Ice Cream · 30–999 coins → previous level",
            "Dragon · 1000+ coins → 10 levels up at once",
            "TikTok Universe · 1000+ coins → 10 levels back at once",
            "Castle · 1000+ coins → reset",
            "Lion · 1000+ coins → anti-reset",
            "1000 taps → blackout, follow → ovation",
        ],
        "preset_id": "minecraft-parkour",
        "rules": [
            _rule("mp-push", "Rose · 1–29 coins → push", {"type": "gift", "gift_name": "Rose", "min_coins": 1, "max_coins": 29}, {"type": "parkour_push"}, "🌹 Shove the streamer!"),
            _rule("mp-forward", "Donut · 30–999 coins → next level", {"type": "gift", "gift_name": "Donut", "min_coins": 30, "max_coins": 999}, {"type": "parkour_level_forward"}, "🍩 Skip a level!"),
            _rule("mp-back", "Ice Cream · 30–999 coins → previous level", {"type": "gift", "gift_name": "Ice Cream", "min_coins": 30, "max_coins": 999}, {"type": "parkour_level_back"}, "↩ Send them back!"),
            _rule("mp-jump-forward", "Dragon · 1000+ coins → +10 levels", {"type": "gift", "gift_name": "Dragon", "min_coins": 1000}, {"type": "parkour_level_jump_forward", "params": {"levels": 10}}, "🚀 Ten levels at once!"),
            _rule("mp-jump-back", "TikTok Universe · 1000+ coins → -10 levels", {"type": "gift", "gift_name": "TikTok Universe", "min_coins": 1000}, {"type": "parkour_level_jump_back", "params": {"levels": 10}}, "🎆 Back ten levels!"),
            _rule("mp-follow", "Follow → jail for 10 s", {"type": "follow"},
                  {"type": "parkour_jail", "params": {"seconds": 10}}, "🔒 To jail!"),
            _rule("mp-reset", "Castle · 1000+ coins → reset in 60 s", {"type": "gift", "gift_name": "Castle", "min_coins": 1000}, {"type": "parkour_reset"}, "🏰 Reset in 60 seconds!", True),
            _rule("mp-antireset", "Lion · 1000+ coins → cancel reset", {"type": "gift", "gift_name": "Lion", "min_coins": 1000}, {"type": "parkour_antireset"}, "🦁 Reset saved!", True),
            # Wow events: blackout on 1000 taps, follow, share, comment
            _wow_rule("mp-darkness", "1000 taps → blackout for 15 s",
                      {"type": "like", "like_threshold": 1000, "like_global": True},
                      {"type": "parkour_blackout"}, "🌑 1000 taps — lights out!", cooldown=30),
            _wow_rule("mp-follow-heart", "Follow → hearts + ovation",
                      {"type": "follow"}, {"type": "parkour_heart"}, "💚 Thanks for the follow!", once=True),
            _wow_rule("mp-share-lightning", "Share → lightning",
                      {"type": "share"}, {"type": "parkour_lightning"}, "⚡ Lightning for the share!", cooldown=20),
            _wow_rule("mp-disco", "Comment “disco” → disco",
                      {"type": "comment", "keyword": "disco"}, {"type": "parkour_disco"}, "🪩 DISCO!", cooldown=45),
            _wow_rule("mp-checkpoint", "Back to checkpoint → current level",
                      {"type": "comment", "keyword": "checkpoint"}, {"type": "parkour_checkpoint"},
                      "📍 Back to the checkpoint!", cooldown=10),
        ],
    },
    {
        "id": "minecraft-dropper",
        "title": "Minecraft: Dropper",
        "category": "Dropper",
        "status": "bridge",
        "integration": "GiftStream Local Minecraft",
        "icon": "🪂",
        "tagline": "100 Dropper levels controlled by your viewers.",
        "description": "GiftStream generates 100 colourful Dropper levels locally, with varied obstacles, water checkpoints and automatic progress after a landing. Viewers can fire a Punch II arrow, skip or undo a level, or reset the run. No plugins or mods required.",
        "ideas": ["Rose → Punch II", "Donut → next level", "Ice Cream → previous level", "Castle → reset"],
        "preset_id": "minecraft-dropper",
        "rules": [
            _rule("md-push", "Rose → push", {"type": "gift", "gift_name": "Rose"}, {"type": "dropper_push"}, "🌹 Shove them down the shaft!"),
            _rule("md-forward", "Donut → higher level", {"type": "gift", "gift_name": "Donut"}, {"type": "dropper_level_forward"}, "🍩 Higher shaft!"),
            _rule("md-back", "Ice Cream → lower level", {"type": "gift", "gift_name": "Ice Cream"}, {"type": "dropper_level_back"}, "↩ Lower shaft!"),
            _rule("md-reset", "Castle → back to the start", {"type": "gift", "gift_name": "Castle"}, {"type": "dropper_reset"}, "🏰 Back to the top!", True),
            _wow_rule("md-darkness", "1000 taps → blackout for 15 s",
                      {"type": "like", "like_threshold": 1000, "like_global": True},
                      {"type": "dropper_blackout"}, "🌑 1000 taps — lights out!", cooldown=30),
            _wow_rule("md-share-lightning", "Share → lightning",
                      {"type": "share"}, {"type": "dropper_lightning"}, "⚡ Lightning for the share!", cooldown=20),
            _wow_rule("md-disco", "Comment “disco” → disco",
                      {"type": "comment", "keyword": "disco"}, {"type": "dropper_disco"}, "🪩 DISCO!", cooldown=45),
            _rule("md-slow", "Subscribe → slowness for 7 s", {"type": "subscribe"}, {"type": "dropper_slow"}, "🐌 Slow down!"),
            _rule("md-jump", "Join → high jump", {"type": "join"}, {"type": "dropper_jump"}, "🦘 High jump!"),
        ],
    },
]


def get_game(game_id: str) -> dict | None:
    """Built-in game mode by id (None for unknown ids)."""
    return next((game for game in GAMES if game["id"] == game_id), None)

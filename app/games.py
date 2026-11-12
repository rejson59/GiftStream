"""Game catalog and ready-to-use GiftStream interaction presets."""
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


GAMES = [
    {
        "id": "giftstream-zombie-arena", "title": "GiftStream: arena zombie", "category": "Gra wbudowana",
        "status": "bridge", "integration": "Gra przeglądarkowa", "game_url": "/game", "icon": "🧟",
        "tagline": "Widzowie pomagają przetrwać kolejne fale albo przywołują bossa.",
        "description": "Gotowy preset współpracuje z wbudowaną grą demo. Róże przywołują zombie, polubienia uruchamiają fale, a droższe prezenty leczą lub przywołują bossa.",
        "ideas": ["Róża → zombie", "100 polubień → fala", "Donut → leczenie", "Smok → boss"],
        "preset_id": "giftstream-zombie-arena",
        "rules": [
            _rule("za-rose", "Róża → zombie", {"type": "gift", "gift_name": "Rose"}, {"type": "spawn_zombie", "params": {"count": 1}}, "🌹 Zombie nadchodzi!"),
            _rule("za-likes", "100 polubień → fala", {"type": "like", "like_threshold": 100}, {"type": "spawn_enemy", "params": {"count": 2}}, "♡ Fala zombie!"),
            _rule("za-donut", "Donut → leczenie", {"type": "gift", "gift_name": "Donut"}, {"type": "heal", "params": {"amount": 18}}, "🍩 Uzupełniono zdrowie!"),
            _rule("za-dragon", "Smok → boss", {"type": "gift", "gift_name": "Dragon"}, {"type": "spawn_boss", "params": {"boss": "dragon"}}, "🐉 Boss na arenie!", True),
            _rule("za-follow", "Obserwacja → tarcza", {"type": "follow"}, {"type": "shield", "params": {"duration_sec": 10}}, "🛡️ Widz daje tarczę!"),
        ],
    },
    {
        "id": "minecraft-survival", "title": "Minecraft: przetrwanie", "category": "Piaskownica",
        "status": "bridge", "integration": "ServerTap", "icon": "⛏️",
        "tagline": "Chat buduje świat albo zamienia go w koszmar.",
        "description": "Gotowe komendy przez ServerTap dla serwerów Paper, Spigot i Bukkit. Prezenty przywołują moby, dają przedmioty, leczą lub zmieniają pogodę.",
        "ideas": ["Róża → zombie", "Panda → regeneracja", "Donut → diament", "Lew → fala bossów"],
        "preset_id": "minecraft-survival",
        "rules": [
            _rule("mc-rose", "Róża → zombie", {"type": "gift", "gift_name": "Rose"}, {"type": "spawn_zombie", "params": {"count": 1}}, "🌹 Zombie nadchodzi!"),
            _rule("mc-donut", "Donut → diament", {"type": "gift", "gift_name": "Donut"}, {"type": "drop_diamond", "params": {"count": 1}}, "🍩 Diament dla gracza!"),
            _rule("mc-panda", "Panda → regeneracja", {"type": "gift", "gift_name": "Panda"}, {"type": "heal", "params": {"duration": 10}}, "🐼 Regeneracja!"),
            _rule("mc-dragon", "Smok → boss", {"type": "gift", "gift_name": "Dragon"}, {"type": "spawn_boss", "params": {"boss": "wither"}}, "🐉 Boss na serwerze!", True),
            _rule("mc-likes", "100 lajków → creeper", {"type": "like", "like_threshold": 100}, {"type": "spawn_enemy", "params": {"entity": "creeper", "count": 1}}, "♡ Creeper dla czatu!"),
        ],
    },
    {
        "id": "minecraft-parkour", "title": "Minecraft: parkour na żywo", "category": "Parkour",
        "status": "bridge", "integration": "ServerTap", "icon": "🧗",
        "tagline": "Widzowie pomagają wejść na szczyt — lub dorzucają utrudnienia.",
        "description": "Gotowy preset ServerTap z bezpiecznymi efektami, mobami i zmianą pory dnia. Konkretne checkpointy zależą od mapy.",
        "ideas": ["Róża → skok", "Follow → szybkość", "Donut → regeneracja", "Smok → noc i creepery"],
        "preset_id": "minecraft-parkour",
        "rules": [
            _rule("mp-rose", "Róża → skok", {"type": "gift", "gift_name": "Rose"}, {"type": "jump", "params": {"duration_sec": 6}}, "🌹 Skok w górę!"),
            _rule("mp-follow", "Follow → szybkość", {"type": "follow"}, {"type": "speed_boost", "params": {"duration_sec": 12}}, "＋ Przyspieszenie!"),
            _rule("mp-donut", "Donut → regeneracja", {"type": "gift", "gift_name": "Donut"}, {"type": "heal", "params": {"duration": 8}}, "🍩 Druga szansa!"),
            _rule("mp-dragon", "Smok → nocna fala", {"type": "gift", "gift_name": "Dragon"}, {"type": "spawn_enemy", "params": {"entity": "creeper", "count": 3}}, "🐉 Parkour w ciemności!", True),
        ],
    },
    {
        "id": "minecraft-arena", "title": "Minecraft: arena widzów kontra streamer", "category": "Arena",
        "status": "bridge", "integration": "ServerTap", "icon": "⚔️",
        "tagline": "Prezenty zmieniają tempo pojedynku i wyposażenie gracza.",
        "description": "Gotowy zestaw komend ServerTap: fale mobów, bezpieczne leczenie, przedmioty oraz boss event. Parametry mobów i przedmiotów są ograniczone allow-listą.",
        "ideas": ["Róża → szkielet", "Donut → chleb", "Follow → tarcza", "Smok → Wither"],
        "preset_id": "minecraft-arena",
        "rules": [
            _rule("ma-rose", "Róża → szkielety", {"type": "gift", "gift_name": "Rose"}, {"type": "spawn_enemy", "params": {"entity": "skeleton", "count": 2}}, "🏹 Szkielety dołączają!"),
            _rule("ma-donut", "Donut → chleb", {"type": "gift", "gift_name": "Donut"}, {"type": "give_item", "params": {"item": "bread", "count": 4}}, "🍞 Zapasy dla gracza!"),
            _rule("ma-follow", "Follow → tarcza", {"type": "follow"}, {"type": "shield", "params": {"duration_sec": 12}}, "🛡️ Ochrona aktywna!"),
            _rule("ma-dragon", "Smok → Wither", {"type": "gift", "gift_name": "Dragon"}, {"type": "spawn_boss", "params": {"boss": "wither"}}, "🐉 Wchodzisz na własne ryzyko!", True),
            _rule("ma-likes", "100 lajków → noc", {"type": "like", "like_threshold": 100}, {"type": "change_time", "params": {"time": "night"}}, "🌙 Arena przechodzi w noc!"),
        ],
    },
    {
        "id": "minecraft-mob-rush", "title": "Minecraft: nocna horda", "category": "Survival",
        "status": "bridge", "integration": "ServerTap", "icon": "🌙",
        "tagline": "Każdy próg lajków podkręca falę mobów.",
        "description": "Preset survivalowy używający wyłącznie obsługiwanych komend ServerTap. Połączenie wymaga serwera Paper/Spigot/Bukkit i wtyczki ServerTap.",
        "ideas": ["Róża → zombie", "100 lajków → creepery", "Panda → regeneracja", "Follow → szybkość"],
        "preset_id": "minecraft-mob-rush",
        "rules": [
            _rule("mr-rose", "Róża → zombie", {"type": "gift", "gift_name": "Rose"}, {"type": "spawn_zombie", "params": {"count": 2}}, "🧟 Nadchodzi fala!"),
            _rule("mr-likes", "100 lajków → creepery", {"type": "like", "like_threshold": 100}, {"type": "spawn_enemy", "params": {"entity": "creeper", "count": 3}}, "💥 Trzy creepery na arenie!", True),
            _rule("mr-panda", "Panda → regeneracja", {"type": "gift", "gift_name": "Panda"}, {"type": "heal", "params": {"duration": 8}}, "🐼 Chwila oddechu!"),
            _rule("mr-follow", "Follow → szybkość", {"type": "follow"}, {"type": "speed_boost", "params": {"duration_sec": 12}}, "⚡ Sprint!"),
        ],
    },
    {
        "id":"seven-days","title":"7 Days to Die: horda","category":"Survival","status":"idea","icon":"🧟",
        "tagline":"Czat decyduje, co przetrwa do następnego świtu.",
        "description":"Zainspirowane interaktywnymi wyzwaniami survivalowymi: fale, zasoby i zmiana pory dnia. Wymaga własnego moda lub adaptera; nie jest gotową integracją.",
        "ideas":["Róża → pojedynczy zombie", "Donut → amunicja", "Smok → horda", "Lew → noc natychmiast"],
    },
    {
        "id":"gta-v","title":"GTA V: miasto chaosu","category":"Sandbox","status":"idea","icon":"🚘",
        "tagline":"Prezenty uruchamiają zdarzenia w trybie fabularnym.",
        "description":"Pomysły dla GTA V Story Mode/offline: pojazdy, pogoda, pościgi i wyzwania jazdy. Wymaga lokalnego moda/adaptera; bez modyfikowania rozgrywki online.",
        "ideas":["Róża → mały ruch uliczny", "Panda → naprawa auta", "Smok → pościg", "Lajki → deszcz"],
    },
    {
        "id":"rdr2","title":"Red Dead Redemption 2: Dziki Zachód","category":"Sandbox","status":"idea","icon":"🤠",
        "tagline":"Widzowie nagradzają wyprawę albo sprowadzają kłopoty.",
        "description":"Pomysły do trybu fabularnego: pogoda, wyzwania konne, zaopatrzenie i potyczki. Potrzebny lokalny adapter/mod do gry.",
        "ideas":["Róża → zapasy", "Donut → leczenie", "Smok → zasadzka", "Follow → spokojna pogoda"],
    },
    {
        "id":"raft","title":"Raft: dryfująca załoga","category":"Survival","status":"idea","icon":"🛟",
        "tagline":"Czat pomaga budować tratwę albo przywołuje rekina.",
        "description":"Zdarzenia wokół zapasów, rekinów, pogody i napraw. Wymaga lokalnego adaptera lub moda do gry.",
        "ideas":["Róża → drewno", "Donut → jedzenie", "Smok → rekin", "Follow → naprawa"],
    },
    {
        "id":"valheim","title":"Valheim: wyprawa wikingów","category":"Survival","status":"idea","icon":"🪓",
        "tagline":"Dar od widza może uratować wyprawę — lub przywołać bossa.",
        "description":"Runy, przeciwnicy, pogoda i bossowie sterowani przez kontrolowany mod/adapter po stronie gry.",
        "ideas":["Róża → greydwarf", "Panda → leczenie", "Smok → boss", "Lajki → burza"],
    },
    {
        "id":"lethal-company","title":"Lethal Company: wyprawa po złom","category":"Kooperacja","status":"idea","icon":"👾",
        "tagline":"Widzowie dokładają łup, alarmy i dodatkowe zagrożenia.",
        "description":"Tryb do wspólnych streamów: losowe wyzwania, limity ekwipunku i ostrzeżenia. Wymaga moda zgodnego z lobby i wersją gry.",
        "ideas":["Róża → alarm", "Donut → dodatkowy łup", "Smok → zagrożenie", "Follow → bezpieczny powrót"],
    },
    {
        "id":"phasmophobia","title":"Phasmophobia: nocne śledztwo","category":"Horror","status":"idea","icon":"👻",
        "tagline":"Prezenty wpływają na napięcie, światło i zadania drużyny.",
        "description":"Koncepcja do prywatnych rozgrywek: losowe cele, światło i efekty atmosferyczne. Wymaga wspieranego, dozwolonego lokalnego adaptera.",
        "ideas":["Róża → szum radia", "Donut → światło", "Smok → blackout", "Lajki → nowy cel"],
    },
    {
        "id":"sons-of-the-forest","title":"Sons of the Forest: obóz przetrwania","category":"Survival","status":"idea","icon":"🏕️",
        "tagline":"Widzowie dostarczają zasoby albo utrudniają nocną obronę.",
        "description":"Pomysły na materiały, pogodę i obronę obozu. Wymaga własnego moda/adaptera; nie jest gotowym połączeniem.",
        "ideas":["Róża → patyki", "Donut → jedzenie", "Smok → nocna fala", "Follow → leczenie"],
    },
    {
        "id":"roblox","title":"Roblox: wyzwania społeczności","category":"Minigry","status":"idea","icon":"🧱",
        "tagline":"Minigry z wyzwaniami, które widzowie uruchamiają prezentami.",
        "description":"Tor przeszkód, wyścig, King of the Hill i arena we własnej grze z bezpiecznym, uwierzytelnionym endpointem serwerowym.",
        "ideas":["Róża → przeszkoda", "Donut → przyspieszenie", "Smok → boss", "Lew → powrót do startu"],
    },
]


def get_game(game_id: str) -> dict | None:
    return next((game for game in GAMES if game["id"] == game_id), None)

"""Katalog gier i gotowych pomysłów na interakcje dla GiftStream."""
from __future__ import annotations

GAMES = [
    {
        "id": "minecraft-survival", "title": "Minecraft: przetrwanie", "category": "Piaskownica",
        "status": "bridge", "icon": "⛏️", "tagline": "Chat buduje świat albo zamienia go w koszmar.",
        "description": "Prezenty mogą przywoływać moby, podarować przedmioty, leczyć gracza albo zmieniać warunki rozgrywki. Integracja przez ServerTap dla serwerów Paper/Spigot/Bukkit.",
        "ideas": ["Róża → przywołaj zombie", "Panda → regeneracja", "Donut → diament", "Lew → fala bossów"],
        "preset_id": "minecraft-survival",
        "rules": [
            {"id":"mc-rose","name":"Róża → zombie","trigger":{"type":"gift","gift_name":"Rose"},"action":{"type":"spawn_zombie","params":{"count":1}},"alert_text":"🌹 Zombie nadchodzi!"},
            {"id":"mc-donut","name":"Donut → diament","trigger":{"type":"gift","gift_name":"Donut"},"action":{"type":"drop_diamond","params":{"count":1}},"alert_text":"🍩 Diament dla gracza!"},
            {"id":"mc-panda","name":"Panda → regeneracja","trigger":{"type":"gift","gift_name":"Panda"},"action":{"type":"heal","params":{"amount":10}},"alert_text":"🐼 Regeneracja!"},
            {"id":"mc-dragon","name":"Smok → boss","trigger":{"type":"gift","gift_name":"Dragon"},"action":{"type":"spawn_boss","params":{"boss":"wither"}},"interrupt":True,"alert_text":"🐉 Boss na serwerze!"},
            {"id":"mc-likes","name":"100 lajków → creeper","trigger":{"type":"like","like_threshold":100},"action":{"type":"spawn_enemy","params":{"entity":"creeper","count":1}}},
        ],
    },
    {
        "id":"minecraft-parkour","title":"Minecraft: parkour na żywo","category":"Parkour",
        "status":"idea","icon":"🧗", "tagline":"Widzowie pomagają wejść na szczyt… albo cofają na start.",
        "description":"Mapa parkour z checkpointami, ruchomymi platformami i głosowaniem widzów. Wymaga datapacka lub pluginu do efektów specyficznych dla mapy.",
        "ideas":["Róża → mały skok", "Serce → checkpoint", "Donut → śliska podłoga", "Lew → teleport na start"],
    },
    {
        "id":"minecraft-arena","title":"Minecraft: arena mobów","category":"Arena",
        "status":"idea","icon":"⚔️", "tagline":"Fale przeciwników rosną wraz z hojnością czatu.",
        "description":"Osobna arena z falami mobów, punktacją i przerwami na nagrody. Połączenie przez ServerTap plus skonfigurowane komendy serwera.",
        "ideas":["Róża → zombie", "Panda → jedzenie", "Smok → Wither", "Lajki → następna fala"],
    },
    {
        "id":"seven-days","title":"7 Days to Die: horda","category":"Survival",
        "status":"idea","icon":"🧟", "tagline":"Czat decyduje, co przetrwa do następnego świtu.",
        "description":"Pomysły na zdarzenia: hordy, zmiana pory dnia, losowy ekwipunek, pułapki i teleporty. Potrzebny adapter/mod gry, który odbierze akcje GiftStream.",
        "ideas":["Róża → pojedynczy zombie", "Donut → amunicja", "Smok → horda", "Lew → noc natychmiast"],
    },
    {
        "id":"gta-v","title":"GTA V: miasto chaosu","category":"Sandbox",
        "status":"idea","icon":"🚘", "tagline":"Prezenty uruchamiają zabawne zdarzenia w trybie jednoosobowym.",
        "description":"Pomysły dla trybu fabularnego/offline: pojazdy, pogoda, pościgi i fizyka. Wymaga lokalnego moda/adaptera. Nie przeznaczone do omijania zabezpieczeń ani modyfikowania rozgrywki online.",
        "ideas":["Róża → mały ruch uliczny", "Panda → naprawa pojazdu", "Smok → pościg", "Lajki → zmiana pogody"],
    },
    {
        "id":"raft","title":"Raft: dryfująca załoga","category":"Survival",
        "status":"idea","icon":"🛟", "tagline":"Załoga pomaga budować tratwę i dorzuca rekiny.",
        "description":"Wydarzenia wokół zapasów, rekinów, pogody i napraw tratwy. Potrzebny lokalny adapter lub mod.",
        "ideas":["Róża → drewno", "Donut → jedzenie", "Smok → rekin", "Follow → naprawa"],
    },
    {
        "id":"valheim","title":"Valheim: wyprawa wikingów","category":"Survival",
        "status":"idea","icon":"🪓", "tagline":"Dar od widza może uratować wyprawę — lub przywołać bossa.",
        "description":"Pomysły na runy, przeciwników, pogodę i bossów. Integracja wymaga kontrolowanego moda/adaptera po stronie gry.",
        "ideas":["Róża → greydwarf", "Panda → leczenie", "Smok → boss", "Lajki → burza"],
    },
    {
        "id":"roblox","title":"Roblox: wyzwania społeczności","category":"Minigry",
        "status":"idea","icon":"🧱", "tagline":"Minigry z wyzwaniami, które widzowie uruchamiają prezentami.",
        "description":"Możliwe tryby: tor przeszkód, wyścig, king of the hill i arena. Wymaga własnej gry w Roblox z serwerowym endpointem przyjmującym bezpieczne akcje.",
        "ideas":["Róża → przeszkoda", "Donut → przyspieszenie", "Smok → boss", "Lew → powrót do startu"],
    },
]


def get_game(game_id: str) -> dict | None:
    return next((g for g in GAMES if g["id"] == game_id), None)

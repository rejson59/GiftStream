# Katalog pomysłów na interaktywne gry

Katalog w panelu jest inspiracją, a nie deklaracją gotowych, oficjalnych integracji z tymi tytułami. Obecnie pierwszy działający adapter to ServerTap dla serwerów Minecraft; pozostałe gry wymagają własnego lokalnego modu/pluginu, który odbierze akcje TipStream.

## Tryby do zaprojektowania

### Minecraft
- **Przetrwanie:** prezenty przywołują moby, dają ekwipunek lub pomagają graczowi.
- **Parkour:** widzowie dodają przeszkody, zmieniają checkpointy lub wybierają skróty.
- **Arena mobów:** fale przeciwników, bossy, przerwy na nagrody i ranking.
- **King of the Hill:** publiczność wzmacnia jedną ze stron i modyfikuje arenę.

### 7 Days to Die — obrona przed hordą
Zdarzenia mogą przyspieszać nadejście nocy, dodawać przeciwników, uzupełniać amunicję albo zmieniać zapasy. Wymaga adaptera/moda, który interpretuje wyłącznie bezpieczne akcje.

### GTA V — chaos w trybie fabularnym/offline
Proponowane akcje: zmiana pogody, losowy pojazd, krótki pościg albo wyzwanie jazdy. Projektujemy to z myślą o trybie offline i modach single-player, nie o omijaniu anti-cheata ani zakłócaniu gry online.

### Raft — wspólna tratwa
Widzowie mogą dostarczać materiały i żywność, rozpoczynać ataki rekina lub głosować nad ulepszeniem. Wymaga lokalnego moda/adaptera.

### Valheim — wyprawa i bossowie
Prezenty uruchamiają błogosławieństwa, przeciwników, zmianę pogody lub boss event; wartości powinny być ograniczane przez cooldown i bezpieczny preset.

### Roblox — minigry twórcy
Tor przeszkód, arena, wyścig lub King of the Hill. Najbezpieczniejsza droga to własna gra i własny, uwierzytelniony endpoint serwerowy.

## Jak dodawać kolejne gry

1. Opisać konkretny tryb i limity akcji.
2. Zbudować lokalny adapter/plugin z allow-listą, bez dowolnego wykonywania poleceń.
3. Dodać mapowanie `GameAction → API/mod` oraz preset startowy.
4. Przetestować tryb bez live, a potem z symulatorem giftów.

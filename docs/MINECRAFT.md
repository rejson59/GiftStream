# Minecraft przez ServerTap (pierwszy adapter)

GiftStream ma wstępne, działające połączenie z serwerami **Paper / Spigot / Bukkit** przez wtyczkę [ServerTap](https://github.com/servertap-io/servertap). Instalacja wtyczki i konfiguracja serwera odbywa się po stronie właściciela serwera.

## Konfiguracja

1. Zainstaluj ServerTap na serwerze Minecraft i uruchom go ponownie.
2. Włącz uwierzytelnianie kluczem w `plugins/ServerTap/config.yml`:

   ```yaml
   useKeyAuth: true
   key: "długi-losowy-klucz"
   ```

3. Udostępnij API serwera **tylko GiftStream**. Zalecany jest HTTPS albo tunel/VPN; nie otwieraj publicznie portu ServerTap bez ochrony.
4. W GiftStream otwórz **Integracje → Minecraft przez ServerTap**, wpisz adres API, klucz i nick gracza. Zapisz i użyj **Testuj połączenie**.
5. W widoku **Gry** wybierz „Minecraft: przetrwanie” i utwórz gotowy preset. Każda akcja pasująca do obsługiwanej mapy zostanie też wysłana na serwer, gdy integracja jest włączona.

Domyślny adres ServerTap to często `http://127.0.0.1:4567`, ale port zależy od konfiguracji Twojego serwera.

## Mapowane akcje

- `spawn_zombie`, `spawn_enemy` — zombie, szkielet, creeper, pająk, slime lub wiedźma; maksymalnie 5 stworzeń na wyzwolenie.
- `spawn_boss`, `boss_raid` — Wither, Smok Endu, Warden lub Ravager. Używaj ostrożnie.
- `heal`, `shield`, `speed_boost` — dozwolone efekty dla skonfigurowanego gracza, z limitami czasu.
- `drop_diamond`, `drop_item`, `give_item` — tylko przedmioty z krótkiej allow-listy i maksymalnie 64 sztuki.
- `change_time`, `change_weather`, `confetti` — kilka efektów serwerowych.

Pozostałe akcje nadal są widoczne w dashboardzie i działają w grze demo, ale ten adapter je pomija. Komenda jest budowana z allow-listy GiftStream. Treść komentarzy, nazwy prezentów ani parametry przychodzące z webhooka nigdy nie są doklejane do komendy konsoli.

## Granice obecnej integracji

To adapter do poleceń serwerowych, a nie jeszcze dedykowany plugin z konfiguracją aren, checkpointów, głosowań czy eventów przypisanych do konkretnej mapy. Dla trybów typu parkour/king-of-the-hill potrzebny będzie później mały plugin GiftStream z własnymi, ograniczonymi akcjami. SerwerTap działa tylko wtedy, gdy GiftStream może sięgnąć do jego adresu sieciowego; lokalne `127.0.0.1` na hostingu chmurowym nie jest adresem Twojego serwera Minecraft.

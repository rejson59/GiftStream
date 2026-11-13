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

## Lokalny serwer Parkour 100 Levels

Panel **Integracje → Minecraft · Parkour 100 Levels** ma przycisk **Utwórz i uruchom serwer**. Po wpisaniu nicku i samodzielnym zaakceptowaniu Minecraft EULA GiftStream:

- rozpakowuje do nowego, pustego folderu dołączoną mapę `100-levels-5229-v1.7.4.zip` (metadane świata: Minecraft 26.2; datapack ma regiony dla poziomów 1–100);
- pobiera serwer Minecraft 26.2 z oficjalnego manifestu Mojang i weryfikuje SHA-1 podany w manifeście;
- sprawdza wymagany major Java na podstawie manifestu i uruchamia serwer z ograniczeniem do `127.0.0.1:25565`;
- ustawia losowe hasło RCON, które nasłuchuje wyłącznie na localhost; sekrety RCON nie są ujawniane przez API.

Wymaga zainstalowanej zgodnej wersji Java oraz połączenia z Internetem podczas pierwszej konfiguracji. Minecraft server binary podlega osobnej licencji Mojang/Microsoft; GiftStream nie zawiera serwera. Nie wybieraj folderu z istniejącymi danymi — konfiguracja odmówi nadpisania niepustego folderu. Zapisz dostęp do serwera jako `localhost:25565`. Włącz następnie pole „Wysyłaj akcje presetu parkour”.

Dostępne akcje presetu: kolejny/poprzedni obszar poziomu (wyznaczany z datapacka mapy), więzienie na 20 sekund, reset z 60-sekundowym odliczaniem i prezentem anty-reset, który anuluje licznik. Parkour steruje lokalnym serwerem przez ograniczone komendy RCON; ServerTap nie jest wymagany dla tego trybu. Serwer może potrzebować chwili na pierwszy start; log znajduje się w `giftstream-server.log` w folderze serwera. Zatrzymuj serwer przyciskiem **Zatrzymaj**.

To lokalny tryb dla komputera streamera. `127.0.0.1` nie jest adresem widzów ani serwera uruchomionego na innym hoście; nie przekierowuj portu RCON ani nie udostępniaj go publicznie.

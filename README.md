# GiftStream

**Prezenty z TikTok LIVE sterują grą.** GiftStream przypisuje prezenty, polubienia, obserwacje i komentarze do akcji w grze. Skonfiguruj preset, przetestuj symulatorem, a potem połącz grę przez WebSocket, HTTP, UDP lub adapter Minecraft.

## Co działa w MVP

- Polski panel twórcy z aktywnością na żywo, statystykami i rankingiem wspierających.
- Presety i edytor reguł: prezent / próg polubień / obserwacja / słowo w komentarzu → akcja gry.
- Cooldowny, obsługa serii prezentów i oznaczenia akcji priorytetowych.
- Symulator zdarzeń oraz nieoficjalny konektor TikTokLive i adapter zewnętrznego WebSocket API.
- Gra demo „Zombie: przetrwanie” i nakładka OBS.
- Integracja Minecraft **Paper / Spigot / Bukkit przez ServerTap**. Obsługuje ograniczony zestaw komend z allow-listy; konfiguracja w panelu Integracje.
- Katalog pomysłów na interaktywne tryby: Minecraft, 7 Days to Die, GTA V offline, Raft, Valheim, Roblox.
- Biblioteka giftów: wartości przykładowe są oznaczone jako próbki; prawdziwe ID, ceny i adresy oryginalnych grafik pobierane są z metadanych giftów odebranych podczas LIVE. GiftStream nie kopiuje ani nie hostuje grafik TikToka.
- Lokalne pliki JSON; konto ani baza danych nie są wymagane do testów.

## Aplikacja Windows i automatyczne aktualizacje

**GiftStream dla Windows jest dostępny.** Pobierz [instalator GiftStream](https://github.com/rejson59/GiftStream/releases/latest/download/GiftStream-Setup-win-x64.exe) albo pobierz [wersję przenośną](https://github.com/rejson59/GiftStream/releases/latest/download/GiftStream.exe). Instalator tworzy wpis GiftStream w menu Start i na liście aplikacji Windows; opcjonalnie doda skrót na pulpicie. Z menu Start możesz przypiąć GiftStream do paska zadań. Windows nie pozwala instalatorom przypinać aplikacji do paska automatycznie.

Panel uruchamia się w natywnym oknie aplikacji z osadzonym WebView2 — nie otwiera osobnej karty przeglądarki. Instalator dostarcza bootstrapper WebView2 i doinstaluje runtime, jeśli go brakuje. Python nie musi być zainstalowany.

Otwarta aplikacja sprawdza aktualizacje co godzinę i pobiera je w tle, nie przerywając transmisji. Po pobraniu pokaże przycisk do zastosowania aktualizacji w panelu. Presety, ustawienia, gift-katalog i historia są zachowane w `%LOCALAPPDATA%\TipStream` — dotychczasowej ścieżce zgodności, więc wcześniejsze dane TipStream pozostają dostępne. Przy problemie z siecią launcher uruchomi ostatnią poprawnie pobraną wersję.

Nowe wydania są budowane przez GitHub Actions z taga `vX.Y.Z`. Wewnętrzne nazwy paczek `TipStreamApp` i folder `%LOCALAPPDATA%\TipStream` pozostają dla zgodności ze starszymi instalacjami. Pliki nie są podpisane Authenticode, więc Windows SmartScreen może pokazać ostrzeżenie.

## Uruchomienie deweloperskie

Wymagany Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Otwórz `http://localhost:8000`. Domyślnie działa symulator. „Szybki test” wysyła przykładowy prezent; grę demo otworzysz w panelu. Adres nakładki OBS: `http://localhost:8000/overlay?template=grid` (dostępne też `list` i `minimal`).

## Minecraft

Zainstaluj ServerTap na Paper/Spigot/Bukkit, włącz klucz API w konfiguracji wtyczki, a następnie w GiftStream przejdź do **Integracje → Minecraft przez ServerTap**. Wpisz bazowy adres, klucz oraz nick gracza; przetestuj i włącz integrację. Szczegółowa instrukcja: [`docs/MINECRAFT.md`](docs/MINECRAFT.md).

Komendy są budowane z allow-listy i ograniczane parametrami. Komentarz, nick widza ani treść eventu webhook nigdy nie są wykonywane jako polecenie konsoli Minecraft. Nie wystawiaj portu ServerTap publicznie bez ochrony.

## TikTok LIVE

Wybierz tryb połączenia i wpisz publiczną nazwę kanału. Biblioteka TikTokLive jest nieoficjalna i jej działanie zależy od zmian TikToka. Tryb zewnętrznego API może wymagać klucza dostawcy. Patrz [`docs/TIKTOK.md`](docs/TIKTOK.md).

## Integracje z grami

Formaty WebSocket, HTTP webhook, UDP oraz JSONL opisuje [`docs/BRIDGE.md`](docs/BRIDGE.md). Katalog pomysłów na gry: [`docs/GAME_IDEAS.md`](docs/GAME_IDEAS.md). Poza Minecraftem i grą demo pozostałe karty są koncepcjami, a nie gotowymi integracjami.

## Zmienne środowiskowe

Skopiuj `.env.example` do `.env`. `TIKTOOL_API_KEY` włącza tryb zewnętrznego API; `BRIDGE_WEBHOOK_SECRET` chroni zdalne webhooki. Nie commituj sekretów. Klucz ServerTap jest przechowywany w lokalnym `config.json`, pomijanym przez Git; ustaw HTTPS/VPN i zabezpiecz tę maszynę.

## Architektura

```text
TikTok LIVE / symulator / webhook
                 ↓ TikTokEvent
         silnik reguł i presetów
                 ↓ GameAction
 WebSocket + UDP + JSONL + ServerTap
                 ↓
 gra demo / Minecraft / własny adapter / OBS
```

Lokalny MVP nie wymaga Supabase ani Vercel. Produkcyjne wdrożenie potrzebuje trwałego magazynu oraz działającego stale backendu Python/WebSocket; sam Vercel nie utrzyma konektora LIVE.

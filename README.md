# TipStream

**Prezenty z TikTok LIVE sterują grą.** TipStream przypisuje prezenty, polubienia, obserwacje i komentarze do akcji w grze. Skonfiguruj preset, przetestuj symulatorem, a potem połącz grę przez WebSocket, HTTP, UDP lub adapter Minecraft.

## Co działa w MVP

- Polski panel twórcy z aktywnością na żywo, statystykami i rankingiem wspierających.
- Presety i edytor reguł: prezent / próg polubień / obserwacja / słowo w komentarzu → akcja gry.
- Cooldowny, obsługa serii prezentów i oznaczenia akcji priorytetowych.
- Symulator zdarzeń oraz nieoficjalny konektor TikTokLive i adapter zewnętrznego WebSocket API.
- Gra demo „Zombie: przetrwanie” i nakładka OBS.
- Integracja Minecraft **Paper / Spigot / Bukkit przez ServerTap**. Obsługuje ograniczony zestaw komend z allow-listy; konfiguracja w panelu Integracje.
- Katalog pomysłów na interaktywne tryby: Minecraft, 7 Days to Die, GTA V offline, Raft, Valheim, Roblox.
- Biblioteka giftów: wartości przykładowe są oznaczone jako próbki; prawdziwe ID, ceny i adresy oryginalnych grafik pobierane są z metadanych giftów odebranych podczas LIVE. TipStream nie kopiuje ani nie hostuje grafik TikToka.
- Lokalne pliki JSON; konto ani baza danych nie są wymagane do testów.

## Aplikacja Windows i automatyczne aktualizacje

Wydania Windows x64 są budowane przez GitHub Actions po opublikowaniu tagu `vX.Y.Z`. Z wydania pobierasz tylko `TipStream.exe` (launcher). Przy pierwszym uruchomieniu sprawdza on GitHub Releases, pobiera paczkę aplikacji, weryfikuje SHA-256, instaluje ją bez uprawnień administratora w `%LOCALAPPDATA%\\TipStream` i uruchamia. Przy każdym następnym uruchomieniu launchera sprawdza, czy jest nowsze wydanie i automatycznie je pobiera. Po uruchomieniu aplikacji otwiera lokalny panel; Python nie musi być zainstalowany.

Launcher potrzebuje internetu przy pierwszym uruchomieniu. Jeżeli po instalacji GitHub jest niedostępny, uruchomi ostatnią poprawnie pobraną wersję. Otwarta aplikacja dodatkowo sprawdza aktualizacje co godzinę i pobiera je w tle; nie przerywa transmisji. Po pobraniu pokaże przycisk zastosowania aktualizacji — najlepiej kliknąć go po LIVE. Sam plik launchera warto zachować i uruchamiać zamiast wersjonowanego `TipStreamApp.exe`.

Dane użytkownika (presety, ustawienia, katalog giftów i historia zdarzeń) są przechowywane osobno w `%LOCALAPPDATA%\\TipStream`, więc aktualizacja ich nie nadpisuje. Port lokalny jest związany tylko z `127.0.0.1`.

> **Ważne:** konfiguracja wydania nie oznacza jeszcze, że plik `.exe` jest już opublikowany. Pierwsza paczka pojawi się po opublikowaniu tagu wersji `vX.Y.Z` na GitHubie i pomyślnym zakończeniu workflow. Środowisko developerskie TipStream działa na Linuksie, dlatego docelowy plik Windows buduje GitHub Actions na runnerze Windows.

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

Zainstaluj ServerTap na Paper/Spigot/Bukkit, włącz klucz API w konfiguracji wtyczki, a następnie w TipStream przejdź do **Integracje → Minecraft przez ServerTap**. Wpisz bazowy adres, klucz oraz nick gracza; przetestuj i włącz integrację. Szczegółowa instrukcja: [`docs/MINECRAFT.md`](docs/MINECRAFT.md).

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

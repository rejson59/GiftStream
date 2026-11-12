# GiftStream

**Prezenty z TikTok LIVE sterują grą.** GiftStream przypisuje prezenty, polubienia, obserwacje i komentarze do akcji w grze. Skonfiguruj preset, przetestuj symulatorem, a potem połącz grę przez WebSocket, HTTP, UDP lub adapter Minecraft.

## Co działa w MVP

- Polski panel twórcy z aktywnością na żywo, statystykami i rankingiem wspierających.
- Presety i edytor reguł: prezent / próg polubień / obserwacja / słowo w komentarzu → akcja gry.
- Cooldowny, obsługa serii prezentów i oznaczenia akcji priorytetowych.
- Symulator zdarzeń oraz nieoficjalny konektor TikTokLive i adapter zewnętrznego WebSocket API.
- Gra demo „Arena zombie”, pięć gotowych presetów (w tym Minecraft: przetrwanie, parkour, arena i nocna horda) oraz wyszukiwalny katalog dodatkowych koncepcji gier.
- Alerty prezentów i obserwacji: polska synteza mowy z systemowego WebView, dźwiękowy sygnał i regulacja głośności — bez zewnętrznych usług.
- Integracja Minecraft **Paper / Spigot / Bukkit przez ServerTap**. Obsługuje ograniczony zestaw komend z allow-listy; konfiguracja w panelu Integracje.
- Katalog dodatkowych koncepcji gier (m.in. Lethal Company, Phasmophobia, Sons of the Forest, 7 Days to Die, GTA V offline, Raft, Valheim i Roblox); te karty nie oznaczają gotowych integracji.
- Biblioteka do 100 popularnych giftów: katalog TikToka i oryginalne grafiki z jego CDN pobierane są automatycznie bez logowania i bez połączenia transmisji. GiftStream zapisuje metadane i adresy lokalnie, nie kopiuje ani nie hostuje grafik.
- Lokalne pliki JSON; konto ani baza danych nie są wymagane do testów.

## Aplikacja Windows i automatyczne aktualizacje

**GiftStream dla Windows to jeden samodzielny plik EXE.** Pobierz [GiftStream.exe](https://github.com/rejson59/GiftStream/releases/latest/download/GiftStream.exe) i uruchom go — osobny instalator ani launcher nie są potrzebne. Przy pierwszym uruchomieniu aplikacja zapisze swoją kopię w `%LOCALAPPDATA%\GiftStream`, utworzy skrót GiftStream w menu Start i uruchomi natywne okno z osadzonym WebView2. Python nie musi być zainstalowany; WebView2 musi być dostępny w Windows.

Aplikacja sprawdza aktualizacje podczas uruchamiania oraz co 30 minut i ma przycisk „Sprawdź aktualizacje”. Pobiera zweryfikowaną sumą SHA-256 kopię tego samego pliku GiftStream.exe. Jeśli aktualizacja zostanie znaleziona przy uruchamianiu, nowa wersja otworzy się od razu; aktualizacja pobrana podczas pracy nie przerywa transmisji, a skrót Start wskazuje już nową wersję. Dane aplikacji są przechowywane w `%LOCALAPPDATA%\GiftStream`. Nowa instalacja zaczyna z czystymi ustawieniami i nie importuje danych poprzednich wersji.

Nowe wydania są budowane przez GitHub Actions z taga `vX.Y.Z` i zawierają wyłącznie `GiftStream.exe` oraz plik sumy kontrolnej. Plik nie jest podpisany Authenticode, więc Windows SmartScreen może pokazać ostrzeżenie.

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

Skopiuj `.env.example` do `.env`. `TIKTOOL_API_KEY` włącza tryb zewnętrznego API; `GIFTSTREAM_BRIDGE_WEBHOOK_SECRET` chroni zdalne webhooki. Nie commituj sekretów. Klucz ServerTap jest przechowywany w lokalnym `config.json`, pomijanym przez Git; ustaw HTTPS/VPN i zabezpiecz tę maszynę.

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

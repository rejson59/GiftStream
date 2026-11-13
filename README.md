# GiftStream

**Prezenty z TikTok LIVE sterują grą.** GiftStream przypisuje prezenty, polubienia, obserwacje i komentarze do akcji w grze. Skonfiguruj preset, przetestuj symulatorem, a potem połącz grę przez WebSocket, HTTP, UDP lub adapter Minecraft.

## Co działa w MVP

- Polski panel twórcy z aktywnością na żywo, statystykami i rankingiem wspierających; orientacyjne zarobki z giftów w PLN są liczone z diamentów eventu, edytowalnej stawki USD/diament i automatycznie odświeżanego kursu USD/PLN z tabeli NBP. Kwota per gift pojawia się w aktywności i katalogu.
- Presety i edytor reguł: prezent / próg polubień / obserwacja / słowo w komentarzu → akcja gry; gdzie TikTok udostępnia grafikę giftu, pokazujemy oryginalny obraz z jego CDN zamiast emoji.
- Cooldowny, obsługa serii prezentów i oznaczenia akcji priorytetowych.
- Symulator zdarzeń oraz nieoficjalny konektor TikTokLive i adapter zewnętrznego WebSocket API.
- Gra demo „Arena zombie”, pięć gotowych presetów (w tym Minecraft: przetrwanie, parkour, arena i nocna horda) oraz wyszukiwalny katalog dodatkowych koncepcji gier.
- Alerty prezentów i obserwacji: polska synteza mowy, wbudowany sygnał albo własny bezpośredni publiczny URL HTTPS audio oraz regulacja głośności. Linki MyInstants działają tylko wtedy, gdy użytkownik ma dostęp do bezpośredniego pliku dźwięku; GiftStream nie korzysta z nieudokumentowanego API ani nie przegląda katalogu MyInstants.
- Edytowalne nakładki browser-source dla OBS i TikTok LIVE Studio: legenda giftów, alerty oraz osobny panel streamera z szacunkowymi zarobkami, ostatnimi giftami i akcjami oraz liczbą widzów.
- Integracja Minecraft **Paper / Spigot / Bukkit przez ServerTap**. Obsługuje ograniczony zestaw komend z allow-listy; konfiguracja w panelu Integracje.
- Katalog dodatkowych koncepcji gier (m.in. Lethal Company, Phasmophobia, Sons of the Forest, 7 Days to Die, GTA V offline, Raft, Valheim i Roblox); te karty nie oznaczają gotowych integracji.
- Biblioteka do 100 giftów z oryginalnymi grafikami z CDN TikToka, wyszukiwaniem i sortowaniem po popularności orientacyjnej albo cenie w monetach. Wartość monet płacą widzowie; diamenty są odrębną miarą nagród twórcy. Oferta i ceny mogą się różnić w aplikacji, regionie i kanale zakupu; ceny oznaczone „≈” są szacowane, jeśli katalog nie podaje bezpośrednio wartości monet. Obrazy pozostają na CDN TikToka, a GiftStream zapisuje wyłącznie adresy i metadane.
- Lokalne pliki JSON; konto ani baza danych nie są wymagane do testów.

## Aplikacja Windows i automatyczne aktualizacje

**GiftStream dla Windows to jeden samodzielny plik EXE.** Pobierz [GiftStream.exe](https://github.com/rejson59/GiftStream/releases/latest/download/GiftStream.exe) i uruchom go — osobny instalator ani launcher nie są potrzebne. Przy pierwszym uruchomieniu aplikacja od razu otwiera natywne okno z osadzonym WebView2 i tworzy skrót GiftStream w menu Start; nie kopiuje dużego pliku EXE przed pokazaniem UI. Python nie musi być zainstalowany; WebView2 musi być dostępny w Windows.

Aplikacja sprawdza aktualizacje podczas uruchamiania oraz co 30 minut i ma przycisk „Sprawdź aktualizacje”. Pobiera zweryfikowaną sumą SHA-256 kopię tego samego pliku GiftStream.exe. Jeśli pobranie zakończy się podczas pracy aplikacji Windows, nowa wersja uruchamia się automatycznie, a poprzednia zamyka. GiftStream może na chwilę przestać odbierać zdarzenia, a po restarcie może być potrzebne ponowne połączenie; sama transmisja TikTok nie jest zamykana. Dane aplikacji są przechowywane w `%LOCALAPPDATA%\GiftStream`. Nowa instalacja zaczyna z czystymi ustawieniami i nie importuje danych poprzednich wersji.

Nowe wydania są budowane przez GitHub Actions z taga `vX.Y.Z`  i zawierają wyłącznie `GiftStream.exe` oraz plik sumy kontrolnej. Plik nie jest podpisany Authenticode, więc Windows SmartScreen może pokazać ostrzeżenie.

## Uruchomienie deweloperskie

Wymagany Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Otwórz `http://localhost:8000`. Domyślnie działa symulator. „Szybki test” wysyła przykładowy prezent; grę demo otworzysz w panelu. Nakładki browser-source działają w OBS i TikTok LIVE Studio: `/overlay?template=grid`, `list`, `minimal` albo `streamer`; panel streamera przyjmuje pola `earnings,gifts,actions,viewers` w parametrze `fields`.

## Minecraft

Dla serwerów Paper/Spigot/Bukkit skonfiguruj ServerTap w panelu **Minecraft przez ServerTap**. Dla dostarczonej mapy wybierz **Minecraft · Parkour 100 Levels** i użyj przycisku **Utwórz i uruchom serwer**; potrzebna jest Java wymagana przez manifest Mojang, Internet przy pierwszym pobraniu oraz akceptacja Minecraft EULA. Szczegóły i ograniczenia: [`docs/MINECRAFT.md`](docs/MINECRAFT.md).

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

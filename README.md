# GiftStream

**TikTok LIVE steruje Minecraft Parkour.** GiftStream odbiera zdarzenia LIVE, dopasowuje je do jednego gotowego presetu i wykonuje bezpieczne akcje na lokalnym serwerze z mapą 100 Levels.

## Co zawiera GiftStream

- Jeden obsługiwany tryb gry: **Minecraft Parkour 100 Levels**. Nie ma katalogu innych gier ani zestawów gotowych presetów.
- Reguły parkour można edytować: push jest najtańszy (1–29 monet), zmiany poziomu kosztują od 30 monet, a reset i anty-reset od 1000 monet. Progi opierają się wyłącznie na cenie monet jawnie znanej z katalogu TikToka — diamenty nie są traktowane jako cena widza.
- Jednoklikowe przygotowanie lokalnego serwera vanilla z wyborem najnowszej stabilnej lub jednej z ostatnich wersji Minecrafta. GiftStream pobiera i weryfikuje serwer z oficjalnego manifestu Mojang, izoluje świat dla każdej wersji oraz pokazuje adres `localhost:25565`, który można skopiować. Mapa działa jako datapack, bez niezweryfikowanych pluginów; zgodność jest najlepsza z wersją mapy 26.2. Wymagana jest zgodna Java, internet przy pierwszej konfiguracji i samodzielna akceptacja Minecraft EULA. Szczegóły: [`docs/MINECRAFT.md`](docs/MINECRAFT.md).
- Opcjonalne przekazywanie treści komentarzy LIVE do czatu Minecraft. Tekst kodowany jest jako `tellraw` — nie jest wykonywany jako polecenie.
- Symulator oraz **nieoficjalny** konektor TikTokLive. Zdarzenia, w tym prezenty, komentarze, polubienia, follow, dołączenia i udostępnienia, zależą od aktualnej dostępności biblioteki i TikToka; GiftStream ponawia zerwane połączenia, ale nie gwarantuje przechwycenia każdego zdarzenia.
- Biblioteka giftów z oryginalnymi grafikami TikToka, wyszukiwaniem i sortowaniem według popularności orientacyjnej lub ceny w monetach. Monety widza i diamenty twórcy są odrębnymi wartościami.
- Alerty dźwiękowe, synteza mowy, widżety OBS oraz szacunkowa wartość nagród w PLN. Szacunek nie jest oficjalną stawką ani obietnicą wypłaty TikToka.
- Wyszukiwarka i dodawanie dźwięków MyInstants. Jest to nieoficjalny odczyt strony publicznej i może przestać działać, jeśli zmieni się jej układ lub dostępność.

## Aplikacja Windows i aktualizacje

**GiftStream dla Windows to jeden samodzielny plik EXE.** Pobierz [GiftStream.exe](https://github.com/rejson59/GiftStream/releases/latest/download/GiftStream.exe) i uruchom go — osobny instalator ani launcher nie są potrzebne. Aplikacja otwiera natywne okno z osadzonym WebView2 bez czekania na sprawdzenie sieci ani utworzenie skrótu; skrót GiftStream w menu Start przygotowuje w tle. Python nie musi być zainstalowany; WebView2 musi być dostępny w Windows.

Aplikacja sprawdza aktualizacje podczas uruchamiania oraz co 30 minut. Zweryfikowana nowa wersja jest pobierana i automatycznie uruchamiana; w trakcie restartu GiftStream może na chwilę przestać odbierać zdarzenia, a po restarcie może być potrzebne ponowne połączenie z LIVE. Dane są przechowywane w `%LOCALAPPDATA%\GiftStream`. Nowa instalacja jest czysta i nie importuje danych z poprzednich instalacji.

Nowe wydania buduje GitHub Actions z taga `vX.Y.Z`; artefakt to GiftStream.exe i suma kontrolna. Plik nie jest podpisany Authenticode, więc Windows SmartScreen może pokazać ostrzeżenie.

## Uruchomienie deweloperskie

Wymagany Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Otwórz `http://localhost:8000`. Domyślnie działa symulator. Nakładki OBS są dostępne pod `/overlay?template=grid`, `list`, `minimal` lub `streamer`.

## Bezpieczeństwo i ograniczenia

- Lokalny parkour nasłuchuje na `127.0.0.1`; nie wystawiaj portu RCON do Internetu.
- GiftStream nie wykonuje treści czatu jako komendy serwera. Relaying komentarzy jest domyślnie wyłączony i działa tylko po ręcznym włączeniu.
- TikTokLive nie jest oficjalnym API i może się zepsuć; automatyczne ponawianie połączenia nie odtwarza zdarzeń, które wystąpiły podczas rozłączenia.
- Integracja MyInstants nie korzysta z oficjalnego API; wyszukiwanie nieoficjalnie odczytuje publiczną stronę i zależy od jej dostępności.
- Lokalna wersja nie wymaga Supabase ani Vercel. Szczegóły TikTok LIVE: [`docs/TIKTOK.md`](docs/TIKTOK.md).

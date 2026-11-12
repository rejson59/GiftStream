# GiftStream: Windows launcher i aktualizacje

## Model dystrybucji

- `GiftStream.exe` jest nowym launcherem użytkownika. Przy każdym uruchomieniu sprawdza najnowsze publiczne wydanie w repozytorium GitHub `rejson59/GiftStream`.
- `TipStream.exe` jest dołączany jako zgodnościowy alias, aby istniejące instalacje GiftStream/TipStream nadal mogły pobierać aktualizacje.
- `TipStreamApp-win-x64.zip` zawiera desktopową aplikację (`TipStreamApp.exe`), lokalny serwer i zasoby panelu. Nazwy wewnętrznej paczki pozostają stabilne dla launchera v0.1.0.
- `checksums.txt` zawiera SHA-256 paczki aplikacji. Launcher pobiera assety przez HTTPS, porównuje sumę i odrzuca uszkodzoną lub niezgodną paczkę.
- Wersje i dane użytkownika pozostają w `%LOCALAPPDATA%\TipStream`. Zachowujemy ten dotychczasowy katalog, żeby zmiana nazwy aplikacji nie zgubiła istniejących presetów, ustawień ani historii.

Launcher sprawdza wydanie przy każdym uruchomieniu. Otwarta aplikacja ponawia sprawdzanie co godzinę i pobiera aktualizację w tle, bez przerywania transmisji. Po pobraniu pokaże przycisk zastosowania aktualizacji; można kliknąć go po LIVE. Do uruchamiania aplikacji używaj launchera `GiftStream.exe` (stary `TipStream.exe` nadal jest wspierany).

## Publikacja

Workflow `.github/workflows/release-windows.yml` uruchamia się po wypchnięciu taga semver, np. `v0.2.0`. Na runnerze Windows uruchamia testy, buduje launcher i aplikację PyInstallerem, a następnie publikuje release z plikami:

- `GiftStream.exe` — nowa nazwa launchera do pobrania,
- `TipStream.exe` — zgodnościowy alias dla istniejących użytkowników,
- `TipStreamApp-win-x64.zip` i `checksums.txt` — format aktualizacji zachowujący zgodność z launcherem v0.1.0.

Stary adres repozytorium `rejson59/TipStream` jest przekierowywany do `rejson59/GiftStream`. Identyfikatory API `TIPSTREAM_*` / `X-TipStream-Secret` pozostają niezmienione, aby starsze instalacje i integracje nadal działały. Folder `%LOCALAPPDATA%\TipStream` jest celowo zachowany.

## Bezpieczeństwo i ograniczenia

SHA-256 wykrywa uszkodzenie lub niepełne pobranie, ale nie zastępuje podpisu kodu. Aktualizator ufa wydaniom opublikowanym w repozytorium projektu przez HTTPS. Pliki nie są podpisane Authenticode, więc Windows SmartScreen może wyświetlać ostrzeżenie.

# Windows launcher i aktualizacje

## Model dystrybucji

- `TipStream.exe` jest małym, trwałym launcherem. Sprawdza najnowsze publiczne GitHub Release projektu `rejson59/TipStream` przy każdym uruchomieniu.
- `TipStreamApp-win-x64.zip` zawiera właściwą aplikację desktopową (`TipStreamApp.exe`), serwer FastAPI i zasoby panelu.
- `checksums.txt` zawiera SHA-256 paczki aplikacji. Launcher pobiera oba assety po HTTPS, porównuje sumę i odrzuca uszkodzoną/niezgodną paczkę.
- Wersje są instalowane obok siebie w `%LOCALAPPDATA%\TipStream\versions\<tag>`. `current.json` wskazuje ostatnią poprawnie zainstalowaną wersję.
- Presety i ustawienia nie są trzymane w folderze wersji. Pozostają w `%LOCALAPPDATA%\TipStream`, więc nie giną podczas aktualizacji.
- Jeżeli sprawdzenie sieci albo pobranie wydania się nie powiedzie, launcher uruchomi ostatnią poprawnie zapisaną aplikację. Przy pierwszej instalacji potrzebne jest połączenie z internetem.

Launcher sprawdza wydanie przy każdym uruchomieniu, a otwarta aplikacja ponawia sprawdzanie co godzinę. W tle pobiera i weryfikuje nową paczkę, ale nie przerywa transmisji. Po pobraniu pokaże przycisk zastosowania aktualizacji; aplikacja zamknie się i uruchomi nową wersję, gdy użytkownik go kliknie. Nie uruchamiaj ręcznie `TipStreamApp.exe` z folderu `versions` — uruchamiaj zachowany launcher `TipStream.exe`, który sprawdza wydania.

## Publikacja nowej wersji

GitHub Actions workflow `.github/workflows/release-windows.yml` uruchamia się po wypchnięciu taga w formacie semver, np. `v0.2.0`. Na runnerze Windows buduje oba programy PyInstallerem i publikuje w GitHub Release:

- `TipStream.exe` — launcher do pobrania przez użytkownika,
- `TipStreamApp-win-x64.zip` — aplikację aktualizowaną automatycznie,
- `checksums.txt` — kontrolną sumę SHA-256.

Pierwszy tag należy opublikować dopiero, gdy zmiany desktopowe są już na domyślnej gałęzi/repozytorium. W tym checkoutie nie da się zbudować natywnego Windows `.exe`, bo środowisko developerskie działa pod Linuksem; build w GitHub Actions jest właściwym miejscem na wygenerowanie binariów Windows.

## Uwagi bezpieczeństwa

Suma SHA-256 wykrywa uszkodzenie lub niepełne pobranie, ale nie zastępuje podpisu kodu. Launcher ufa wydaniom publikowanym przez repozytorium projektu przez HTTPS. Do dystrybucji publicznej warto dodać podpis cyfrowy kodu (EV/Authenticode), aby ograniczyć ostrzeżenia SmartScreen i mocniej potwierdzić autora.

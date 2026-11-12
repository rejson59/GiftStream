# GiftStream dla Windows: aplikacja, instalator i aktualizacje

## Instalacja i uruchamianie

- `GiftStream-Setup-win-x64.exe` instaluje launcher per-user do `%LOCALAPPDATA%\Programs\GiftStream`, tworzy pozycję GiftStream w menu Start i na liście aplikacji Windows. Opcjonalny skrót na pulpicie można zaznaczyć w instalatorze.
- Instalator uruchamia Microsoft Edge WebView2 Evergreen Bootstrapper. WebView2 zapewnia natywne okno z osadzonym panelem; nie otwieramy osobnej przeglądarki. Wymagane jest połączenie z internetem, jeśli runtime WebView2 nie jest jeszcze zainstalowany.
- `GiftStream.exe` jest dostępny osobno jako przenośny launcher. `TipStream.exe` pozostaje zgodnościowym aliasem.
- Aby dodać aplikację do paska zadań, uruchom GiftStream z menu Start, kliknij prawym przyciskiem jego ikonę na pasku i wybierz **Przypnij do paska zadań**. Windows nie udostępnia wspieranego sposobu, by instalator przypinał aplikację automatycznie.
- Standardowe odinstalowanie usuwa pliki programu i skróty, ale nie kasuje danych użytkownika.

## Aktualizacje i dane

Launcher sprawdza wydanie przy każdym uruchomieniu, pobiera właściwą aplikację desktopową oraz uruchamia ją w natywnym oknie GiftStream. Sama aplikacja ponawia sprawdzanie co godzinę. Aktualizacja pobiera się w tle; po zakończeniu transmisji użyj banera **Zastosuj i uruchom ponownie** w panelu. Aktualizacja zamknie aktualne okno, uruchomi nową wersję i nie nadpisze presetów ani ustawień.

Dla zgodności z istniejącymi użytkownikami:

- wersje i dane użytkownika pozostają w `%LOCALAPPDATA%\TipStream`,
- `TipStream.exe` jest nadal publikowany jako alias,
- wewnętrzny pakiet aktualizacji zachowuje nazwy `TipStreamApp.exe` i `TipStreamApp-win-x64.zip`,
- poprzedni adres repozytorium `rejson59/TipStream` przekierowuje do `rejson59/GiftStream`,
- identyfikatory `TIPSTREAM_*` i nagłówek webhooka `X-TipStream-Secret` nie zmieniają się.

## Zawartość wydania

Workflow `.github/workflows/release-windows.yml` uruchamia się po tagu semver, np. `v0.3.0`. Na Windows uruchamia testy i buduje PyInstallerem aplikację, launcher oraz Inno Setup installer. Release zawiera:

- `GiftStream-Setup-win-x64.exe` — zalecana instalacja z menu Start i opcjonalnym skrótem na pulpicie,
- `GiftStream.exe` — przenośny launcher,
- `TipStream.exe` — zgodnościowy alias dla starszych użytkowników,
- `TipStreamApp-win-x64.zip` i `checksums.txt` — wstecznie zgodny format aktualizacji,
Instalator zawiera Microsoft Edge WebView2 bootstrapper, niezbędny do przygotowania runtime przy pierwszej instalacji.

SHA-256 wykrywa uszkodzenie albo niepełne pobranie, ale nie zastępuje podpisu kodu. Pliki nie są podpisane Authenticode, więc Windows SmartScreen może wyświetlać ostrzeżenie.

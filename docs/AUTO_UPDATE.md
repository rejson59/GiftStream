# GiftStream dla Windows: jedna aplikacja, samodzielne aktualizacje

## Uruchamianie

GiftStream jest dostarczany jako jeden plik `GiftStream.exe`. Nie ma osobnego launchera ani instalatora. Po uruchomieniu aplikacja umieszcza własną kopię w `%LOCALAPPDATA%\GiftStream\versions\<wersja>`, zachowuje ustawienia w `%LOCALAPPDATA%\GiftStream` i tworzy albo odświeża skrót `GiftStream` w menu Start. W menu Start znajduje się skrót do aktualnego pliku aplikacji.

Panel działa w natywnym oknie GiftStream z osadzonym Microsoft Edge WebView2. Instalacja Pythona nie jest wymagana. Jeśli WebView2 nie jest dostępny, GiftStream pokaże błąd uruchomienia; runtime można pobrać z oficjalnej strony Microsoft.

## Aktualizacje

Przy starcie i następnie co 30 minut GiftStream sprawdza najnowsze wydanie GitHub. Aktualizacja jest pobierana jako nowe `GiftStream.exe`, weryfikowana przez SHA-256 i zapisywana w katalogu wersji. Jeśli aktualizacja zostanie znaleziona podczas startu, GiftStream uruchamia ją przed pokazaniem okna. Kontrola okresowa nie przerywa transmisji: aplikacja odświeża skrót menu Start, aby kolejne uruchomienie wybrało nową wersję. Przycisk **Sprawdź aktualizacje** uruchamia kontrolę ręcznie.

Wydanie zawiera tylko `GiftStream.exe` oraz `checksums.txt`. Workflow `.github/workflows/release-windows.yml` buduje pojedynczy plik aplikacji po utworzeniu taga w formacie `vX.Y.Z`.

## Dane

Ustawienia, presety, katalog giftów i historia są przechowywane w `%LOCALAPPDATA%\GiftStream`. Użytkownik wybrał czystą instalację: nowe wydanie nie importuje danych z poprzednich instalacji.

## Bezpieczeństwo

Suma SHA-256 wykrywa uszkodzenie lub niepełne pobranie, ale nie zastępuje podpisu Authenticode. Plik nie jest podpisany, więc Windows SmartScreen może wyświetlić ostrzeżenie.

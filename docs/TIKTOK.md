# TikTok LIVE connection options

GiftStream currently offers three source modes in **Creator Studio → Stream connection**.

## Simulator

Runs locally and produces synthetic gifts, likes, comments, follows and joins. It is the default so you can test the full gift → preset → game pipeline without a LIVE room.

## TikTokLive (free, unofficial)

Install dependencies, select **TikTok Live · free**, and enter the creator's `@username`. The integration uses the community-maintained `TikTokLive` Python package. It is not an official TikTok API and can be affected by TikTok protocol changes, connection limits or signing-service availability. No TikTok login/password is requested by GiftStream.

TikTok does not provide a public official API for reading arbitrary LIVE chat/gifts, so third-party clients may stop working or require changes. GiftStream keeps one client session per channel, can restore the last explicitly selected TikTok channel after an app restart, exposes connecting/reconnecting state, cleans up the previous async websocket before retrying, and retries ordinary dropped connections with increasing, interruptible delays. Choosing **Rozłącz** turns off automatic reconnect on the next app start. Do not click Connect repeatedly while the status says it is retrying. The **Logi diagnostyczne** panels show failures across the whole app (including Minecraft setup, game actions, API and browser errors) as well as the connection and retry reason; use **Kopiuj logi** from the dashboard or Minecraft view to share them. Logs are also stored locally in the GiftStream data folder and redact common token/password fields.

TikTokLive v7 uses EulerStream's signing service. If logs show `SignatureRateLimitError` or `rate_limit_account_hour`, the signing service has hit its hourly connection-start limit; this is not a problem with the creator's username or LIVE status. GiftStream now pauses automatic retries for this specific error rather than repeatedly consuming quota. Add your own EulerStream signing key as `SIGN_API_KEY` in the local `.env` file (see [`.env.example`](../.env.example)), then restart GiftStream and connect again. Keep this key private; never paste it into shared logs or commit it. Without a key, wait for the service's quota to reset before manually retrying. Other transient disconnects still use backoff retries. Retries cannot recover events missed while disconnected or guarantee that every event is captured. Use only with streams you are authorized to monitor and in line with TikTok's current terms and policies.

## Managed WebSocket adapter

Select **Managed API** and configure `TIKTOOL_API_KEY` in `.env`. The adapter uses the provider's documented WebSocket connection format. A managed vendor may charge fees and has its own availability, terms and privacy policy. Do not commit API keys.

## Biblioteka oryginalnych giftów

Po połączeniu TikTokLive prosi o katalog prezentów pokoju LIVE. GiftStream zapisuje lokalnie ID, nazwę, wartość, informację o serii i bezpośredni URL obrazka z metadanych giftu. Biblioteka OBS korzysta z tego oryginalnego obrazka z hostingu TikToka; GiftStream nie kopiuje ani nie hostuje assetów. Jeżeli katalog lub oryginalna grafika nie są dostępne, lista pokazuje placeholder zamiast podmieniać artwork na emoji. Rzeczywista cena i lista giftów mogą się różnić zależnie od regionu oraz zmian po stronie TikToka.

## Orientacyjny kalkulator zarobku twórcy

Pulpit pokazuje szacunkową wartość pojedynczego giftu, sumę diamentów i estymowany zarobek z bieżącej sesji. Kwota używa **diamentów po stronie twórcy** z eventu (a jeśli ich brakuje — z zapisanego katalogu giftów), liczby powtórzeń zakończonej serii oraz edytowalnych stawek: `diamenty × USD/diament × kurs USD/PLN`. Domyślny punkt startowy to 0,005 USD za diament i kurs 4,00 PLN za USD; obie wartości można zmienić i są zapisywane lokalnie. Nie wyliczamy wypłaty z monet widza ani nie zakładamy, że monety i diamenty mają równą wartość.

To **szacunek**, nie oficjalny kurs ani kwota potwierdzona przez TikToka. [Polityka wirtualnych przedmiotów TikToka](https://support.tiktok.com/legal/virtual-items?lang=en) określa przeliczanie nagród według czynników ustalanych przez TikToka, bez gwarantowanej stałej stawki gotówkowej. Stawka początkowa w GiftStream jest jedynie edytowalnym założeniem; sprawdź własne saldo i podsumowanie LIVE. Szacunek nie odejmuje podatków, opłat wypłaty, prowizji ani innych korekt. Serie są księgowane dopiero przy zdarzeniu kończącym, żeby nie sumować kolejnych aktualizacji tej samej serii.

## Security notes

- Treat event payloads as untrusted input. GiftStream maps known event types to configured actions; it does not execute arbitrary TikTok comments as shell or game-server commands.
- Keep the API bound to a trusted/local network unless you configure a reverse proxy and authentication.
- When accepting remote events, set `GIFTSTREAM_BRIDGE_WEBHOOK_SECRET` and provide `X-GiftStream-Secret`.
- Avoid putting private TikTok account credentials in `.env` or the dashboard; this MVP only needs the public LIVE username for the unofficial connector.

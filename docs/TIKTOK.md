# TikTok LIVE connection options

GiftStream currently offers three source modes in **Creator Studio → Stream connection**.

## Simulator

Runs locally and produces synthetic gifts, likes, comments, follows and joins. It is the default so you can test the full gift → preset → game pipeline without a LIVE room.

## TikTokLive (free, unofficial)

Install dependencies, select **TikTok Live · free**, and enter the creator's `@username`. The integration uses the community-maintained `TikTokLive` Python package. It is not an official TikTok API and can be affected by TikTok protocol changes, connection limits or signing-service availability. No TikTok login/password is requested by GiftStream.

TikTok does not provide a public official API for reading arbitrary LIVE chat/gifts, so third-party clients may stop working or require changes. Use only with streams you are authorized to monitor and in line with TikTok's current terms and policies.

## Managed WebSocket adapter

Select **Managed API** and configure `TIKTOOL_API_KEY` in `.env`. The adapter uses the provider's documented WebSocket connection format. A managed vendor may charge fees and has its own availability, terms and privacy policy. Do not commit API keys.

## Biblioteka oryginalnych giftów

Po połączeniu TikTokLive prosi o katalog prezentów pokoju LIVE. GiftStream zapisuje lokalnie ID, nazwę, wartość, informację o serii i bezpośredni URL obrazka z metadanych giftu. Biblioteka OBS korzysta z tego oryginalnego obrazka z hostingu TikToka; GiftStream nie kopiuje ani nie hostuje assetów. Jeżeli katalog nie jest dostępny, lista pokazuje przykładowe nazwy i emoji zastępcze. Rzeczywista cena i lista giftów mogą się różnić zależnie od regionu oraz zmian po stronie TikToka.

## Security notes

- Treat event payloads as untrusted input. GiftStream maps known event types to configured actions; it does not execute arbitrary TikTok comments as shell or game-server commands.
- Keep the API bound to a trusted/local network unless you configure a reverse proxy and authentication.
- When accepting remote events, set `BRIDGE_WEBHOOK_SECRET` and provide `X-TipStream-Secret`.
- Avoid putting private TikTok account credentials in `.env` or the dashboard; this MVP only needs the public LIVE username for the unofficial connector.

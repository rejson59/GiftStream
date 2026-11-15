# TikTok LIVE connection options

GiftStream offers the real TikTokLive connector and an optional external WebSocket adapter in **Creator Studio → Stream connection**. It starts disconnected and does not generate simulated activity.

Changing to a different TikTok username stops the previous connector, clears the current session counters/history, and only then starts receiving the new channel's data. The first valid channel connection also clears any old session/demo statistics. Manual disconnect remains disabled for automatic reconnect on the next app start.

## TikTokLive (free, unofficial)

Install dependencies, select **TikTok Live · free**, and enter the creator's `@username`. The integration uses the community-maintained `TikTokLive` Python package. It is not an official TikTok API and can be affected by TikTok protocol changes, connection limits or signing-service availability. No TikTok login/password is requested by GiftStream.

TikTok does not provide a public official API for reading arbitrary LIVE chat/gifts, so third-party clients may stop working or require changes. GiftStream keeps one client session per channel, can restore the last explicitly selected TikTok channel after an app restart, exposes connecting/reconnecting/offline state, cleans up the previous async websocket before retrying, retries ordinary dropped connections with increasing, interruptible delays, and checks an offline creator again after about two minutes, increasing to at most about five minutes between checks. Choosing **Disconnect** turns off automatic reconnect on the next app start. Do not click Connect repeatedly while the status says it is retrying. The **Logi diagnostyczne** panels show failures across the whole app (including Minecraft setup, game actions, API and browser errors) as well as the connection and retry reason; use **Kopiuj logi** from the dashboard or Minecraft view to share them. Logs are also stored locally in the GiftStream data folder and redact common token/password fields.

TikTokLive v7 uses EulerStream's signing service. If logs show `SignatureRateLimitError` or `rate_limit_account_hour`, the signing service has hit its hourly connection-start limit; this is not a problem with the creator's username or LIVE status. GiftStream now pauses automatic retries for this specific error rather than repeatedly consuming quota. Add your own EulerStream signing key as `SIGN_API_KEY` in the local `.env` file (see [`.env.example`](../.env.example)), then restart GiftStream and connect again. Keep this key private; never paste it into shared logs or commit it. Without a key, wait for the service's quota to reset before manually retrying. Other transient disconnects still use backoff retries. Retries cannot recover events missed while disconnected or guarantee that every event is captured. Use only with streams you are authorized to monitor and in line with TikTok's current terms and policies.

## Local browser relay (experimental)

For a local-only alternative, download [`GiftStream-Browser-Relay.zip`](https://github.com/rejson59/GiftStream/releases/latest/download/GiftStream-Browser-Relay.zip), unpack and load its folder as an unpacked extension, then open the creator's public LIVE page in Chrome, and set the GiftStream address in the extension popup (desktop builds can choose a port other than 8000). The helper watches only newly rendered, visible LIVE chat/notice elements and posts normalized events to `127.0.0.1` at `/api/browser/event`; the endpoint rejects non-loopback clients. Game rules triggered by this source are off by default in the extension popup; verify event recognition before opting in. It does not read browser cookies, passwords, page storage, or private WebSocket frames and does not require a remote event vendor.

This is an experimental best-effort source: TikTok changes its page markup and localization, and some event types or messages that are not visible in the page can be missed. The extension cannot replay events from before it was installed or while the browser/page is closed. Check its popup for the last forwarded event and the local received count. Run one source at a time while game rules are enabled: if TikTokLive and Browser relay both report the same event, GiftStream may trigger the matching action twice because cross-source deduplication is not guaranteed.

## Managed WebSocket adapter

Select **Managed API** and configure `TIKTOOL_API_KEY` in `.env`. The adapter uses the provider's documented WebSocket connection format. A managed vendor may charge fees and has its own availability, terms and privacy policy. Do not commit API keys.

## Original gift library

GiftStream refreshes the public TikTok catalog and keeps up to 1000 entries, including gifts without artwork. It stores the ID, name, creator diamonds, explicit coin price fields (when the source exposes them), streak information and the direct artwork URL. Panel and overlay images are fetched through a local proxy limited to trusted TikTok CDN domains, which helps with hotlink blocking; after an error the app tries to refresh the catalog once. A missing artwork never hides a gift. In the library, type a name into the search field; in the rule editor, type a name into the “Gift” field to filter the list instead of scrolling. The coin price is never guessed from diamonds — if TikTok does not provide it, it cannot be derived reliably. Prices and the gift list depend on the region and on changes on TikTok's side.

## Sounds and rules

In **Sounds & alerts**, search public MyInstants sounds, preview them and pick one. There you can also upload your own MP3, WAV, OGG, M4A, AAC or FLAC file up to 10 MB, or paste a public HTTPS link. In the rule editor choose “Use the sound selected in the Studio” to assign the currently selected sound to a specific action. The rule stores a copy of the chosen address; after changing the Studio sound, save the rule again if you also want to change the action's sound. Custom files are stored locally in GiftStream data; older files are kept so already saved rules do not lose their sound when the global alert changes. The MyInstants search is unofficial and depends on their page and file availability.

## Approximate creator earnings calculator

The dashboard shows the estimated value of a single gift, the diamond total and the estimated earnings of the current session. The amount uses the event's **creator-side diamonds** (or the saved gift catalog when they are missing), the repeat count of the finished streak and editable rates: `diamonds × USD/diamond × USD/PLN rate`. The default starting point is 0.005 USD per diamond and a rate of 4.00 PLN per USD; both values are editable and stored locally. A payout is never derived from viewer coins, and coins and diamonds are never assumed to be equal in value.

This is an **estimate**, not an official rate or an amount confirmed by TikTok. [TikTok's virtual items policy](https://support.tiktok.com/legal/virtual-items?lang=en) defines reward conversion through factors chosen by TikTok, with no guaranteed fixed cash rate. The starting rate in GiftStream is only an editable assumption; check your own balance and LIVE summary. The estimate subtracts no taxes, payout fees, commissions or other adjustments. Streaks are booked only on the closing event, so consecutive updates of the same streak are not summed.

## Security notes

- Treat event payloads as untrusted input. GiftStream maps known event types to configured actions; it does not execute arbitrary TikTok comments as shell or game-server commands.
- Keep the API bound to a trusted/local network unless you configure a reverse proxy and authentication.
- When accepting remote events, set `GIFTSTREAM_BRIDGE_WEBHOOK_SECRET` and provide `X-GiftStream-Secret`.
- Avoid putting private TikTok account credentials in `.env` or the dashboard; this MVP only needs the public LIVE username for the unofficial connector.

# GiftStream

**TikTok LIVE drives Minecraft Parkour and Dropper.** GiftStream receives LIVE events, matches them against a ready-made preset and runs safe actions on your local Minecraft server.

## What GiftStream includes

- Two ready-made local game modes: **Minecraft Parkour 100 Levels** and **Minecraft Dropper 100 Levels** with a locally generated 100-shaft map, varied obstacles and automatic progress after a water landing. Dropper runs on vanilla and never downloads maps or plugins from untrusted sources.
- Parkour rules are fully editable: punch, next/previous level, reset and anti-reset plus five viewer effects — slowness, darkness, high jump with a safe landing, a short shield and a cleanse of negative effects. Every one of them is selectable in the rule editor, and the Minecraft panel can test them locally without a LIVE event. Default coin prices: punch 1–29 coins, level change 30–999, reset and anti-reset from 1000; thresholds rely only on an explicit TikTok price. There is **no speed boost** — it disturbed the run more than it helped — and **the map always looks like day**.
- **Level detection and checkpoints (0.22.0).** GiftStream reads the level from the player's real position using the map's own `setlevel` rules (the datapack applies its boxes in file order, so overlapping boxes resolve the same way the map does — this fixes players on level 1 being treated as level 100). Next/previous level teleports to the start plate of that level, stored in `app/level_checkpoints_data.py` so it is always present in the packaged app (`tools/build_level_checkpoints.py` rebuilds it from the map).
- **Punch always hits (0.22.0).** The arrow starts one block in front of the player's chest and flies straight back into their hitbox, so it visibly flies *at* the runner and a wall behind or around them cannot block it. Knockback still comes from Punch II; the arrow deals light damage.
- **The jail is a floating glass cage (0.22.0).** Instead of teleporting the player thousands of blocks away, GiftStream lifts them into a 3×3 tinted-glass cage two blocks above the ground, where they stay safe for the sentence and are then dropped back on the same spot. Nothing is carved out of the map, so the cage cannot destroy course blocks.
- **Everything is in English (0.21.0)** — the dashboard, the overlays and every message the game shows.
- **“Wow” actions:** blackout for 1000 taps — `darkness` + `blindness` for 15 s, so you can barely see, with the time of day untouched; follow gives a heart ovation; sharing the stream calls lightning on the player; a `disco` comment starts a particle disco. All of them are ordinary actions in the rule editor (`parkour_blackout`, `parkour_lightning`, `parkour_disco`, `parkour_heart` and the `dropper_*` equivalents), with default rules in both presets and cooldowns so the chat cannot turn the map into chaos.
- Like thresholds counted **across all viewers at once**: the “Count likes from all viewers” option makes 1000 taps from the whole chat fire the effect, with the overflow carried to the next threshold. By default thresholds are still counted per viewer.
- **Rule order is editable** — drag a card by its `⠿` handle or use the ↑/↓ buttons; the order is saved in the preset and used by the panel, the OBS overlay and action execution.
- Dropper has its own preset: Punch II arrow, next/previous level, back to the start, slowness, darkness, high jump, shield and cleanse. Action testing works from the Minecraft panel without TikTok LIVE. Vanilla is a deliberate choice: nothing requires Bukkit/Paper plugins, which would mean replacing the server and a separate security review.
- One-click setup of the local vanilla server with a choice of the latest stable or one of the recent Minecraft releases. GiftStream downloads and verifies the server from Mojang's official manifest, isolates each version's world and shows the `localhost:25565` address you can copy. The map works as a datapack without unverified plugins; setup repairs two incompatible item-modifier resources and adds a level HUD next to the existing timer. The original map was prepared for 26.2; the fix removes the reported resource-loading error on 26.3, but is not a full certification of the map for every version. GiftStream finds Java in your launchers or installs a matching per-user runtime automatically; internet access for the first setup and accepting the Minecraft EULA yourself are required. Details: [`docs/MINECRAFT.md`](docs/MINECRAFT.md).
- Optional relay of LIVE comment text into the Minecraft chat. The text is encoded as `tellraw` — it is never executed as a command.
- **Unofficial** TikTokLive connector. GiftStream never generates fake events or counters; it starts disconnected and waits for a manual channel connection. Changing the channel first stops the previous connection and resets the statistics, then starts collecting events from the new LIVE. The connection depends on the current availability of the library and TikTok; GiftStream retries dropped connections with a clear status and growing backoff, recognises an offline channel and rechecks it every 2–5 minutes, and pauses pointless attempts when the signing service is rate limited.
- Experimental Browser relay for visible LIVE notifications. A Chrome/Edge extension forwards them only to the local GiftStream, without a paid server and without reading private WebSocket frames; availability depends on TikTok's current DOM. The action history now distinguishes pending, executed, failed and sent-to-bridge.
- Diagnostics cover connections, incoming events, rules and Parkour actions, Java/server/map installation, RCON, API errors and UI errors; the server's JVM log is included in the Minecraft panel. Logs can be copied from the main panel or the Minecraft tab; diagnostics never log LIVE comment content.
- The library can keep up to 1000 gifts from the current TikTok catalog; search gifts by name both in the library and directly in the rule editor. Artwork is served through a safe proxy to the TikTok CDN with catalog refresh on a loading error; an entry without available artwork stays visible. Viewer coins and creator diamonds are kept apart, and missing prices are never guessed.
- **Sound trimming (0.20.0):** in the Sound studio you pick the exact alert fragment on the waveform — with handles, start/end fields or one click (“First 8 s”, “Loudest fragment”, “Middle of the track”). Plus fade in/out in milliseconds, preview of the selection only and a library of uploaded files with their duration. WAV is cut by the server without ffmpeg (PCM 8/16/24/32 bit, mono and stereo), while MP3/M4A/OGG/FLAC are decoded by the browser and saved as WAV. A linked sound (e.g. MyInstants) can be downloaded safely into a local file first — public HTTPS only, redirect checks and a 10 MB limit. Details: [`docs/SOUNDS.md`](docs/SOUNDS.md).
- A separate LIVE sound studio with a MyInstants search, preview and one-click selection; the recommendation list opens results for a manual preview and choice; previews and alerts are limited to 12 seconds and GiftStream never downloads full YouTube tracks. You can also upload your own MP3, WAV, OGG, M4A, AAC or FLAC (up to 10 MB), set a public HTTPS URL, volume and TTS. A Studio sound can be assigned to a specific rule. OBS overlays have seven layouts, including the transparent LIVE Arena with rule cards, live counters, the top viewer and recent gifts. The arena can be configured separately for 16:9 and 9:16 canvases: drag the modules, resize them and share the saved layout in the OBS URL. The editor also exposes module visibility, color theme, accent color, scale, card opacity, density and title; HUD statistics come only from real events.
- Sound alerts, speech synthesis, OBS widgets and an estimated reward value in PLN. The estimate is not an official TikTok rate and not a promise of a payout.

## Windows app and updates

**GiftStream for Windows is a single standalone EXE.** Download [GiftStream.exe](https://github.com/rejson59/GiftStream/releases/latest/download/GiftStream.exe) and run it — no separate installer or launcher is needed. The app opens its native WebView2 window without waiting for a network check or a shortcut; the GiftStream Start-menu shortcut is prepared in the background. Starting it again while the app runs does not open a second window. Python does not have to be installed; WebView2 must be available on Windows.

The app checks for updates at startup and every 30 minutes. A verified new version is downloaded and launched automatically; during the restart GiftStream may briefly stop receiving events, and you may need to reconnect to LIVE afterwards. Data is stored in `%LOCALAPPDATA%\GiftStream`. A fresh install is clean and does not import data from previous installations.

New releases are built by GitHub Actions from a `vX.Y.Z` tag; the artifact is GiftStream.exe plus its checksum. The file is not Authenticode-signed, so Windows SmartScreen may show a warning.

## Development run

Python 3.10+ is required.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000`. GiftStream starts disconnected; connect a real TikTok LIVE channel to start counting statistics. OBS overlays are available at `/overlay?template=grid`, `list`, `minimal`, `streamer`, `ticker`, `spotlight` or `arena`; LIVE Arena has a transparent background and a responsive landscape/portrait layout.

## Security and limitations

- The local parkour server listens on `127.0.0.1`; never expose the RCON port to the internet.
- GiftStream never executes chat content as a server command. Comment relaying is off by default and works only after you enable it.
- TikTokLive is not an official API and may break; automatic reconnection does not replay events that happened while disconnected.
- The MyInstants integration does not use an official API; the search reads the public page unofficially and depends on its availability.
- The local build requires neither Supabase nor Vercel. TikTok LIVE details: [`docs/TIKTOK.md`](docs/TIKTOK.md).

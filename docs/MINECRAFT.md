# Minecraft Parkour and Dropper

GiftStream includes two local Minecraft game modes: Parkour uses the bundled `100-levels-5229-v1.7.4.zip` world; Dropper now generates an original 100-level arena in a fresh vanilla world using controlled, loopback-only RCON commands.

## Dropper 100 Levels

Choose **Minecraft Dropper · 100 Levels** in the Minecraft panel. GiftStream uses a separate `MinecraftDropper/servers/<version>` folder, then generates **GiftStream Dropper 100 Levels 2.0**: a 10×10 field of 100 distinct colored shafts, each with three deterministic, shifting glass obstacles and a water checkpoint. A stage banner displays `LEVEL n / 100`. When the configured streamer lands in that stage's water pool, GiftStream recognizes the landing and automatically teleports them to the next stage; completing stage 100 records a victory. Gift actions can still move a player forward/back or reset to level 1. Old five-shaft Dropper installations are migrated by clearing only their former five documented shaft bounds and replacing them with the 100-level map; other world areas are preserved. The map is generated locally rather than copied from a third-party download. GitHub searches during this research did not surface a redistributable, maintained 100-stage map source, so the built-in map is an original vanilla implementation inspired by the familiar drop-through-obstacle format—not a claim to bundle a specific creator's popular map. The vanilla server does not load Bukkit/Paper plugins, and no plugin or mod is needed for audience actions or automatic progression.

The built-in **Dropper rules** preset includes Punch II, jump to a higher/lower level, return to level 1, slow, and high jump. The action editor also offers the timed effects used by Parkour: slow, darkness, jump plus slow-falling, resistance, and cleanse. There is no speed boost: it disturbed the run more than it helped. Assign a gift/event or test locally after the arena is ready and game control is enabled. Successful water landings advance the configured player automatically; gift actions can skip, reverse, or reset progress.

## One-click setup

In **Minecraft Parkour** or **Minecraft Dropper**, select **Latest stable** or one of the recent official releases, enter your Minecraft nickname, read and accept the Minecraft EULA, then choose **Create and start the server**. GiftStream queries Mojang's official version manifest; snapshots are not offered. Each selected release gets its own server and world folder, so switching versions does not overwrite another version's world. On first setup it:

- downloads the selected official Minecraft server JAR using Mojang's version manifest and verifies its published SHA-1;
- resolves **Latest stable** at setup time and checks that installed Java meets that release's requirement;
- extracts the included 100 Levels world, which has map datapack regions for levels 1–100, then migrates the two training-mode glint item modifiers from the bundled array/`function` form to the typed object (`type`) resource format Minecraft 26.3 expects; the bundled archive is never modified;
- adds a per-player `LEVEL n / 100` prefix to the map's existing actionbar timer, preserving its timer display and leaving the map's optional scoreboard sidebar controls untouched;
- configures and starts the vanilla server bound only to `127.0.0.1:25565`, with Minecraft online authentication and the whitelist disabled. This avoids Mojang session-server 429 errors for this local-only server;
- creates a random RCON password and binds RCON only to `127.0.0.1`.

For servers installed by earlier GiftStream releases, startup migrates `online-mode`, `white-list` and `enforce-whitelist` to `false`; if that server is already running, GiftStream also sends the RCON `whitelist off` command. Restart the server for the authentication-mode change to take effect. Offline authentication is appropriate here only because the Minecraft server listens exclusively on loopback (`127.0.0.1`); do not expose its port to a LAN or the internet. Offline mode uses different player UUIDs than authenticated mode, so existing player-specific inventory/data may not carry over, though the parkour world and scoreboards remain stored locally.

The map works as a datapack and does not require mods, a mod loader, or third-party plugins. The official Minecraft server is downloaded at setup time and is not bundled with GiftStream. GiftStream searches PATH, `JAVA_HOME`, common launcher runtimes (including `.minecraft/runtime`, Horizon, Prism and MultiMC) and running Java game processes. If no compatible runtime is found on Windows, it installs a per-user Adoptium JRE into GiftStream's data folder, verifies its SHA-256, and uses it without requiring administrator rights. Internet access is needed for first setup and the Minecraft EULA must be accepted by the user. The server uses up to 2 GB of memory.

When the server is ready, join from Minecraft Multiplayer using **`localhost:25565`** (or use **Copy address** in GiftStream). This server is intentionally reachable only from the same computer. The dashboard shows the selected Minecraft version and connected player count when RCON is ready. Enable **Send Parkour preset actions to the local game** to allow gifts to trigger game actions. Use **Stop** for a graceful shutdown. In the Minecraft view, **Application and Minecraft logs** captures setup stages, Java/server/map downloads, server start/stop, RCON failures, preset actions, API errors, and browser-side errors. Its copy button also includes the latest JVM output from `giftstream-server.log` in that version's server folder; **Clear** clears both app diagnostics and the server log.

The bundled 100 Levels map was prepared for Minecraft **26.2**. Its `training_mode/glint/disable` and `enable` item modifier files use a JSON array that Minecraft **26.3** rejects; setup now safely converts those two known one-element resources to the expected typed object format (`type: minecraft:set_components`) before launching. This fixes the reported datapack-load failure, but does not certify every map mechanic on every later Minecraft release. If the server exits during startup, GiftStream reports it as stopped/not ready rather than RCON-ready. Stop is safe to repeat when the process has already exited or RCON is unavailable because the server is gone. The launcher checks the server download's hash and never overwrites a non-empty version folder. First-time setup can take longer because GiftStream may need to download the server JAR or install a compatible Java runtime; later starts reuse both. During JVM world/registry warm-up, the dashboard now reports “Minecraft is loading the world and registries…” instead of repeatedly opening RCON connections, and the server uses a smaller initial heap to reduce memory pressure on launch.

## Map reset on every start

Every start of the local server restores the bundled 100 Levels map: the world folder is replaced by a freshly unpacked copy of the map that ships with GiftStream, and the previous world is removed only after the new one is in place. This keeps a stream safe from accidental edits (a broken command block, a hole in the course, blocks left behind by a cage or a test) without any extra action. The dashboard shows the last reset time next to the server status, and the **Reset map** button repeats the reset on demand — it refuses to run while the server is still up, because Minecraft holds the region files open.

## Preset and coin prices

The built-in **Parkour** preset maps:

- Rose (1–29 coins) to a Punch II arrow that always hits: it starts one block in front of the player's chest, on a side that is verified to be free, and flies back into them — so it visibly flies *at* the runner and neither a wall nor a 1-block corridor can block it;
- Donut (30–999 coins) to the next level — a teleport to that level's own checkpoint from the map data;
- Ice Cream (30–999 coins) to the previous level checkpoint;
- Dragon (1000+ coins) to jump **10 levels up at once** and TikTok Universe (1000+ coins) to jump **10 levels back** — one rule each, straight to the real checkpoint of the target level, clamped at level 1 and 100;
- Castle (at least 1,000 coins) to a 60-second reset countdown;
- Lion (at least 1,000 coins) to cancel the countdown;
- Follow to a 20-second jail: the player is lifted into a small floating cage (iron bars with a glass floor and roof) two blocks above the ground for 20 seconds, then dropped back on the exact spot they stood on. Blocks are only placed into air (`keep`) and only the cage material is removed afterwards (`replace`), so the course is never edited and nothing can be destroyed.

The rule editor also offers five timed audience effects: **Slow** (slowness for 7 s), **Darkness** (4 s), **High jump** (jump boost plus slow falling), **Shield** (resistance for 6 s), and **Cleanse** (clears selected negative effects without removing other buffs). They affect only the configured local player and expire automatically. Assign any gift/event to these actions in **Parkour rules**. In the Minecraft panel, start the server, enable Parkour control, then use **Test action** to try an effect locally without waiting for a LIVE event.

### Audience "wow" actions (0.19.0)

Five extra actions are available for both Parkour and Dropper, and the built-in presets already use them:

- **Blackout** (`parkour_blackout` / `dropper_blackout`) — `darkness` + `blindness` for 15 s, so the screen is almost black; used by the default **1,000 taps → blackout** rule. The world time is never changed: the map always looks like day.
- **Lightning** (`*_lightning`) — a single lightning bolt on the runner; used by the default **share → lightning** rule (20 s cooldown).
- **Disco** (`*_disco`) — end-rod and note particles; used by the default **comment "disco"** rule (45 s cooldown).
- **Heart ovation** (`*_heart`) — heart/happy-villager particles and a thank-you action bar; used by the default **follow → heart** rule.

The 1,000-like rule counts likes from **all viewers at once**: enable **Count likes from all viewers** in the rule editor (field `like_global`) and the counter is shared, with the overflow kept for the next threshold. Leave it off to keep the older per-rule counter. Rule order in the editor is editable — drag the `⠿` handle or use the ↑/↓ buttons — and is stored in the preset.

Rules can be reordered in the editor: drag a card by its `⠿` handle or use the ↑/↓ buttons; the order is saved in the preset and used everywhere.

Rules can be edited in GiftStream. Coin thresholds use only an explicit coin price from TikTok's gift catalog. If a catalog entry exposes only `diamond_count` or has no verified coin price, the coin-based rule will not fire for that gift. TikTok gift catalog data and prices can vary by region.

## Transparent LIVE Arena overlay

In **OBS overlay**, choose **LIVE Arena** for a stream HUD inspired by Minecraft gift overlays. It composes the active rule set into left/right gift-action cards, places live counters and the current top donor in the center, and shows the latest real gifts in a bottom strip. The page background remains transparent, so Minecraft footage stays visible behind the modules. It reports actual LIVE connection state and actual session counts; it does not invent win/loss points or viewer activity. Choose landscape (16:9) or portrait (9:16), then use **Move elements** in the preview to drag modules; pull the lower-right handle to resize. Positions are saved independently per canvas and included in the shareable OBS URL.

The overlay editor can hide/show counters, rules, gift strip and top donor, set accent/theme and custom title, and adjust scale, card opacity and density. It adapts to wide and portrait Browser Source canvases. When styling is changed, copy the refreshed URL into OBS/TikTok LIVE Studio if the source does not reload its address automatically. Use the transparency checker in the editor preview to judge card opacity before going live.

## Optional TikTok chat relay

The option **Relay TikTok LIVE comments to the Minecraft chat unchanged** is off by default. When enabled, GiftStream passes the comment text as a JSON-escaped `tellraw` component. It does not prefix a username, trim or otherwise rewrite the message, and never interprets the message as a Minecraft command. The relay is best-effort: it only handles comments actually received by the unofficial TikTokLive connector, and messages over 2,000 characters are rejected rather than truncated.

## Network safety

This is a local streamer-PC feature. `127.0.0.1` is not reachable by viewers or another host. Do not forward or publicly expose Minecraft RCON or the server port. Third-party plugins are not required or automatically installed for either mode. Dropper uses the vanilla server and its own generated world; adding an unrelated Bukkit/Paper plugin would require replacing the server type and a separate compatibility/security review.

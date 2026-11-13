# Minecraft Parkour 100 Levels

GiftStream's only built-in game flow is a local Minecraft Parkour server using the bundled `100-levels-5229-v1.7.4.zip` world.

## One-click setup

In **Minecraft Parkour**, select **Najnowsza stabilna** or one of the recent official releases, enter your Minecraft nickname, read and accept the Minecraft EULA, then choose **Utwórz i uruchom serwer**. GiftStream queries Mojang's official version manifest; snapshots are not offered. Each selected release gets its own server and world folder, so switching versions does not overwrite another version's world. On first setup it:

- downloads the selected official Minecraft server JAR using Mojang's version manifest and verifies its published SHA-1;
- resolves **Najnowsza stabilna** at setup time and checks that installed Java meets that release's requirement;
- extracts the included 100 Levels world, which has map datapack regions for levels 1–100;
- configures and starts the vanilla server bound only to `127.0.0.1:25565`;
- creates a random RCON password and binds RCON only to `127.0.0.1`.

The map works as a datapack and does not require a third-party plugin. The official Minecraft server is downloaded at setup time and is not bundled with GiftStream. Internet access and compatible Java are needed during setup. The server uses up to 2 GB of memory and the Minecraft EULA must be accepted by the user.

When the server is ready, join from Minecraft Multiplayer using **`localhost:25565`** (or use **Kopiuj adres** in GiftStream). This server is intentionally reachable only from the same computer. The dashboard shows the selected Minecraft version and connected player count when RCON is ready. Enable **Wysyłaj akcje presetu parkour do lokalnej gry** to allow gifts to trigger game actions. Use **Zatrzymaj** for a graceful shutdown. The log is `giftstream-server.log` in that version's server folder.

The bundled 100 Levels map was prepared for Minecraft **26.2**. Newer versions are offered so you can use the newest vanilla server, but the map datapack is not independently certified against every Minecraft release; choose the map-matched release for the most predictable behavior. The launcher checks the server download's hash and never overwrites a non-empty version folder.

## Preset and coin prices

The sole built-in preset maps:

- Rose (1–29 Coins) to a small push;
- Donut (30–999 Coins) to the next level;
- Ice Cream (30–999 Coins) to the previous level;
- Castle (at least 1,000 Coins) to a 60-second reset countdown;
- Lion (at least 1,000 Coins) to cancel the countdown;
- Follow to a 20-second jail.

Rules can be edited in GiftStream. Coin thresholds use only an explicit coin price from TikTok's gift catalog. If a catalog entry exposes only `diamond_count` or has no verified coin price, the coin-based rule will not fire for that gift. TikTok gift catalog data and prices can vary by region.

## Optional TikTok chat relay

The option **Przekazuj komentarze TikTok LIVE do czatu Minecraft bez zmian** is off by default. When enabled, GiftStream passes the comment text as a JSON-escaped `tellraw` component. It does not prefix a username, trim or otherwise rewrite the message, and never interprets the message as a Minecraft command. The relay is best-effort: it only handles comments actually received by the unofficial TikTokLive connector, and messages over 2,000 characters are rejected rather than truncated.

## Network safety

This is a local streamer-PC feature. `127.0.0.1` is not reachable by viewers or another host. Do not forward or publicly expose Minecraft RCON or the server port. Third-party plugins are not required for this Parkour flow.

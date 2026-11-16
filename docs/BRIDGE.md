# GiftStream event bridge

GiftStream ships one ready-to-run game integration: **Minecraft Parkour 100 Levels**. The generic event bridge remains available for local tools and custom integrations; it is not a bundled game or a claim of support for additional games.

## WebSocket feed

Connect to `ws://localhost:8000/ws/feed` (use `wss://` behind HTTPS). The feed emits `snapshot`, `event`, `action`, and `status` JSON frames for the GiftStream dashboard and local tools.

## HTTP event webhook

```bash
curl -X POST http://localhost:8000/api/bridge/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"gift","user":"viewer_123","nickname":"Viewer","gift_name":"Rose","diamonds":1,"source":"webhook"}'
```

Supported normalized event types include `gift`, `like`, `follow`, `comment`, `join`, `share`, and `subscribe`. If `GIFTSTREAM_BRIDGE_WEBHOOK_SECRET` is set, send it in the `X-GiftStream-Secret` header. Comments are treated as data; they are never executed as Minecraft console commands.

TikTok viewer purchase price is expressed in Coins. The separate `diamonds` field is creator-side gift value and is not used as a substitute for the viewer's coin price.

## Local output formats

Triggered actions are also sent as UTF-8 JSON datagrams to `127.0.0.1:47821` and appended to GiftStream's local JSONL event file. Bind any listener to loopback. The Minecraft Parkour flow uses its restricted local RCON controller instead; do not expose RCON to a public network.

# GiftStream event bridge

GiftStream currently ships the Minecraft Parkour 100 Levels integration. A generic local event feed is available to external tools; it does not include additional bundled games.

## WebSocket

Connect to `ws://localhost:8000/ws/feed` (use `wss://` on HTTPS). Incoming messages include `snapshot`, `event`, `action`, and `status` kinds.

## HTTP webhook

```bash
curl -X POST http://localhost:8000/api/bridge/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"gift","user":"viewer_123","gift_name":"Rose","diamonds":1,"source":"webhook"}'
```

If `GIFTSTREAM_BRIDGE_WEBHOOK_SECRET` is set, include `-H 'X-GiftStream-Secret: your-secret'`. Event text is treated as untrusted data; GiftStream never executes comments as Minecraft commands.

## UDP and JSONL

The generic local bridge emits JSON action payloads to UDP `127.0.0.1:47821` and appends one action per line to the local JSONL file. Keep any UDP listener on loopback.

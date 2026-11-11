# TipStream Game Bridge

Every matching event becomes a `GameAction` and is broadcast to connected browser games over `/ws/game`. Actions are also sent to UDP `127.0.0.1:47821` and appended to `events.jsonl`.

## WebSocket

Connect to `ws://localhost:8000/ws/game` (use `wss://` on HTTPS). Incoming messages have a `kind` field (`action`, `event`, or `status`) and a `data` object.

## HTTP webhook

```bash
curl -X POST http://localhost:8000/api/bridge/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"gift","user":"viewer_123","gift_name":"Rose","diamonds":1,"source":"webhook"}'
```

If `BRIDGE_WEBHOOK_SECRET` is set, include `-H 'X-TipStream-Secret: your-secret'`. Event types: `gift`, `like`, `follow`, `comment`, `join`, `share`, `subscribe`.

## UDP and JSONL

The UDP payload is the action object, UTF-8 encoded JSON. The JSONL file has one action per line. Keep the UDP listener bound to loopback; it is intended for a local game process.

Action identifiers include `spawn_zombie`, `spawn_enemy`, `spawn_boss`, `boss_raid`, `heal`, `drop_diamond`, `drop_item`, `give_item`, `move_left`, `move_right`, `jump`, `shield`, `speed_boost`, `teleport`, `spawn_wall`, `change_weather`, `change_time`, `screen_shake`, `confetti`, `vote`, and `custom`. Action parameters are an open JSON map. Implement only a safe allow-list in your game adapter; do not execute chat text as commands.

# GiftStream Game Bridge

The bridge sends normalized actions to supported games. Choose one or combine several.

## 1. Browser game (WebSocket)

Open `http://localhost:8000/game`. The game connects to `/ws/game` and receives JSON frames:

```json
{
  "kind": "action",
  "data": {
    "action": "spawn_zombie",
    "params": {"count": 1, "interrupt": false, "alert_text": "Rose = zombie!"},
    "triggered_by": {"type": "gift", "user": "viewer", "gift_name": "Rose"},
    "rule_name": "Rose → Spawn zombie",
    "ts": 1794422400.0
  }
}
```

Events are broadcast as `{ "kind": "event", "data": { ...TikTokEvent } }`.

## 2. HTTP event webhook

Send a TikTok event to the server. It is matched against the active preset and any actions are forwarded to the game clients.

```bash
curl -X POST http://localhost:8000/api/bridge/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"gift","user":"viewer_123","nickname":"Viewer","gift_name":"Rose","diamonds":1,"source":"webhook"}'
```

Supported event `type`: `gift`, `like`, `follow`, `comment`, `join`, `share`, `subscribe`.

For a protected webhook, set `BRIDGE_WEBHOOK_SECRET` in `.env` and send it in the `X-TipStream-Secret` header.

## 3. UDP (localhost only)

Every triggered action is also sent as one UTF-8 JSON datagram to `127.0.0.1:47821`. Your local game/mod can bind that port and parse each datagram. Example payload is the same as the `data` in a WebSocket action frame. GiftStream sends to local loopback so no gameplay command port is exposed to the public network.

## 4. JSONL file

Every action is appended to `events.jsonl` in the project root. Each line is an independent UTF-8 JSON action. A game process may tail this file. Rotate or truncate it between long streams if desired.

## Action names

Built-in action identifiers include `spawn_zombie`, `spawn_enemy`, `spawn_boss`, `boss_raid`, `heal`, `drop_diamond`, `drop_item`, `give_item`, `move_left`, `move_right`, `jump`, `shield`, `speed_boost`, `teleport`, `spawn_wall`, `change_weather`, `change_time`, `screen_shake`, `confetti`, `vote` and `custom`. `params` is an open JSON object: the game adapter decides what fields to honor.

## Minecraft / game-server adapter

For Minecraft, a small local plugin/companion service should receive UDP or HTTP and execute only an allow-listed set of server commands. Do not expose RCON credentials or arbitrary command execution to TikTok events. The first version deliberately provides a generic adapter; a dedicated Minecraft plugin can map actions such as `spawn_zombie` or `give_item` to safe, configured server commands.

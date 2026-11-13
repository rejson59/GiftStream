import asyncio
import threading

from app.diagnostics import _redact
from app.tiktok_connector import TikTokConnector, _is_signing_rate_limit


def test_signing_account_hour_limit_is_classified_as_non_retryable():
    class SignatureRateLimitError(Exception):
        pass

    assert _is_signing_rate_limit(SignatureRateLimitError("too many connections"))
    assert _is_signing_rate_limit(RuntimeError("rate_limit_account_hour"))
    assert not _is_signing_rate_limit(ConnectionError("websocket closed"))


def test_connection_start_is_idempotent_while_client_is_connecting():
    async def run():
        connector = TikTokConnector(lambda _event: asyncio.sleep(0))
        starts = []

        async def fake_start():
            starts.append(1)
            connector.connection_state = "connecting"
            connector._thread = threading.Thread(target=connector._tt_stop.wait, daemon=True)
            connector._thread.start()
            return {"ok": True, "mode": "tiktok", "message": "connecting"}

        connector._start_tiktoklive = fake_start
        first = await connector.start("tiktok", "@ExampleLive")
        original_thread = connector._thread
        second = await connector.start("tiktok", "examplelive")
        assert first["ok"] and second["ok"]
        assert len(starts) == 1
        assert connector._thread is original_thread
        assert "już działa" in second["message"]
        await connector.stop()
        assert connector._thread is None

    asyncio.run(run())


def test_stop_awaits_tiktoklive_async_disconnect():
    async def run():
        connector = TikTokConnector(lambda _event: asyncio.sleep(0))
        loop = asyncio.new_event_loop()
        called = []

        class Client:
            _owned_asyncio_loop = loop

            async def disconnect(self, close_client=False):
                called.append(close_client)

        connector._tt_client = Client()
        connector.mode = "tiktok"
        connector.connection_state = "connected"
        connector.connected = True
        await connector.stop()
        assert called == [True]
        assert connector.connection_state == "disconnected"
        assert not connector.connected
        loop.close()

    asyncio.run(run())


def test_invalid_tiktok_username_is_reported_without_starting_a_thread():
    async def run():
        connector = TikTokConnector(lambda _event: asyncio.sleep(0))
        result = await connector.start("tiktok", "not a valid username")
        assert result["ok"] is False
        assert connector.connection_state == "error"
        assert connector._thread is None

    asyncio.run(run())


def test_diagnostic_redaction_removes_authentication_values():
    message = "Failed wss://example.invalid?apiKey=secret123 access_token:private rcon_password=hidden"
    redacted = _redact(message)
    assert "secret123" not in redacted
    assert "private" not in redacted
    assert "hidden" not in redacted
    assert redacted.count("[REDACTED]") == 3

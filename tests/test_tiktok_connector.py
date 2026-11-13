import asyncio
import threading

from app.diagnostics import _redact
from app.tiktok_connector import TikTokConnector, _is_signing_rate_limit, _is_user_offline, _retry_delay


def test_signing_account_hour_limit_is_classified_as_non_retryable():
    class SignatureRateLimitError(Exception):
        pass

    assert _is_signing_rate_limit(SignatureRateLimitError("too many connections"))
    assert _is_signing_rate_limit(RuntimeError("rate_limit_account_hour"))
    assert not _is_signing_rate_limit(ConnectionError("websocket closed"))


def test_user_offline_is_expected_and_retried_at_a_slow_cadence():
    class UserOfflineError(Exception):
        pass

    assert _is_user_offline(UserOfflineError())
    assert not _is_user_offline(ConnectionError("network disconnected"))
    assert 120 <= _retry_delay(1, user_offline=True) <= 140
    assert 300 <= _retry_delay(4, user_offline=True) <= 320


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

        class WebClient:
            async def close(self):
                called.append("http-closed")

        class WebSocket:
            async def disconnect(self):
                called.append("websocket-disconnected")

        class Client:
            _owned_asyncio_loop = loop
            _web = WebClient()
            _ws = WebSocket()

        connector._tt_client = Client()
        connector.mode = "tiktok"
        connector.connection_state = "connected"
        connector.connected = True
        await connector.stop()
        assert called == ["websocket-disconnected", "http-closed"]
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
    message = "Failed ?apiKey=secret123 access_token:private rcon_password=hidden authorization: Bearer bearer-secret"
    redacted = _redact(message)
    for secret in ("secret123", "private", "hidden", "bearer-secret"):
        assert secret not in redacted
    assert redacted.count("[REDACTED]") == 4

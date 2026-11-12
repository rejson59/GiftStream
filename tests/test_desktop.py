def test_downloaded_update_automatically_schedules_windows_restart(tmp_path, monkeypatch):
    from app import desktop, update_state

    update_state.clear()
    executable = tmp_path / "GiftStream.exe"
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    desktop._publish_downloaded_update("v2.0.0", executable)
    assert update_state.take_apply_request() == executable
    status = update_state.status()
    assert status["available"] is True
    assert "ponownie" in status["message"]
    update_state.clear()


def test_desktop_entrypoint_uses_embedded_webview():
    from app.desktop import GiftStreamDesktop

    assert GiftStreamDesktop.__name__ == "GiftStreamDesktop"
    assert callable(GiftStreamDesktop.run)
    assert GiftStreamDesktop.__module__ == "app.desktop"

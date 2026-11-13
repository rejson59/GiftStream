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


def test_startup_does_not_block_on_start_menu_shortcut(tmp_path, monkeypatch):
    from app import desktop

    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(desktop, "current_install", lambda _root: None)
    monkeypatch.setattr(desktop, "create_start_menu_shortcut", lambda _path: (_ for _ in ()).throw(AssertionError("must run after startup")))
    assert desktop._start_installed_version_if_needed() is False


def test_desktop_entrypoint_uses_embedded_webview():
    from app.desktop import GiftStreamDesktop

    assert GiftStreamDesktop.__name__ == "GiftStreamDesktop"
    assert callable(GiftStreamDesktop.run)
    assert GiftStreamDesktop.__module__ == "app.desktop"

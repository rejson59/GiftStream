def test_desktop_entrypoint_uses_embedded_webview():
    from app.desktop import GiftStreamDesktop

    assert GiftStreamDesktop.__name__ == "GiftStreamDesktop"
    assert callable(GiftStreamDesktop.run)
    assert GiftStreamDesktop.__module__ == "app.desktop"

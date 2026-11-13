from app.myinstants import _InstantParser, search


def test_myinstants_parser_extracts_button_label_and_audio_path():
    parser = _InstantParser()
    parser.feed('<button class="instant" data-url="/media/sounds/test.mp3">Hello <b>there</b></button>')
    assert parser.results == [{"url": "/media/sounds/test.mp3", "name": "Hello there"}]


def test_myinstants_parser_ignores_buttons_without_audio_urls():
    parser = _InstantParser()
    parser.feed('<button class="instant">No audio URL</button><button data-url="/media/sounds/ok.mp3">Okay</button>')
    assert parser.results == [{"url": "/media/sounds/ok.mp3", "name": "Okay"}]


def test_search_returns_only_trusted_myinstants_media_urls(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://www.myinstants.com/en/search/?name=hello"

        def read(self, _size):
            return b'''<button class="instant" data-url="/media/sounds/good.mp3">Good</button>
                        <button class="instant" data-url="https://evil.example/bad.mp3">Bad</button>'''

    monkeypatch.setattr("app.myinstants.urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    assert search("hello") == [{"name": "Good", "url": "https://www.myinstants.com/media/sounds/good.mp3"}]


def test_search_rejects_unexpected_redirect(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://evil.example/"

    monkeypatch.setattr("app.myinstants.urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    import pytest
    with pytest.raises(RuntimeError, match="przekierował"):
        search("hello")

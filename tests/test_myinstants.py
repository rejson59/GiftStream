from app import myinstants


def test_parser_supports_myinstants_play_button_markup_and_data_url_markup():
    page = '''
    <div class="instant" onclick="play('/media/sounds/bruh.mp3')">
      <button><img src="thumb.png"><span>Bruh sound</span></button>
    </div>
    <button class="instant" data-url="/media/sounds/air-horn.ogg" data-name="Air Horn"></button>
    '''
    parser = myinstants._InstantParser()
    parser.feed(page)
    assert parser.results == [
        {"url": "/media/sounds/bruh.mp3", "name": "Bruh sound"},
        {"url": "/media/sounds/air-horn.ogg", "name": "Air Horn"},
    ]


def test_search_extracts_sanitized_results_and_deduplicates(monkeypatch):
    class Response:
        def geturl(self):
            return "https://www.myinstants.com/en/search/?name=bruh"

        def read(self, _limit):
            return b'''<div class="instant" onclick="play('/media/sounds/bruh.mp3')"><button>Bruh!</button></div>
            <button data-url="/media/sounds/bruh.mp3" data-name="Duplicate"></button>
            <button data-url="https://evil.example/media/sounds/evil.mp3" data-name="Evil"></button>'''

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(myinstants.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    results = myinstants.search("bruh")
    assert results == [{"name": "Bruh!", "url": "https://www.myinstants.com/media/sounds/bruh.mp3"}]


def test_normalize_audio_url_rejects_external_hosts_and_path_traversal():
    assert myinstants._normalize_audio_url("https://evil.example/media/sounds/a.mp3") is None
    assert myinstants._normalize_audio_url("/media/sounds/../secret.mp3") is None
    assert myinstants._normalize_audio_url("/media/sounds/valid%20name.mp3") == \
        "https://www.myinstants.com/media/sounds/valid%20name.mp3"


def test_parser_ignores_buttons_without_audio_urls():
    parser = myinstants._InstantParser()
    parser.feed('<button class="instant">No audio URL</button><button data-url="/media/sounds/ok.mp3">Okay</button>')
    assert parser.results == [{"url": "/media/sounds/ok.mp3", "name": "Okay"}]


def test_search_rejects_unexpected_redirect(monkeypatch):
    import pytest

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://evil.example/"

    monkeypatch.setattr(myinstants.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(RuntimeError, match="przekierował"):
        myinstants.search("hello")

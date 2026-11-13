"""Best-effort MyInstants search adapter (unofficial third-party page scraper)."""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BASE_URL = "https://www.myinstants.com"
SEARCH_URL = f"{BASE_URL}/en/search/"
MAX_PAGE_BYTES = 2_000_000
_AUDIO_PATH = re.compile(r'''(?:https?://[^"'\s<>]+)?/media/sounds/[^"'\s<>]*[.](?:mp3|ogg|wav|m4a)''', re.IGNORECASE)


def _audio_from_attrs(attrs: dict[str, str]) -> str:
    for key in ("data-url", "data-audio", "data-sound", "href"):
        value = attrs.get(key, "").strip()
        if "/media/sounds/" in value:
            match = _AUDIO_PATH.search(value)
            if match:
                return match.group(0).replace("\\/", "/")
    for value in attrs.values():
        if "/media/sounds/" in value:
            match = _AUDIO_PATH.search(value)
            if match:
                return match.group(0).replace("\\/", "/")
    return ""


class _InstantParser(HTMLParser):
    """Handle current and older MyInstants markup (data attrs or play() onclick)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._active: dict[str, str] | None = None
        self._active_depth = 0
        self._text: list[str] = []
        self._active_tag = ""
        self._void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): html.unescape(value or "") for key, value in attrs}
        if self._active is not None:
            if tag not in self._void_tags:
                self._active_depth += 1
            return
        if tag not in {"button", "div", "a", "article"}:
            return
        classes = attrs_map.get("class", "").lower().split()
        has_instant_class = any("instant" in name or "sound" in name for name in classes)
        url = _audio_from_attrs(attrs_map)
        # Most MyInstants versions use onclick="play('/media/sounds/name.mp3')"
        # on an instant container, rather than a data-url attribute.
        if not url and (has_instant_class or tag == "button"):
            for key in ("onclick", "data-play", "data-src"):
                value = attrs_map.get(key, "")
                match = _AUDIO_PATH.search(value)
                if match:
                    url = match.group(0).replace("\\/", "/")
                    break
        if not url:
            return
        title = (attrs_map.get("data-name") or attrs_map.get("title")
                 or attrs_map.get("aria-label") or attrs_map.get("alt") or "")
        self._active = {"url": url, "name": title}
        self._active_depth = 1
        self._active_tag = tag
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._active is None:
            return
        if tag not in self._void_tags:
            self._active_depth -= 1
        if self._active_depth <= 0 and tag == self._active_tag:
            item = self._active
            item["name"] = item["name"] or " ".join(" ".join(self._text).split())
            self.results.append(item)
            self._active = None
            self._active_depth = 0
            self._text = []


def _normalize_audio_url(value: str) -> str | None:
    value = html.unescape(value.strip()).replace("\\/", "/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme and (parsed.scheme != "https" or parsed.hostname not in {"myinstants.com", "www.myinstants.com"}):
        return None
    path = urllib.parse.unquote(parsed.path or value)
    if not path.startswith("/media/sounds/") or ".." in path.split("/"):
        return None
    if not re.search(r"\.(?:mp3|ogg|wav|m4a)$", path, re.IGNORECASE):
        return None
    return urllib.parse.urljoin(BASE_URL, urllib.parse.quote(path, safe="/._-()+%"))


def search(query: str, limit: int = 20) -> list[dict[str, str]]:
    query = " ".join((query or "").split())[:100]
    if not query:
        return []
    url = SEARCH_URL + "?" + urllib.parse.urlencode({"name": query})
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; GiftStream/1; sound search)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(request, timeout=12) as response:
        final_url = urllib.parse.urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname not in {"myinstants.com", "www.myinstants.com"}:
            raise RuntimeError("MyInstants przekierował na nieoczekiwany adres.")
        page = response.read(MAX_PAGE_BYTES + 1)
    if len(page) > MAX_PAGE_BYTES:
        raise RuntimeError("Wyniki MyInstants przekraczają dozwolony rozmiar.")
    source = page.decode("utf-8", errors="replace")
    parser = _InstantParser()
    parser.feed(source)
    candidates = parser.results
    # Retain compatibility with JSON/inline-script result formats as the site evolves.
    if not candidates:
        candidates = [{"url": match.group(0), "name": ""} for match in _AUDIO_PATH.finditer(source)]
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        audio_url = _normalize_audio_url(item.get("url", ""))
        if not audio_url or audio_url in seen:
            continue
        seen.add(audio_url)
        name = " ".join(html.unescape(item.get("name", "")).split())
        if not name:
            name = urllib.parse.unquote(urllib.parse.urlparse(audio_url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]).replace("_", " ")
        results.append({"name": name[:120] or "Dźwięk MyInstants", "url": audio_url})
        if len(results) >= max(1, min(30, limit)):
            break
    return results

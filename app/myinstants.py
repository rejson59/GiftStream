"""Best-effort MyInstants search adapter (unofficial third-party page scraper)."""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BASE_URL = "https://www.myinstants.com"
SEARCH_URL = f"{BASE_URL}/en/search/"
MAX_PAGE_BYTES = 1_500_000


class _InstantParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "button":
            return
        data = {key: value or "" for key, value in attrs}
        classes = data.get("class", "").lower().split()
        url = data.get("data-url", "") or data.get("data-audio", "")
        if "instant" not in " ".join(classes) and not url:
            return
        if url:
            self.current = {"url": url, "name": data.get("data-name", "") or data.get("title", "") or data.get("aria-label", "")}
            self.text_parts = []

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self.current is not None:
            item = self.current
            item["name"] = item["name"] or " ".join(" ".join(self.text_parts).split())
            self.results.append(item)
            self.current = None
            self.text_parts = []


def search(query: str, limit: int = 15) -> list[dict[str, str]]:
    query = " ".join((query or "").split())[:100]
    if not query:
        return []
    url = SEARCH_URL + "?" + urllib.parse.urlencode({"name": query})
    request = urllib.request.Request(url, headers={"User-Agent": "GiftStream/1 (sound search)", "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=12) as response:
        final_url = urllib.parse.urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname not in {"myinstants.com", "www.myinstants.com"}:
            raise RuntimeError("MyInstants przekierował na nieoczekiwany adres.")
        page = response.read(MAX_PAGE_BYTES + 1)
    if len(page) > MAX_PAGE_BYTES:
        raise RuntimeError("Wyniki MyInstants przekraczają dozwolony rozmiar.")
    parser = _InstantParser()
    parser.feed(page.decode("utf-8", errors="replace"))
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parser.results:
        path = urllib.parse.urlparse(item["url"])
        if path.scheme or path.netloc or not path.path.startswith("/media/sounds/") or ".." in path.path.split("/"):
            continue
        audio_url = urllib.parse.urljoin(BASE_URL, path.path)
        if not re.search(r"\.(?:mp3|ogg|wav|m4a)$", path.path, re.IGNORECASE) or audio_url in seen:
            continue
        seen.add(audio_url)
        results.append({"name": (item["name"] or "Dźwięk MyInstants")[:120], "url": audio_url})
        if len(results) >= max(1, min(30, limit)):
            break
    return results

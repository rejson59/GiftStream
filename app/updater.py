"""Pobieranie wydania GiftStream z GitHub Releases i bezpieczna instalacja ZIP."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

APP_EXE = "TipStreamApp.exe"
PACKAGE_ASSET = "TipStreamApp-win-x64.zip"
CHECKSUM_ASSET = "checksums.txt"
MAX_PACKAGE_BYTES = 400 * 1024 * 1024


class UpdateError(RuntimeError):
    pass


def valid_release_tag(tag: str) -> bool:
    return bool(re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", tag or ""))


def release_api_url(repository: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise UpdateError("Niepoprawna nazwa repozytorium aktualizacji.")
    return f"https://api.github.com/repos/{repository}/releases/latest"


def _open(url: str, timeout: int = 15) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GiftStream-Updater/1",
            "Accept": "application/vnd.github+json, application/octet-stream, text/plain",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_PACKAGE_BYTES:
            raise UpdateError("Plik aktualizacji jest większy niż dozwolony limit.")
        body = response.read(MAX_PACKAGE_BYTES + 1)
    if len(body) > MAX_PACKAGE_BYTES:
        raise UpdateError("Plik aktualizacji jest większy niż dozwolony limit.")
    return body


def fetch_latest_release(repository: str) -> dict[str, Any]:
    try:
        release = json.loads(_open(release_api_url(repository)))
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f"Nie można sprawdzić wydań GitHub: {exc}") from exc

    tag = str(release.get("tag_name", ""))
    if not valid_release_tag(tag):
        raise UpdateError("Wydanie ma nieprawidłowy numer wersji.")
    assets = {str(a.get("name")): a for a in release.get("assets", [])}
    package = assets.get(PACKAGE_ASSET)
    checksums = assets.get(CHECKSUM_ASSET)
    if not package or not checksums:
        raise UpdateError("Wydanie nie zawiera paczki Windows ani pliku sum kontrolnych.")
    for asset in (package, checksums):
        url = str(asset.get("browser_download_url", ""))
        if not url.startswith("https://github.com/"):
            raise UpdateError("Wydanie zawiera nieprawidłowy adres pobierania.")
    return {"tag": tag, "package_url": package["browser_download_url"],
            "checksum_url": checksums["browser_download_url"]}


def expected_sha256(manifest: str, filename: str = PACKAGE_ASSET) -> str:
    for line in manifest.splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+?)\s*", line)
        if match and match.group(2) == filename:
            return match.group(1).lower()
    raise UpdateError("Nie znaleziono sumy SHA-256 dla paczki aplikacji.")


def _install_archive(package: bytes, tag: str, target_root: Path) -> Path:
    if not valid_release_tag(tag):
        raise UpdateError("Nieprawidłowy tag wydania.")
    target_root.mkdir(parents=True, exist_ok=True)
    version_dir = target_root / "versions" / tag
    version_dir.mkdir(parents=True, exist_ok=True)
    destination = version_dir / APP_EXE

    try:
        with zipfile.ZipFile(__import__("io").BytesIO(package)) as archive:
            matches = [info for info in archive.infolist() if Path(info.filename).name == APP_EXE and not info.is_dir()]
            if len(matches) != 1 or matches[0].file_size > MAX_PACKAGE_BYTES:
                raise UpdateError("Paczka nie zawiera prawidłowego pliku aplikacji.")
            info = matches[0]
            # Odczytujemy tylko oczekiwany plik, nigdy nie wypakowujemy ścieżek z ZIP-a.
            executable = archive.read(info)
    except UpdateError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise UpdateError("Pobrana paczka aktualizacji jest uszkodzona.") from exc

    if len(executable) < 1024 or not executable.startswith(b"MZ"):
        raise UpdateError("Pobrany plik nie wygląda na aplikację Windows.")
    tmp = destination.with_suffix(".exe.new")
    tmp.write_bytes(executable)
    os.replace(tmp, destination)
    metadata = {"tag": tag, "executable": str(destination)}
    metadata_path = target_root / "current.json"
    temp_metadata = metadata_path.with_suffix(".json.new")
    temp_metadata.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    os.replace(temp_metadata, metadata_path)
    return destination


def current_install(data_root: Path) -> tuple[str, Path] | None:
    metadata = data_root / "current.json"
    try:
        info = json.loads(metadata.read_text(encoding="utf-8"))
        tag = str(info.get("tag", ""))
        if valid_release_tag(tag):
            path = data_root / "versions" / tag / APP_EXE
            if path.is_file():
                return tag, path
    except (OSError, ValueError, TypeError):
        pass
    return None


def prepare_latest(repository: str, data_root: Path) -> tuple[str, Path, bool, str]:
    """Zwraca (tag, exe, zaktualizowano, komunikat); działa też offline po instalacji."""
    cached = current_install(data_root)
    try:
        release = fetch_latest_release(repository)
    except UpdateError as exc:
        if cached:
            return cached[0], cached[1], False, f"Nie sprawdzono aktualizacji — uruchamiam zapisaną wersję ({exc})."
        raise

    if cached and cached[0] == release["tag"]:
        return cached[0], cached[1], False, "Masz najnowszą wersję."

    try:
        package = _open(release["package_url"], timeout=45)
        manifest = _open(release["checksum_url"], timeout=15).decode("utf-8-sig")
        expected = expected_sha256(manifest)
        actual = hashlib.sha256(package).hexdigest()
        if not hmac.compare_digest(actual, expected):
            raise UpdateError("Suma SHA-256 paczki się nie zgadza — aktualizacja została odrzucona.")
        installed = _install_archive(package, release["tag"], data_root)
    except UpdateError as exc:
        if cached:
            return cached[0], cached[1], False, f"Odrzucono aktualizację — uruchamiam zapisaną wersję ({exc})."
        raise
    except Exception as exc:
        if cached:
            return cached[0], cached[1], False, f"Aktualizacja się nie powiodła — uruchamiam zapisaną wersję ({exc})."
        raise UpdateError(f"Nie można pobrać aplikacji: {exc}") from exc

    return release["tag"], installed, True, f"Pobrano GiftStream {release['tag']}."

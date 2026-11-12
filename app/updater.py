"""Self-update support for the single-file GiftStream Windows application."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path
from typing import Any

APP_EXE = "GiftStream.exe"
MAX_EXECUTABLE_BYTES = 400 * 1024 * 1024


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
        if length and int(length) > MAX_EXECUTABLE_BYTES:
            raise UpdateError("Plik aktualizacji jest większy niż dozwolony limit.")
        body = response.read(MAX_EXECUTABLE_BYTES + 1)
    if len(body) > MAX_EXECUTABLE_BYTES:
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
    assets = {str(asset.get("name")): asset for asset in release.get("assets", [])}
    executable = assets.get(APP_EXE)
    checksums = assets.get("checksums.txt")
    if not executable or not checksums:
        raise UpdateError("Wydanie nie zawiera GiftStream.exe ani pliku sum kontrolnych.")
    for asset in (executable, checksums):
        url = str(asset.get("browser_download_url", ""))
        if not url.startswith("https://github.com/"):
            raise UpdateError("Wydanie zawiera nieprawidłowy adres pobierania.")
    return {"tag": tag, "executable_url": executable["browser_download_url"],
            "checksum_url": checksums["browser_download_url"]}


def expected_sha256(manifest: str, filename: str = APP_EXE) -> str:
    for line in manifest.splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+?)\s*", line)
        if match and match.group(2) == filename:
            return match.group(1).lower()
    raise UpdateError("Nie znaleziono sumy SHA-256 dla aplikacji.")


def _write_current(data_root: Path, tag: str, destination: Path) -> None:
    metadata = {"tag": tag, "executable": str(destination)}
    metadata_path = data_root / "current.json"
    temporary = metadata_path.with_suffix(".json.new")
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    os.replace(temporary, metadata_path)


def _install_executable(executable: bytes, tag: str, data_root: Path) -> Path:
    if not valid_release_tag(tag):
        raise UpdateError("Nieprawidłowy tag wydania.")
    if len(executable) < 1024 or not executable.startswith(b"MZ"):
        raise UpdateError("Pobrany plik nie wygląda na aplikację Windows.")

    version_dir = data_root / "versions" / tag
    version_dir.mkdir(parents=True, exist_ok=True)
    destination = version_dir / APP_EXE
    temporary_executable = destination.with_suffix(".exe.new")
    temporary_executable.write_bytes(executable)
    os.replace(temporary_executable, destination)
    _write_current(data_root, tag, destination)
    return destination


def cache_running_executable(executable: Path, tag: str, data_root: Path) -> Path:
    """Keep the currently running single-file app available for offline startup."""
    if not valid_release_tag(tag):
        raise UpdateError("Nieprawidłowy numer wersji aplikacji.")
    source = executable.resolve()
    destination = data_root / "versions" / tag / APP_EXE
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source != destination.resolve():
        temporary = destination.with_suffix(".exe.new")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    _write_current(data_root, tag, destination)
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


def prepare_latest(
    repository: str,
    data_root: Path,
    running_executable: Path | None = None,
    running_tag: str = "",
) -> tuple[str, Path, bool, str]:
    """Return the latest verified executable, falling back to the running one offline."""
    cached = current_install(data_root)
    if cached is None and running_executable is not None and running_executable.is_file():
        cached_path = cache_running_executable(running_executable, running_tag, data_root)
        cached = (running_tag, cached_path)

    try:
        release = fetch_latest_release(repository)
    except UpdateError as exc:
        if cached:
            return cached[0], cached[1], False, f"Nie sprawdzono aktualizacji — uruchamiam zapisaną wersję ({exc})."
        raise

    if cached and cached[0] == release["tag"]:
        return cached[0], cached[1], False, "Masz najnowszą wersję."

    try:
        executable = _open(release["executable_url"], timeout=45)
        manifest = _open(release["checksum_url"], timeout=15).decode("utf-8-sig")
        expected = expected_sha256(manifest)
        actual = hashlib.sha256(executable).hexdigest()
        if not hmac.compare_digest(actual, expected):
            raise UpdateError("Suma SHA-256 aplikacji się nie zgadza — aktualizacja została odrzucona.")
        installed = _install_executable(executable, release["tag"], data_root)
    except UpdateError as exc:
        if cached:
            return cached[0], cached[1], False, f"Odrzucono aktualizację — uruchamiam zapisaną wersję ({exc})."
        raise
    except Exception as exc:
        if cached:
            return cached[0], cached[1], False, f"Aktualizacja się nie powiodła — uruchamiam zapisaną wersję ({exc})."
        raise UpdateError(f"Nie można pobrać aplikacji: {exc}") from exc

    return release["tag"], installed, True, f"Pobrano GiftStream {release['tag']}."

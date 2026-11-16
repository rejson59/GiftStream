"""Self-update support for the single-file GiftStream Windows application."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from . import diagnostics

APP_EXE = "GiftStream.exe"
MAX_EXECUTABLE_BYTES = 400 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 4 * 1024 * 1024
DOWNLOAD_WORKERS = 6


class UpdateError(RuntimeError):
    pass


def valid_release_tag(tag: str) -> bool:
    return bool(re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", tag or ""))


def release_api_url(repository: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise UpdateError("Invalid update repository name.")
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
            raise UpdateError("The update file is larger than the allowed limit.")
        body = response.read(MAX_EXECUTABLE_BYTES + 1)
    if len(body) > MAX_EXECUTABLE_BYTES:
        raise UpdateError("The update file is larger than the allowed limit.")
    return body


def _download_range(url: str, start: int, end: int, total: int) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "GiftStream-Updater/1",
        "Accept": "application/octet-stream",
        "Range": f"bytes={start}-{end}",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        if getattr(response, "status", response.getcode()) != 206:
            raise UpdateError("The server does not support range downloads.")
        expected_range = f"bytes {start}-{end}/{total}"
        if response.headers.get("Content-Range", "").strip() != expected_range:
            raise UpdateError("The server returned an invalid update chunk.")
        chunk = response.read(end - start + 2)
    if len(chunk) != end - start + 1:
        raise UpdateError("Niekompletny fragment aktualizacji.")
    return chunk


def download_executable(url: str, on_progress: Callable[[int, str], None] | None = None) -> bytes:
    """Download an update using parallel HTTP ranges, with a safe full-download fallback."""
    request = urllib.request.Request(url, headers={
        "User-Agent": "GiftStream-Updater/1",
        "Accept": "application/octet-stream",
        "Range": "bytes=0-0",
    })
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            status = getattr(response, "status", response.getcode())
            if status == 200:  # Server ignored Range and already sent the complete executable.
                data = response.read(MAX_EXECUTABLE_BYTES + 1)
                if len(data) > MAX_EXECUTABLE_BYTES:
                    raise UpdateError("The update file is larger than the allowed limit.")
                if on_progress:
                    on_progress(100, "Update download finished.")
                return data
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes 0-0/(\d+)", content_range.strip())
            probe = response.read(2)
            if status != 206 or not match or len(probe) != 1:
                raise ValueError("Partial download is unsupported")
            total = int(match.group(1))
            if total > MAX_EXECUTABLE_BYTES:
                raise UpdateError("The update file is larger than the allowed limit.")
    except UpdateError:
        raise
    except Exception:
        data = _open(url, timeout=45)
        if on_progress:
            on_progress(100, "Update download finished.")
        return data

    ranges = [(start, min(total - 1, start + DOWNLOAD_CHUNK_BYTES - 1))
              for start in range(0, total, DOWNLOAD_CHUNK_BYTES)]
    pieces: list[bytes | None] = [None] * len(ranges)
    done = 0
    progress_lock = threading.Lock()
    try:
        with ThreadPoolExecutor(max_workers=min(DOWNLOAD_WORKERS, len(ranges))) as pool:
            futures = {pool.submit(_download_range, url, start, end, total): index
                       for index, (start, end) in enumerate(ranges)}
            for future in as_completed(futures):
                pieces[futures[future]] = future.result()
                with progress_lock:
                    done += len(pieces[futures[future]] or b"")
                    percent = min(99, int(done * 100 / max(1, total)))
                if on_progress:
                    on_progress(percent, f"Downloading the update: {percent}%")
    except Exception:
        # Some release hosts/proxies do not honor Range reliably. Restart as one
        # bounded streaming read rather than leave a corrupted or partial update.
        data = _open(url, timeout=45)
        if on_progress:
            on_progress(100, "Update download finished.")
        return data

    if any(piece is None for piece in pieces):
        raise UpdateError("Could not download all update chunks.")
    executable = b"".join(piece for piece in pieces if piece is not None)
    if len(executable) != total:
        raise UpdateError("The downloaded update size does not match the server.")
    if on_progress:
        on_progress(100, "Update download finished.")
    return executable


def fetch_latest_release(repository: str) -> dict[str, Any]:
    try:
        release = json.loads(_open(release_api_url(repository), timeout=6))
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f"Cannot check the GitHub releases: {exc}") from exc

    tag = str(release.get("tag_name", ""))
    if not valid_release_tag(tag):
        raise UpdateError("The release has an invalid version number.")
    assets = {str(asset.get("name")): asset for asset in release.get("assets", [])}
    executable = assets.get(APP_EXE)
    checksums = assets.get("checksums.txt")
    if not executable or not checksums:
        raise UpdateError("The release contains neither GiftStream.exe nor a checksum file.")
    for asset in (executable, checksums):
        url = str(asset.get("browser_download_url", ""))
        if not url.startswith("https://github.com/"):
            raise UpdateError("The release contains an invalid download URL.")
    return {"tag": tag, "executable_url": executable["browser_download_url"],
            "checksum_url": checksums["browser_download_url"]}


def expected_sha256(manifest: str, filename: str = APP_EXE) -> str:
    for line in manifest.splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+?)\s*", line)
        if match and match.group(2) == filename:
            return match.group(1).lower()
    raise UpdateError("No SHA-256 checksum found for the application.")


def _write_current(data_root: Path, tag: str, destination: Path) -> None:
    metadata = {"tag": tag, "executable": str(destination)}
    metadata_path = data_root / "current.json"
    temporary = metadata_path.with_suffix(".json.new")
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    os.replace(temporary, metadata_path)


def _install_executable(executable: bytes, tag: str, data_root: Path) -> Path:
    if not valid_release_tag(tag):
        raise UpdateError("Invalid release tag.")
    if len(executable) < 1024 or not executable.startswith(b"MZ"):
        raise UpdateError("The downloaded file does not look like a Windows application.")

    version_dir = data_root / "versions" / tag
    version_dir.mkdir(parents=True, exist_ok=True)
    # Only the new build and the one before it are worth keeping on disk.
    prune_versions(data_root, protected=(tag,))
    destination = version_dir / APP_EXE
    temporary_executable = destination.with_suffix(".exe.new")
    temporary_executable.write_bytes(executable)
    os.replace(temporary_executable, destination)
    _write_current(data_root, tag, destination)
    return destination


def cache_running_executable(executable: Path, tag: str, data_root: Path) -> Path:
    """Keep the currently running single-file app available for offline startup."""
    if not valid_release_tag(tag):
        raise UpdateError("Invalid application version number.")
    source = executable.resolve()
    destination = data_root / "versions" / tag / APP_EXE
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source != destination.resolve():
        temporary = destination.with_suffix(".exe.new")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    _write_current(data_root, tag, destination)
    prune_versions(data_root, protected=(tag,))
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
    on_progress: Callable[[int, str], None] | None = None,
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
            return cached[0], cached[1], False, f"The update check was skipped — starting the installed version ({exc})."
        raise

    if cached and cached[0] == release["tag"]:
        return cached[0], cached[1], False, "You have the newest version."

    try:
        if on_progress:
            on_progress(0, "Downloading the update in several parallel streams…")
        # The small checksum and large EXE travel concurrently to save a network round trip.
        with ThreadPoolExecutor(max_workers=2) as pool:
            executable_future = pool.submit(download_executable, release["executable_url"], on_progress)
            manifest_future = pool.submit(_open, release["checksum_url"], 12)
            executable = executable_future.result()
            manifest = manifest_future.result().decode("utf-8-sig")
        expected = expected_sha256(manifest)
        actual = hashlib.sha256(executable).hexdigest()
        if not hmac.compare_digest(actual, expected):
            raise UpdateError("The application SHA-256 checksum does not match — the update was rejected.")
        installed = _install_executable(executable, release["tag"], data_root)
    except UpdateError as exc:
        if cached:
            return cached[0], cached[1], False, f"Update rejected — starting the installed version ({exc})."
        raise
    except Exception as exc:
        if cached:
            return cached[0], cached[1], False, f"The update failed — starting the installed version ({exc})."
        raise UpdateError(f"Cannot download the application: {exc}") from exc

    return release["tag"], installed, True, f"Downloaded GiftStream {release['tag']}."


def _version_key(tag: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", tag or "")
    return tuple(int(part) for part in numbers[:3]) if numbers else ()


def prune_versions(data_root: Path, keep_previous: int = 1,
                   protected: tuple[str, ...] | set[str] = ()) -> list[str]:
    """Delete old version folders, keeping the current one and one step back.

    Every update used to leave its ``versions/<tag>/GiftStream.exe`` behind, so a
    few weeks of updates could quietly fill the disk with dozens of 35 MB copies.
    The newest installed version, the one directly below it and the running /
    about-to-start version always stay, so a bad update can still be rolled back
    by hand. Anything that is not a version folder is never touched.
    """
    versions_root = data_root / "versions"
    if not versions_root.is_dir():
        return []
    candidates: list[tuple[tuple[int, ...], str, Path]] = []
    for folder in versions_root.iterdir():
        if not folder.is_dir() or not valid_release_tag(folder.name):
            continue
        candidates.append((_version_key(folder.name), folder.name, folder))
    if not candidates:
        return []
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)

    keep: set[str] = {tag for tag in protected if tag}
    for _key, name, _folder in candidates[: 1 + max(0, keep_previous)]:
        keep.add(name)
    current = current_install(data_root)
    if current:
        keep.add(current[0])
    removed: list[str] = []
    for _key, name, folder in candidates:
        if name in keep:
            continue
        try:
            shutil.rmtree(folder)
        except OSError as exc:
            diagnostics.warning("Could not remove the old version %s: %s", folder, exc)
            continue
        removed.append(name)
    if removed:
        diagnostics.info("Removed %d old GiftStream versions, keeping %s.", len(removed), ", ".join(sorted(keep)))
    return removed

"""Thread-safe update status shared by the desktop host and the local web UI."""
from __future__ import annotations

import threading
from pathlib import Path

_lock = threading.Lock()
_apply_requested = threading.Event()
_pending_executable: Path | None = None
_state: dict[str, str | bool] = {
    "available": False,
    "tag": "",
    "message": "",
}


def publish_update(tag: str, executable: Path) -> None:
    global _pending_executable
    with _lock:
        _pending_executable = executable
        _state.update({
            "available": True,
            "tag": tag,
            "message": f"GiftStream {tag} pobrano. Aktualizacja uruchomi się automatycznie przy następnym starcie aplikacji.",
        })


def status() -> dict[str, str | bool]:
    with _lock:
        return dict(_state)


def request_apply() -> bool:
    with _lock:
        if not _state["available"] or _pending_executable is None:
            return False
        _apply_requested.set()
        return True


def take_apply_request() -> Path | None:
    if not _apply_requested.is_set():
        return None
    _apply_requested.clear()
    with _lock:
        return _pending_executable


def clear() -> None:
    global _pending_executable
    with _lock:
        _pending_executable = None
        _state.update({"available": False, "tag": "", "message": ""})
        _apply_requested.clear()

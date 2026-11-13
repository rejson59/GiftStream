"""Small, copyable, redacted diagnostics for the desktop app."""
from __future__ import annotations

import logging
import re
import threading
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .paths import data_dir

_LOG_PATH = data_dir() / "giftstream.log"
_MAX_ENTRIES = 600
_MAX_ENTRY_CHARS = 8000
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|cookie|rcon[_-]?password)"
    r"(\s*[=:]\s*)([^&\s,;]+)"
)
_RING: deque[str] = deque(maxlen=_MAX_ENTRIES)
_LOCK = threading.RLock()
_LOGGER = logging.getLogger("giftstream")
_CONFIGURED = False


def _redact(value: str) -> str:
    return _SECRET_RE.sub(r"\1\2[REDACTED]", value)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = _redact(record.getMessage())
            record.args = ()
            if record.exc_info:
                record.exc_text = _redact(logging.Formatter().formatException(record.exc_info))
        except Exception:
            pass
        return True


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = _redact(self.format(record))[:_MAX_ENTRY_CHARS]
            with _LOCK:
                _RING.append(line)
        except Exception:
            self.handleError(record)


class _MirrorHandler(logging.Handler):
    """Mirror upstream logger records into GiftStream's copyable diagnostics."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name == _LOGGER.name:
                return
            message = f"[{record.name}] {record.getMessage()}"
            _LOGGER.log(record.levelno, message, exc_info=record.exc_info)
        except Exception:
            self.handleError(record)


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False
    _LOGGER.addFilter(_RedactFilter())
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    ring = _RingHandler()
    ring.setFormatter(formatter)
    _LOGGER.addHandler(ring)
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(_LOG_PATH, maxBytes=1_500_000, backupCount=2, encoding="utf-8")
        file_handler.setFormatter(formatter)
        _LOGGER.addHandler(file_handler)
    except OSError:
        # Keep in-memory logs available if the user's data folder is read-only.
        pass
    _CONFIGURED = True


def log(level: int, message: str, *args: Any, exc_info: Any = None) -> None:
    _configure()
    _LOGGER.log(level, message, *args, exc_info=exc_info)


def info(message: str, *args: Any) -> None:
    log(logging.INFO, message, *args)


def warning(message: str, *args: Any) -> None:
    log(logging.WARNING, message, *args)


def error(message: str, *args: Any, exc_info: Any = None) -> None:
    log(logging.ERROR, message, *args, exc_info=exc_info)


def attach_logger(name: str) -> None:
    _configure()
    target = logging.getLogger(name)
    if not any(getattr(handler, "_giftstream_mirror", False) for handler in target.handlers):
        handler = _MirrorHandler()
        handler._giftstream_mirror = True  # type: ignore[attr-defined]
        target.addHandler(handler)


def get_logs(limit: int = 300) -> list[str]:
    _configure()
    limit = max(1, min(int(limit), _MAX_ENTRIES))
    with _LOCK:
        return list(_RING)[-limit:]


def clear_logs() -> None:
    _configure()
    with _LOCK:
        _RING.clear()
    try:
        _LOG_PATH.write_text("", encoding="utf-8")
        for index in (1, 2):
            Path(f"{_LOG_PATH}.{index}").unlink(missing_ok=True)
    except OSError:
        pass

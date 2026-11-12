"""Native GiftStream window with an embedded web UI and local FastAPI backend."""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
import webview

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import update_state
from app.main import app
from app.paths import data_dir, installed_release_tag
from app.shortcuts import create_start_menu_shortcut
from app.updater import prepare_latest
from app.version import RELEASE_TAG

GITHUB_REPOSITORY = os.environ.get("GIFTSTREAM_GITHUB_REPOSITORY", "rejson59/GiftStream")
UPDATE_CHECK_SECONDS = 30 * 60
FIRST_UPDATE_CHECK_SECONDS = 15


class GiftStreamDesktop:
    def __init__(self) -> None:
        self.port = self._choose_port(8000)
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.server = uvicorn.Server(uvicorn.Config(
            app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
            use_colors=False,
        ))
        self.server_thread = threading.Thread(target=self._serve, name="GiftStream API", daemon=True)
        self.update_thread = threading.Thread(target=self._update_loop, name="GiftStream updater", daemon=True)
        self.stop_event = threading.Event()
        self.window = None
        self.current_tag = installed_release_tag()

    @staticmethod
    def _choose_port(preferred: int) -> int:
        for port in [preferred, *range(preferred + 1, preferred + 21)]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _serve(self) -> None:
        try:
            asyncio.run(self.server.serve())
        except Exception:
            self.server.should_exit = True

    def _wait_for_server(self) -> bool:
        self.server_thread.start()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not self.stop_event.is_set():
            if self.server.started:
                return True
            if not self.server_thread.is_alive():
                return False
            self.stop_event.wait(0.1)
        return bool(self.server.started)

    def _update_loop(self) -> None:
        next_check = time.monotonic() + FIRST_UPDATE_CHECK_SECONDS
        while not self.stop_event.is_set():
            manual_check = update_state.take_check_request()
            if manual_check or time.monotonic() >= next_check:
                update_state.begin_check()
                message = "Nie udało się sprawdzić aktualizacji. Spróbuj ponownie później."
                try:
                    tag, executable, updated, message = prepare_latest(GITHUB_REPOSITORY, data_dir())
                    if updated and tag != self.current_tag:
                        create_start_menu_shortcut(executable)
                        update_state.publish_update(tag, executable)
                except Exception as exc:
                    # Network trouble must never interrupt the running stream or UI.
                    message = f"Nie udało się sprawdzić aktualizacji: {exc}"
                finally:
                    update_state.finish_check(message)
                next_check = time.monotonic() + UPDATE_CHECK_SECONDS

            pending = update_state.take_apply_request()
            if pending is not None and self._apply_update(pending):
                return
            remaining = max(0.05, next_check - time.monotonic())
            self.stop_event.wait(min(0.25, remaining))

    def _apply_update(self, executable: Path) -> bool:
        if os.name != "nt":
            return False
        try:
            create_start_menu_shortcut(executable)
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen([str(executable)], cwd=str(data_dir()), creationflags=flags, close_fds=True)
            self.stop()
            return True
        except OSError:
            # Keep the downloaded update available so it can be retried at next launch.
            return False

    def stop(self) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self.server.should_exit = True
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass

    def run(self) -> None:
        data_dir()
        if not self._wait_for_server():
            raise RuntimeError("Nie udało się uruchomić lokalnego serwera GiftStream.")

        self.window = webview.create_window(
            "GiftStream",
            f"{self.base_url}/?desktop=1",
            width=1440,
            height=920,
            min_size=(1024, 700),
            background_color="#0b0b0d",
            text_select=True,
        )
        self.window.events.closed += self.stop
        self.update_thread.start()
        try:
            # Windows uses the native Edge WebView2 control; no external browser tab is opened.
            webview.start(gui="edgechromium", debug=False, http_server=False)
        except Exception as exc:
            if os.name == "nt":
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(
                        0,
                        f"Nie udało się uruchomić okna GiftStream. Sprawdź, czy Microsoft Edge WebView2 jest dostępny w systemie.\n\n{exc}",
                        "GiftStream",
                        0x10,
                    )
                except Exception:
                    pass
            raise
        finally:
            self.stop()
            self.server_thread.join(timeout=5)
            update_state.clear()


def _start_installed_version_if_needed() -> bool:
    """Self-update this app before showing its UI, then point Start Menu at it."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return False

    running_executable = Path(sys.executable).resolve()
    try:
        _tag, latest_executable, _updated, _message = prepare_latest(
            GITHUB_REPOSITORY,
            data_dir(),
            running_executable=running_executable,
            running_tag=RELEASE_TAG,
        )
    except Exception:
        # A first launch without network still runs the executable the user opened.
        create_start_menu_shortcut(running_executable)
        return False

    create_start_menu_shortcut(latest_executable)
    if latest_executable.resolve() == running_executable:
        return False

    flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        subprocess.Popen([str(latest_executable)], cwd=str(data_dir()), creationflags=flags, close_fds=True)
        return True
    except OSError:
        return False


def main() -> None:
    if not _start_installed_version_if_needed():
        GiftStreamDesktop().run()


if __name__ == "__main__":
    main()

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
from app.updater import prepare_latest

GITHUB_REPOSITORY = os.environ.get("TIPSTREAM_GITHUB_REPOSITORY", "rejson59/GiftStream")
UPDATE_CHECK_SECONDS = 60 * 60
FIRST_UPDATE_CHECK_SECONDS = 90


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
        if self.stop_event.wait(FIRST_UPDATE_CHECK_SECONDS):
            return
        while not self.stop_event.is_set():
            try:
                tag, executable, updated, _message = prepare_latest(GITHUB_REPOSITORY, data_dir())
                if updated and tag != self.current_tag:
                    update_state.publish_update(tag, executable)
            except Exception:
                # Network trouble must never interrupt the running stream or UI.
                pass

            next_check = time.monotonic() + UPDATE_CHECK_SECONDS
            while not self.stop_event.is_set():
                pending = update_state.take_apply_request()
                if pending is not None and self._apply_update(pending):
                    return
                remaining = next_check - time.monotonic()
                if remaining <= 0:
                    break
                self.stop_event.wait(min(0.5, remaining))

    @staticmethod
    def _ps_quote(value: str | Path) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def _apply_update(self, executable: Path) -> bool:
        if os.name != "nt":
            return False
        script_path = data_dir() / "restart_giftstream.ps1"
        script = (
            f"$oldPid = {os.getpid()}\n"
            f"while (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {{ Start-Sleep -Seconds 1 }}\n"
            f"Start-Process -FilePath {self._ps_quote(executable)} -WorkingDirectory {self._ps_quote(data_dir())}\n"
            f"Remove-Item -LiteralPath {self._ps_quote(script_path)} -Force -ErrorAction SilentlyContinue\n"
        )
        try:
            script_path.write_text(script, encoding="utf-8")
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                creationflags=flags,
                close_fds=True,
            )
            self.stop()
            return True
        except OSError:
            # Keep the downloaded update available so the user can retry.
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
                        f"Nie udało się uruchomić okna GiftStream. Zainstaluj aplikację instalatorem, który przygotowuje Microsoft Edge WebView2.\n\n{exc}",
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


def main() -> None:
    GiftStreamDesktop().run()


if __name__ == "__main__":
    main()

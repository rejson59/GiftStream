"""Proste okno desktopowe: uruchamia lokalne API i otwiera panel GiftStream."""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path

import uvicorn

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.paths import data_dir, installed_release_tag
from app.updater import prepare_latest

GITHUB_REPOSITORY = os.environ.get("TIPSTREAM_GITHUB_REPOSITORY", "rejson59/GiftStream")
UPDATE_CHECK_SECONDS = 60 * 60


class TipStreamDesktop:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("GiftStream")
        self.root.geometry("470x365")
        self.root.resizable(False, False)
        self.root.configure(bg="#0b0b0d")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)
        self.port = self._choose_port(8000)
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=self.port, log_level="warning",
            access_log=False, use_colors=False,
        ))
        self.server_thread = threading.Thread(target=self._serve, name="GiftStream API", daemon=True)
        self.server_error: str | None = None
        self.current_tag = installed_release_tag()
        self.pending_executable: Path | None = None
        self._update_check_running = False

        outer = tk.Frame(self.root, bg="#0b0b0d", padx=27, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="giftstream", bg="#0b0b0d", fg="#f2f1ef",
                 font=("Segoe UI", 23, "bold")).pack(anchor="w")
        tk.Label(outer, text="PREZENTY Z LIVE STERUJĄ GRĄ", bg="#0b0b0d", fg="#a0a0a7",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 15))

        self.status = tk.StringVar(value="Uruchamiam lokalny serwer…")
        tk.Label(outer, textvariable=self.status, bg="#151518", fg="#d8d8dc",
                 font=("Segoe UI", 10), padx=13, pady=11, anchor="w", justify="left",
                 wraplength=382).pack(fill="x")

        actions = tk.Frame(outer, bg="#0b0b0d")
        actions.pack(fill="x", pady=(16, 0))
        self._button(actions, "Otwórz panel", self.open_dashboard, primary=True).pack(fill="x", pady=(0, 7))
        row = tk.Frame(actions, bg="#0b0b0d")
        row.pack(fill="x")
        self._button(row, "Otwórz grę demo", lambda: self.open_path("/game")).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._button(row, "Adres nakładki OBS", self.copy_overlay).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.update_button = self._button(actions, "Pobierz i zastosuj aktualizację", self.apply_update, primary=True)
        self.update_button.pack(fill="x", pady=(8, 0))
        self.update_button.pack_forget()
        tk.Label(outer, text=f"Lokalnie: {self.base_url}  ·  wersja {self.current_tag}",
                 bg="#0b0b0d", fg="#66666e", font=("Consolas", 8)).pack(anchor="w", pady=(15, 0))

        self.server_thread.start()
        self.root.after(250, self._poll_server)
        # Po starcie sprawdza wydania okresowo; pobieranie nie zatrzymuje LIVE.
        self.root.after(90_000, self._check_for_updates)

    @staticmethod
    def _button(parent: tk.Widget, text: str, command, primary: bool = False) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command, relief="flat", padx=12, pady=9,
            bg="#c3f53c" if primary else "#1d1d21",
            fg="#11130b" if primary else "#e5e5e8",
            activebackground="#d9ff7a" if primary else "#29292e",
            font=("Segoe UI", 9, "bold"), cursor="hand2",
        )

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
        except Exception as exc:
            self.server_error = str(exc)

    def _poll_server(self) -> None:
        if self.server.started:
            self.status.set(f"● GiftStream działa. Symulator jest gotowy.\n{self.base_url}")
            # Otwórz dashboard automatycznie po starcie, bez blokowania aplikacji.
            self.root.after(450, self.open_dashboard)
            return
        if not self.server_thread.is_alive():
            self.status.set(f"Nie udało się uruchomić serwera: {self.server_error or 'nieznany błąd'}")
            return
        self.root.after(250, self._poll_server)

    def open_dashboard(self) -> None:
        webbrowser.open_new_tab(self.base_url)

    def open_path(self, path: str) -> None:
        webbrowser.open_new_tab(f"{self.base_url}{path}")

    def copy_overlay(self) -> None:
        url = f"{self.base_url}/overlay?template=grid"
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.status.set(f"Skopiowano adres nakładki OBS:\n{url}")

    def _check_for_updates(self) -> None:
        if self._update_check_running:
            self.root.after(UPDATE_CHECK_SECONDS * 1000, self._check_for_updates)
            return
        self._update_check_running = True
        threading.Thread(target=self._update_worker, name="GiftStream update check", daemon=True).start()

    def _update_worker(self) -> None:
        try:
            tag, executable, updated, message = prepare_latest(GITHUB_REPOSITORY, data_dir())
            if updated and tag != self.current_tag:
                self.root.after(0, lambda: self._update_ready(tag, executable))
        except Exception:
            # Utrata sieci podczas transmisji nie może zatrzymać działającej gry.
            pass
        finally:
            self._update_check_running = False
            try:
                self.root.after(UPDATE_CHECK_SECONDS * 1000, self._check_for_updates)
            except tk.TclError:
                pass

    def _update_ready(self, tag: str, executable: Path) -> None:
        self.pending_executable = executable
        self.status.set(f"Pobrano aktualizację GiftStream {tag}. Zastosuj ją po zakończeniu transmisji.")
        self.update_button.pack(fill="x", pady=(8, 0))

    def apply_update(self) -> None:
        if not self.pending_executable:
            return
        if os.name != "nt":
            self.status.set("Aktualizacja zostanie uruchomiona przy następnym starcie launchera.")
            return
        script_path = data_dir() / "restart_giftstream.ps1"
        ps_quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        script = (
            f"$oldPid = {os.getpid()}\n"
            f"while (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {{ Start-Sleep -Seconds 1 }}\n"
            f"Start-Process -FilePath {ps_quote(self.pending_executable)} -WorkingDirectory {ps_quote(data_dir())}\n"
            f"Remove-Item -LiteralPath {ps_quote(script_path)} -Force -ErrorAction SilentlyContinue\n"
        )
        try:
            script_path.write_text(script, encoding="utf-8")
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden",
                              "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                             creationflags=flags, close_fds=True)
            self.stop()
        except OSError as exc:
            self.status.set(f"Nie udało się przygotować aktualizacji: {exc}")

    def stop(self) -> None:
        if self.server.started:
            self.server.should_exit = True
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    data_dir()
    TipStreamDesktop().run()


if __name__ == "__main__":
    main()

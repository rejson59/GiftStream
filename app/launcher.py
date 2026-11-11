"""Windows bootstrapper: checks GitHub Releases, verifies ZIP and starts TipStream."""
from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

# PyInstaller builds this as a one-file entry script inside the app package.
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.paths import data_dir
from app.updater import UpdateError, prepare_latest

GITHUB_REPOSITORY = os.environ.get("TIPSTREAM_GITHUB_REPOSITORY", "rejson59/TipStream")


class Launcher:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("TipStream — aktualizator")
        self.root.geometry("390x190")
        self.root.resizable(False, False)
        self.root.configure(bg="#0b0b0d")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.status = tk.StringVar(value="Sprawdzam aktualizacje TipStream…")

        outer = tk.Frame(self.root, bg="#0b0b0d", padx=24, pady=20)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="tipstream", fg="#f2f1ef", bg="#0b0b0d",
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(outer, textvariable=self.status, fg="#b5b5bb", bg="#0b0b0d",
                 font=("Segoe UI", 10), wraplength=335, justify="left").pack(anchor="w", pady=(10, 13))
        self.progress = ttk.Progressbar(outer, mode="indeterminate", length=335)
        self.progress.pack(anchor="w", pady=(0, 12))
        self.progress.start(12)
        self.retry = tk.Button(outer, text="Spróbuj ponownie", command=self.start_check,
                               bg="#c3f53c", fg="#11130b", relief="flat", padx=12, pady=6,
                               font=("Segoe UI", 9, "bold"))
        self.retry.pack(anchor="e")
        self.retry.pack_forget()
        self.root.after(150, self.start_check)

    def start_check(self) -> None:
        self.retry.pack_forget()
        self.progress.pack(anchor="w", pady=(0, 12))
        self.progress.start(12)
        self.status.set("Sprawdzam najnowszą wersję na GitHubie…")
        threading.Thread(target=self._prepare, daemon=True).start()

    def _prepare(self) -> None:
        try:
            tag, executable, updated, message = prepare_latest(GITHUB_REPOSITORY, data_dir())
            self.root.after(0, lambda: self._launch(tag, executable, updated, message))
        except UpdateError as exc:
            self.root.after(0, lambda: self._failed(str(exc)))
        except Exception as exc:  # nie pozwól, aby nieoczekiwany błąd zamknął launcher bez komunikatu
            self.root.after(0, lambda: self._failed(f"Nie udało się uruchomić TipStream: {exc}"))

    def _launch(self, tag: str, executable: Path, updated: bool, message: str) -> None:
        try:
            self.status.set(f"{message}\nUruchamiam TipStream {tag}…")
            subprocess.Popen([str(executable)], cwd=str(data_dir()), close_fds=True)
            self.root.after(650, self.root.destroy)
        except OSError as exc:
            self._failed(f"Nie udało się uruchomić aplikacji: {exc}")

    def _failed(self, message: str) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.status.set(f"{message}\n\nSprawdź połączenie z internetem i spróbuj ponownie.")
        self.retry.pack(anchor="e")

    def close(self) -> None:
        self.progress.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    Launcher().run()


if __name__ == "__main__":
    main()

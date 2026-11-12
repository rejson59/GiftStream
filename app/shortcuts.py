"""Create the GiftStream Start Menu shortcut from inside the application."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _powershell_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def create_start_menu_shortcut(executable: Path) -> bool:
    """Point the user's Start Menu entry directly at the current GiftStream app."""
    if os.name != "nt":
        return False
    appdata_value = os.environ.get("APPDATA")
    if not appdata_value:
        return False
    appdata = Path(appdata_value)
    shortcut = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "GiftStream.lnk"
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$link = $shell.CreateShortcut({_powershell_literal(shortcut)}); "
        f"$link.TargetPath = {_powershell_literal(executable.resolve())}; "
        f"$link.WorkingDirectory = {_powershell_literal(executable.resolve().parent)}; "
        f"$link.IconLocation = {_powershell_literal(str(executable.resolve()) + ',0')}; "
        "$link.Save()"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            timeout=20,
            creationflags=flags,
            capture_output=True,
            text=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False

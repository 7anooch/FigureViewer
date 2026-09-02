from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def resolve_path(path_str: str) -> Path:
    return Path(os.path.expanduser(path_str.strip())).resolve()


def pick_directory_dialog(initial: Optional[str] = None) -> Optional[str]:
    """Open a native folder picker in a subprocess (safe with Streamlit threads)."""
    initial_path = initial if initial and Path(initial).exists() else str(Path.home())

    if sys.platform == "darwin":
        script = 'POSIX path of (choose folder with prompt "Select folder")'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        chosen = result.stdout.strip()
        return str(Path(chosen).resolve()) if chosen else None

    if sys.platform.startswith("linux"):
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=Select folder"],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        chosen = result.stdout.strip()
        return str(Path(chosen).resolve()) if chosen else None

    if os.name == "nt":
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$dialog.SelectedPath = '{initial_path.replace(chr(39), chr(39) + chr(39))}'; "
            "if ($dialog.ShowDialog() -eq 'OK') { Write-Output $dialog.SelectedPath }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        chosen = result.stdout.strip()
        return str(Path(chosen).resolve()) if chosen else None

    return None


def folder_dialog_available() -> bool:
    if sys.platform == "darwin":
        return True
    if sys.platform.startswith("linux"):
        from shutil import which

        return which("zenity") is not None
    if os.name == "nt":
        return True
    return False


def folder_dialog_hint() -> str:
    if sys.platform == "darwin":
        return "Opens the macOS folder picker."
    if sys.platform.startswith("linux"):
        return "Requires `zenity` (install if Browse is disabled)."
    if os.name == "nt":
        return "Opens the Windows folder picker."
    return "Not available on this platform; type a path instead."

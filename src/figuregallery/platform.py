from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def reveal_in_file_manager(path: Path) -> None:
    path = path.expanduser().resolve()
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=False)
        return
    if os.name == "nt":
        subprocess.run(["explorer", "/select,", str(path)], check=False)
        return
    subprocess.run(["xdg-open", str(path.parent)], check=False)


def open_folder_in_file_manager(path: Path) -> None:
    path = path.expanduser().resolve()
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
        return
    if os.name == "nt":
        subprocess.run(["explorer", str(path)], check=False)
        return
    subprocess.run(["xdg-open", str(path)], check=False)

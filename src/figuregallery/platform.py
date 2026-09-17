from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _qt_plugin_candidates() -> list[Path]:
    """Likely Qt6 plugin roots, conda-forge first, then pip's bundled Qt6."""
    candidates: list[Path] = [
        Path(sys.prefix) / "lib" / "qt6" / "plugins",
        Path(sys.prefix) / "Library" / "plugins",  # some osx layouts
    ]
    try:
        import PyQt6

        candidates.append(Path(PyQt6.__file__).resolve().parent / "Qt6" / "plugins")
    except ImportError:
        pass
    return candidates


def configure_qt_plugins() -> None:
    """Ensure Qt6 finds matching platform plugins (cocoa / windows / xcb).

    Mixed installs fail with ``Could not find the Qt platform plugin "cocoa"``:
    conda ``pyqt6`` + ``qt6-main`` (e.g. 6.8) plus pip ``PyQt6-Qt6`` (e.g. 6.9)
    makes Qt look at pip's 6.9 plugins, which it then rejects as incompatible.
    Prefer conda-forge's ``{prefix}/lib/qt6/plugins`` when present.
    """
    try:
        from PyQt6.QtCore import QCoreApplication
    except ImportError:
        return

    plugins = next((p for p in _qt_plugin_candidates() if (p / "platforms").is_dir()), None)
    if plugins is None:
        return

    paths = [str(plugins)]
    for existing in QCoreApplication.libraryPaths():
        if existing not in paths:
            paths.append(existing)
    QCoreApplication.setLibraryPaths(paths)
    os.environ["QT_PLUGIN_PATH"] = str(plugins)


def warn_if_bad_qt_macos_cursor() -> None:
    """Qt 6.11.0/6.11.1 can abort on macOS when widgets set the I-beam cursor (QTBUG-147602)."""
    if sys.platform != "darwin":
        return
    try:
        from PyQt6.QtCore import QT_VERSION_STR
    except ImportError:
        return
    if QT_VERSION_STR in {"6.11.0", "6.11.1"}:
        print(
            f"warning: Qt {QT_VERSION_STR} on macOS can crash when focusing text fields "
            "(Directories… search, etc.; QTBUG-147602). "
            "Upgrade with: conda install -n figviewer -c conda-forge 'qt6-main>=6.11.2'",
            file=sys.stderr,
        )


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

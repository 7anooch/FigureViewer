from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from figuregallery.platform import configure_qt_plugins

configure_qt_plugins()

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from figureviewer.desktop.mode_shell import ModeController, resolve_initial_mode
from figureviewer.desktop.modes import AppMode


def _apply_app_icon(app: QApplication) -> None:
    for env_key in ("FIGUREVIEWER_APP_ICON", "FIGUREGALLERY_APP_ICON"):
        icon_path = os.environ.get(env_key, "").strip()
        if icon_path and Path(icon_path).is_file():
            app.setWindowIcon(QIcon(icon_path))
            return


def run(
    *,
    mode: AppMode | str | None = None,
    initial_root: Path | None = None,
    browse_kwargs: dict[str, Any] | None = None,
    default_mode: AppMode = AppMode.COMPARE,
) -> int:
    """Launch the unified desktop app (Compare + Browse modes)."""
    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication(sys.argv)
    assert app is not None
    app.setApplicationName("Figure Viewer")
    app.setOrganizationName("figureviewer")
    _apply_app_icon(app)

    kwargs = dict(browse_kwargs or {})
    if initial_root is not None:
        kwargs.setdefault("initial_root", initial_root)

    initial = resolve_initial_mode(mode=mode, default=default_mode)
    ModeController(app, initial_mode=initial, browse_kwargs=kwargs)
    if not owns_app:
        # Embedded / test host already owns the event loop.
        return 0
    return app.exec()

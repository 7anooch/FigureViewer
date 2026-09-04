from __future__ import annotations

import os
import sys
from pathlib import Path

from figuregallery.platform import configure_qt_plugins

configure_qt_plugins()

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from figuregallery.models import GroupMode, SortMode
from figuregallery.ui.main_window import MainWindow


def run(
    *,
    initial_root: Path | None = None,
    group_mode: GroupMode = GroupMode.STEM,
    sort_mode: SortMode = SortMode.CATEGORY_THEN_PATH,
) -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Figure Gallery")
    app.setOrganizationName("figuregallery")
    icon_path = os.environ.get("FIGUREGALLERY_APP_ICON", "").strip()
    if icon_path and Path(icon_path).is_file():
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow(
        initial_root=initial_root,
        group_mode=group_mode,
        sort_mode=sort_mode,
    )
    window.show()
    return app.exec()

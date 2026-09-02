from __future__ import annotations

import sys
from pathlib import Path

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
    window = MainWindow(
        initial_root=initial_root,
        group_mode=group_mode,
        sort_mode=sort_mode,
    )
    window.show()
    return app.exec()

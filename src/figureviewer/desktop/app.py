from __future__ import annotations

import sys

from figuregallery.platform import configure_qt_plugins

configure_qt_plugins()

from PyQt6.QtWidgets import QApplication

from figureviewer.desktop.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Figure Viewer")
    app.setOrganizationName("figureviewer")
    window = MainWindow()
    window.show()
    return app.exec()

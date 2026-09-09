"""Unified desktop shell: swap Compare / Browse windows in one QApplication."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar

from figureviewer.desktop.modes import AppMode
from figureviewer.settings import load_desktop_mode, save_desktop_mode


class ModeController:
    """Owns the single visible main window and switches modes without quitting."""

    def __init__(
        self,
        app: QApplication,
        *,
        initial_mode: AppMode,
        browse_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._app = app
        self._browse_kwargs = dict(browse_kwargs or {})
        self._window: QMainWindow | None = None
        self._mode: AppMode | None = None
        self._geometry: QByteArray | None = None
        self._switching = False
        self.show(initial_mode)

    @property
    def mode(self) -> AppMode | None:
        return self._mode

    @property
    def window(self) -> QMainWindow | None:
        return self._window

    def show(self, mode: AppMode) -> None:
        if self._switching:
            return
        if mode == self._mode and self._window is not None:
            return

        self._switching = True
        prev_quit = self._app.quitOnLastWindowClosed()
        self._app.setQuitOnLastWindowClosed(False)
        try:
            if self._window is not None:
                self._geometry = self._window.saveGeometry()
                self._window.close()
                self._window.deleteLater()
                self._window = None
                self._app.processEvents()

            window = self._build_window(mode)
            self._install_mode_chrome(window, mode)
            if self._geometry is not None:
                window.restoreGeometry(self._geometry)
            self._window = window
            self._mode = mode
            save_desktop_mode(mode.value)
            window.show()
            window.raise_()
            window.activateWindow()
        finally:
            self._app.setQuitOnLastWindowClosed(prev_quit)
            self._switching = False

    def _build_window(self, mode: AppMode) -> QMainWindow:
        if mode is AppMode.COMPARE:
            from figureviewer.desktop.main_window import MainWindow

            window = MainWindow()
            window.setWindowTitle("Figure Viewer — Compare")
            return window

        from figuregallery.ui.main_window import MainWindow

        window = MainWindow(**self._browse_kwargs)
        window.setWindowTitle("Figure Viewer — Browse")
        return window

    def _install_mode_chrome(self, window: QMainWindow, mode: AppMode) -> None:
        other = AppMode.BROWSE if mode is AppMode.COMPARE else AppMode.COMPARE
        label = "Browse" if other is AppMode.BROWSE else "Compare"
        shortcut = "Ctrl+2" if other is AppMode.BROWSE else "Ctrl+1"
        tip = (
            "Switch to gallery Browse mode"
            if other is AppMode.BROWSE
            else "Switch to multi-panel Compare mode"
        )

        switch = QAction(label, window)
        switch.setShortcut(QKeySequence(shortcut))
        native = switch.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        switch.setToolTip(f"{tip} ({native})")
        switch.triggered.connect(lambda: self.show(other))

        menu = window.menuBar().addMenu("Mode")
        menu.addAction(switch)

        toolbars = window.findChildren(QToolBar)
        toolbar = toolbars[0] if toolbars else None
        if toolbar is None:
            toolbar = QToolBar("Mode", window)
            toolbar.setMovable(False)
            window.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        else:
            toolbar.addSeparator()
        toolbar.addAction(switch)


def resolve_initial_mode(
    *,
    mode: AppMode | str | None = None,
    default: AppMode = AppMode.COMPARE,
) -> AppMode:
    if mode is not None:
        return mode if isinstance(mode, AppMode) else AppMode.parse(mode)
    saved = load_desktop_mode()
    if saved:
        try:
            return AppMode.parse(saved)
        except ValueError:
            pass
    return default

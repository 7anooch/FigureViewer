from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from figuregallery.platform import reveal_in_file_manager
from figuregallery.ui.nav_controls import NavControls
from figureviewer.desktop.directory_navigator import DirectoryNavigator
from figureviewer.desktop.export_panel import ExportPanel
from figureviewer.desktop.metadata_panel import MetadataPanel
from figureviewer.desktop.settings_panel import SettingsPanel
from figureviewer.desktop.shortcuts import empty_state_html, shortcuts_help_text
from figureviewer.desktop.viewport import MultiPanelViewport
from figureviewer.display_state import get_viewport_snapshot
from figureviewer.settings import load_default_browse_root, load_sticky_prefs, save_sticky_prefs
from figureviewer.viewer_state import ViewerState


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Figure Viewer")
        self.resize(1280, 800)
        overrides = dict(load_sticky_prefs())
        saved_root = load_default_browse_root()
        if saved_root:
            overrides["browse_root"] = saved_root
            overrides["tree_stack"] = [saved_root]
        self._state = ViewerState(**overrides)

        self._settings = SettingsPanel(self._state)
        self._export = ExportPanel(self._state)
        self._navigator = DirectoryNavigator(self._state)
        self._viewport = MultiPanelViewport()
        self._nav = NavControls()
        self._current_label = QLabel()
        self._current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._metadata = MetadataPanel()

        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(8, 8, 8, 8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.addWidget(self._settings)
        inner_layout.addWidget(self._export)
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        side_layout.addWidget(scroll)

        figure_col = QWidget()
        figure_layout = QVBoxLayout(figure_col)
        figure_layout.setContentsMargins(0, 0, 0, 0)
        figure_layout.addWidget(self._viewport, stretch=1)
        figure_layout.addWidget(self._nav)
        figure_layout.addWidget(self._current_label)
        self._zoom_hint = QLabel()
        self._zoom_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_hint.setStyleSheet("color: #666; font-size: 12px;")
        self._zoom_hint.hide()
        figure_layout.addWidget(self._zoom_hint)
        figure_layout.addWidget(self._metadata)

        # Slide-in navigator sits beside figures (hidden by default — no vertical tax).
        right = QWidget()
        right_row = QHBoxLayout(right)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(4)
        right_row.addWidget(self._navigator)
        right_row.addWidget(figure_col, stretch=1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(sidebar)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 980])
        self.setCentralWidget(splitter)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        dirs_action = QAction("Directories", self)
        dirs_action.setShortcut(QKeySequence("Ctrl+D"))
        dirs_action.setToolTip("Show or hide the directory navigator (also `)")
        dirs_action.triggered.connect(self._toggle_navigator)
        toolbar.addAction(dirs_action)

        reveal_label = "Reveal in Finder" if sys.platform == "darwin" else "Show in folder"
        reveal_action = QAction(reveal_label, self)
        reveal_action.setShortcut(QKeySequence("Ctrl+E"))
        reveal_action.triggered.connect(self._reveal_current)
        toolbar.addAction(reveal_action)
        self._reveal_action = reveal_action

        self._settings.settings_changed.connect(self._on_settings_changed)
        self._settings.go_first.connect(self._go_first)
        self._settings.go_last.connect(self._go_last)
        self._settings.remove_panel.connect(self._remove_panel)
        self._settings.clear_panels.connect(self._clear_panels)
        self._navigator.panels_changed.connect(self._on_panels_changed)
        self._navigator.closed.connect(self._viewport.focus_display)
        self._export.export_dir_changed.connect(self._persist_sticky_prefs)
        self._viewport.local_index_changed.connect(self._on_local_index)
        self._viewport.zoom_hint_changed.connect(self._on_zoom_hint)
        self._nav.index_changed.connect(self._set_index)

        self._build_shortcuts()
        self._status.showMessage(
            shortcuts_help_text(for_console=False).replace("\n", "  ·  "),
            12000,
        )
        self._refresh_view()

    def _build_shortcuts(self) -> None:
        # Window-level figure nav — stays active even if focus drifts to the nav
        # slider / chrome. Disabled while typing or while the directory navigator
        # has focus (so ←/→/Space keep their navigator meanings).
        self._figure_nav_shortcuts: list[QShortcut] = []

        def _nav_shortcut(key: QKeySequence | str | Qt.Key, slot) -> None:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)
            self._figure_nav_shortcuts.append(sc)

        def _zoom_shortcut(key: QKeySequence | str | Qt.Key, slot) -> None:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)

        _nav_shortcut(Qt.Key.Key_Left, self._go_prev)
        _nav_shortcut(Qt.Key.Key_Right, self._go_next)
        _nav_shortcut(Qt.Key.Key_Space, self._go_next)
        _nav_shortcut(Qt.Key.Key_Home, self._go_first)
        _nav_shortcut(Qt.Key.Key_End, self._go_last)
        _nav_shortcut("Ctrl+Left", self._go_first)
        _nav_shortcut("Ctrl+Right", self._go_last)
        _zoom_shortcut("Ctrl+=", lambda: self._viewport.zoom_by(1.25))
        _zoom_shortcut("Ctrl++", lambda: self._viewport.zoom_by(1.25))
        _zoom_shortcut("Ctrl+-", lambda: self._viewport.zoom_by(1.0 / 1.25))
        _zoom_shortcut("Ctrl+0", self._viewport.reset_zoom)

        toggle = QShortcut(QKeySequence(Qt.Key.Key_QuoteLeft), self)
        toggle.setContext(Qt.ShortcutContext.WindowShortcut)
        toggle.activated.connect(self._toggle_panel_focus)

        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._sync_figure_nav_shortcuts)
        self._sync_figure_nav_shortcuts()

    @staticmethod
    def _is_text_entry(widget: QWidget | None) -> bool:
        w = widget
        while w is not None:
            if isinstance(
                w, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)
            ):
                return True
            w = w.parentWidget()
        return False

    def _sync_figure_nav_shortcuts(self, *args) -> None:  # noqa: ANN002
        del args
        sync = bool(self._state.get("sync_mode", True))
        nav_focus = self._navigator.is_open() and self._navigator.has_panel_focus()
        text = self._is_text_entry(QApplication.focusWidget())
        enabled = sync and not nav_focus and not text
        for sc in self._figure_nav_shortcuts:
            sc.setEnabled(enabled)

    def _toggle_navigator(self) -> None:
        if self._navigator.is_open():
            self._navigator.close_picker()
            self._viewport.focus_display()
        else:
            root = Path(self._state.get("browse_root") or Path.home())
            self._navigator.open_for(root)

    def _toggle_panel_focus(self) -> None:
        # ` cycles: figures ↔ open/focus directory navigator (Gallery root-picker pattern).
        if self._navigator.is_open() and self._navigator.has_panel_focus():
            self._navigator.close_picker()
            self._viewport.focus_display()
        elif self._navigator.is_open():
            self._navigator.focus_list()
        else:
            root = Path(self._state.get("browse_root") or Path.home())
            self._navigator.open_for(root)

    def _persist_sticky_prefs(self) -> None:
        save_sticky_prefs(
            display_mode=self._state.get("display_mode"),
            pdf_dpi=self._state.get("pdf_dpi"),
            custom_width=self._state.get("custom_width"),
            trim_whitespace=self._state.get("trim_whitespace"),
            columns_per_row=self._state.get("columns_per_row"),
            export_output_dir=self._state.get("export_output_dir") or None,
            export_pdf_dpi=self._state.get("export_pdf_dpi"),
        )

    def _reveal_current(self) -> None:
        path = self._viewport.focused_figure_path()
        if path is None or not path.exists():
            title = "Reveal in Finder" if sys.platform == "darwin" else "Show in folder"
            QMessageBox.information(
                self,
                title,
                "No figure is loaded to reveal. Select panels and navigate to a figure first.",
            )
            return
        reveal_in_file_manager(path)
        self._status.showMessage(f"Revealed {path.name}", 4000)

    def _on_zoom_hint(self, text: str) -> None:
        if text:
            if self._zoom_hint.text() != text:
                self._zoom_hint.setText(text)
            if not self._zoom_hint.isVisible():
                self._zoom_hint.show()
        else:
            self._zoom_hint.clear()
            self._zoom_hint.hide()

    def _on_settings_changed(self) -> None:
        self._persist_sticky_prefs()
        self._refresh_view()

    def _on_panels_changed(self) -> None:
        self._settings.refresh_panels()
        self._export.sync_default_dir()
        self._state["current_index"] = 0
        self._refresh_view()

    def _remove_panel(self, path: str) -> None:
        dirs = [
            d
            for d in self._state.get("panel_directories", [])
            if str(Path(d).resolve()) != str(Path(path).resolve())
        ]
        self._state["panel_directories"] = dirs
        if self._navigator.is_open():
            self._navigator.open_for(Path(self._state.get("browse_root") or Path.home()))
        self._on_panels_changed()

    def _clear_panels(self) -> None:
        self._state["panel_directories"] = []
        if self._navigator.is_open():
            self._navigator.open_for(Path(self._state.get("browse_root") or Path.home()))
        self._on_panels_changed()

    def _on_local_index(self, key: str, value: int) -> None:
        self._state[key] = value
        self._refresh_view()

    def _set_index(self, index: int) -> None:
        if not self._state.get("sync_mode", True):
            return
        self._state["current_index"] = index
        self._viewport.note_navigate(
            panel_count=len(self._state.get("panel_directories", []) or [])
        )
        self._refresh_view()
        # Defer until after deleteLater cleanup from show_snapshot.
        QTimer.singleShot(0, self._viewport.focus_display)
        self._sync_figure_nav_shortcuts()

    def _go_prev(self) -> None:
        self._set_index(max(0, int(self._state.get("current_index", 0)) - 1))

    def _go_next(self) -> None:
        self._set_index(int(self._state.get("current_index", 0)) + 1)

    def _go_first(self) -> None:
        self._set_index(0)

    def _go_last(self) -> None:
        self._set_index(int(self._state.get("max_index", 0)))

    def _prefetch_neighbors(self) -> None:
        if not self._state.get("sync_mode", True):
            return
        index = int(self._state.get("current_index", 0))
        total = int(self._state.get("max_index", 0)) + 1
        if total <= 1:
            return
        radius = self._viewport._pacing.budget.prefetch_radius
        paths: list[Path] = []
        offsets = [
            o
            for pair in zip(range(1, radius + 1), range(-1, -radius - 1, -1))
            for o in pair
        ]
        for offset in offsets:
            neighbor = index + offset
            if neighbor < 0 or neighbor >= total:
                continue
            snap = get_viewport_snapshot(self._state, index=neighbor)
            if snap is None:
                continue
            for path in snap.figure_paths:
                if path is not None:
                    paths.append(path)
        self._viewport.prefetch_paths(paths)

    def _refresh_view(self) -> None:
        self._viewport.set_display_options(
            display_mode=str(self._state.get("display_mode", "Fill panel")),
            custom_width=int(self._state.get("custom_width", 700)),
            pdf_dpi=int(self._state.get("pdf_dpi", 200)),
            trim=bool(self._state.get("trim_whitespace", False)),
        )
        sync_mode = bool(self._state.get("sync_mode", True))
        self._nav.setEnabled(sync_mode)
        snapshot = get_viewport_snapshot(self._state)
        if snapshot is None:
            dirs = self._state.get("panel_directories", [])
            raw_dirs = [Path(p) for p in dirs]
            missing = [str(p) for p in raw_dirs if not p.expanduser().exists()]
            if not dirs:
                self._viewport.show_message(empty_state_html(), rich=True)
            elif missing:
                self._viewport.show_message(
                    "Some panel directories are missing:\n" + "\n".join(missing[:5])
                    + (f"\n… and {len(missing) - 5} more" if len(missing) > 5 else "")
                )
            elif sync_mode and self._state.get("match_by") == "filename stem":
                self._viewport.show_message(
                    "No common filename stems across the selected panels."
                )
            else:
                self._viewport.show_message("No figures found in the selected directories.")
            self._nav.set_total(0)
            self._current_label.setText(
                "Unsynced: use each panel’s slider." if not sync_mode and dirs else ""
            )
            self._metadata.set_panels(None)
            self._reveal_action.setEnabled(False)
            return

        self._state["max_index"] = max(snapshot.total - 1, 0)
        self._state["current_index"] = snapshot.index
        self._nav.set_total(snapshot.total, index=snapshot.index)
        if sync_mode:
            self._current_label.setText(f"Current: {snapshot.current_label}")
        else:
            self._current_label.setText("Unsynced: use each panel’s slider (global ←/→ disabled).")
        self._viewport.show_snapshot(snapshot, sync_mode=sync_mode)
        if sync_mode:
            self._prefetch_neighbors()
        if self._state.get("show_metadata") and snapshot.panels:
            self._metadata.set_panels(list(snapshot.panels))
        else:
            self._metadata.set_panels(None)
        self._settings.refresh_panels()
        self._reveal_action.setEnabled(any(p is not None for p in snapshot.figure_paths))

        raw_dirs = [Path(p) for p in self._state.get("panel_directories", [])]
        missing = [str(p) for p in raw_dirs if not p.expanduser().exists()]
        if missing:
            self._status.showMessage(
                f"Missing panel director{'y' if len(missing) == 1 else 'ies'}: {missing[0]}"
                + (f" (+{len(missing) - 1} more)" if len(missing) > 1 else ""),
                8000,
            )
        self._sync_figure_nav_shortcuts()

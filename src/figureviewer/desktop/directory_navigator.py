from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from figuregallery.ui.root_picker import (
    child_directories,
    drill_into,
    initial_list_parent,
    navigate_up,
)
from figureviewer.figures import parse_panels
from figureviewer.settings import (
    clear_default_browse_root,
    load_default_browse_root,
    load_recent_roots,
    remember_recent_root,
    save_default_browse_root,
)
from figureviewer.viewer_state import ViewerState

_PATH_ROLE = Qt.ItemDataRole.UserRole


class DirectoryNavigator(QWidget):
    """Slide-in nearby/recent directory picker for adding compare panels.

    Hidden by default so it does not steal vertical space from the figure grid.
    Mirrors Gallery’s RootPicker navigation (↑↓ ←→ Enter Esc), but Enter/Space
    toggles panel membership instead of replacing a scan root.
    """

    panels_changed = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, state: ViewerState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._list_parent: Path = Path.home()
        self._selected_path: Path | None = None

        title = QLabel("Directories")
        title.setStyleSheet("font-weight: 600;")

        self._crumb = QLabel()
        self._crumb.setStyleSheet("color: #666; font-size: 12px;")
        self._crumb.setWordWrap(True)

        self._browse_btn = QPushButton("Browse…")
        self._default_check = QCheckBox("Default root")
        self._browse_btn.clicked.connect(self._browse_root)
        self._default_check.toggled.connect(self._on_default_toggled)
        root_row = QHBoxLayout()
        root_row.addWidget(self._browse_btn)
        root_row.addWidget(self._default_check)
        root_row.addStretch(1)

        nearby_label = QLabel("Nearby")
        nearby_label.setStyleSheet("color: #666; font-size: 12px;")
        self._nearby = QListWidget()
        self._nearby.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._nearby.itemDoubleClicked.connect(self._toggle_nearby_item)
        self._nearby.currentItemChanged.connect(self._on_nearby_current_changed)

        recent_label = QLabel("Recent")
        recent_label.setStyleSheet("color: #666; font-size: 12px;")
        self._recent = QListWidget()
        self._recent.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._recent.itemDoubleClicked.connect(self._toggle_recent_item)

        self._toggle_btn = QPushButton("Add / remove as panel")
        self._toggle_btn.clicked.connect(self._toggle_current)

        self._manual = QPlainTextEdit()
        self._manual.setPlaceholderText("Or paste paths, one per line")
        self._manual.setMaximumHeight(56)
        self._apply_manual = QPushButton("Apply manual paths")
        self._apply_manual.clicked.connect(self._apply_manual_paths)

        hint = QLabel("Enter/Space toggle panel · ←/→ up/into · Esc close · ` figures")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(title)
        layout.addWidget(self._crumb)
        layout.addLayout(root_row)
        layout.addWidget(nearby_label)
        layout.addWidget(self._nearby, stretch=2)
        layout.addWidget(recent_label)
        layout.addWidget(self._recent, stretch=1)
        layout.addWidget(self._toggle_btn)
        layout.addWidget(self._manual)
        layout.addWidget(self._apply_manual)
        layout.addWidget(hint)

        self.setMinimumWidth(220)
        self.setMaximumWidth(300)
        self.hide()
        self._install_shortcuts()

    def _install_shortcuts(self) -> None:
        def _sc(key: Qt.Key | str, slot, widget: QWidget) -> None:
            sc = QShortcut(QKeySequence(key), widget)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(slot)

        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            _sc(key, self._toggle_current, self._nearby)
            _sc(key, self._toggle_current, self._recent)
        _sc(Qt.Key.Key_Left, self._go_up, self._nearby)
        _sc(Qt.Key.Key_Right, self._go_into, self._nearby)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(lambda: self.close_picker(notify=True))

        tab = QShortcut(QKeySequence(Qt.Key.Key_Tab), self._nearby)
        tab.setContext(Qt.ShortcutContext.WidgetShortcut)
        tab.activated.connect(self._focus_recent)
        backtab = QShortcut(QKeySequence("Shift+Tab"), self._recent)
        backtab.setContext(Qt.ShortcutContext.WidgetShortcut)
        backtab.activated.connect(self._focus_nearby)
        tab_recent = QShortcut(QKeySequence(Qt.Key.Key_Tab), self._recent)
        tab_recent.setContext(Qt.ShortcutContext.WidgetShortcut)
        tab_recent.activated.connect(self._focus_nearby)

    def is_open(self) -> bool:
        return self.isVisible()

    def has_panel_focus(self) -> bool:
        focus = QApplication.focusWidget()
        return focus is not None and self.isAncestorOf(focus)

    def open_for(self, browse_root: Path | None = None) -> None:
        root = browse_root
        if root is None:
            text = self._state.get("browse_root") or ""
            root = Path(text) if text else None
        self._list_parent = initial_list_parent(root)
        if root is not None:
            try:
                self._selected_path = root.expanduser().resolve()
            except OSError:
                self._selected_path = None
        else:
            recent = load_recent_roots()
            self._selected_path = recent[0] if recent else None
        saved = load_default_browse_root()
        current = str(self._selected_path) if self._selected_path else ""
        self._default_check.blockSignals(True)
        self._default_check.setChecked(bool(saved) and saved == current)
        self._default_check.blockSignals(False)
        self._rebuild_nearby()
        self._rebuild_recent()
        self.show()
        self._focus_nearby()

    def close_picker(self, *, notify: bool = True) -> None:
        if not self.isVisible():
            return
        self.hide()
        if notify:
            self.closed.emit()

    def focus_list(self) -> None:
        if not self.isVisible():
            self.open_for()
            return
        self._focus_nearby()

    def _focus_nearby(self) -> None:
        self._nearby.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if self._nearby.count() > 0 and self._nearby.currentRow() < 0:
            self._nearby.setCurrentRow(0)

    def _focus_recent(self) -> None:
        self._recent.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if self._recent.count() > 0 and self._recent.currentRow() < 0:
            self._recent.setCurrentRow(0)

    def _panel_paths(self) -> set[str]:
        return {str(Path(p).expanduser().resolve()) for p in self._state.get("panel_directories", [])}

    def _rebuild_nearby(self) -> None:
        self._nearby.blockSignals(True)
        self._nearby.clear()
        kids = child_directories(self._list_parent)
        panels = self._panel_paths()
        restore_row = -1
        selected = self._selected_path
        for i, child in enumerate(kids):
            mark = "✓ " if str(child) in panels else ""
            item = QListWidgetItem(f"{mark}{child.name}")
            item.setData(_PATH_ROLE, str(child))
            item.setToolTip(str(child))
            self._nearby.addItem(item)
            if selected is not None and child == selected:
                restore_row = i
        if not kids:
            mark = "✓ " if str(self._list_parent) in panels else ""
            item = QListWidgetItem(f"{mark}{self._list_parent.name} (empty)")
            item.setData(_PATH_ROLE, str(self._list_parent))
            item.setToolTip(str(self._list_parent))
            self._nearby.addItem(item)
            restore_row = 0
            self._selected_path = self._list_parent
        self._crumb.setText(str(self._list_parent))
        self._nearby.blockSignals(False)
        if restore_row >= 0:
            self._nearby.setCurrentRow(restore_row)
        elif self._nearby.count() > 0:
            self._nearby.setCurrentRow(0)
            self._sync_selected_from_nearby()
        self._update_toggle_label()

    def _rebuild_recent(self) -> None:
        self._recent.blockSignals(True)
        self._recent.clear()
        panels = self._panel_paths()
        for path in load_recent_roots():
            mark = "✓ " if str(path) in panels else ""
            item = QListWidgetItem(f"{mark}{path.name}")
            item.setData(_PATH_ROLE, str(path))
            item.setToolTip(str(path))
            self._recent.addItem(item)
        self._recent.blockSignals(False)
        if self._recent.count() > 0:
            self._recent.setCurrentRow(0)

    def _sync_selected_from_nearby(self) -> None:
        item = self._nearby.currentItem()
        if item is None:
            return
        raw = item.data(_PATH_ROLE)
        if isinstance(raw, str):
            self._selected_path = Path(raw)

    def _on_nearby_current_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        raw = current.data(_PATH_ROLE)
        if isinstance(raw, str):
            self._selected_path = Path(raw)
            self._update_toggle_label()

    def _update_toggle_label(self) -> None:
        path = self._current_path()
        if path is None:
            self._toggle_btn.setText("Add / remove as panel")
            return
        is_panel = str(path.resolve()) in self._panel_paths()
        name = path.name or str(path)
        self._toggle_btn.setText(f"{'Remove' if is_panel else 'Add'} “{name}” as panel")

    def _current_path(self) -> Path | None:
        focus = QApplication.focusWidget()
        if focus is self._recent:
            return self._path_from_item(self._recent.currentItem())
        item = self._nearby.currentItem()
        if item is not None:
            return self._path_from_item(item)
        return self._selected_path

    def _path_from_item(self, item: QListWidgetItem | None) -> Path | None:
        if item is None:
            return None
        raw = item.data(_PATH_ROLE)
        if isinstance(raw, str):
            return Path(raw)
        return None

    def _go_into(self) -> None:
        self._sync_selected_from_nearby()
        if self._selected_path is None:
            return
        new_parent, new_sel = drill_into(self._selected_path)
        if new_parent == self._list_parent and new_sel == self._selected_path:
            return
        self._list_parent = new_parent
        self._selected_path = new_sel
        self._rebuild_nearby()

    def _go_up(self) -> None:
        self._sync_selected_from_nearby()
        if self._selected_path is None:
            self._selected_path = self._list_parent
        new_parent, new_sel = navigate_up(
            list_parent=self._list_parent,
            selected=self._selected_path,
        )
        if new_parent == self._list_parent:
            return
        self._list_parent = new_parent
        self._selected_path = new_sel
        self._rebuild_nearby()

    def _toggle_nearby_item(self, item: QListWidgetItem) -> None:
        path = self._path_from_item(item)
        if path is not None:
            self._toggle_path(path)

    def _toggle_recent_item(self, item: QListWidgetItem) -> None:
        path = self._path_from_item(item)
        if path is not None:
            self._toggle_path(path)

    def _toggle_current(self) -> None:
        path = self._current_path()
        if path is not None:
            self._toggle_path(path)

    def _toggle_path(self, path: Path) -> None:
        try:
            resolved = str(path.expanduser().resolve())
        except OSError:
            return
        if not Path(resolved).is_dir():
            return
        dirs = [str(Path(p).expanduser().resolve()) for p in self._state.get("panel_directories", [])]
        if resolved in dirs:
            dirs = [d for d in dirs if d != resolved]
        else:
            dirs.append(resolved)
            remember_recent_root(resolved)
            self._state["browse_root"] = resolved
            self._state["tree_stack"] = [resolved]
        self._state["panel_directories"] = dirs
        self._rebuild_nearby()
        self._rebuild_recent()
        self.panels_changed.emit()

    def _browse_root(self) -> None:
        initial = self._state.get("browse_root") or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select directory", str(initial))
        if not chosen:
            return
        root = Path(chosen).expanduser().resolve()
        if not root.is_dir():
            QMessageBox.warning(self, "Browse", f"Not a directory:\n{root}")
            return
        self._state["browse_root"] = str(root)
        self._state["tree_stack"] = [str(root)]
        remember_recent_root(root)
        if self._default_check.isChecked():
            save_default_browse_root(str(root))
        self.open_for(root)

    def _on_default_toggled(self, checked: bool) -> None:
        if checked:
            path = self._current_path() or Path(self._state.get("browse_root") or Path.home())
            try:
                save_default_browse_root(str(path.resolve()))
            except OSError:
                pass
        else:
            clear_default_browse_root()

    def _apply_manual_paths(self) -> None:
        text = self._manual.toPlainText().replace(";", "\n")
        panels = parse_panels(text.replace(",", "\n") if "\n" not in text else text)
        if not panels:
            QMessageBox.information(self, "Manual paths", "No valid directories found in the pasted text.")
            return
        resolved = [str(p.directory.expanduser().resolve()) for p in panels]
        self._state["panel_directories"] = resolved
        for path in resolved:
            remember_recent_root(path)
        if resolved:
            self._state["browse_root"] = resolved[-1]
            self._state["tree_stack"] = [resolved[-1]]
        self._rebuild_nearby()
        self._rebuild_recent()
        self.panels_changed.emit()

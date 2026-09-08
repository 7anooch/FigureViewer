from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from figuregallery.settings import load_recent_roots

_PATH_ROLE = Qt.ItemDataRole.UserRole


def child_directories(parent: Path) -> list[Path]:
    """Return sorted child directories of parent; empty on error."""
    try:
        resolved = parent.expanduser().resolve()
    except OSError:
        return []
    if not resolved.is_dir():
        return []
    kids: list[Path] = []
    try:
        for entry in resolved.iterdir():
            try:
                if entry.is_dir() and not entry.name.startswith("."):
                    kids.append(entry.resolve())
            except OSError:
                continue
    except OSError:
        return []
    kids.sort(key=lambda p: p.name.lower())
    return kids


def initial_list_parent(scan_root: Path | None) -> Path:
    """Parent whose children are listed when the picker opens."""
    if scan_root is not None:
        try:
            root = scan_root.expanduser().resolve()
            parent = root.parent
            if parent != root:
                return parent
            return root
        except OSError:
            pass
    recent = load_recent_roots()
    if recent:
        try:
            return recent[0].parent
        except OSError:
            pass
    return Path.home().resolve()


def drill_into(selected: Path) -> tuple[Path, Path]:
    """Enter selected: list its children; select first child or selected if empty."""
    target = selected.expanduser().resolve()
    kids = child_directories(target)
    if kids:
        return target, kids[0]
    return target, target


def navigate_up(*, list_parent: Path, selected: Path) -> tuple[Path, Path]:
    """Go up one level; select the folder we left. No-op at filesystem root."""
    try:
        current = list_parent.expanduser().resolve()
        parent = current.parent
    except OSError:
        return list_parent, selected
    if parent == current:
        return current, selected.expanduser().resolve() if selected.exists() else current
    return parent, current


class RootPicker(QWidget):
    """Slide-in panel: nearby sibling dirs + recent roots."""

    root_chosen = pyqtSignal(Path)
    closed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list_parent: Path = Path.home()
        self._selected_path: Path | None = None

        title = QLabel("Roots")
        title.setStyleSheet("font-weight: 600;")

        self._crumb = QLabel()
        self._crumb.setStyleSheet("color: #666; font-size: 12px;")
        self._crumb.setWordWrap(True)

        nearby_label = QLabel("Nearby")
        nearby_label.setStyleSheet("color: #666; font-size: 12px;")
        self._nearby = QListWidget()
        self._nearby.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._nearby.itemDoubleClicked.connect(self._commit_nearby_item)
        self._nearby.currentItemChanged.connect(self._on_nearby_current_changed)

        recent_label = QLabel("Recent")
        recent_label.setStyleSheet("color: #666; font-size: 12px;")
        self._recent = QListWidget()
        self._recent.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._recent.itemDoubleClicked.connect(self._commit_recent_item)

        hint = QLabel("Enter open · Esc close · Tab recent")
        hint.setStyleSheet("color: #888; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        layout.addWidget(self._crumb)
        layout.addWidget(nearby_label)
        layout.addWidget(self._nearby, stretch=2)
        layout.addWidget(recent_label)
        layout.addWidget(self._recent, stretch=1)
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

        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            _sc(key, self._commit_current, self._nearby)
            _sc(key, self._commit_current, self._recent)
        _sc(Qt.Key.Key_Left, self._go_up, self._nearby)
        _sc(Qt.Key.Key_Right, self._go_into, self._nearby)
        esc_self = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_self.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc_self.activated.connect(self.close_picker)

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

    def open_for(self, scan_root: Path | None) -> None:
        self._list_parent = initial_list_parent(scan_root)
        if scan_root is not None:
            try:
                self._selected_path = scan_root.expanduser().resolve()
            except OSError:
                self._selected_path = None
        else:
            recent = load_recent_roots()
            self._selected_path = recent[0] if recent else None
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
        self._focus_nearby()

    def _focus_nearby(self) -> None:
        self._nearby.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if self._nearby.count() > 0 and self._nearby.currentRow() < 0:
            self._nearby.setCurrentRow(0)

    def _focus_recent(self) -> None:
        self._recent.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if self._recent.count() > 0 and self._recent.currentRow() < 0:
            self._recent.setCurrentRow(0)

    def _rebuild_nearby(self) -> None:
        self._nearby.blockSignals(True)
        self._nearby.clear()
        kids = child_directories(self._list_parent)
        restore_row = -1
        selected = self._selected_path
        for i, child in enumerate(kids):
            item = QListWidgetItem(child.name)
            item.setData(_PATH_ROLE, str(child))
            item.setToolTip(str(child))
            self._nearby.addItem(item)
            if selected is not None and child == selected:
                restore_row = i
        if not kids:
            # Empty folder: show the list_parent itself as the only commit target.
            item = QListWidgetItem(f"{self._list_parent.name} (empty)")
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

    def _rebuild_recent(self) -> None:
        self._recent.blockSignals(True)
        self._recent.clear()
        for path in load_recent_roots():
            item = QListWidgetItem(path.name)
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

    def _go_into(self) -> None:
        self._sync_selected_from_nearby()
        if self._selected_path is None:
            return
        new_parent, new_sel = drill_into(self._selected_path)
        if new_parent == self._list_parent and new_sel == self._selected_path:
            # Already as deep as we can go — hand focus back to categories.
            self.close_picker()
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

    def _path_from_item(self, item: QListWidgetItem | None) -> Path | None:
        if item is None:
            return None
        raw = item.data(_PATH_ROLE)
        if isinstance(raw, str):
            return Path(raw)
        return None

    def _commit_nearby_item(self, item: QListWidgetItem) -> None:
        path = self._path_from_item(item)
        if path is not None:
            self._emit_chosen(path)

    def _commit_recent_item(self, item: QListWidgetItem) -> None:
        path = self._path_from_item(item)
        if path is not None:
            self._emit_chosen(path)

    def _commit_current(self) -> None:
        focus = QApplication.focusWidget()
        if focus is self._recent:
            path = self._path_from_item(self._recent.currentItem())
        else:
            self._sync_selected_from_nearby()
            path = self._selected_path
        if path is not None:
            self._emit_chosen(path)

    def _emit_chosen(self, path: Path) -> None:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            return
        if not resolved.is_dir():
            return
        self.hide()
        self.root_chosen.emit(resolved)

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from figuregallery.directory_tree import filter_by_directory_exclusions
from figuregallery.models import Category, FigureRef

_UNAVAILABLE_FG = QBrush(QColor("#999999"))


def visible_category_refs(category: Category, excluded: set[Path]) -> list[FigureRef]:
    refs = category.displayable_refs
    if not excluded:
        return refs
    return filter_by_directory_exclusions(refs, excluded)


def category_is_available(category: Category, excluded: set[Path]) -> bool:
    """True when the category has at least one displayable figure after dir exclusions."""
    if not category.is_selectable:
        return False
    return bool(visible_category_refs(category, excluded))


def category_list_label(category: Category, excluded: set[Path]) -> str:
    """Sidebar label: ``key (n)`` or ``key (visible/total)`` when dirs are filtered."""
    visible = len(visible_category_refs(category, excluded))
    total = category.count
    if excluded and visible != total:
        return f"{category.key} ({visible}/{total})"
    return f"{category.key} ({visible})"


class CategoryPanel(QWidget):
    selection_changed = pyqtSignal()
    category_activated = pyqtSignal(str)
    focus_figure_requested = pyqtSignal()
    open_root_picker_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._categories: dict[str, Category] = {}
        self._selected: set[str] = set()
        self._filter_text = ""
        self._excluded_dirs: set[Path] = set()
        self._hide_unavailable = False

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter categories…")
        # Click only — avoid stealing Tab/focus from the figure viewport.
        self._filter.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._filter.textChanged.connect(self._on_filter_changed)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.viewport().installEventFilter(self)
        # Jump to filter without leaving the categories pane (/ is typed in the filter itself).
        focus_filter = QShortcut(QKeySequence("/"), self._list)
        focus_filter.setContext(Qt.ShortcutContext.WidgetShortcut)
        focus_filter.activated.connect(self.focus_filter)
        toggle_all = QShortcut(QKeySequence(Qt.Key.Key_A), self._list)
        toggle_all.setContext(Qt.ShortcutContext.WidgetShortcut)
        toggle_all.activated.connect(self._toggle_select_all_visible)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            toggle_check = QShortcut(QKeySequence(key), self._list)
            toggle_check.setContext(Qt.ShortcutContext.WidgetShortcut)
            toggle_check.activated.connect(self._toggle_current_check)
        # → from the list hands focus to the figure (← on first figure does the reverse).
        focus_figure = QShortcut(QKeySequence(Qt.Key.Key_Right), self._list)
        focus_figure.setContext(Qt.ShortcutContext.WidgetShortcut)
        focus_figure.activated.connect(self.focus_figure_requested.emit)
        # ← opens the slide-in root picker (sibling / recent roots).
        open_roots = QShortcut(QKeySequence(Qt.Key.Key_Left), self._list)
        open_roots.setContext(Qt.ShortcutContext.WidgetShortcut)
        open_roots.activated.connect(self.open_root_picker_requested.emit)

        self._summary = QLabel("No categories")
        self._summary.setStyleSheet("color: #666; font-size: 12px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Categories")
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(self._filter)
        layout.addWidget(self._list, stretch=1)
        layout.addWidget(self._summary)

        self.setMinimumWidth(220)
        self.setMaximumWidth(320)

    def set_categories(self, categories: dict[str, Category], *, preserve_selection: set[str] | None = None) -> None:
        self._categories = categories
        if preserve_selection is not None:
            self._selected = {
                k
                for k in preserve_selection
                if k in categories and category_is_available(categories[k], self._excluded_dirs)
            }
        else:
            self._prune_unavailable_selection()
        self._rebuild_list()

    def apply_scan(
        self,
        categories: dict[str, Category],
        excluded: set[Path],
        *,
        select_all: bool = False,
        preserve_selection: set[str] | None = None,
    ) -> None:
        """Atomically replace categories + directory exclusions after a scan."""
        self._categories = categories
        self._excluded_dirs = set(excluded)
        if select_all:
            self._selected = {
                key
                for key, category in categories.items()
                if category_is_available(category, self._excluded_dirs)
            }
        elif preserve_selection is not None:
            self._selected = {
                key
                for key in preserve_selection
                if key in categories and category_is_available(categories[key], self._excluded_dirs)
            }
        else:
            self._prune_unavailable_selection()
        self._rebuild_list()

    def set_excluded_directories(self, excluded: set[Path]) -> None:
        """Update labels/summary for Directories… exclusions; drop empty selections."""
        new_excluded = set(excluded)
        if new_excluded == self._excluded_dirs:
            return
        self._excluded_dirs = new_excluded
        pruned = self._prune_unavailable_selection()
        self._rebuild_list()
        if pruned:
            self.selection_changed.emit()

    def set_hide_unavailable(self, hide: bool) -> None:
        """When True, omit empty categories; when False, show them grayed out."""
        hide = bool(hide)
        if hide == self._hide_unavailable:
            return
        self._hide_unavailable = hide
        self._rebuild_list()

    def hide_unavailable(self) -> bool:
        return self._hide_unavailable

    def selected_keys(self) -> set[str]:
        return set(self._selected)

    def select_all_available(self) -> None:
        """Select every category that currently has figures under the dir filter."""
        self._selected = {
            key
            for key, category in self._categories.items()
            if self._is_available(category)
        }
        self._rebuild_list()
        self.selection_changed.emit()

    def select_key(self, key: str) -> bool:
        """Ensure ``key`` is selected if available. Returns True when selection changed."""
        category = self._categories.get(key)
        if category is None or not self._is_available(category):
            return False
        if key in self._selected:
            return False
        self._selected.add(key)
        self._rebuild_list()
        self.selection_changed.emit()
        return True

    def clear(self) -> None:
        self._categories = {}
        self._selected = set()
        self._excluded_dirs = set()
        self._list.clear()
        self._summary.setText("No categories")

    def focus_list(self) -> None:
        self._list.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if self._list.count() > 0 and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)

    def focus_filter(self) -> None:
        self._filter.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._filter.selectAll()

    def has_panel_focus(self) -> bool:
        focus = QApplication.focusWidget()
        return focus is self._list or focus is self._filter

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        # Label click → jump to first figure. Must not rebuild synchronously (PyQt6 abort on macOS).
        if obj is self._list.viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            try:
                if event.button() == Qt.MouseButton.LeftButton:
                    pos = event.position().toPoint()
                    item = self._list.itemAt(pos)
                    if item is not None and not self._is_checkbox_click(item, pos):
                        key = item.data(Qt.ItemDataRole.UserRole)
                        if isinstance(key, str):
                            category = self._categories.get(key)
                            if category is not None and self._is_available(category):
                                QTimer.singleShot(0, lambda k=key: self.category_activated.emit(k))
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _is_checkbox_click(self, item: QListWidgetItem, pos) -> bool:  # noqa: ANN001
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return False
        # Fixed left strip ≈ indicator; avoids fragile SE_ItemViewItemCheckIndicator geometry.
        indicator = self._list.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, self._list)
        margin = self._list.style().pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, self._list)
        strip = max(24, indicator + margin * 2 + 8)
        rect = self._list.visualItemRect(item)
        return pos.x() <= rect.left() + strip

    def _visible_refs(self, category: Category) -> list[FigureRef]:
        return visible_category_refs(category, self._excluded_dirs)

    def _is_available(self, category: Category) -> bool:
        return category_is_available(category, self._excluded_dirs)

    def _category_label(self, category: Category) -> str:
        return category_list_label(category, self._excluded_dirs)

    def _prune_unavailable_selection(self) -> bool:
        before = set(self._selected)
        self._selected = {
            k
            for k in self._selected
            if k in self._categories and self._is_available(self._categories[k])
        }
        return self._selected != before

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._rebuild_list()

    def _current_key(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        key = item.data(Qt.ItemDataRole.UserRole)
        return key if isinstance(key, str) else None

    def _rebuild_list(self) -> None:
        preserve_key = self._current_key()
        self._list.blockSignals(True)
        self._list.clear()

        keys = sorted(self._categories.keys(), key=str.lower)
        listed = 0
        unavailable_total = 0
        restore_row = -1
        for key in keys:
            if self._filter_text and self._filter_text not in key.lower():
                continue
            category = self._categories[key]
            available = self._is_available(category)
            if not available:
                unavailable_total += 1
                if self._hide_unavailable:
                    continue
            listed += 1
            item = QListWidgetItem(self._category_label(category))
            item.setData(Qt.ItemDataRole.UserRole, key)
            if available:
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    Qt.CheckState.Checked if key in self._selected else Qt.CheckState.Unchecked
                )
            else:
                # Gray out and keep non-checkable (never leave a ticked empty category).
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setForeground(_UNAVAILABLE_FG)
                item.setToolTip("No figures in the currently included directories")
            self._list.addItem(item)
            if preserve_key is not None and key == preserve_key:
                restore_row = self._list.count() - 1

        selected_count = len(self._selected)
        figure_count = sum(len(self._visible_refs(self._categories[k])) for k in self._selected)
        if not self._categories:
            self._summary.setText("No categories")
        else:
            parts = [
                f"{listed} categories",
                f"{selected_count} selected",
                f"{figure_count} figures",
            ]
            if self._excluded_dirs:
                parts.append("dirs filtered")
            if unavailable_total and self._hide_unavailable:
                parts.append(f"{unavailable_total} empty hidden")
            elif unavailable_total:
                parts.append(f"{unavailable_total} empty")
            self._summary.setText(" · ".join(parts))
        self._list.blockSignals(False)
        if restore_row >= 0:
            self._list.setCurrentRow(restore_row)

    def _toggle_current_check(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)

    def _visible_selectable_keys(self) -> set[str]:
        keys: set[str] = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            key = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(key, str):
                continue
            category = self._categories.get(key)
            if category is not None and self._is_available(category):
                keys.add(key)
        return keys

    def _toggle_select_all_visible(self) -> None:
        keys = self._visible_selectable_keys()
        if not keys:
            return
        if keys.issubset(self._selected):
            self._selected -= keys
        else:
            self._selected |= keys
        self._rebuild_list()
        self.selection_changed.emit()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(key, str):
            return
        category = self._categories.get(key)
        if category is None or not self._is_available(category):
            return

        if item.checkState() == Qt.CheckState.Checked:
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self._rebuild_list()
        self.selection_changed.emit()

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from figuregallery.models import Category


class CategoryPanel(QWidget):
    selection_changed = pyqtSignal()
    pdf_only_attempted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._categories: dict[str, Category] = {}
        self._selected: set[str] = set()
        self._filter_text = ""

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter categories…")
        self._filter.textChanged.connect(self._on_filter_changed)

        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_item_changed)

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
            self._selected = {k for k in preserve_selection if k in categories and categories[k].is_selectable}
        else:
            self._selected = {k for k in self._selected if k in categories and categories[k].is_selectable}
        self._rebuild_list()

    def selected_keys(self) -> set[str]:
        return set(self._selected)

    def clear(self) -> None:
        self._categories = {}
        self._selected = set()
        self._list.clear()
        self._summary.setText("No categories")

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()

        keys = sorted(self._categories.keys(), key=str.lower)
        visible = 0
        for key in keys:
            if self._filter_text and self._filter_text not in key.lower():
                continue
            visible += 1
            category = self._categories[key]
            item = QListWidgetItem(category.label())
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            if category.is_selectable:
                item.setCheckState(
                    Qt.CheckState.Checked if key in self._selected else Qt.CheckState.Unchecked
                )
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setForeground(Qt.GlobalColor.gray)
            self._list.addItem(item)

        selected_count = len(self._selected)
        figure_count = sum(len(self._categories[k].displayable_refs) for k in self._selected)
        if not self._categories:
            self._summary.setText("No categories")
        else:
            self._summary.setText(
                f"{selected_count} selected · {figure_count} figures · {visible} shown"
            )
        self._list.blockSignals(False)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(key, str):
            return
        category = self._categories.get(key)
        if category is None:
            return

        if not category.is_selectable:
            if item.checkState() == Qt.CheckState.Checked:
                self._list.blockSignals(True)
                item.setCheckState(Qt.CheckState.Unchecked)
                self._list.blockSignals(False)
                self.pdf_only_attempted.emit(key)
            return

        if item.checkState() == Qt.CheckState.Checked:
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self._rebuild_list()
        self.selection_changed.emit()

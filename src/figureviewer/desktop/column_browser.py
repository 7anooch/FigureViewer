from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from figureviewer.browsing import format_breadcrumb, next_tree_stack, tree_column_levels
from figureviewer.figures import panels_from_directories
from figureviewer.settings import (
    clear_default_browse_root,
    load_default_browse_root,
    save_default_browse_root,
)
from figureviewer.viewer_state import ViewerState


class ColumnBrowser(QWidget):
    panels_changed = pyqtSignal()

    def __init__(self, state: ViewerState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._column_lists: list[QListWidget] = []

        self._root_edit = QLineEdit(self._state.get("browse_root", ""))
        self._browse_btn = QPushButton("Browse…")
        self._open_btn = QPushButton("Open")
        self._default_check = QCheckBox("Default")
        saved = load_default_browse_root()
        self._default_check.setChecked(bool(saved) and saved == str(Path(self._root_edit.text()).expanduser()))

        self._crumb = QLabel()
        self._crumb.setStyleSheet("color: #666;")

        self._columns = QHBoxLayout()
        self._columns.setContentsMargins(0, 0, 0, 0)

        self._toggle_current = QPushButton()
        self._manual_edit = QPlainTextEdit()
        self._manual_edit.setPlaceholderText("Or paste paths, one per line, then Apply")
        self._manual_edit.setMaximumHeight(70)
        self._apply_manual = QPushButton("Apply manual paths")

        self._browse_btn.clicked.connect(self._browse_root)
        self._open_btn.clicked.connect(self._open_root)
        self._default_check.toggled.connect(self._on_default_toggled)
        self._toggle_current.clicked.connect(self._toggle_current_panel)
        self._apply_manual.clicked.connect(self._apply_manual_paths)

        root_row = QHBoxLayout()
        root_row.addWidget(self._root_edit, stretch=1)
        root_row.addWidget(self._browse_btn)
        root_row.addWidget(self._default_check)
        root_row.addWidget(self._open_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Directories")
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)
        layout.addLayout(root_row)
        layout.addWidget(self._crumb)
        layout.addLayout(self._columns)
        layout.addWidget(self._toggle_current)
        layout.addWidget(self._manual_edit)
        layout.addWidget(self._apply_manual)
        self.refresh()

    def focus_list(self) -> None:
        """Focus the rightmost column list (for `` ` `` toggle from figures)."""
        if self._column_lists:
            self._focus_column(len(self._column_lists) - 1)
        else:
            self.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def has_panel_focus(self) -> bool:
        focus = QApplication.focusWidget()
        return focus is not None and self.isAncestorOf(focus)

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        if event.type() == QEvent.Type.KeyPress and obj in self._column_lists:
            assert isinstance(event, QKeyEvent)
            col_idx = self._column_lists.index(obj)
            key = event.key()
            if key == Qt.Key.Key_Left:
                if col_idx > 0:
                    self._focus_column(col_idx - 1)
                return True
            if key == Qt.Key.Key_Right:
                self._column_go_right(col_idx)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                item = obj.currentItem()
                if item is not None:
                    self._toggle_path(Path(str(item.data(Qt.ItemDataRole.UserRole))))
                return True
        return super().eventFilter(obj, event)

    def refresh(self, *, focus_column: int | None = None) -> None:
        stack = list(self._state.get("tree_stack") or [self._state["browse_root"]])
        self._root_edit.setText(self._state.get("browse_root", ""))
        self._crumb.setText(format_breadcrumb(stack))

        while self._columns.count():
            item = self._columns.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._column_lists = []

        panel_paths = {str(Path(p).resolve()) for p in self._state.get("panel_directories", [])}
        levels = tree_column_levels(stack)
        for column_index, (parent, selected, children) in enumerate(levels):
            column = QListWidget()
            column.setMinimumWidth(150)
            column.setMaximumWidth(220)
            column.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            column.installEventFilter(self)
            header = QLabel(parent.name or str(parent))
            header.setStyleSheet("font-size: 11px; color: #888; font-weight: 600;")
            wrap = QWidget()
            col_layout = QVBoxLayout(wrap)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.addWidget(header)
            col_layout.addWidget(column)
            current_item: QListWidgetItem | None = None
            for child in children:
                is_panel = str(child.resolve()) in panel_paths
                mark = "✓ " if is_panel else ""
                list_item = QListWidgetItem(f"{mark}{child.name}")
                list_item.setData(Qt.ItemDataRole.UserRole, str(child.resolve()))
                list_item.setToolTip(
                    "↑/↓ move · ←/→ columns · Enter/Space toggle panel · click to open"
                )
                if selected is not None and child.resolve() == selected.resolve():
                    current_item = list_item
                column.addItem(list_item)
            if current_item is not None:
                column.setCurrentItem(current_item)
            column.itemClicked.connect(
                lambda item, idx=column_index: self._on_item_clicked(idx, item)
            )
            column.itemDoubleClicked.connect(
                lambda item, idx=column_index: self._toggle_path(
                    Path(str(item.data(Qt.ItemDataRole.UserRole)))
                )
            )
            self._columns.addWidget(wrap)
            self._column_lists.append(column)

        current = Path(stack[-1]) if stack else Path.home()
        is_panel = str(current.resolve()) in panel_paths
        self._toggle_current.setText(
            f"{'Remove' if is_panel else 'Add'} “{current.name or current}” as panel"
        )

        if focus_column is not None and self._column_lists:
            self._focus_column(focus_column)

    def _focus_column(self, index: int) -> None:
        if not self._column_lists:
            return
        index = max(0, min(index, len(self._column_lists) - 1))
        column = self._column_lists[index]
        column.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if column.count() > 0 and column.currentRow() < 0:
            column.setCurrentRow(0)

    def _focused_column_index(self) -> int | None:
        focus = QApplication.focusWidget()
        if focus in self._column_lists:
            return self._column_lists.index(focus)  # type: ignore[arg-type]
        return None

    def _column_go_right(self, column_index: int) -> None:
        if column_index + 1 < len(self._column_lists):
            self._focus_column(column_index + 1)
            return
        column = self._column_lists[column_index]
        item = column.currentItem()
        if item is None:
            return
        self._on_item_clicked(column_index, item)

    def _on_item_clicked(self, column_index: int, item: QListWidgetItem) -> None:
        path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        self._state["tree_stack"] = next_tree_stack(
            list(self._state.get("tree_stack") or []),
            column_index,
            path,
        )
        self.refresh(focus_column=column_index + 1)

    def _toggle_path(self, path: Path) -> None:
        focus_idx = self._focused_column_index()
        resolved = str(path.resolve())
        dirs = [str(p) for p in self._state.get("panel_directories", [])]
        if resolved in dirs:
            dirs = [d for d in dirs if d != resolved]
        else:
            dirs.append(resolved)
        self._state["panel_directories"] = dirs
        self.refresh(focus_column=focus_idx)
        self.panels_changed.emit()

    def _toggle_current_panel(self) -> None:
        stack = list(self._state.get("tree_stack") or [self._state["browse_root"]])
        self._toggle_path(Path(stack[-1]))

    def _browse_root(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        initial = self._root_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select root directory", initial)
        if chosen:
            self._root_edit.setText(chosen)
            self._open_root()

    def _open_root(self) -> None:
        text = self._root_edit.text().strip()
        if not text:
            QMessageBox.warning(
                self,
                "Open root",
                "Enter a directory path, or use Browse… to pick one.",
            )
            return
        try:
            root = Path(text).expanduser().resolve(strict=False)
        except OSError as exc:
            QMessageBox.warning(self, "Open root", f"Could not resolve path:\n{text}\n\n{exc}")
            return
        if not root.exists():
            QMessageBox.warning(
                self,
                "Open root",
                f"Directory does not exist:\n{root}",
            )
            return
        if not root.is_dir():
            QMessageBox.warning(
                self,
                "Open root",
                f"Not a directory:\n{root}",
            )
            return
        self._state["browse_root"] = str(root)
        self._state["tree_stack"] = [str(root)]
        if self._default_check.isChecked():
            save_default_browse_root(str(root))
        self.refresh(focus_column=0)

    def _on_default_toggled(self, checked: bool) -> None:
        if checked:
            text = self._root_edit.text().strip()
            if text:
                save_default_browse_root(text)
        else:
            clear_default_browse_root()

    def _apply_manual_paths(self) -> None:
        from figureviewer.figures import parse_panels

        text = self._manual_edit.toPlainText().replace(";", "\n")
        panels = parse_panels(text.replace(",", "\n") if "\n" not in text else text)
        if not panels:
            return
        self._state["panel_directories"] = [str(p.directory.expanduser().resolve()) for p in panels]
        self.refresh()
        self.panels_changed.emit()

    def selected_panel_labels(self) -> list[str]:
        dirs = [Path(p) for p in self._state.get("panel_directories", [])]
        return [p.label for p in panels_from_directories(dirs)]

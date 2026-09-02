from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from figuregallery.directory_tree import (
    FilterNode,
    FilterNodeKind,
    build_filter_display_tree,
    collect_exclusions,
    filter_by_directory_exclusions,
    initial_checked_state,
)
from figuregallery.models import FigureRef

_CHECK_COLUMN = 0


class DirectoryFilterDialog(QDialog):
    """Checkbox tree of directories; folds identical structures across branches."""

    def __init__(
        self,
        refs: list[FigureRef],
        excluded: set[Path],
        *,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Directory filter")
        self.resize(480, 520)
        self._refs = refs
        self._display_nodes = build_filter_display_tree(refs)
        self._initial_excluded = set(excluded)
        self._checked: dict[int, bool] = initial_checked_state(self._display_nodes, excluded)
        self._block_changes = False

        intro = QLabel(
            "Uncheck directories to hide their figures. When branches share the same layout, "
            "top-level variants (e.g. A, B) are listed once with shared subdirectories below."
        )
        intro.setWordWrap(True)

        self._summary = QLabel()
        self._summary.setStyleSheet("color: #666;")

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemChanged.connect(self._on_item_changed)

        include_all_btn = QPushButton("Include all")
        include_all_btn.clicked.connect(self._include_all)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.addStretch(1)
        top_row.addWidget(include_all_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(top_row)
        layout.addWidget(self._tree, stretch=1)
        layout.addWidget(self._summary)
        layout.addWidget(buttons)

        self._populate_tree()
        self._update_summary()

    def excluded_directories(self) -> set[Path]:
        return collect_exclusions(self._display_nodes, self._checked)

    def _populate_tree(self) -> None:
        self._block_changes = True
        self._tree.clear()
        if not self._display_nodes:
            empty = QTreeWidgetItem(["(no subdirectories in selection)"])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._tree.addTopLevelItem(empty)
            self._block_changes = False
            return

        for node in self._display_nodes:
            self._tree.addTopLevelItem(self._make_item(node))
        self._tree.expandToDepth(2)
        self._block_changes = False

    def _make_item(self, node: FilterNode) -> QTreeWidgetItem:
        if node.fan_variants:
            container = QTreeWidgetItem([f"Branches ({node.figure_count} figures)"])
            container.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            container.setData(0, Qt.ItemDataRole.UserRole, None)
            for variant in node.fan_variants:
                container.addChild(self._make_checkable_item(variant))
            for child in node.children:
                container.addChild(self._make_item(child))
            return container

        return self._make_checkable_item(node)

    def _make_checkable_item(self, node: FilterNode) -> QTreeWidgetItem:
        if node.kind == FilterNodeKind.SHARED:
            label = f"{node.name}/ ({node.figure_count})"
        else:
            label = f"{node.name} ({node.figure_count})"
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, id(node))
        item.setFlags(
            item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        included = self._checked.get(id(node), True)
        item.setCheckState(
            _CHECK_COLUMN,
            Qt.CheckState.Checked if included else Qt.CheckState.Unchecked,
        )
        for child in node.children:
            item.addChild(self._make_item(child))
        return item

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        if self._block_changes:
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(node_id, int):
            return
        self._block_changes = True
        state = item.checkState(_CHECK_COLUMN)
        self._checked[node_id] = state == Qt.CheckState.Checked
        self._set_children_state(item, state)
        self._block_changes = False
        self._update_summary()

    def _set_children_state(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for index in range(item.childCount()):
            child = item.child(index)
            child_id = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(child_id, int):
                child.setCheckState(_CHECK_COLUMN, state)
                self._checked[child_id] = state == Qt.CheckState.Checked
            self._set_children_state(child, state)

    def _include_all(self) -> None:
        self._block_changes = True
        for node_id in list(self._checked.keys()):
            self._checked[node_id] = True
        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            if item is not None:
                self._set_item_checked_recursive(item, Qt.CheckState.Checked)
        self._block_changes = False
        self._update_summary()

    def _set_item_checked_recursive(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node_id, int):
            item.setCheckState(_CHECK_COLUMN, state)
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None:
                self._set_item_checked_recursive(child, state)

    def _update_summary(self) -> None:
        excluded = self.excluded_directories()
        visible = len(filter_by_directory_exclusions(self._refs, excluded))
        if excluded:
            noun = "directories" if len(excluded) != 1 else "directory"
            self._summary.setText(
                f"Showing {visible} of {len(self._refs)} figures · {len(excluded)} {noun} excluded"
            )
        else:
            self._summary.setText(f"Showing all {len(self._refs)} figures")

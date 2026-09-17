from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        hide_unavailable_categories: bool = False,
        scan_root: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if scan_root is not None:
            self.setWindowTitle(f"Directory filter — {scan_root}")
        else:
            self.setWindowTitle("Directory filter")
        self.resize(480, 520)
        self._refs = list(refs)
        self._scan_root = scan_root
        self._display_nodes = build_filter_display_tree(self._refs)
        self._initial_excluded = set(excluded)
        self._checked: dict[int, bool] = initial_checked_state(self._display_nodes, excluded)
        self._block_changes = False
        # Next Fold press collapses one depth; flips to expand after fully collapsed.
        self._fold_collapsing = True
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(80)
        self._filter_timer.timeout.connect(self._apply_filter_now)

        intro = QLabel(
            "Uncheck directories to hide their figures. When branches share the same layout, "
            "top-level variants (e.g. A, B) are listed once with shared subdirectories below."
        )
        intro.setWordWrap(True)
        if scan_root is not None:
            root_line = QLabel(f"Scan root: {scan_root}")
            root_line.setStyleSheet("color: #666;")
            root_line.setWordWrap(True)
        else:
            root_line = None

        self._summary = QLabel()
        self._summary.setStyleSheet("color: #666;")

        self._hide_unavailable = QCheckBox("Hide categories with no figures in included directories")
        self._hide_unavailable.setChecked(bool(hide_unavailable_categories))
        self._hide_unavailable.setToolTip(
            "When off, empty categories stay visible but grayed out in the sidebar. "
            "When on, those categories are omitted from the list."
        )

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter directories…")
        # Avoid QLineEdit's built-in clear QToolButton/QAction — uncaught errors in
        # cascaded slots abort the process under PyQt6 on macOS.
        self._filter.setClearButtonEnabled(False)
        self._filter.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._filter.textChanged.connect(self._on_filter_changed)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemChanged.connect(self._on_item_changed)

        include_all_btn = QPushButton("Include all")
        include_all_btn.clicked.connect(self._include_all)
        exclude_all_btn = QPushButton("Exclude all")
        exclude_all_btn.clicked.connect(self._exclude_all)

        self._fold_btn = QPushButton("Collapse")
        self._fold_btn.setToolTip(
            "Collapse one tree depth at a time, then expand again (C when the tree is focused)."
        )
        self._fold_btn.clicked.connect(self._cycle_fold)
        fold_shortcut = QShortcut(QKeySequence("C"), self._tree)
        fold_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        fold_shortcut.activated.connect(self._cycle_fold)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.addWidget(self._filter, stretch=1)
        top_row.addWidget(self._fold_btn)
        top_row.addWidget(include_all_btn)
        top_row.addWidget(exclude_all_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        if root_line is not None:
            layout.addWidget(root_line)
        layout.addLayout(top_row)
        layout.addWidget(self._tree, stretch=1)
        layout.addWidget(self._hide_unavailable)
        layout.addWidget(self._summary)
        layout.addWidget(buttons)

        self._populate_tree()
        self._update_summary()
        self._update_fold_button()
        self._filter.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        # Plain-Python snapshots filled in accept() so callers never touch Qt
        # widgets after exec() returns (PyQt6 aborts on "C++ object deleted").
        self._accepted_excluded: set[Path] | None = None
        self._accepted_hide_unavailable: bool | None = None

    def accept(self) -> None:
        try:
            self._accepted_excluded = set(self.excluded_directories())
            self._accepted_hide_unavailable = bool(self.hide_unavailable_categories())
        except Exception:
            self._accepted_excluded = set()
            self._accepted_hide_unavailable = bool(self._hide_unavailable.isChecked())
        super().accept()

    def excluded_directories(self) -> set[Path]:
        return collect_exclusions(self._display_nodes, self._checked)

    def hide_unavailable_categories(self) -> bool:
        return self._hide_unavailable.isChecked()

    def accepted_result(self) -> tuple[set[Path], bool] | None:
        """Return (excluded, hide_unavailable) captured at accept(), else None."""
        if self._accepted_excluded is None or self._accepted_hide_unavailable is None:
            return None
        return set(self._accepted_excluded), bool(self._accepted_hide_unavailable)

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
        self._fold_collapsing = True
        self._apply_expand_depth(min(2, self._max_expand_depth()))
        self._block_changes = False
        self._apply_filter_now()
        self._update_fold_button()

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
        try:
            node_id = item.data(0, Qt.ItemDataRole.UserRole)
            if not isinstance(node_id, int):
                return
            self._block_changes = True
            state = item.checkState(_CHECK_COLUMN)
            self._checked[node_id] = state == Qt.CheckState.Checked
            self._set_children_state(item, state)
            self._block_changes = False
            self._update_summary()
        except Exception:
            self._block_changes = False

    def _set_children_state(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for index in range(item.childCount()):
            child = item.child(index)
            child_id = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(child_id, int):
                child.setCheckState(_CHECK_COLUMN, state)
                self._checked[child_id] = state == Qt.CheckState.Checked
            self._set_children_state(child, state)

    def _include_all(self) -> None:
        try:
            self._set_all_checked(True)
        except Exception:
            pass

    def _exclude_all(self) -> None:
        try:
            self._set_all_checked(False)
        except Exception:
            pass

    def _set_all_checked(self, included: bool) -> None:
        state = Qt.CheckState.Checked if included else Qt.CheckState.Unchecked
        self._block_changes = True
        for node_id in list(self._checked.keys()):
            self._checked[node_id] = included
        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            if item is not None:
                self._set_item_checked_recursive(item, state)
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
        try:
            excluded = self.excluded_directories()
            visible = len(filter_by_directory_exclusions(self._refs, excluded))
            if excluded:
                noun = "directories" if len(excluded) != 1 else "directory"
                self._summary.setText(
                    f"Showing {visible} of {len(self._refs)} figures · {len(excluded)} {noun} excluded"
                )
            else:
                self._summary.setText(f"Showing all {len(self._refs)} figures")
        except Exception:
            pass

    def _on_filter_changed(self, text: str) -> None:
        del text
        # Debounce: avoid re-entrant hide/expand while Qt is still delivering key events
        # (uncaught errors here abort the process under PyQt6).
        self._filter_timer.start()

    def _apply_filter_now(self) -> None:
        try:
            self._apply_filter(self._filter.text())
        except Exception:
            # Never let a filter glitch take down the app (PyQt treats slot exceptions as fatal).
            pass

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._filter_timer.stop()
        super().closeEvent(event)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        self._tree.blockSignals(True)
        try:
            if not needle:
                for index in range(self._tree.topLevelItemCount()):
                    item = self._tree.topLevelItem(index)
                    if item is not None:
                        self._set_item_hidden_recursive(item, False)
                # Restore fold depth after a search, starting in collapse direction.
                self._fold_collapsing = True
                self._apply_expand_depth(min(2, self._max_expand_depth()))
                self._update_fold_button()
                return

            for index in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(index)
                if item is not None:
                    self._filter_item(item, needle)
            self._update_fold_button()
        finally:
            self._tree.blockSignals(False)

    def _filter_item(self, item: QTreeWidgetItem, needle: str) -> bool:
        """Hide non-matching branches; keep ancestors of matches visible and expanded.

        A direct name match keeps that item's full subtree visible so you can
        include/exclude children without clearing the filter.
        """
        text = item.text(0)
        if needle in text.lower():
            self._set_item_hidden_recursive(item, False)
            if item.childCount() > 0:
                item.setExpanded(True)
            return True

        child_match = False
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None and self._filter_item(child, needle):
                child_match = True
        item.setHidden(not child_match)
        if child_match and item.childCount() > 0:
            item.setExpanded(True)
        return child_match

    def _set_item_hidden_recursive(self, item: QTreeWidgetItem, hidden: bool) -> None:
        item.setHidden(hidden)
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None:
                self._set_item_hidden_recursive(child, hidden)

    def _max_expand_depth(self) -> int:
        """Deepest depth among expandable items, or -1 if the tree is flat."""
        deepest = -1

        def walk(item: QTreeWidgetItem, depth: int) -> None:
            nonlocal deepest
            if item.childCount() <= 0:
                return
            deepest = max(deepest, depth)
            for index in range(item.childCount()):
                child = item.child(index)
                if child is not None:
                    walk(child, depth + 1)

        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            if item is not None:
                walk(item, 0)
        return deepest

    def _current_expand_depth(self) -> int:
        """Deepest currently expanded item depth, or -1 if fully collapsed."""
        deepest = -1

        def walk(item: QTreeWidgetItem, depth: int) -> None:
            nonlocal deepest
            if item.childCount() <= 0:
                return
            if not item.isExpanded():
                return
            deepest = max(deepest, depth)
            for index in range(item.childCount()):
                child = item.child(index)
                if child is not None:
                    walk(child, depth + 1)

        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            if item is not None:
                walk(item, 0)
        return deepest

    def _apply_expand_depth(self, depth: int) -> None:
        if depth < 0:
            self._tree.collapseAll()
            return
        self._tree.collapseAll()
        self._tree.expandToDepth(depth)

    def _cycle_fold(self) -> None:
        try:
            max_depth = self._max_expand_depth()
            if max_depth < 0:
                return

            current = self._current_expand_depth()
            if self._fold_collapsing:
                if current < 0:
                    self._fold_collapsing = False
                    target = 0
                else:
                    target = current - 1
                    if target < 0:
                        # Landed fully collapsed; next press will expand.
                        pass
            else:
                if current >= max_depth:
                    self._fold_collapsing = True
                    target = current - 1
                else:
                    target = current + 1
                    if target >= max_depth:
                        # Landed fully expanded; next press will collapse.
                        pass

            self._apply_expand_depth(target)
            # Keep direction aligned with the *next* action after landing at an extreme.
            if target < 0:
                self._fold_collapsing = False
            elif target >= max_depth:
                self._fold_collapsing = True
            self._update_fold_button()
        except Exception:
            pass

    def _update_fold_button(self) -> None:
        max_depth = self._max_expand_depth()
        enabled = max_depth >= 0
        self._fold_btn.setEnabled(enabled)
        if not enabled:
            self._fold_btn.setText("Fold")
            return
        current = self._current_expand_depth()
        if self._fold_collapsing and current >= 0:
            self._fold_btn.setText("Collapse")
        elif not self._fold_collapsing and current < max_depth:
            self._fold_btn.setText("Expand")
        elif current < 0:
            self._fold_btn.setText("Expand")
        else:
            self._fold_btn.setText("Collapse")

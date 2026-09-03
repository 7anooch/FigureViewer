from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QRadioButton,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from figurecommon.paths import pick_directory_dialog
from figurecommon.scan import ScanOptions
from figuregallery.cache import ImageCache
from figuregallery.grouping import group_index, remap_selection
from figuregallery.index import build_scan_index
from figuregallery.models import Category, FigureRef, GroupMode, ScanIndex, SortMode
from figuregallery.platform import reveal_in_file_manager
from figuregallery.playlist import (
    build_playlist,
    category_position,
    filter_by_path_prefix,
    list_figures_in_directory,
    preserve_position,
)
from figuregallery.directory_tree import filter_by_directory_exclusions
from figuregallery.export import export_playlist_pdf
from figuregallery.shortcuts import empty_state_html, shortcuts_help_text
from figuregallery.ui.category_panel import CategoryPanel
from figuregallery.ui.directory_filter_dialog import DirectoryFilterDialog
from figuregallery.ui.export_dialog import ExportPdfDialog
from figuregallery.ui.loader import FigureLoader
from figuregallery.ui.nav_controls import NavControls
from figuregallery.ui.path_bar import PathBar
from figuregallery.ui.viewport import FigureViewport

PDF_ONLY_MESSAGE = (
    "PDF display is not available yet (coming in v2).\n\n"
    "This category contains only PDF files. Select a category with images to browse."
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        initial_root: Path | None = None,
        group_mode: GroupMode = GroupMode.STEM,
        sort_mode: SortMode = SortMode.CATEGORY_THEN_PATH,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Figure Gallery")
        self.resize(1100, 700)

        self._group_mode = group_mode
        self._sort_mode = sort_mode
        self._scan_index: ScanIndex | None = None
        self._categories: dict[str, Category] = {}
        self._base_playlist: list[FigureRef] = []
        self._playlist: list[FigureRef] = []
        self._path_filter: Path | None = None
        self._excluded_dirs: set[Path] = set()
        self._this_folder_only = False
        self._this_folder_anchor: Path | None = None
        self._current_index = 0
        self._cache = ImageCache()
        self._loader = FigureLoader()
        self._loader.loaded.connect(self._on_image_loaded)
        self._loader.failed.connect(self._on_image_failed)

        self._build_toolbar()
        self._build_ui()
        self._build_shortcuts()
        self._build_status_bar()
        self._viewport.set_message(empty_state_html(), rich=True)
        self._status.showMessage(shortcuts_help_text(for_console=False).replace("\n", "  ·  "), 12000)

        if initial_root is not None:
            self._scan_root(initial_root)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)

        open_action = QAction("Open…", self)
        open_action.triggered.connect(self._open_directory)
        toolbar.addAction(open_action)

        rescan_action = QAction("Rescan", self)
        rescan_action.triggered.connect(self._rescan)
        toolbar.addAction(rescan_action)

        reveal_action = QAction("Open enclosing folder", self)
        reveal_action.triggered.connect(self._reveal_current)
        toolbar.addAction(reveal_action)
        self._reveal_action = reveal_action

        self._dir_filter_action = QAction("Directories…", self)
        self._dir_filter_action.triggered.connect(self._open_directory_filter)
        self._dir_filter_action.setEnabled(False)
        toolbar.addAction(self._dir_filter_action)

        self._this_folder_action = QAction("This folder", self)
        self._this_folder_action.setCheckable(True)
        self._this_folder_action.setEnabled(False)
        self._this_folder_action.triggered.connect(self._toggle_this_folder_only)
        self._this_folder_action.setToolTip(
            "Show all figures in the current figure's directory (H to toggle)."
        )
        self._this_folder_action.setShortcut(QKeySequence("H"))
        toolbar.addAction(self._this_folder_action)

        self._export_action = QAction("Export PDF…", self)
        self._export_action.triggered.connect(self._export_pdf)
        self._export_action.setEnabled(False)
        self._export_action.setToolTip("Export the current playlist as a multi-page PDF.")
        self._export_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Save))
        toolbar.addAction(self._export_action)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel(" Sort: "))
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Category → Path", SortMode.CATEGORY_THEN_PATH)
        self._sort_combo.addItem("Path → Category", SortMode.PATH_THEN_CATEGORY)
        if self._sort_mode == SortMode.PATH_THEN_CATEGORY:
            self._sort_combo.setCurrentIndex(1)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        toolbar.addWidget(self._sort_combo)

        toolbar.addSeparator()

        self._stem_radio = QRadioButton("Stem")
        self._filename_radio = QRadioButton("Filename")
        if self._group_mode == GroupMode.FILENAME:
            self._filename_radio.setChecked(True)
        else:
            self._stem_radio.setChecked(True)
        self._stem_radio.toggled.connect(self._on_group_mode_changed)
        toolbar.addWidget(self._stem_radio)
        toolbar.addWidget(self._filename_radio)

        reveal_action.setShortcut(QKeySequence("Ctrl+E"))
        open_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        rescan_action.setShortcut(QKeySequence("Ctrl+R"))

    def _build_ui(self) -> None:
        self._category_panel = CategoryPanel()
        self._category_panel.selection_changed.connect(self._on_selection_changed)
        self._category_panel.pdf_only_attempted.connect(self._on_pdf_only_attempted)

        self._path_bar = PathBar()
        self._path_bar.segment_clicked.connect(self._on_path_segment_clicked)
        self._viewport = FigureViewport()
        self._nav = NavControls()
        self._nav.index_changed.connect(self._set_index)

        self._caption = QLabel()
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption.setStyleSheet("color: #555;")

        right = QVBoxLayout()
        right.addWidget(self._path_bar)
        right.addWidget(self._viewport, stretch=1)
        right.addWidget(self._nav)
        right.addWidget(self._caption)

        right_widget = QWidget()
        right_widget.setLayout(right)

        central = QHBoxLayout()
        central.addWidget(self._category_panel)
        central.addWidget(right_widget, stretch=1)

        container = QWidget()
        container.setLayout(central)
        self.setCentralWidget(container)

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._go_prev)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._go_next)
        QShortcut(QKeySequence(Qt.Key.Key_Home), self, self._go_first)
        QShortcut(QKeySequence(Qt.Key.Key_End), self, self._go_last)
        # Laptop-friendly: Cmd+← / Cmd+→ (Ctrl+← / Ctrl+→ on other platforms)
        QShortcut(QKeySequence("Ctrl+Left"), self, self._go_first)
        QShortcut(QKeySequence("Ctrl+Right"), self, self._go_last)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._go_next)

    def _build_status_bar(self) -> None:
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._root_label = QLabel("No root selected")
        self._status.addPermanentWidget(self._root_label)

    def _open_directory(self) -> None:
        initial = str(self._scan_index.root) if self._scan_index else None
        picked = pick_directory_dialog(initial)
        if picked:
            self._scan_root(Path(picked))

    def _rescan(self) -> None:
        if self._scan_index is None:
            self._open_directory()
            return
        self._scan_root(self._scan_index.root)

    def _scan_root(self, root: Path) -> None:
        started = time.perf_counter()
        try:
            index = build_scan_index(root, options=ScanOptions())
        except Exception as exc:
            QMessageBox.critical(self, "Scan failed", str(exc))
            return

        elapsed = time.perf_counter() - started
        self._scan_index = index
        self._path_filter = None
        self._excluded_dirs = set()
        self._clear_this_folder_only()
        self._categories = group_index(index, self._group_mode)
        self._category_panel.set_categories(self._categories)
        self._root_label.setText(f"Root: {index.root}")
        pdf_count = sum(1 for r in index.refs if not r.is_displayable)
        displayable = sum(1 for r in index.refs if r.is_displayable)
        self._status.showMessage(
            f"Scanned {len(index.refs)} figures ({displayable} images, {pdf_count} pdf) in {elapsed:.1f}s",
            5000,
        )
        self._rebuild_playlist(reset_index=True)

    def _on_group_mode_changed(self, checked: bool) -> None:
        if not checked or self._scan_index is None:
            return
        new_mode = GroupMode.STEM if self._stem_radio.isChecked() else GroupMode.FILENAME
        if new_mode == self._group_mode:
            return
        old_mode = self._group_mode
        self._group_mode = new_mode
        selected = remap_selection(
            self._category_panel.selected_keys(),
            old_mode,
            new_mode,
            self._scan_index,
        )
        self._categories = group_index(self._scan_index, self._group_mode)
        self._category_panel.set_categories(self._categories, preserve_selection=selected)
        self._rebuild_playlist(reset_index=False)

    def _on_sort_changed(self, index: int) -> None:
        mode = self._sort_combo.itemData(index)
        if not isinstance(mode, SortMode) or mode == self._sort_mode:
            return
        self._sort_mode = mode
        self._rebuild_playlist(reset_index=False)

    def _on_selection_changed(self) -> None:
        self._path_filter = None
        self._excluded_dirs = set()
        self._clear_this_folder_only()
        self._rebuild_playlist(reset_index=True)

    def _on_pdf_only_attempted(self, key: str) -> None:
        QMessageBox.information(self, "PDF not supported yet", PDF_ONLY_MESSAGE)

    def _rebuild_playlist(self, *, reset_index: bool) -> None:
        old_playlist = self._playlist
        old_index = self._current_index
        selected = self._category_panel.selected_keys()

        if not selected:
            self._base_playlist = []
            self._playlist = []
            self._current_index = 0
            self._dir_filter_action.setEnabled(False)
            self._this_folder_action.setEnabled(False)
            self._export_action.setEnabled(False)
            self._clear_this_folder_only()
            self._nav.set_total(0)
            self._path_bar.clear()
            self._caption.setText("")
            self._viewport.set_message("Select one or more categories to browse.")
            return

        self._base_playlist = build_playlist(
            self._categories,
            selected,
            self._sort_mode,
            group_mode=self._group_mode,
        )
        self._dir_filter_action.setEnabled(bool(self._base_playlist))
        self._this_folder_action.setEnabled(bool(self._base_playlist))
        self._apply_playlist_filters(
            reset_index=reset_index,
            old_playlist=old_playlist,
            old_index=old_index,
        )

    def _apply_playlist_filters(
        self,
        *,
        reset_index: bool,
        old_playlist: list[FigureRef] | None = None,
        old_index: int = 0,
    ) -> None:
        old_playlist = old_playlist if old_playlist is not None else self._playlist
        old_index = old_index if old_playlist is self._playlist else old_index

        if self._this_folder_only and self._this_folder_anchor is not None and self._scan_index is not None:
            self._playlist = list_figures_in_directory(
                self._scan_index.refs,
                self._this_folder_anchor,
            )
        else:
            filtered = filter_by_directory_exclusions(self._base_playlist, self._excluded_dirs)
            self._playlist = filter_by_path_prefix(filtered, self._path_filter)

        if not self._playlist:
            self._current_index = 0
            self._nav.set_total(0)
            self._export_action.setEnabled(False)
            self._caption.setText("")
            if self._this_folder_only:
                self._viewport.set_message(
                    f"No figures in {self._this_folder_anchor}."
                )
            elif self._path_filter is not None:
                self._viewport.set_message(
                    f"No figures under {self._path_filter} with the current filters."
                )
            elif self._excluded_dirs:
                self._viewport.set_message("No figures remain after directory exclusions.")
            else:
                self._viewport.set_message("No figures to display.")
            return

        if reset_index:
            self._current_index = 0
        else:
            self._current_index = preserve_position(old_playlist, old_index, self._playlist)

        self._nav.set_total(len(self._playlist), index=self._current_index)
        self._export_action.setEnabled(bool(self._playlist))
        self._show_current_figure()

    def _show_current_figure(self) -> None:
        if not self._playlist:
            return
        ref = self._playlist[self._current_index]
        self._path_bar.set_path(ref.relative_path, active_prefix=self._path_filter)
        pos, total_in_cat = category_position(ref, self._playlist, group_mode=self._group_mode)
        key = ref.category_key(self._group_mode)
        caption = f"{key} · {pos} of {total_in_cat} in this category"
        if self._this_folder_only and self._this_folder_anchor is not None:
            caption += f" · this folder only ({self._this_folder_anchor})"
        elif self._excluded_dirs:
            caption += f" · {len(self._excluded_dirs)} dir{'s' if len(self._excluded_dirs) != 1 else ''} excluded"
        if self._path_filter is not None:
            caption += f" · filtered to {self._path_filter}"
        self._caption.setText(caption)
        self._nav.set_index(self._current_index)

        cached = self._cache.get(ref.absolute_path)
        if cached is not None:
            self._viewport.set_image(cached)
            return

        self._viewport.set_loading()
        self._loader.load(ref.absolute_path)

    def _on_image_loaded(self, path_str: str, image) -> None:
        if not self._playlist:
            return
        current = self._playlist[self._current_index]
        if str(current.absolute_path.resolve()) != path_str:
            return
        self._cache.put(current.absolute_path, image)
        self._viewport.set_image(image)

    def _on_image_failed(self, path_str: str, message: str) -> None:
        if not self._playlist:
            return
        current = self._playlist[self._current_index]
        if str(current.absolute_path.resolve()) != path_str:
            return
        self._viewport.set_message(f"Could not load figure:\n{message}")

    def _set_index(self, index: int) -> None:
        if not self._playlist:
            return
        self._current_index = max(0, min(index, len(self._playlist) - 1))
        self._show_current_figure()

    def _go_prev(self) -> None:
        if self._playlist and self._current_index > 0:
            self._set_index(self._current_index - 1)

    def _go_next(self) -> None:
        if self._playlist and self._current_index < len(self._playlist) - 1:
            self._set_index(self._current_index + 1)

    def _go_first(self) -> None:
        if self._playlist:
            self._set_index(0)

    def _go_last(self) -> None:
        if self._playlist:
            self._set_index(len(self._playlist) - 1)

    def _reveal_current(self) -> None:
        if not self._playlist:
            return
        reveal_in_file_manager(self._playlist[self._current_index].absolute_path)

    def _on_path_segment_clicked(self, relative: Path, is_filename: bool) -> None:
        if self._scan_index is None or not self._base_playlist:
            return
        if is_filename:
            target = (self._scan_index.root / relative).resolve()
            reveal_in_file_manager(target)
            return

        if self._path_filter == relative:
            self._path_filter = None
        else:
            self._path_filter = relative
        self._clear_this_folder_only()
        self._apply_playlist_filters(reset_index=True)

    def _clear_this_folder_only(self) -> None:
        self._this_folder_only = False
        self._this_folder_anchor = None
        self._this_folder_action.setChecked(False)

    def _toggle_this_folder_only(self, checked: bool) -> None:
        if not self._playlist and checked:
            self._this_folder_action.setChecked(False)
            return
        if checked:
            if not self._playlist:
                return
            ref = self._playlist[self._current_index]
            self._this_folder_only = True
            self._this_folder_anchor = ref.parent_relative
            self._apply_playlist_filters(reset_index=False)
            return
        self._clear_this_folder_only()
        self._apply_playlist_filters(reset_index=False)

    def _open_directory_filter(self) -> None:
        if not self._base_playlist:
            return
        dialog = DirectoryFilterDialog(
            self._base_playlist,
            self._excluded_dirs,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._excluded_dirs = dialog.excluded_directories()
        self._apply_playlist_filters(reset_index=False)

    def _export_pdf(self) -> None:
        if not self._playlist:
            return
        scan_root = self._scan_index.root if self._scan_index is not None else None
        dialog = ExportPdfDialog(
            self._playlist,
            scan_root=scan_root,
            group_mode=self._group_mode,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_path = dialog.output_path()
        if output_path.exists():
            reply = QMessageBox.question(
                self,
                "Overwrite file?",
                f"File already exists:\n{output_path}\n\nOverwrite?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        progress = QProgressDialog("Exporting PDF…", "Cancel", 0, len(self._playlist), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        cancelled = False

        def on_progress(index: int, total: int, ref) -> None:
            nonlocal cancelled
            progress.setValue(index)
            progress.setLabelText(f"Exporting {index + 1} / {total}\n{ref.relative_path}")
            if progress.wasCanceled():
                cancelled = True
                raise RuntimeError("Export cancelled")

        try:
            result = export_playlist_pdf(
                self._playlist,
                output_path,
                progress_callback=on_progress,
            )
        except RuntimeError as exc:
            if cancelled or "cancelled" in str(exc).lower():
                self._status.showMessage("Export cancelled", 4000)
                return
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        finally:
            progress.setValue(len(self._playlist))
            progress.close()

        self._status.showMessage(
            f"Exported {result.pages} page{'s' if result.pages != 1 else ''} → {result.path}",
            8000,
        )
        QMessageBox.information(
            self,
            "Export complete",
            f"Wrote {result.pages} page{'s' if result.pages != 1 else ''}:\n{result.path}",
        )

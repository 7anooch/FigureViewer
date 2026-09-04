from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QRadioButton,
    QSlider,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from figurecommon.paths import pick_directory_dialog
from figurecommon.scan import ScanOptions
from figuregallery.browse_pacing import BrowsePacing
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

DEFAULT_PDF_DPI = 200
MIN_PDF_DPI = 100
MAX_PDF_DPI = 400
PDF_DPI_STEP = 25


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
        self._pdf_dpi = DEFAULT_PDF_DPI
        self._trim_whitespace = False
        self._pacing = BrowsePacing()
        self._cache = ImageCache(max_items=self._pacing.budget.cache_size)
        self._loader = FigureLoader()
        self._loader.loaded.connect(self._on_image_loaded)
        self._loader.failed.connect(self._on_image_failed)
        self._prefetch = FigureLoader()
        self._prefetch.loaded.connect(self._on_prefetch_loaded)
        self._prefetch.failed.connect(self._on_prefetch_failed)
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(2000)
        self._idle_timer.timeout.connect(self._on_idle_tick)
        self._idle_timer.start()

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

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" PDF DPI: "))
        self._dpi_slider = QSlider(Qt.Orientation.Horizontal)
        self._dpi_slider.setMinimum(MIN_PDF_DPI)
        self._dpi_slider.setMaximum(MAX_PDF_DPI)
        self._dpi_slider.setSingleStep(PDF_DPI_STEP)
        self._dpi_slider.setPageStep(PDF_DPI_STEP)
        self._dpi_slider.setTickInterval(PDF_DPI_STEP)
        self._dpi_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._dpi_slider.setValue(DEFAULT_PDF_DPI)
        self._dpi_slider.setFixedWidth(120)
        self._dpi_slider.setToolTip("Rasterization DPI for PDF and SVG display and export.")
        self._dpi_slider.valueChanged.connect(self._on_dpi_changed)
        toolbar.addWidget(self._dpi_slider)
        self._dpi_label = QLabel(str(DEFAULT_PDF_DPI))
        toolbar.addWidget(self._dpi_label)

        self._trim_checkbox = QCheckBox("Trim margins")
        self._trim_checkbox.setToolTip(
            "Crop near-white page margins. Applies to display and PDF export."
        )
        self._trim_checkbox.toggled.connect(self._on_trim_toggled)
        toolbar.addWidget(self._trim_checkbox)

        reveal_action.setShortcut(QKeySequence("Ctrl+E"))
        open_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        rescan_action.setShortcut(QKeySequence("Ctrl+R"))

    def _build_ui(self) -> None:
        self._category_panel = CategoryPanel()
        self._category_panel.selection_changed.connect(self._on_selection_changed)

        self._path_bar = PathBar()
        self._path_bar.segment_clicked.connect(self._on_path_segment_clicked)
        self._viewport = FigureViewport()
        self._category_panel.focus_figure_requested.connect(self._viewport.focus_display)
        self._nav = NavControls()
        self._nav.index_changed.connect(self._set_index)

        self._caption = QLabel()
        self._caption.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._caption.setStyleSheet("color: #555;")
        self._caption.setWordWrap(True)

        self._zoom_hint = QLabel()
        self._zoom_hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._zoom_hint.setStyleSheet("color: #888; font-size: 11px;")
        self._zoom_hint.hide()
        self._viewport.zoom_hint_changed.connect(self._on_zoom_hint_changed)

        caption_row = QHBoxLayout()
        caption_row.setContentsMargins(0, 0, 0, 0)
        caption_row.addWidget(self._caption, stretch=1)
        caption_row.addWidget(self._zoom_hint)

        right = QVBoxLayout()
        right.addWidget(self._path_bar)
        right.addWidget(self._viewport, stretch=1)
        right.addWidget(self._nav)
        right.addLayout(caption_row)

        right_widget = QWidget()
        right_widget.setLayout(right)

        central = QHBoxLayout()
        central.addWidget(self._category_panel)
        central.addWidget(right_widget, stretch=1)

        container = QWidget()
        container.setLayout(central)
        self.setCentralWidget(container)

    def _build_shortcuts(self) -> None:
        # Figure nav / zoom only when the viewport (or a child) has focus —
        # so Space / arrows work for category checkboxes while the list is focused.
        def _figure_shortcut(key: QKeySequence | str | Qt.Key, slot) -> None:
            sc = QShortcut(QKeySequence(key), self._viewport)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        _figure_shortcut(Qt.Key.Key_Left, self._go_prev)
        _figure_shortcut(Qt.Key.Key_Right, self._go_next)
        _figure_shortcut(Qt.Key.Key_Home, self._go_first)
        _figure_shortcut(Qt.Key.Key_End, self._go_last)
        # Laptop-friendly: Cmd+← / Cmd+→ (Ctrl+← / Ctrl+→ on other platforms)
        _figure_shortcut("Ctrl+Left", self._go_first)
        _figure_shortcut("Ctrl+Right", self._go_last)
        _figure_shortcut(Qt.Key.Key_Space, self._go_next)
        _figure_shortcut("Ctrl+=", lambda: self._viewport.zoom_by(1.25))
        _figure_shortcut("Ctrl++", lambda: self._viewport.zoom_by(1.25))
        _figure_shortcut("Ctrl+-", lambda: self._viewport.zoom_by(1.0 / 1.25))
        _figure_shortcut("Ctrl+0", self._viewport.reset_zoom)

        toggle = QShortcut(QKeySequence(Qt.Key.Key_QuoteLeft), self)
        toggle.setContext(Qt.ShortcutContext.WindowShortcut)
        toggle.activated.connect(self._toggle_panel_focus)

    def _toggle_panel_focus(self) -> None:
        if self._category_panel.has_panel_focus():
            self._viewport.focus_display()
        else:
            self._category_panel.focus_list()

    def _build_status_bar(self) -> None:
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._root_label = QLabel("No root selected")
        self._status.addPermanentWidget(self._root_label)

    def _on_zoom_hint_changed(self, text: str) -> None:
        if text:
            if self._zoom_hint.text() != text:
                self._zoom_hint.setText(text)
            if not self._zoom_hint.isVisible():
                self._zoom_hint.show()
        else:
            self._zoom_hint.clear()
            self._zoom_hint.hide()

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
        pdf_count = sum(1 for r in index.refs if r.absolute_path.suffix.lower() == ".pdf")
        other = len(index.refs) - pdf_count
        self._status.showMessage(
            f"Scanned {len(index.refs)} figures ({other} images, {pdf_count} pdf) in {elapsed:.1f}s",
            5000,
        )
        self._rebuild_playlist(reset_index=True)
        self._viewport.focus_display()

    def _on_dpi_changed(self, value: int) -> None:
        stepped = MIN_PDF_DPI + ((value - MIN_PDF_DPI) // PDF_DPI_STEP) * PDF_DPI_STEP
        if stepped != value:
            self._dpi_slider.blockSignals(True)
            self._dpi_slider.setValue(stepped)
            self._dpi_slider.blockSignals(False)
            value = stepped
        self._pdf_dpi = value
        self._dpi_label.setText(str(value))
        self._cache.clear()
        if self._playlist:
            self._show_current_figure()

    def _on_trim_toggled(self, checked: bool) -> None:
        self._trim_whitespace = checked
        self._cache.clear()
        if self._playlist:
            self._show_current_figure()

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

        cached = self._cache.get(
            ref.absolute_path, pdf_dpi=self._pdf_dpi, trim=self._trim_whitespace
        )
        if cached is not None:
            self._viewport.set_image(cached)
            self._prefetch_neighbors()
            return

        self._viewport.set_loading()
        self._loader.load(ref.absolute_path, pdf_dpi=self._pdf_dpi, trim=self._trim_whitespace)

    def _on_image_loaded(self, path_str: str, image) -> None:
        if not self._playlist:
            return
        current = self._playlist[self._current_index]
        self._cache.put(
            Path(path_str),
            image,
            pdf_dpi=self._pdf_dpi,
            trim=self._trim_whitespace,
        )
        if str(current.absolute_path.resolve()) != path_str:
            # Stale load; still cached for later, then resume prefetch.
            self._prefetch_neighbors()
            return
        self._viewport.set_image(image)
        self._prefetch_neighbors()

    def _on_image_failed(self, path_str: str, message: str) -> None:
        if not self._playlist:
            return
        current = self._playlist[self._current_index]
        if str(current.absolute_path.resolve()) != path_str:
            self._prefetch_neighbors()
            return
        self._viewport.set_message(f"Could not load figure:\n{message}")

    def _on_prefetch_loaded(self, path_str: str, image) -> None:
        self._cache.put(
            Path(path_str),
            image,
            pdf_dpi=self._pdf_dpi,
            trim=self._trim_whitespace,
        )
        self._prefetch_neighbors()

    def _on_prefetch_failed(self, path_str: str, message: str) -> None:
        # Skip bad neighbors; keep warming the rest of the window.
        del path_str, message
        self._prefetch_neighbors()

    def _apply_browse_budget(self) -> None:
        budget = self._pacing.budget
        self._cache.set_max_items(budget.cache_size)

    def _on_idle_tick(self) -> None:
        changed = self._pacing.decay_if_idle()
        if changed is not None:
            self._apply_browse_budget()

    def _prefetch_neighbors(self) -> None:
        """Warm nearby playlist entries so ←/→ rarely shows Loading…"""
        if not self._playlist or self._prefetch.isRunning() or self._loader.isRunning():
            return
        radius = self._pacing.budget.prefetch_radius
        # Prefer forward direction (typical browsing), then backward.
        offsets = [o for pair in zip(range(1, radius + 1), range(-1, -radius - 1, -1)) for o in pair]
        for offset in offsets:
            index = self._current_index + offset
            if index < 0 or index >= len(self._playlist):
                continue
            ref = self._playlist[index]
            if self._cache.get(
                ref.absolute_path, pdf_dpi=self._pdf_dpi, trim=self._trim_whitespace
            ) is not None:
                continue
            self._prefetch.load(
                ref.absolute_path,
                pdf_dpi=self._pdf_dpi,
                trim=self._trim_whitespace,
            )
            return

    def _set_index(self, index: int) -> None:
        if not self._playlist:
            return
        self._pacing.note_navigate()
        self._apply_browse_budget()
        self._current_index = max(0, min(index, len(self._playlist) - 1))
        self._show_current_figure()

    def _go_prev(self) -> None:
        if not self._playlist:
            self._category_panel.focus_list()
            return
        if self._current_index > 0:
            self._set_index(self._current_index - 1)
        else:
            # Already on the first figure — hand focus to categories instead of a no-op.
            self._category_panel.focus_list()

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
                pdf_dpi=self._pdf_dpi,
                trim=self._trim_whitespace,
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

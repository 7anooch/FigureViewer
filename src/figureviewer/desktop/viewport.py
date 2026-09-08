from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QImage,
    QMouseEvent,
    QNativeGestureEvent,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from figuregallery.browse_pacing import BrowsePacing
from figuregallery.cache import ImageCache
from figuregallery.ui.loader import FigureLoader
from figureviewer.display_state import ViewportSnapshot

_MIN_ZOOM = 0.25
_MAX_ZOOM = 8.0
_GESTURE_SUPPRESS_S = 0.35
_ZOOM_HINT_FIT = "Zoom: Fit  ·  pinch or ⌘/Ctrl+scroll  ·  double-click to reset"


class _PanelCell(QWidget):
    """One panel: fit/natural/custom at zoom 1.0; gestures request shared viewport zoom."""

    zoom_by_requested = pyqtSignal(float, object)  # factor, optional QPoint
    reset_zoom_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-weight: 600;")
        self._local_slider = QSlider(Qt.Orientation.Horizontal)
        self._local_slider.hide()

        self._image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._image_label.setScaledContents(False)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._image_label)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setMinimumHeight(120)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._scroll.viewport().installEventFilter(self)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #a33;")
        self._message.hide()

        self._source: QImage | None = None
        self._figure_path: Path | None = None
        self._fill = True
        self._logical_width: int | None = None
        self._zoom = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._title)
        layout.addWidget(self._local_slider)
        layout.addWidget(self._scroll, stretch=1)
        layout.addWidget(self._message)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_figure_path(self, path: Path | None) -> None:
        self._figure_path = path

    def set_image(self, image: QImage, *, fill: bool, logical_width: int | None = None, zoom: float = 1.0) -> None:
        self._source = image
        self._fill = fill
        self._logical_width = logical_width
        self._zoom = zoom
        self._message.hide()
        self._scroll.show()
        self._prepare_default_view()
        self._update_pixmap(anchor=None)
        if abs(zoom - 1.0) < 1e-3:
            QTimer.singleShot(0, self._refit_if_default_zoom)

    def set_loading(self) -> None:
        """Placeholder while the figure loads — keep path for reveal."""
        self._source = None
        self._zoom = 1.0
        self._prepare_default_view()
        self._scroll.hide()
        self._message.setText("Loading…")
        self._message.show()

    def set_message(self, text: str) -> None:
        self._source = None
        self._figure_path = None
        self._zoom = 1.0
        self._prepare_default_view()
        self._scroll.hide()
        self._message.setText(text)
        self._message.show()

    def refit(self) -> None:
        if self._source is not None and not self._source.isNull():
            self._update_pixmap(anchor=None)

    def set_zoom_level(self, zoom: float, *, anchor: QPoint | None = None) -> None:
        if self._source is None or self._source.isNull():
            return
        self._zoom = zoom
        self._update_pixmap(anchor=anchor)
        if abs(zoom - 1.0) < 1e-3:
            QTimer.singleShot(0, self._refit_if_default_zoom)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._scroll.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if event.size() == event.oldSize():
            return
        if self._source is not None and not self._source.isNull():
            self._update_pixmap(anchor=None)

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        if obj is self._scroll.viewport():
            etype = event.type()
            if etype == QEvent.Type.NativeGesture and isinstance(event, QNativeGestureEvent):
                return self._handle_native_gesture(event)
            if etype == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
                return self._handle_wheel(event)
            if etype == QEvent.Type.MouseButtonDblClick:
                if self._source is not None:
                    self._scroll.setFocus(Qt.FocusReason.MouseFocusReason)
                    self.reset_zoom_requested.emit()
                    return True
            if etype == QEvent.Type.MouseButtonPress:
                self._scroll.setFocus(Qt.FocusReason.MouseFocusReason)
        return super().eventFilter(obj, event)

    def event(self, event) -> bool:  # noqa: ANN001
        if event.type() == QEvent.Type.NativeGesture and isinstance(event, QNativeGestureEvent):
            if self._handle_native_gesture(event):
                return True
        return super().event(event)

    def _prepare_default_view(self) -> None:
        self._image_label.clear()
        self._image_label.setText("")
        self._image_label.resize(1, 1)
        self._scroll.horizontalScrollBar().setValue(0)
        self._scroll.verticalScrollBar().setValue(0)

    def _refit_if_default_zoom(self) -> None:
        if self._source is None or abs(self._zoom - 1.0) >= 1e-3:
            return
        self._update_pixmap(anchor=None)

    def _handle_native_gesture(self, event: QNativeGestureEvent) -> bool:
        if self._source is None:
            return False
        if event.gestureType() != Qt.NativeGestureType.ZoomNativeGesture:
            return False
        self._scroll.setFocus(Qt.FocusReason.MouseFocusReason)
        factor = 1.0 + float(event.value())
        if factor <= 0:
            return True
        anchor = self._scroll.viewport().mapFromGlobal(event.globalPosition().toPoint())
        self.zoom_by_requested.emit(factor, anchor)
        return True

    def _handle_wheel(self, event: QWheelEvent) -> bool:
        if self._source is None:
            return False
        modifiers = event.modifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            self._scroll.setFocus(Qt.FocusReason.MouseFocusReason)
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.pixelDelta().y()
            if delta == 0:
                return False
            factor = 1.1 if delta > 0 else 1.0 / 1.1
            self.zoom_by_requested.emit(factor, event.position().toPoint())
            return True
        if self._zoom > 1.0 + 1e-3:
            return False  # let scroll area pan
        return False

    def _available_size(self) -> QSize:
        size = self._scroll.maximumViewportSize()
        if size.width() < 10 or size.height() < 10:
            size = self._scroll.viewport().size()
        return size

    def _fit_size(self) -> QSize:
        assert self._source is not None
        available = self._available_size()
        if available.width() < 10 or available.height() < 10:
            return QSize(1, 1)
        img_w = max(self._source.width(), 1)
        img_h = max(self._source.height(), 1)
        if self._fill:
            scale = min(available.width() / img_w, available.height() / img_h)
            return QSize(max(1, int(img_w * scale)), max(1, int(img_h * scale)))
        if self._logical_width is not None:
            lw = max(1, self._logical_width)
        else:
            lw = img_w
        lw = min(lw, available.width())
        scale = lw / img_w
        return QSize(max(1, lw), max(1, int(round(img_h * scale))))

    def _update_pixmap(self, *, anchor: QPoint | None) -> None:
        if self._source is None or self._source.isNull():
            return
        available = self._available_size()
        if available.width() < 10 or available.height() < 10:
            return

        fit = self._fit_size()
        display_w = max(1, int(round(fit.width() * self._zoom)))
        display_h = max(1, int(round(fit.height() * self._zoom)))

        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        old_size = self._image_label.size()
        if anchor is not None and old_size.width() > 0 and old_size.height() > 0:
            content_x = (hbar.value() + anchor.x()) / old_size.width()
            content_y = (vbar.value() + anchor.y()) / old_size.height()
        else:
            content_x = content_y = 0.5

        dpr = max(self._scroll.viewport().devicePixelRatioF(), 1.0)
        target = QSize(max(1, int(display_w * dpr)), max(1, int(display_h * dpr)))
        pixmap = QPixmap.fromImage(self._source)
        scaled = pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        self._image_label.setPixmap(scaled)
        self._image_label.resize(display_w, display_h)

        if anchor is not None:
            hbar.setValue(int(content_x * display_w - anchor.x()))
            vbar.setValue(int(content_y * display_h - anchor.y()))
        elif self._zoom <= 1.0 + 1e-3:
            hbar.setValue(0)
            vbar.setValue(0)


class MultiPanelViewport(QWidget):
    local_index_changed = pyqtSignal(str, int)
    zoom_hint_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pacing = BrowsePacing()
        self._cache = ImageCache(max_items=self._pacing.budget.cache_size)
        self._loader = FigureLoader()
        self._loader.loaded.connect(self._on_loaded)
        self._loader.failed.connect(self._on_failed)
        self._prefetch_loader = FigureLoader()
        self._prefetch_loader.loaded.connect(self._on_prefetch_loaded)
        self._prefetch_loader.failed.connect(self._on_prefetch_failed)
        self._pending: list[tuple[int, Path]] = []
        self._prefetch_queue: list[Path] = []
        self._panel_count = 1
        self._pdf_dpi = 200
        self._trim = False
        self._fill = True
        self._custom_width = 700
        self._display_mode = "Fill panel"
        self._cells: list[_PanelCell] = []
        self._zoom = 1.0
        self._ignore_zoom_until = 0.0
        self._last_zoom_hint: str | None = None

        self._grid = QGridLayout()
        inner = QWidget()
        inner.setLayout(self._grid)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(inner)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._empty = QLabel("Select one or more directories to begin.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet("color: #666; font-size: 14px;")
        layout.addWidget(self._empty)

        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(2000)
        self._idle_timer.timeout.connect(self._on_idle_tick)
        self._idle_timer.start()

    def focus_display(self) -> None:
        """Put keyboard focus on the figure surface (for chrome that still expects it)."""
        if self._empty.isVisible():
            self.setFocus(Qt.FocusReason.ShortcutFocusReason)
            return
        # Outer scroll stays visible even while panel cells show "Loading…"
        # (per-cell scrolls are hidden then, so focusing them can fail).
        self._scroll.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def set_display_options(self, *, display_mode: str, custom_width: int, pdf_dpi: int, trim: bool) -> None:
        dpi_changed = pdf_dpi != self._pdf_dpi
        trim_changed = trim != self._trim
        self._display_mode = display_mode
        self._custom_width = custom_width
        self._pdf_dpi = pdf_dpi
        self._trim = trim
        self._fill = display_mode == "Fill panel"
        if dpi_changed or trim_changed:
            # Cache keys include dpi/trim — drop stale variants and pending work.
            self._cache.clear()
            self._pending = []
            self._prefetch_queue = []

    def note_navigate(self, *, panel_count: int | None = None) -> None:
        """Call on each figure flip so cache/prefetch budget can ramp with pace."""
        if panel_count is not None:
            self._panel_count = max(1, panel_count)
        self._pacing.note_navigate()
        self._apply_browse_budget()

    def prefetch_paths(self, paths: list[Path]) -> None:
        """Warm neighboring figure paths (full multi-panel sets) in the background."""
        for path in paths:
            if self._cache.get(path, pdf_dpi=self._pdf_dpi, trim=self._trim) is not None:
                continue
            resolved = path.resolve()
            if any(p.resolve() == resolved for p in self._prefetch_queue):
                continue
            if any(p.resolve() == resolved for _, p in self._pending):
                continue
            self._prefetch_queue.append(path)
        self._prefetch_next()

    def focused_figure_path(self) -> Path | None:
        """Path of the first loaded panel figure (for Reveal in Finder)."""
        for cell in self._cells:
            if cell._figure_path is not None:
                return cell._figure_path
        return None

    def zoom_by(self, factor: float, *, anchor: QPoint | None = None, source: _PanelCell | None = None) -> None:
        if time.monotonic() < self._ignore_zoom_until:
            return
        if not any(cell._source is not None for cell in self._cells):
            return
        new_zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-4:
            return
        self._zoom = new_zoom
        for cell in self._cells:
            cell_anchor = anchor if cell is source else None
            cell.set_zoom_level(self._zoom, anchor=cell_anchor)
        self._emit_zoom_hint()

    def reset_zoom(self) -> None:
        self._suppress_zoom_gestures()
        self._zoom = 1.0
        for cell in self._cells:
            if cell._source is not None:
                cell.set_zoom_level(1.0, anchor=None)
        self._emit_zoom_hint()

    def show_message(self, text: str, *, rich: bool = False) -> None:
        self._clear_cells()
        self._prefetch_queue = []
        self._zoom = 1.0
        self._empty.setTextFormat(
            Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText
        )
        self._empty.setText(text)
        self._empty.show()
        self.zoom_hint_changed.emit("")
        self._last_zoom_hint = None

    def show_snapshot(self, snapshot: ViewportSnapshot, *, sync_mode: bool = True) -> None:
        self._empty.hide()
        # Cells are destroyed below — remember if keyboard focus lived in this viewport
        # so ←/→ (WidgetWithChildrenShortcut) keep working after the flip.
        fw = QApplication.focusWidget()
        restore_keyboard = fw is not None and (fw is self or self.isAncestorOf(fw))
        self._clear_cells()
        self._suppress_zoom_gestures()
        self._zoom = 1.0
        self._prefetch_queue = []
        self._panel_count = max(len(snapshot.panels), 1)
        self._apply_browse_budget()
        cols = max(snapshot.columns_per_row, 1)
        self._pending = []
        for i, (panel, path) in enumerate(zip(snapshot.panels, snapshot.figure_paths)):
            cell = _PanelCell()
            cell.zoom_by_requested.connect(self._on_cell_zoom_by)
            cell.reset_zoom_requested.connect(self.reset_zoom)
            row, col = divmod(i, cols)
            self._grid.addWidget(cell, row, col)
            self._cells.append(cell)
            if path is None:
                cell.set_title(panel.label)
                cell.set_message("No matching figure in this panel.")
                continue
            cell.set_figure_path(path)
            cell.set_title(f"{panel.label}  ·  {path.name}")
            if not sync_mode:
                from figureviewer.figures import list_figures

                figs = list_figures(panel.directory, recursive=False)
                cell._local_slider.setVisible(True)
                cell._local_slider.setMaximum(max(len(figs) - 1, 0))
                key = f"local_idx_{panel.label}_{panel.directory.resolve()}"
                cell._local_slider.blockSignals(True)
                try:
                    local_val = figs.index(path)
                except ValueError:
                    resolved = {str(p.resolve()): idx for idx, p in enumerate(figs)}
                    local_val = resolved.get(str(path.resolve()), 0)
                cell._local_slider.setValue(local_val)
                cell._local_slider.blockSignals(False)
                cell._local_slider.valueChanged.connect(
                    lambda value, k=key: self.local_index_changed.emit(k, int(value))
                )
            cached = self._cache.get(path, pdf_dpi=self._pdf_dpi, trim=self._trim)
            if cached is not None:
                self._apply_image(cell, cached)
            else:
                cell.set_loading()
                self._pending.append((i, path))
        self._load_next()
        QTimer.singleShot(0, self._refit_cells)
        self._emit_zoom_hint()
        if restore_keyboard:
            QTimer.singleShot(0, self.focus_display)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refit_cells()

    def _suppress_zoom_gestures(self) -> None:
        self._ignore_zoom_until = time.monotonic() + _GESTURE_SUPPRESS_S

    def _on_cell_zoom_by(self, factor: float, anchor: object) -> None:
        source = self.sender()
        cell = source if isinstance(source, _PanelCell) else None
        point = anchor if isinstance(anchor, QPoint) else None
        self.zoom_by(factor, anchor=point, source=cell)

    def _emit_zoom_hint(self) -> None:
        if not any(cell._source is not None for cell in self._cells):
            hint = ""
        elif abs(self._zoom - 1.0) < 1e-3:
            hint = _ZOOM_HINT_FIT
        else:
            hint = (
                f"Zoom: {self._zoom * 100:.0f}%  ·  two-finger scroll to pan  ·  double-click to reset"
            )
        if self._last_zoom_hint == hint:
            return
        self._last_zoom_hint = hint
        self.zoom_hint_changed.emit(hint)

    def _apply_browse_budget(self) -> None:
        budget = self._pacing.budget
        # Multi-panel pages cost N images each — size cache ≈ panels × (2r+1) with pacing floor.
        page = self._panel_count * (2 * budget.prefetch_radius + 1)
        target = max(budget.cache_size, page + self._panel_count)
        self._cache.set_max_items(min(240, target))

    def _on_idle_tick(self) -> None:
        if self._pacing.decay_if_idle() is not None:
            self._apply_browse_budget()

    def _refit_cells(self) -> None:
        for cell in self._cells:
            cell.refit()

    def _load_next(self) -> None:
        if not self._pending:
            self._prefetch_next()
            return
        _index, path = self._pending[0]
        self._loader.load(path, pdf_dpi=self._pdf_dpi, trim=self._trim)

    def _prefetch_next(self) -> None:
        if self._prefetch_loader.isRunning() or self._loader.isRunning() or self._pending:
            return
        while self._prefetch_queue:
            path = self._prefetch_queue.pop(0)
            if self._cache.get(path, pdf_dpi=self._pdf_dpi, trim=self._trim) is not None:
                continue
            self._prefetch_loader.load(path, pdf_dpi=self._pdf_dpi, trim=self._trim)
            return

    def _on_loaded(self, path_str: str, image: QImage) -> None:
        self._cache.put(Path(path_str), image, pdf_dpi=self._pdf_dpi, trim=self._trim)
        if not self._pending:
            self._prefetch_next()
            return
        index, path = self._pending[0]
        if str(path.resolve()) != path_str:
            if not self._loader.isRunning():
                self._load_next()
            return
        self._pending.pop(0)
        if index < len(self._cells):
            self._apply_image(self._cells[index], image)
        self._load_next()

    def _on_failed(self, path_str: str, message: str) -> None:
        if not self._pending:
            self._prefetch_next()
            return
        index, path = self._pending[0]
        if str(path.resolve()) != path_str:
            if not self._loader.isRunning():
                self._load_next()
            return
        self._pending.pop(0)
        if index < len(self._cells):
            self._cells[index].set_message(f"Could not load figure:\n{message}")
        self._load_next()

    def _on_prefetch_loaded(self, path_str: str, image: QImage) -> None:
        self._cache.put(Path(path_str), image, pdf_dpi=self._pdf_dpi, trim=self._trim)
        self._prefetch_next()

    def _on_prefetch_failed(self, path_str: str, message: str) -> None:
        del path_str, message
        self._prefetch_next()

    def _apply_image(self, cell: _PanelCell, image: QImage) -> None:
        if self._display_mode == "Custom width":
            cell.set_image(image, fill=False, logical_width=self._custom_width, zoom=self._zoom)
        else:
            cell.set_image(image, fill=self._fill, zoom=self._zoom)

    def _clear_cells(self) -> None:
        self._pending = []
        for cell in self._cells:
            self._grid.removeWidget(cell)
            cell.deleteLater()
        self._cells = []

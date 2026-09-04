from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, QPoint, Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QNativeGestureEvent, QPixmap, QWheelEvent
from PyQt6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_MIN_ZOOM = 0.25
_MAX_ZOOM = 8.0
_GESTURE_SUPPRESS_S = 0.35
_ZOOM_HINT_FIT = "Zoom: Fit  ·  pinch or ⌘/Ctrl+scroll to zoom  ·  double-click to reset"


class FigureViewport(QWidget):
    """Figure display with Finder-like pinch / scroll zoom and pan when zoomed."""

    zoom_hint_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._image_label.setScaledContents(False)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._image_label)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.viewport().installEventFilter(self)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._message_label = QLabel(alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet("color: #666; font-size: 14px;")
        self._message_label.setTextFormat(Qt.TextFormat.PlainText)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._scroll, stretch=1)
        layout.addWidget(self._message_label)

        self._current_image: QImage | None = None
        self._zoom = 1.0  # 1.0 = fit in view
        self._ignore_zoom_until = 0.0
        self.set_message("")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def focus_display(self) -> None:
        """Put keyboard focus on the figure surface (for nav / zoom shortcuts)."""
        if self._scroll.isVisible():
            self._scroll.setFocus(Qt.FocusReason.ShortcutFocusReason)
        else:
            self.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def set_message(self, text: str, *, rich: bool = False) -> None:
        self._current_image = None
        self._zoom = 1.0
        self._prepare_default_view()
        self._scroll.hide()
        self._last_zoom_hint = None
        self.zoom_hint_changed.emit("")
        self._message_label.setTextFormat(
            Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText
        )
        self._message_label.setText(text)
        self._message_label.show()

    def set_loading(self) -> None:
        self._current_image = None
        self._zoom = 1.0
        self._prepare_default_view()
        # Keep the scroll area shown so focus does not jump to the category filter.
        self._image_label.setText("Loading…")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vp = self._scroll.viewport().size()
        self._image_label.resize(max(vp.width(), 120), max(vp.height(), 80))
        self._scroll.show()
        self._message_label.hide()
        # Stay on the Fit hint while loading (do not hide — that causes a flash).
        self._emit_zoom_hint(_ZOOM_HINT_FIT)
    def set_image(self, image: QImage) -> None:
        self._suppress_zoom_gestures()
        self._current_image = image
        self._zoom = 1.0
        self._message_label.hide()
        self._prepare_default_view()
        self._scroll.show()
        self._update_pixmap(anchor=None)
        # Scrollbars from the previous (zoomed) figure can shrink the viewport;
        # refit once layout settles so every figure truly fits the window.
        QTimer.singleShot(0, self._refit_if_default_zoom)

    def reset_zoom(self) -> None:
        if self._current_image is None:
            return
        self._suppress_zoom_gestures()
        self._zoom = 1.0
        self._prepare_default_view()
        self._update_pixmap(anchor=None)
        QTimer.singleShot(0, self._refit_if_default_zoom)

    def zoom_by(self, factor: float, *, anchor: QPoint | None = None) -> None:
        if self._current_image is None or self._current_image.isNull():
            return
        if time.monotonic() < self._ignore_zoom_until:
            return
        new_zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-4:
            return
        self._zoom = new_zoom
        self._update_pixmap(anchor=anchor)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._current_image is not None:
            self._update_pixmap(anchor=None)

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        if obj is self._scroll.viewport():
            etype = event.type()
            if etype == QEvent.Type.NativeGesture and isinstance(event, QNativeGestureEvent):
                return self._handle_native_gesture(event)
            if etype == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
                return self._handle_wheel(event)
            if etype == QEvent.Type.MouseButtonDblClick:
                self.reset_zoom()
                return True
        return super().eventFilter(obj, event)

    def event(self, event) -> bool:  # noqa: ANN001
        if event.type() == QEvent.Type.NativeGesture and isinstance(event, QNativeGestureEvent):
            if self._handle_native_gesture(event):
                return True
        return super().event(event)

    def _suppress_zoom_gestures(self) -> None:
        self._ignore_zoom_until = time.monotonic() + _GESTURE_SUPPRESS_S

    def _prepare_default_view(self) -> None:
        """Drop the previous oversized label so scrollbars don't shrink the viewport."""
        self._image_label.clear()
        self._image_label.setText("")
        self._image_label.resize(1, 1)
        self._scroll.horizontalScrollBar().setValue(0)
        self._scroll.verticalScrollBar().setValue(0)

    def _refit_if_default_zoom(self) -> None:
        if self._current_image is None or abs(self._zoom - 1.0) >= 1e-3:
            return
        self._update_pixmap(anchor=None)

    def _handle_native_gesture(self, event: QNativeGestureEvent) -> bool:
        if self._current_image is None:
            return False
        if event.gestureType() != Qt.NativeGestureType.ZoomNativeGesture:
            return False
        if time.monotonic() < self._ignore_zoom_until:
            return True
        factor = 1.0 + float(event.value())
        if factor <= 0:
            return True
        anchor = self._scroll.viewport().mapFromGlobal(event.globalPosition().toPoint())
        self.zoom_by(factor, anchor=anchor)
        return True

    def _handle_wheel(self, event: QWheelEvent) -> bool:
        if self._current_image is None:
            return False
        modifiers = event.modifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            if time.monotonic() < self._ignore_zoom_until:
                return True
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.pixelDelta().y()
            if delta == 0:
                return False
            factor = 1.1 if delta > 0 else 1.0 / 1.1
            self.zoom_by(factor, anchor=event.position().toPoint())
            return True
        if self._zoom > 1.0 + 1e-3:
            return False
        return False

    def _available_size(self) -> QSize:
        # Size as if scrollbars were not shown — stable fit-to-window baseline.
        size = self._scroll.maximumViewportSize()
        if size.width() < 10 or size.height() < 10:
            size = self._scroll.viewport().size()
        return size

    def _fit_size(self) -> QSize:
        assert self._current_image is not None
        available = self._available_size()
        if available.width() < 10 or available.height() < 10:
            return QSize(1, 1)
        img_w = max(self._current_image.width(), 1)
        img_h = max(self._current_image.height(), 1)
        scale = min(available.width() / img_w, available.height() / img_h)
        return QSize(max(1, int(img_w * scale)), max(1, int(img_h * scale)))

    def _update_pixmap(self, *, anchor: QPoint | None) -> None:
        if self._current_image is None or self._current_image.isNull():
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
        pixmap = QPixmap.fromImage(self._current_image)
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

        if abs(self._zoom - 1.0) < 1e-3:
            hint = _ZOOM_HINT_FIT
        else:
            hint = (
                f"Zoom: {self._zoom * 100:.0f}%  ·  two-finger scroll to pan  ·  double-click to reset"
            )
        self._emit_zoom_hint(hint)

    def _emit_zoom_hint(self, hint: str) -> None:
        if getattr(self, "_last_zoom_hint", None) == hint:
            return
        self._last_zoom_hint = hint
        self.zoom_hint_changed.emit(hint)

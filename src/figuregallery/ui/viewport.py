from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QUrl, Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QDrag,
    QImage,
    QMouseEvent,
    QNativeGestureEvent,
    QPixmap,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from figuregallery.ui.figure_transfer import figure_file_mime_data

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget

    _HAS_MULTIMEDIA = True
except ImportError:  # pragma: no cover
    _HAS_MULTIMEDIA = False

_MIN_ZOOM = 0.25
_MAX_ZOOM = 8.0
_GESTURE_SUPPRESS_S = 0.35
_ZOOM_HINT_FIT = (
    "Zoom: Fit  ·  pinch or ⌘/Ctrl+scroll to zoom  ·  drag out or ⌘/Ctrl+C to copy"
)
_VIDEO_HINT = (
    "Video  ·  scrub to seek  ·  P or Pause to toggle  ·  ←/→ change figure"
)


def _format_ms(ms: int) -> str:
    total_s = max(0, int(ms) // 1000)
    hours, rem = divmod(total_s, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class FigureViewport(QWidget):
    """Figure display with Finder-like pinch / scroll zoom and pan when zoomed.

    Browse mode can also play ``.mp4`` via Qt Multimedia when available.
    """

    zoom_hint_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_image: QImage | None = None
        self._source_path: Path | None = None
        self._drag_start: QPoint | None = None
        self._zoom = 1.0  # 1.0 = fit in view
        self._ignore_zoom_until = 0.0
        self._video_active = False
        self._scrubbing = False

        self._image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._image_label.setScaledContents(False)
        self._image_label.setCursor(Qt.CursorShape.OpenHandCursor)
        self._image_label.installEventFilter(self)

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

        self._video_panel, self._player, self._play_btn = self._build_video_panel()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._scroll, stretch=1)
        layout.addWidget(self._video_panel, stretch=1)
        layout.addWidget(self._message_label)
        self._video_panel.hide()

        self.set_message("")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _build_video_panel(self):
        panel = QWidget()
        panel.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(6)

        play_btn = QPushButton("Pause")
        play_btn.setFixedWidth(88)
        play_btn.clicked.connect(self.toggle_playback)

        self._position_label = QLabel("0:00")
        self._position_label.setMinimumWidth(44)
        self._position_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._duration_label = QLabel("0:00")
        self._duration_label.setMinimumWidth(44)
        self._duration_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self._scrub = QSlider(Qt.Orientation.Horizontal)
        self._scrub.setRange(0, 0)
        self._scrub.setSingleStep(1000)
        self._scrub.setPageStep(5000)
        self._scrub.setToolTip("Scrub video position")
        self._scrub.sliderPressed.connect(self._on_scrub_pressed)
        self._scrub.sliderReleased.connect(self._on_scrub_released)
        self._scrub.sliderMoved.connect(self._on_scrub_moved)

        player = None
        if _HAS_MULTIMEDIA:
            video_widget = QVideoWidget()
            video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            video_widget.setMinimumHeight(120)
            player = QMediaPlayer(self)
            audio = QAudioOutput(self)
            player.setAudioOutput(audio)
            player.setVideoOutput(video_widget)
            player.setLoops(QMediaPlayer.Loops.Infinite)
            player.playbackStateChanged.connect(self._on_playback_state_changed)
            player.positionChanged.connect(self._on_position_changed)
            player.durationChanged.connect(self._on_duration_changed)
            player.errorOccurred.connect(self._on_player_error)
            panel_layout.addWidget(video_widget, stretch=1)
        else:
            missing = QLabel("Video playback requires Qt Multimedia.")
            missing.setAlignment(Qt.AlignmentFlag.AlignCenter)
            missing.setStyleSheet("color: #666;")
            panel_layout.addWidget(missing, stretch=1)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(play_btn)
        controls.addWidget(self._position_label)
        controls.addWidget(self._scrub, stretch=1)
        controls.addWidget(self._duration_label)
        panel_layout.addLayout(controls)
        return panel, player, play_btn

    @property
    def is_showing_video(self) -> bool:
        return self._video_active

    def focus_display(self) -> None:
        """Put keyboard focus on the figure surface (for nav / zoom shortcuts)."""
        if self._video_active and self._video_panel.isVisible():
            self._video_panel.setFocus(Qt.FocusReason.ShortcutFocusReason)
            return
        if self._scroll.isVisible():
            self._scroll.setFocus(Qt.FocusReason.ShortcutFocusReason)
        else:
            self.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def set_message(self, text: str, *, rich: bool = False) -> None:
        self._stop_video()
        self._current_image = None
        self._source_path = None
        self._drag_start = None
        self._zoom = 1.0
        self._prepare_default_view()
        self._scroll.hide()
        self._video_panel.hide()
        self._last_zoom_hint = None
        self.zoom_hint_changed.emit("")
        self._message_label.setTextFormat(
            Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText
        )
        self._message_label.setText(text)
        self._message_label.show()

    def set_loading(self) -> None:
        self._stop_video()
        self._current_image = None
        self._source_path = None
        self._drag_start = None
        self._zoom = 1.0
        self._prepare_default_view()
        self._video_panel.hide()
        # Keep the scroll area shown so focus does not jump to the category filter.
        self._image_label.setText("Loading…")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vp = self._scroll.viewport().size()
        self._image_label.resize(max(vp.width(), 120), max(vp.height(), 80))
        self._scroll.show()
        self._message_label.hide()
        # Stay on the Fit hint while loading (do not hide — that causes a flash).
        self._emit_zoom_hint(_ZOOM_HINT_FIT)

    def set_image(self, image: QImage, *, source_path: Path | None = None) -> None:
        self._stop_video()
        self._suppress_zoom_gestures()
        self._current_image = image
        self._source_path = source_path
        self._drag_start = None
        self._zoom = 1.0
        self._video_panel.hide()
        self._message_label.hide()
        self._prepare_default_view()
        self._scroll.show()
        self._update_pixmap(anchor=None)
        # Scrollbars from the previous (zoomed) figure can shrink the viewport;
        # refit once layout settles so every figure truly fits the window.
        QTimer.singleShot(0, self._refit_if_default_zoom)

    def set_video(self, path: Path) -> None:
        """Show and autoplay a local video (looping)."""
        resolved = path.expanduser().resolve()
        if not _HAS_MULTIMEDIA or self._player is None:
            self.set_message(
                f"Cannot play video (Qt Multimedia unavailable):\n{resolved.name}"
            )
            return
        self._suppress_zoom_gestures()
        self._current_image = None
        self._source_path = resolved
        self._drag_start = None
        self._zoom = 1.0
        self._prepare_default_view()
        self._scroll.hide()
        self._message_label.hide()
        self._video_panel.show()
        self._video_active = True
        self._scrubbing = False
        self._reset_scrub(0, 0)
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(resolved)))
        self._player.play()
        self._play_btn.setText("Pause")
        self._emit_zoom_hint(_VIDEO_HINT)

    def toggle_playback(self) -> None:
        if not self._video_active or self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop_video(self) -> None:
        self._video_active = False
        self._scrubbing = False
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
        self._play_btn.setText("Play")
        self._reset_scrub(0, 0)
        self._video_panel.hide()

    def _reset_scrub(self, position_ms: int, duration_ms: int) -> None:
        duration_ms = max(0, int(duration_ms))
        position_ms = max(0, min(int(position_ms), duration_ms or 0))
        self._scrub.blockSignals(True)
        self._scrub.setRange(0, duration_ms)
        self._scrub.setValue(position_ms)
        self._scrub.blockSignals(False)
        self._position_label.setText(_format_ms(position_ms))
        self._duration_label.setText(_format_ms(duration_ms))

    def _on_duration_changed(self, duration_ms: int) -> None:
        if not self._video_active:
            return
        position = self._player.position() if self._player is not None else 0
        self._reset_scrub(position, duration_ms)

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._video_active or self._scrubbing:
            return
        self._scrub.blockSignals(True)
        self._scrub.setValue(max(0, int(position_ms)))
        self._scrub.blockSignals(False)
        self._position_label.setText(_format_ms(position_ms))

    def _on_scrub_pressed(self) -> None:
        self._scrubbing = True

    def _on_scrub_moved(self, position_ms: int) -> None:
        self._position_label.setText(_format_ms(position_ms))
        if self._player is not None and self._video_active:
            self._player.setPosition(int(position_ms))

    def _on_scrub_released(self) -> None:
        if self._player is not None and self._video_active:
            self._player.setPosition(int(self._scrub.value()))
        self._scrubbing = False

    def _on_playback_state_changed(self, state) -> None:  # noqa: ANN001
        if not self._video_active:
            return
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.setText("Pause" if playing else "Play")

    def _on_player_error(self, error, message: str = "") -> None:  # noqa: ANN001
        del error
        if not self._video_active:
            return
        name = self._source_path.name if self._source_path else "video"
        detail = message.strip() or "Playback failed"
        self.set_message(f"Could not play {name}:\n{detail}")

    def copy_to_clipboard(self) -> bool:
        """Copy the current figure's source file to the clipboard. Returns True on success."""
        if self._source_path is None:
            return False
        mime = figure_file_mime_data(self._source_path)
        if mime is None:
            return False
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setMimeData(mime)
        return True

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
        if obj is self._image_label and self._handle_image_drag_event(event):
            return True
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

    def _handle_image_drag_event(self, event) -> bool:  # noqa: ANN001
        if self._current_image is None or self._current_image.isNull():
            return False
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_start = event.position().toPoint()
            return False
        if etype == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_start = None
            return False
        if etype == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
            if self._drag_start is None or not (event.buttons() & Qt.MouseButton.LeftButton):
                return False
            delta = event.position().toPoint() - self._drag_start
            if delta.manhattanLength() < QApplication.startDragDistance():
                return False
            self._start_external_drag(event.position().toPoint())
            self._drag_start = None
            return True
        return False

    def _start_external_drag(self, hotspot: QPoint) -> None:
        if self._source_path is None:
            return
        mime = figure_file_mime_data(self._source_path)
        if mime is None:
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        preview = self._image_label.pixmap()
        if preview is not None and not preview.isNull():
            max_edge = 160
            scaled = preview.scaled(
                max_edge,
                max_edge,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            drag.setPixmap(scaled)
            drag.setHotSpot(
                QPoint(
                    min(max(hotspot.x(), 0), scaled.width()),
                    min(max(hotspot.y(), 0), scaled.height()),
                )
            )
        drag.exec(Qt.DropAction.CopyAction)

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
                f"Zoom: {self._zoom * 100:.0f}%  ·  two-finger scroll to pan  ·  "
                "drag out or ⌘/Ctrl+C to copy"
            )
        self._emit_zoom_hint(hint)

    def _emit_zoom_hint(self, hint: str) -> None:
        if getattr(self, "_last_zoom_hint", None) == hint:
            return
        self._last_zoom_hint = hint
        self.zoom_hint_changed.emit(hint)

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class FigureViewport(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image_label.setMinimumHeight(200)
        self._message_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet("color: #666; font-size: 14px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._image_label, stretch=1)
        layout.addWidget(self._message_label)

        self._current_image: QImage | None = None
        self.set_message("")

    def set_message(self, text: str) -> None:
        self._current_image = None
        self._image_label.clear()
        self._message_label.setText(text)
        self._message_label.show()

    def set_loading(self) -> None:
        self._current_image = None
        self._image_label.clear()
        self._message_label.setText("Loading…")
        self._message_label.show()

    def set_image(self, image: QImage) -> None:
        self._current_image = image
        self._message_label.hide()
        self._update_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_pixmap()

    def _update_pixmap(self) -> None:
        if self._current_image is None or self._current_image.isNull():
            return
        available = self._image_label.size()
        if available.width() < 10 or available.height() < 10:
            return
        pixmap = QPixmap.fromImage(self._current_image)
        scaled = pixmap.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

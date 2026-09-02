from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)


class NavControls(QWidget):
    index_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._prev_btn = QPushButton("◀")
        self._next_btn = QPushButton("▶")
        self._counter = QLabel("0 / 0")
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setEnabled(False)
        self._total = 0
        self._block_signals = False

        self._prev_btn.clicked.connect(self._on_prev)
        self._next_btn.clicked.connect(self._on_next)
        self._slider.valueChanged.connect(self._on_slider)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._prev_btn)
        layout.addWidget(self._counter)
        layout.addWidget(self._next_btn)
        layout.addWidget(self._slider, stretch=1)

        self.set_enabled(False)

    def set_total(self, total: int, *, index: int = 0) -> None:
        self._total = max(0, total)
        enabled = self._total > 0
        self.set_enabled(enabled)
        if not enabled:
            self._counter.setText("0 / 0")
            self._block_signals = True
            self._slider.setRange(0, 0)
            self._slider.setValue(0)
            self._block_signals = False
            return

        index = max(0, min(index, self._total - 1))
        self._block_signals = True
        self._slider.setRange(0, self._total - 1)
        self._slider.setValue(index)
        self._block_signals = False
        self._update_counter(index)

    def set_index(self, index: int) -> None:
        if self._total <= 0:
            return
        index = max(0, min(index, self._total - 1))
        self._block_signals = True
        self._slider.setValue(index)
        self._block_signals = False
        self._update_counter(index)

    def set_enabled(self, enabled: bool) -> None:
        self._prev_btn.setEnabled(enabled)
        self._next_btn.setEnabled(enabled)
        self._slider.setEnabled(enabled and self._total > 1)

    def _update_counter(self, index: int) -> None:
        if self._total <= 0:
            self._counter.setText("0 / 0")
        else:
            self._counter.setText(f"{index + 1} / {self._total}")

    def _on_prev(self) -> None:
        if self._total <= 0:
            return
        self.index_changed.emit(max(0, self._slider.value() - 1))

    def _on_next(self) -> None:
        if self._total <= 0:
            return
        self.index_changed.emit(min(self._total - 1, self._slider.value() + 1))

    def _on_slider(self, value: int) -> None:
        if self._block_signals:
            return
        self._update_counter(value)
        self.index_changed.emit(value)

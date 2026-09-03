from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QFont, QPalette
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class PathBar(QWidget):
    """Breadcrumb for the current figure; directory segments filter the playlist."""

    segment_clicked = pyqtSignal(Path, bool)  # relative prefix, is_filename

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch(1)
        self._active_prefix: Path | None = None
        self.clear()

    def clear(self) -> None:
        self._active_prefix = None
        self._clear_layout()
        placeholder = QLabel("—")
        placeholder.setStyleSheet(f"color: {self._muted_color()};")
        self._layout.insertWidget(0, placeholder)
        self._layout.insertStretch(0, 1)

    def set_path(self, relative_path: Path, *, active_prefix: Path | None = None) -> None:
        self._active_prefix = active_prefix
        self._clear_layout()
        parts = relative_path.parts
        if not parts:
            self.clear()
            return

        active_parts: tuple[str, ...] = ()
        if active_prefix is not None and active_prefix.parts:
            active_parts = active_prefix.parts

        self._layout.insertStretch(0, 1)
        for index, part in enumerate(parts):
            prefix = Path(*parts[: index + 1])
            is_filename = index == len(parts) - 1
            is_filtered = not is_filename and len(active_parts) >= index + 1 and active_parts[: index + 1] == prefix.parts

            if index > 0:
                sep = QLabel("/")
                sep.setStyleSheet(f"color: {self._muted_color()}; padding: 0 1px;")
                self._layout.addWidget(sep)

            button = self._make_segment_button(
                part,
                bold=is_filename,
                filtered=is_filtered,
                tooltip=self._tooltip_for(prefix, is_filename),
            )
            button.clicked.connect(
                lambda _checked=False, p=prefix, filename=is_filename: self.segment_clicked.emit(p, filename)
            )
            self._layout.addWidget(button)

        self._layout.addStretch(1)

    def _is_dark(self) -> bool:
        return self.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def _link_color(self) -> str:
        if self._is_dark():
            return "#7ec8ff"
        return "#0a58ca"

    def _link_hover_color(self) -> str:
        if self._is_dark():
            return "#b3ddff"
        return "#084298"

    def _filtered_color(self) -> str:
        if self._is_dark():
            return "#ffd166"
        return "#9a6700"

    def _filename_color(self) -> str:
        if self._is_dark():
            return "#f0f3f6"
        return "#1a1d21"

    def _muted_color(self) -> str:
        if self._is_dark():
            return "#9aa4af"
        return "#6c757d"

    def _segment_stylesheet(self, *, bold: bool, filtered: bool) -> str:
        weight = "600" if bold else "500"
        if filtered:
            color = self._filtered_color()
        elif bold:
            color = self._filename_color()
        else:
            color = self._link_color()
        return (
            "QPushButton {"
            f"  color: {color};"
            f"  font-weight: {weight};"
            "  border: none;"
            "  padding: 2px 4px;"
            "  background: transparent;"
            "}"
            "QPushButton:hover {"
            f"  color: {self._link_hover_color() if not filtered else color};"
            "  text-decoration: underline;"
            "}"
            "QPushButton:pressed {"
            f"  color: {self._link_hover_color() if not filtered else color};"
            "}"
        )

    def _make_segment_button(self, text: str, *, bold: bool, filtered: bool, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setFlat(True)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        button.setToolTip(tooltip)
        button.setStyleSheet(self._segment_stylesheet(bold=bold, filtered=filtered))
        if bold:
            font = button.font()
            font.setWeight(QFont.Weight.DemiBold)
            button.setFont(font)
        return button

    @staticmethod
    def _tooltip_for(prefix: Path, is_filename: bool) -> str:
        if is_filename:
            return f"Open enclosing folder: {prefix}"
        return f"Show only figures under {prefix} (click again to clear)"

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            for widget in self.findChildren(QPushButton):
                bold = widget.font().weight() >= QFont.Weight.DemiBold
                widget.setStyleSheet(self._segment_stylesheet(bold=bold, filtered=False))

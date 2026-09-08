from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from figureviewer.figures import panels_from_directories
from figureviewer.viewer_state import ViewerState


class SettingsPanel(QWidget):
    settings_changed = pyqtSignal()
    go_first = pyqtSignal()
    go_last = pyqtSignal()
    remove_panel = pyqtSignal(str)
    clear_panels = pyqtSignal()

    def __init__(self, state: ViewerState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self.setMinimumWidth(240)
        self.setMaximumWidth(340)

        self._panel_list = QListWidget()
        self._clear_btn = QPushButton("Clear all panels")
        self._clear_btn.clicked.connect(self.clear_panels.emit)

        self._recursive = QCheckBox("Include figures in subfolders")
        self._recursive.setChecked(bool(state.get("recursive", False)))
        self._recursive.toggled.connect(lambda v: self._set("recursive", v))

        self._sync = QCheckBox("Sync panels")
        self._sync.setChecked(bool(state.get("sync_mode", True)))
        self._sync.toggled.connect(self._on_sync)

        self._match = QComboBox()
        self._match.addItems(["position", "filename stem"])
        self._match.setCurrentText(str(state.get("match_by", "position")))
        self._match.currentTextChanged.connect(lambda v: self._set("match_by", v))
        self._match.setEnabled(self._sync.isChecked())

        self._metadata = QCheckBox("Show metadata editors")
        self._metadata.setChecked(bool(state.get("show_metadata", False)))
        self._metadata.toggled.connect(lambda v: self._set("show_metadata", v))

        self._columns = QSpinBox()
        self._columns.setRange(1, 4)
        self._columns.setValue(int(state.get("columns_per_row", 2)))
        self._columns.valueChanged.connect(lambda v: self._set("columns_per_row", int(v)))

        self._display_mode = QComboBox()
        self._display_mode.addItems(["Fill panel", "Natural size", "Custom width"])
        self._display_mode.setCurrentText(str(state.get("display_mode", "Fill panel")))
        self._display_mode.currentTextChanged.connect(self._on_display_mode)

        self._custom_width = QSlider(Qt.Orientation.Horizontal)
        self._custom_width.setRange(250, 2400)
        self._custom_width.setSingleStep(50)
        self._custom_width.setValue(int(state.get("custom_width", 700)))
        self._custom_width.valueChanged.connect(lambda v: self._set("custom_width", int(v)))
        self._custom_width.setEnabled(self._display_mode.currentText() == "Custom width")

        self._dpi = QSlider(Qt.Orientation.Horizontal)
        self._dpi.setRange(100, 400)
        self._dpi.setSingleStep(25)
        self._dpi.setValue(int(state.get("pdf_dpi", 200)))
        self._dpi_label = QLabel(str(self._dpi.value()))
        self._dpi.valueChanged.connect(self._on_dpi)

        self._trim = QCheckBox("Trim whitespace margins")
        self._trim.setChecked(bool(state.get("trim_whitespace", False)))
        self._trim.toggled.connect(lambda v: self._set("trim_whitespace", v))

        first_btn = QPushButton("First")
        last_btn = QPushButton("Last")
        first_btn.clicked.connect(self.go_first.emit)
        last_btn.clicked.connect(self.go_last.emit)
        nav_row = QHBoxLayout()
        nav_row.addWidget(first_btn)
        nav_row.addWidget(last_btn)

        panels_box = QGroupBox("Panels")
        panels_layout = QVBoxLayout(panels_box)
        panels_layout.addWidget(QLabel("Selected panels  ·  ` or Directories to browse"))
        panels_layout.addWidget(self._panel_list)
        panels_layout.addWidget(self._clear_btn)
        panels_layout.addWidget(self._recursive)
        panels_layout.addWidget(self._sync)
        panels_layout.addWidget(QLabel("Sync by"))
        panels_layout.addWidget(self._match)
        panels_layout.addWidget(self._metadata)
        form = QFormLayout()
        form.addRow("Panels per row", self._columns)
        panels_layout.addLayout(form)

        display_box = QGroupBox("Display")
        display_layout = QVBoxLayout(display_box)
        display_layout.addWidget(QLabel("Display size"))
        display_layout.addWidget(self._display_mode)
        display_layout.addWidget(QLabel("Custom width (px)"))
        display_layout.addWidget(self._custom_width)
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("PDF raster DPI"))
        dpi_row.addWidget(self._dpi, stretch=1)
        dpi_row.addWidget(self._dpi_label)
        display_layout.addLayout(dpi_row)
        display_layout.addWidget(self._trim)

        nav_box = QGroupBox("Navigation")
        nav_layout = QVBoxLayout(nav_box)
        nav_layout.addWidget(QLabel("← previous · → next · Home first · End last"))
        nav_layout.addLayout(nav_row)

        layout = QVBoxLayout(self)
        layout.addWidget(panels_box)
        layout.addWidget(display_box)
        layout.addWidget(nav_box)
        layout.addStretch(1)

        self._panel_list.itemDoubleClicked.connect(self._on_remove_item)
        self.refresh_panels()

    def refresh_panels(self) -> None:
        self._panel_list.clear()
        dirs = [Path(p) for p in self._state.get("panel_directories", [])]
        for panel in panels_from_directories(dirs):
            item = QListWidgetItem(f"{panel.label}   ×")
            item.setData(Qt.ItemDataRole.UserRole, str(panel.directory.resolve()))
            item.setToolTip("Double-click to remove")
            self._panel_list.addItem(item)

    def _on_remove_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str):
            self.remove_panel.emit(path)

    def _set(self, key: str, value) -> None:
        self._state[key] = value
        self.settings_changed.emit()

    def _on_sync(self, checked: bool) -> None:
        self._match.setEnabled(checked)
        self._set("sync_mode", checked)

    def _on_display_mode(self, value: str) -> None:
        self._custom_width.setEnabled(value == "Custom width")
        self._set("display_mode", value)

    def _on_dpi(self, value: int) -> None:
        stepped = 100 + ((value - 100) // 25) * 25
        if stepped != value:
            self._dpi.blockSignals(True)
            self._dpi.setValue(stepped)
            self._dpi.blockSignals(False)
            value = stepped
        self._dpi_label.setText(str(value))
        self._set("pdf_dpi", value)

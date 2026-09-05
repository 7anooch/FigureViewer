from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from figureviewer.figures import PanelConfig
from figureviewer.metadata import load_metadata, save_metadata


class _MetadataEditor(QWidget):
    def __init__(self, panel: PanelConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._panel = panel
        self._description = QTextEdit()
        self._description.setMaximumHeight(80)
        self._commit = QLineEdit()
        self._script = QLineEdit()
        self._source = QLineEdit()
        self._tags = QLineEdit()
        self._notes = QTextEdit()
        self._notes.setMaximumHeight(60)
        self._fmt = QComboBox()
        self._fmt.addItems(["yaml", "json", "txt"])
        self._save = QPushButton("Save metadata")
        self._save.clicked.connect(self._on_save)

        form = QFormLayout(self)
        form.addRow("Description", self._description)
        form.addRow("Commit hash", self._commit)
        form.addRow("Generating script", self._script)
        form.addRow("Source data", self._source)
        form.addRow("Tags", self._tags)
        form.addRow("Notes", self._notes)
        form.addRow("Save format", self._fmt)
        form.addRow(self._save)
        self.reload()

    def reload(self) -> None:
        meta = load_metadata(self._panel.directory)
        self._description.setPlainText(str(meta.get("description", "")))
        self._commit.setText(str(meta.get("commit_hash", "")))
        self._script.setText(str(meta.get("generating_script", "")))
        self._source.setText(str(meta.get("source_data", "")))
        self._tags.setText(str(meta.get("tags", "")))
        self._notes.setPlainText(str(meta.get("notes", "")))

    def _on_save(self) -> None:
        path = save_metadata(
            self._panel.directory,
            {
                "description": self._description.toPlainText(),
                "commit_hash": self._commit.text(),
                "generating_script": self._script.text(),
                "source_data": self._source.text(),
                "tags": self._tags.text(),
                "notes": self._notes.toPlainText(),
            },
            fmt=self._fmt.currentText(),
        )
        QMessageBox.information(self, "Saved", f"Saved {path}")


class MetadataPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._box = QGroupBox("Metadata")
        self._tabs = QTabWidget()
        box_layout = QVBoxLayout(self._box)
        box_layout.addWidget(self._tabs)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._box)
        self.setVisible(False)

    def set_panel(self, panel: PanelConfig | None) -> None:
        """Back-compat: show a single panel (or hide)."""
        self.set_panels([panel] if panel is not None else None)

    def set_panels(self, panels: list[PanelConfig] | None) -> None:
        while self._tabs.count():
            widget = self._tabs.widget(0)
            self._tabs.removeTab(0)
            if widget is not None:
                widget.deleteLater()
        if not panels:
            self.setVisible(False)
            return
        for panel in panels:
            self._tabs.addTab(_MetadataEditor(panel), panel.label)
        self._box.setTitle("Metadata" if len(panels) > 1 else f"Metadata: {panels[0].label}")
        self.setVisible(True)

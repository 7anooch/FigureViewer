from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from figuregallery.export import suggest_export_directory, suggest_export_filename
from figuregallery.models import FigureRef, GroupMode


class ExportPdfDialog(QDialog):
    """Choose output directory and filename before exporting the playlist."""

    def __init__(
        self,
        refs: list[FigureRef],
        *,
        scan_root: Path | None,
        group_mode: GroupMode,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export PDF")
        self.resize(680, 200)
        self._refs = refs

        default_dir = suggest_export_directory(scan_root)
        default_name = suggest_export_filename(refs, group_mode)

        self._dir_edit = QLineEdit(str(default_dir))
        self._name_edit = QLineEdit(default_name)
        field_height = QFontMetrics(self._dir_edit.font()).height() + 14
        field_min_width = 480
        for edit in (self._dir_edit, self._name_edit):
            edit.setMinimumHeight(field_height)
            edit.setMinimumWidth(field_min_width)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        browse_btn = QPushButton("Browse…")
        browse_btn.setMinimumHeight(field_height)
        browse_btn.clicked.connect(self._browse_directory)

        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.addWidget(self._dir_edit, stretch=1)
        dir_row.addWidget(browse_btn)
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)

        self._path_preview = QLabel()
        self._path_preview.setWordWrap(True)
        self._path_preview.setStyleSheet("color: #555;")

        summary = QLabel(f"Export {len(refs)} figure{'s' if len(refs) != 1 else ''} (one per page).")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow("Output directory:", dir_widget)
        form.addRow("Filename:", self._name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addLayout(form)
        layout.addWidget(self._path_preview)
        layout.addWidget(buttons)

        self._dir_edit.textChanged.connect(self._update_preview)
        self._name_edit.textChanged.connect(self._update_preview)
        self._update_preview()

    def output_path(self) -> Path:
        directory = Path(self._dir_edit.text().strip()).expanduser()
        name = self._name_edit.text().strip() or "figure_gallery.pdf"
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"
        return (directory / name).resolve()

    def _browse_directory(self) -> None:
        initial = self._dir_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select output directory", initial)
        if chosen:
            self._dir_edit.setText(chosen)

    def _update_preview(self) -> None:
        try:
            path = self.output_path()
            self._path_preview.setText(f"Will write: {path}")
        except Exception:
            self._path_preview.setText("Invalid path")

    def accept(self) -> None:
        directory = Path(self._dir_edit.text().strip()).expanduser()
        if not directory.is_dir():
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Invalid directory", f"Not a directory:\n{directory}")
            return
        name = self._name_edit.text().strip()
        if not name:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Missing filename", "Please enter a filename.")
            return
        super().accept()

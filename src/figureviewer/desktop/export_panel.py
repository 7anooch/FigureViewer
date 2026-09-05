from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from figureviewer.display_state import (
    export_index_labels,
    get_viewport_snapshot,
    iter_viewport_snapshots,
)
from figureviewer.export_figures import (
    export_viewport_snapshot,
    format_stem_suptitle,
    resolve_export_titles,
    suggest_export_output_dir,
)
from figureviewer.figures import panels_from_directories
from figureviewer.viewer_state import ViewerState


class ExportPanel(QWidget):
    export_dir_changed = pyqtSignal()

    def __init__(self, state: ViewerState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._dir_edit = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        self._choose_each = QCheckBox("Choose output folder on each save")
        self._custom_titles = QCheckBox("Use custom titles")
        self._titles_edit = QTextEdit()
        self._titles_edit.setMaximumHeight(70)
        self._titles_edit.setVisible(False)
        self._custom_titles.toggled.connect(self._titles_edit.setVisible)

        self._dpi = QSlider(Qt.Orientation.Horizontal)
        self._dpi.setRange(150, 600)
        self._dpi.setSingleStep(25)
        self._dpi.setValue(int(state.get("export_pdf_dpi", 300)))
        self._dpi_label = QLabel(str(self._dpi.value()))
        self._dpi.valueChanged.connect(self._on_dpi)

        self._preserve = QCheckBox("Preserve native resolution")
        self._preserve.setChecked(bool(state.get("export_preserve_native", True)))
        self._min_width = QSlider(Qt.Orientation.Horizontal)
        self._min_width.setRange(400, 4000)
        self._min_width.setSingleStep(50)
        self._min_width.setValue(int(state.get("export_min_panel_width", 1200)))
        self._min_label = QLabel(str(self._min_width.value()))
        self._min_width.valueChanged.connect(self._on_min_width)

        self._save_one = QPushButton("Save figure")
        self._save_all = QPushButton("Save all figures")
        self._save_one.clicked.connect(self._save_current)
        self._save_all.clicked.connect(self._save_all_figures)

        dir_row = QHBoxLayout()
        dir_row.addWidget(self._dir_edit, stretch=1)
        dir_row.addWidget(browse)

        box = QGroupBox("Export")
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("Save the current multi-panel view as one PNG."))
        layout.addLayout(dir_row)
        layout.addWidget(self._choose_each)
        layout.addWidget(self._custom_titles)
        layout.addWidget(self._titles_edit)
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("Export PDF / SVG DPI"))
        dpi_row.addWidget(self._dpi, stretch=1)
        dpi_row.addWidget(self._dpi_label)
        layout.addLayout(dpi_row)
        layout.addWidget(self._preserve)
        min_row = QHBoxLayout()
        min_row.addWidget(QLabel("Min panel width"))
        min_row.addWidget(self._min_width, stretch=1)
        min_row.addWidget(self._min_label)
        layout.addLayout(min_row)
        layout.addWidget(self._save_one)
        layout.addWidget(self._save_all)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        self.sync_default_dir()

    def sync_default_dir(self) -> None:
        dirs = [Path(p) for p in self._state.get("panel_directories", [])]
        panels = panels_from_directories(dirs)
        if not panels:
            return
        if not self._state.get("export_output_dir_user_set"):
            suggested = str(suggest_export_output_dir(panels))
            self._state["export_output_dir"] = suggested
            self._dir_edit.setText(suggested)
        elif self._state.get("export_output_dir"):
            self._dir_edit.setText(str(self._state.get("export_output_dir")))

    def _on_dpi(self, value: int) -> None:
        stepped = 150 + ((value - 150) // 25) * 25
        if stepped != value:
            self._dpi.blockSignals(True)
            self._dpi.setValue(stepped)
            self._dpi.blockSignals(False)
            value = stepped
        self._dpi_label.setText(str(value))
        self._state["export_pdf_dpi"] = value
        self.export_dir_changed.emit()

    def _on_min_width(self, value: int) -> None:
        stepped = 400 + ((value - 400) // 50) * 50
        if stepped != value:
            self._min_width.blockSignals(True)
            self._min_width.setValue(stepped)
            self._min_width.blockSignals(False)
            value = stepped
        self._min_label.setText(str(value))
        self._state["export_min_panel_width"] = value

    def _browse(self) -> None:
        initial = self._dir_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select output directory", initial)
        if chosen:
            self._dir_edit.setText(chosen)
            self._state["export_output_dir"] = chosen
            self._state["export_output_dir_user_set"] = True
            self.export_dir_changed.emit()

    def _output_dir(self) -> Path | None:
        if self._choose_each.isChecked() or not self._dir_edit.text().strip():
            initial = self._dir_edit.text().strip() or str(Path.home())
            chosen = QFileDialog.getExistingDirectory(self, "Select output directory", initial)
            if not chosen:
                return None
            self._dir_edit.setText(chosen)
            self._state["export_output_dir"] = chosen
            self._state["export_output_dir_user_set"] = True
            self.export_dir_changed.emit()
        path = Path(self._dir_edit.text().strip()).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Invalid directory", str(exc))
            return None
        return path

    def _resolve_titles(self):
        dirs = [Path(p) for p in self._state.get("panel_directories", [])]
        panels = panels_from_directories(dirs)
        try:
            return resolve_export_titles(
                panels,
                use_custom=self._custom_titles.isChecked(),
                custom_text=self._titles_edit.toPlainText(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Titles", str(exc))
            return None

    def _stem_suptitle(self, label: str) -> str | None:
        if self._state.get("sync_mode") and self._state.get("match_by") == "filename stem":
            return format_stem_suptitle(label)
        return None

    def _save_current(self) -> None:
        snapshot = get_viewport_snapshot(self._state)
        if snapshot is None:
            QMessageBox.information(self, "Export", "No figures are available to export.")
            return
        output_dir = self._output_dir()
        if output_dir is None:
            return
        titles = self._resolve_titles()
        if titles is None:
            return
        try:
            result = export_viewport_snapshot(
                snapshot,
                titles=titles,
                output_dir=output_dir,
                pdf_dpi=int(self._state.get("export_pdf_dpi", 300)),
                cell_width=int(self._state.get("export_min_panel_width", 1200)),
                trim_whitespace_margins=bool(self._state.get("trim_whitespace", False)),
                preserve_native=self._preserve.isChecked(),
                suptitle=self._stem_suptitle(snapshot.current_label),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Saved", f"Saved {result.path}")

    def _save_all_figures(self) -> None:
        labels = export_index_labels(self._state)
        if not labels:
            QMessageBox.information(self, "Export", "No figures are available to export.")
            return
        output_dir = self._output_dir()
        if output_dir is None:
            return
        titles = self._resolve_titles()
        if titles is None:
            return
        snapshots = list(iter_viewport_snapshots(self._state))
        progress = QProgressDialog("Exporting…", "Cancel", 0, len(snapshots), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        saved = 0
        failures: list[str] = []
        for i, snapshot in enumerate(snapshots):
            progress.setValue(i)
            if progress.wasCanceled():
                break
            try:
                export_viewport_snapshot(
                    snapshot,
                    titles=titles,
                    output_dir=output_dir,
                    pdf_dpi=int(self._state.get("export_pdf_dpi", 300)),
                    cell_width=int(self._state.get("export_min_panel_width", 1200)),
                    trim_whitespace_margins=bool(self._state.get("trim_whitespace", False)),
                    preserve_native=self._preserve.isChecked(),
                    filename=None,
                    suptitle=self._stem_suptitle(snapshot.current_label),
                )
                saved += 1
            except Exception as exc:
                failures.append(f"{snapshot.current_label}: {exc}")
        progress.setValue(len(snapshots))
        summary = f"Saved {saved} of {len(snapshots)} figures."
        if failures:
            shown = failures[:8]
            detail = "\n".join(shown)
            if len(failures) > len(shown):
                detail += f"\n… and {len(failures) - len(shown)} more"
            QMessageBox.warning(self, "Export complete", f"{summary}\n\nFailures:\n{detail}")
        else:
            QMessageBox.information(self, "Export complete", summary)

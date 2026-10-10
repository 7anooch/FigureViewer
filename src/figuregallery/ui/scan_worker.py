from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from figurecommon.scan import ScanOptions
from figuregallery.index import ScanCancelled, build_scan_index
from figuregallery.models import ScanIndex


class ScanWorker(QThread):
    """Build a ScanIndex off the UI thread; supports cancel via requestInterruption()."""

    finished_ok = pyqtSignal(object)  # ScanIndex
    failed = pyqtSignal(str)
    progress = pyqtSignal(int)
    cancelled = pyqtSignal()

    def __init__(
        self,
        root: Path,
        *,
        options: ScanOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._root = root
        self._options = options or ScanOptions()

    def run(self) -> None:
        def _report(count: int) -> None:
            if not self.isInterruptionRequested():
                self.progress.emit(count)

        try:
            index = build_scan_index(
                self._root,
                options=self._options,
                should_cancel=self.isInterruptionRequested,
                on_progress=_report,
            )
        except ScanCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
            else:
                self.cancelled.emit()
            return
        if self.isInterruptionRequested():
            self.cancelled.emit()
            return
        self.finished_ok.emit(index)

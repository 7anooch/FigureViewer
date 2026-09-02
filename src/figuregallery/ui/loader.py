from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from figurecommon.render import load_figure_bytes


class FigureLoader(QThread):
    loaded = pyqtSignal(str, QImage)
    failed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._path: Path | None = None
        self._generation = 0

    def load(self, path: Path) -> None:
        self._generation += 1
        self._path = path
        if self.isRunning():
            self.requestInterruption()
            self.wait(2000)
        self.start()

    def run(self) -> None:
        if self._path is None:
            return
        path = self._path
        generation = self._generation
        try:
            data = load_figure_bytes(str(path), pdf_dpi=150, trim=False)
            image = QImage.fromData(data)
            if image.isNull():
                raise RuntimeError("Could not decode image")
            if generation == self._generation and not self.isInterruptionRequested():
                self.loaded.emit(str(path.resolve()), image)
        except Exception as exc:
            if generation == self._generation and not self.isInterruptionRequested():
                self.failed.emit(str(path.resolve()), str(exc))

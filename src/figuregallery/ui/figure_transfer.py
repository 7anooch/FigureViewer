from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeData, QUrl


def figure_file_mime_data(source_path: Path) -> QMimeData | None:
    """MIME payload that transfers the on-disk figure file (not a rendered preview)."""
    try:
        resolved = source_path.expanduser().resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(resolved))])
    return mime

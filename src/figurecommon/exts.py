from __future__ import annotations

from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VECTOR_EXTS = {".svg"}
PDF_EXTS = {".pdf"}
FIGURE_EXTS = IMAGE_EXTS | VECTOR_EXTS | PDF_EXTS
DISPLAYABLE_EXTS = IMAGE_EXTS | VECTOR_EXTS


def is_displayable_path(path: Path) -> bool:
    return path.suffix.lower() in DISPLAYABLE_EXTS


def is_figure_path(path: Path, *, include_pdf: bool = True) -> bool:
    suffix = path.suffix.lower()
    if suffix in DISPLAYABLE_EXTS:
        return True
    if include_pdf and suffix in PDF_EXTS:
        return True
    return False

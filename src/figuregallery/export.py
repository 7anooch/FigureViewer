from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

from figurecommon.render import load_figure_bytes
from figuregallery.models import FigureRef, GroupMode

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

# US Letter points (72 pt = 1 inch)
_PAGE_WIDTH = 612.0
_PAGE_HEIGHT = 792.0
_MARGIN = 36.0
_TITLE_TOP = 40.0
_TITLE_GAP = 16.0


@dataclass(frozen=True)
class ExportResult:
    path: Path
    pages: int


def path_title(relative_path: Path) -> str:
    """Breadcrumb-style title matching the path bar (no hyperlink styling)."""
    parts = relative_path.parts
    if not parts:
        return str(relative_path)
    return " / ".join(parts)


def _safe_filename_stem(text: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", text.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._")
    return cleaned or "figures"


def suggest_export_filename(refs: list[FigureRef], group_mode: GroupMode) -> str:
    if not refs:
        return "figure_gallery.pdf"
    keys = {ref.category_key(group_mode) for ref in refs}
    if len(keys) == 1:
        return f"{_safe_filename_stem(next(iter(keys)))}_gallery.pdf"
    return f"figure_gallery_{len(refs)}_figures.pdf"


def suggest_export_directory(scan_root: Path | None) -> Path:
    if scan_root is not None and scan_root.is_dir():
        return scan_root.resolve()
    return Path.home()


def export_playlist_pdf(
    refs: list[FigureRef],
    output_path: Path,
    *,
    pdf_dpi: int = 150,
    progress_callback=None,
) -> ExportResult:
    """Write one PDF page per figure in playlist order."""
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for PDF export")
    if not refs:
        raise ValueError("No figures to export")

    output_path = output_path.expanduser().resolve()
    if output_path.suffix.lower() != ".pdf":
        output_path = output_path.with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    try:
        for index, ref in enumerate(refs):
            if progress_callback is not None:
                progress_callback(index, len(refs), ref)
            _add_figure_page(doc, ref, pdf_dpi=pdf_dpi)
        doc.save(str(output_path))
    finally:
        doc.close()

    return ExportResult(path=output_path, pages=len(refs))


def _add_figure_page(doc, ref: FigureRef, *, pdf_dpi: int) -> None:
    page = doc.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
    title = path_title(ref.relative_path)
    page.insert_text(
        (_MARGIN, _TITLE_TOP),
        title,
        fontsize=11,
        fontname="helv",
        color=(0.15, 0.15, 0.15),
    )

    png_bytes = load_figure_bytes(str(ref.absolute_path), pdf_dpi=pdf_dpi, trim=False)
    with Image.open(BytesIO(png_bytes)) as image:
        iw, ih = image.size

    image_top = _TITLE_TOP + _TITLE_GAP
    outer = fitz.Rect(_MARGIN, image_top, _PAGE_WIDTH - _MARGIN, _PAGE_HEIGHT - _MARGIN)
    target = _fit_rect(outer, float(iw), float(ih))
    page.insert_image(target, stream=png_bytes)


def _fit_rect(outer, image_width: float, image_height: float):
    if image_width <= 0 or image_height <= 0:
        return outer
    scale = min(outer.width / image_width, outer.height / image_height)
    width = image_width * scale
    height = image_height * scale
    x0 = outer.x0 + (outer.width - width) / 2.0
    y0 = outer.y0 + (outer.height - height) / 2.0
    return fitz.Rect(x0, y0, x0 + width, y0 + height)

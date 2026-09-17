from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

from figurecommon.exts import is_video_path
from figurecommon.render import load_figure_bytes
from figuregallery.models import FigureRef, GroupMode

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None


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
    pdf_dpi: int = 200,
    trim: bool = False,
    progress_callback=None,
) -> ExportResult:
    """Write one figure-sized PDF page per still figure (videos are skipped)."""
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for PDF export")
    if not refs:
        raise ValueError("No figures to export")

    still_refs = [ref for ref in refs if not is_video_path(ref.absolute_path)]
    if not still_refs:
        raise ValueError("No still figures to export (playlist is video-only)")

    output_path = output_path.expanduser().resolve()
    if output_path.suffix.lower() != ".pdf":
        output_path = output_path.with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    try:
        for index, ref in enumerate(still_refs):
            if progress_callback is not None:
                progress_callback(index, len(still_refs), ref)
            _add_figure_page(doc, ref, pdf_dpi=pdf_dpi, trim=trim)
        doc.save(str(output_path))
    finally:
        doc.close()

    return ExportResult(path=output_path, pages=len(still_refs))


def _add_figure_page(doc, ref: FigureRef, *, pdf_dpi: int, trim: bool = False) -> None:
    """Add a page whose size matches the figure (no fixed Letter/A4 canvas)."""
    png_bytes = load_figure_bytes(str(ref.absolute_path), pdf_dpi=pdf_dpi, trim=trim)
    with Image.open(BytesIO(png_bytes)) as image:
        iw, ih = image.size

    # 1 PDF point per pixel — page crops tightly to the figure.
    width = max(1.0, float(iw))
    height = max(1.0, float(ih))
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=png_bytes)

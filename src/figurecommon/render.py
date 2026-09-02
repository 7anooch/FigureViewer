from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

_WHITESPACE_THRESHOLD = 245
_TRIM_PADDING = 12


def load_raster_image(path: str) -> bytes:
    return Path(path).read_bytes()


def render_pdf_page(path: str, dpi: int = 200) -> bytes:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed")
    doc = fitz.open(path)
    try:
        page = doc[0]
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return pixmap.tobytes("png")
    finally:
        doc.close()


def trim_whitespace(
    image: Image.Image,
    *,
    threshold: int = _WHITESPACE_THRESHOLD,
    padding: int = _TRIM_PADDING,
) -> Image.Image:
    """Crop near-white margins; leave a small padded border around content."""
    rgb = image.convert("RGB")
    r, g, b = rgb.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    content = darkest.point(lambda p: 255 if p < threshold else 0)
    bbox = content.getbbox()
    if bbox is None:
        return rgb

    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(rgb.width, right + padding)
    bottom = min(rgb.height, bottom + padding)
    if right <= left or bottom <= top:
        return rgb
    return rgb.crop((left, top, right, bottom))


def image_to_png_bytes(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def load_figure_bytes(path: str, *, pdf_dpi: int, trim: bool) -> bytes:
    """Load a figure as PNG bytes, optionally trimming near-white margins."""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        if fitz is None:
            raise RuntimeError("PyMuPDF is not installed")
        raw = render_pdf_page(path, dpi=pdf_dpi)
        image = Image.open(BytesIO(raw))
    elif suffix == ".svg":
        if fitz is None:
            raise RuntimeError("PyMuPDF is required to load SVG figures.")
        doc = fitz.open(path)
        try:
            page = doc[0]
            zoom = pdf_dpi / 72.0
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
        finally:
            doc.close()
    else:
        image = Image.open(BytesIO(load_raster_image(path)))

    if trim:
        image = trim_whitespace(image)
    else:
        image = image.convert("RGB")
    return image_to_png_bytes(image)

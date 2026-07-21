from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Union

import streamlit as st
from PIL import Image, ImageChops

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

DisplayWidth = Union[str, int]

# Pixels with all RGB channels >= this are treated as empty margin.
_WHITESPACE_THRESHOLD = 245
# Keep a small border of whitespace around the detected content.
_TRIM_PADDING = 12


@st.cache_data(show_spinner=False)
def load_raster_image(path: str) -> bytes:
    return Path(path).read_bytes()


@st.cache_data(show_spinner=False)
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
    # Content = any RGB channel darker than threshold (keeps pale colored ink).
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


@st.cache_data(show_spinner=False)
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


def resolve_display_width(display_mode: str, custom_width: int) -> DisplayWidth:
    if display_mode == "Fill panel":
        return "stretch"
    if display_mode == "Natural size":
        return "content"
    return custom_width


def show_image(image_data: Union[str, bytes], display_width: DisplayWidth) -> None:
    try:
        st.image(image_data, width=display_width)
        return
    except (TypeError, ValueError):
        pass
    if display_width == "stretch":
        st.image(image_data, use_container_width=True)
    elif display_width == "content":
        st.image(image_data)
    else:
        st.image(image_data, width=display_width)


def render_figure(
    path: Path,
    *,
    display_width: DisplayWidth,
    pdf_dpi: int,
    pdf_mode: str,
    pdf_embed_height: int,
    trim_whitespace_margins: bool = False,
) -> None:
    suffix = path.suffix.lower()
    if suffix == ".pdf" and pdf_mode == "Embedded viewer":
        if trim_whitespace_margins:
            st.caption("Whitespace trim applies to Rasterize mode only.")
        if hasattr(st, "pdf"):
            st.pdf(str(path), height=pdf_embed_height)
        else:
            st.warning("Embedded PDF viewer requires `pip install streamlit[pdf]`.")
        return

    try:
        image_bytes = load_figure_bytes(
            str(path),
            pdf_dpi=pdf_dpi,
            trim=trim_whitespace_margins,
        )
        show_image(image_bytes, display_width)
    except Exception as exc:
        if suffix == ".pdf":
            st.error(f"Could not rasterize PDF: {exc}")
            return
        st.error(f"Could not load figure: {exc}")

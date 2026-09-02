from __future__ import annotations

from pathlib import Path
from typing import Union

import streamlit as st

from figurecommon.render import load_figure_bytes as _load_figure_bytes
from figurecommon.render import trim_whitespace

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

DisplayWidth = Union[str, int]


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


@st.cache_data(show_spinner=False)
def load_figure_bytes(path: str, *, pdf_dpi: int, trim: bool) -> bytes:
    return _load_figure_bytes(path, pdf_dpi=pdf_dpi, trim=trim)


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

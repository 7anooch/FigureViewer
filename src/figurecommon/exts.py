from __future__ import annotations

from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VECTOR_EXTS = {".svg"}
PDF_EXTS = {".pdf"}
# Inline playback (desktop Compare + Browse; Streamlit uses st.video).
VIDEO_EXTS = {".mp4"}
FIGURE_EXTS = IMAGE_EXTS | VECTOR_EXTS | PDF_EXTS
DISPLAYABLE_EXTS = FIGURE_EXTS | VIDEO_EXTS


def is_displayable_path(path: Path) -> bool:
    return path.suffix.lower() in DISPLAYABLE_EXTS


def is_video_path(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def is_figure_path(
    path: Path,
    *,
    include_pdf: bool = True,
    include_video: bool = True,
) -> bool:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTS | VECTOR_EXTS:
        return True
    if include_pdf and suffix in PDF_EXTS:
        return True
    if include_video and suffix in VIDEO_EXTS:
        return True
    return False

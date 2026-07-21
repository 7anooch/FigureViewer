from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from figureviewer.display_state import ViewportSnapshot
from figureviewer.figures import PanelConfig
from figureviewer.render import load_figure_bytes


@dataclass
class ExportResult:
    path: Path
    panels_exported: int


@dataclass
class BatchExportResult:
    output_dir: Path
    saved: int
    failed: int
    total: int
    first_path: Optional[Path] = None
    errors: List[str] | None = None


def suggest_export_output_dir(panels: List[PanelConfig]) -> Path:
    if not panels:
        return Path.home()
    paths = [p.directory.resolve() for p in panels]
    if len(paths) == 1:
        return paths[0].parent
    try:
        common = Path(os.path.commonpath([str(p) for p in paths]))
        return common if common.is_dir() else common.parent
    except ValueError:
        return paths[0].parent


def resolve_export_titles(
    panels: List[PanelConfig],
    *,
    use_custom: bool,
    custom_text: str,
) -> List[str]:
    if not use_custom:
        return [p.label for p in panels]
    lines = [line.strip() for line in custom_text.splitlines() if line.strip()]
    if len(lines) != len(panels):
        raise ValueError(f"Expected {len(panels)} custom titles, got {len(lines)}.")
    return lines


def _title_font(size: int = 18) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def resolve_export_cell_width(
    images: List[Optional[Image.Image]],
    *,
    min_width: int,
    preserve_native: bool,
) -> int:
    """Pick panel width for the composite.

    When preserve_native is on, never downscale: use the widest source image,
    floored by min_width. Otherwise use min_width as a fixed panel width.
    """
    min_width = max(int(min_width), 1)
    if not preserve_native:
        return min_width
    widths = [im.width for im in images if im is not None]
    if not widths:
        return min_width
    return max(max(widths), min_width)


def load_figure_as_image(path: Path, *, pdf_dpi: int, trim: bool = False) -> Image.Image:
    data = load_figure_bytes(str(path), pdf_dpi=pdf_dpi, trim=trim)
    return Image.open(BytesIO(data)).convert("RGB")


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", value.strip())
    return cleaned[:120] or "figure"


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    left, top, right, bottom = box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = left + max((right - left - text_w) // 2, 0)
    y = top + max((bottom - top - text_h) // 2, 0)
    draw.text((x, y), text, fill=fill, font=font)


def _layout_scale(cell_width: int, reference_width: int = 700) -> float:
    return max(cell_width / reference_width, 1.0)


def build_composite_image(
    titles: List[str],
    images: List[Optional[Image.Image]],
    *,
    columns_per_row: int,
    cell_width: int,
    title_height: int | None = None,
    gap: int | None = None,
    pad: int | None = None,
    bg: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    if len(titles) != len(images):
        raise ValueError("Titles and images must have the same length.")

    count = len(titles)
    cols = max(columns_per_row, 1)
    rows = (count + cols - 1) // cols
    scale = _layout_scale(cell_width)
    if title_height is None:
        title_height = max(40, int(round(40 * scale)))
    if gap is None:
        gap = max(16, int(round(16 * scale)))
    if pad is None:
        pad = max(12, int(round(12 * scale)))
    font = _title_font(size=max(18, int(round(18 * scale))))

    scaled_heights: List[int] = []
    for image in images:
        if image is None:
            scaled_heights.append(max(cell_width // 2, 120))
            continue
        width, height = image.size
        scaled_heights.append(max(int(height * cell_width / max(width, 1)), 1))

    row_heights: List[int] = []
    for row in range(rows):
        start = row * cols
        end = min(start + cols, count)
        max_img_h = max(scaled_heights[start:end], default=120)
        row_heights.append(title_height + max_img_h)

    total_w = cols * cell_width + max(cols - 1, 0) * gap + 2 * pad
    total_h = sum(row_heights) + max(rows - 1, 0) * gap + 2 * pad
    canvas = Image.new("RGB", (total_w, total_h), bg)
    draw = ImageDraw.Draw(canvas)

    y = pad
    for row in range(rows):
        x = pad
        row_h = row_heights[row]
        for col in range(cols):
            index = row * cols + col
            if index >= count:
                break

            title_box = (x, y, x + cell_width, y + title_height)
            draw.rectangle(title_box, fill=(245, 245, 245))
            _draw_centered_text(
                draw,
                titles[index],
                title_box,
                font=font,
                fill=(20, 20, 20),
            )

            image_top = y + title_height
            image_height = scaled_heights[index]
            image = images[index]
            if image is not None:
                if image.size == (cell_width, image_height):
                    resized = image
                else:
                    resized = image.resize(
                        (cell_width, image_height),
                        Image.Resampling.LANCZOS,
                    )
                canvas.paste(resized, (x, image_top))
            else:
                draw.rectangle(
                    [x, image_top, x + cell_width, image_top + image_height],
                    fill=(225, 225, 225),
                )
                draw.text(
                    (x + 8, image_top + 8),
                    "No figure",
                    fill=(90, 90, 90),
                    font=font,
                )

            x += cell_width + gap
        y += row_h + gap

    return canvas


def export_viewport_snapshot(
    snapshot: ViewportSnapshot,
    *,
    titles: List[str],
    output_dir: Path,
    pdf_dpi: int,
    cell_width: int,
    trim_whitespace_margins: bool = False,
    preserve_native: bool = True,
    filename: Optional[str] = None,
) -> ExportResult:
    if len(titles) != len(snapshot.panels):
        raise ValueError("Title count does not match panel count.")

    images: List[Optional[Image.Image]] = []
    for path in snapshot.figure_paths:
        if path is None:
            images.append(None)
            continue
        images.append(
            load_figure_as_image(path, pdf_dpi=pdf_dpi, trim=trim_whitespace_margins)
        )

    resolved_width = resolve_export_cell_width(
        images,
        min_width=cell_width,
        preserve_native=preserve_native,
    )
    composite = build_composite_image(
        titles,
        images,
        columns_per_row=snapshot.columns_per_row,
        cell_width=resolved_width,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{_safe_filename(snapshot.current_label)}_{timestamp}.png"
    out_path = output_dir / filename
    # Embed DPI so print tools treat the PNG at the export rasterization density.
    composite.save(out_path, format="PNG", dpi=(pdf_dpi, pdf_dpi))

    exported = sum(1 for path in snapshot.figure_paths if path is not None)
    return ExportResult(path=out_path, panels_exported=exported)


def export_all_viewport_snapshots(
    snapshots: List[ViewportSnapshot],
    *,
    titles: List[str],
    output_dir: Path,
    pdf_dpi: int,
    cell_width: int,
    trim_whitespace_margins: bool = False,
    preserve_native: bool = True,
) -> BatchExportResult:
    """Export every snapshot; filenames are numbered for stable ordering."""
    batch_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = 0
    failed = 0
    first_path: Optional[Path] = None
    errors: List[str] = []

    for snapshot in snapshots:
        filename = (
            f"{snapshot.index + 1:04d}_{_safe_filename(snapshot.current_label)}"
            f"_{batch_stamp}.png"
        )
        try:
            result = export_viewport_snapshot(
                snapshot,
                titles=titles,
                output_dir=output_dir,
                pdf_dpi=pdf_dpi,
                cell_width=cell_width,
                trim_whitespace_margins=trim_whitespace_margins,
                preserve_native=preserve_native,
                filename=filename,
            )
        except Exception as exc:
            failed += 1
            errors.append(f"{snapshot.current_label}: {exc}")
            continue
        saved += 1
        if first_path is None:
            first_path = result.path

    return BatchExportResult(
        output_dir=output_dir,
        saved=saved,
        failed=failed,
        total=len(snapshots),
        first_path=first_path,
        errors=errors or None,
    )

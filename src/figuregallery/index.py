from __future__ import annotations

import time
from pathlib import Path

from figurecommon.scan import ScanOptions, walk_figures
from figurecommon.sort import natural_key

from figuregallery.models import FigureRef, ScanIndex


def build_scan_index(root: Path, *, options: ScanOptions | None = None) -> ScanIndex:
    options = options or ScanOptions()
    root = root.expanduser().resolve()
    refs: list[FigureRef] = []
    for abs_path in walk_figures(root, options):
        rel = abs_path.relative_to(root)
        refs.append(
            FigureRef(
                absolute_path=abs_path,
                relative_path=rel,
                filename=rel.name,
                stem=rel.stem,
            )
        )
    refs.sort(key=lambda r: natural_key(str(r.relative_path)))
    return ScanIndex(root=root, refs=refs, scanned_at=time.time())

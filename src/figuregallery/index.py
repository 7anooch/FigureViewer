from __future__ import annotations

import time
from pathlib import Path

from figurecommon.scan import ScanOptions, walk_figures
from figurecommon.sort import natural_key

from figuregallery.models import FigureRef, ScanIndex


class ScanCancelled(Exception):
    """Raised when a background scan is interrupted."""


def build_scan_index(
    root: Path,
    *,
    options: ScanOptions | None = None,
    should_cancel=None,
    on_progress=None,
) -> ScanIndex:
    """Build a figure index under ``root``.

    Optional ``should_cancel`` / ``on_progress`` support cancellable UI scans.
    ``on_progress`` receives the number of figures found so far.
    """
    options = options or ScanOptions()
    root = root.expanduser().resolve()
    refs: list[FigureRef] = []
    for abs_path in walk_figures(root, options, should_cancel=should_cancel):
        if should_cancel is not None and should_cancel():
            raise ScanCancelled()
        rel = abs_path.relative_to(root)
        refs.append(
            FigureRef(
                absolute_path=abs_path,
                relative_path=rel,
                filename=rel.name,
                stem=rel.stem,
            )
        )
        if on_progress is not None and len(refs) % 50 == 0:
            on_progress(len(refs))
    if should_cancel is not None and should_cancel():
        raise ScanCancelled()
    refs.sort(key=lambda r: natural_key(str(r.relative_path)))
    return ScanIndex(root=root, refs=refs, scanned_at=time.time())

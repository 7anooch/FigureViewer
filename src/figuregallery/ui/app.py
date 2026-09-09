from __future__ import annotations

from pathlib import Path

from figuregallery.models import GroupMode, SortMode
from figureviewer.desktop.modes import AppMode


def run(
    *,
    initial_root: Path | None = None,
    group_mode: GroupMode = GroupMode.STEM,
    sort_mode: SortMode = SortMode.CATEGORY_THEN_PATH,
) -> int:
    """Launch Browse mode inside the unified Figure Viewer desktop app."""
    from figureviewer.desktop.app import run as run_desktop

    return run_desktop(
        mode=AppMode.BROWSE,
        default_mode=AppMode.BROWSE,
        browse_kwargs={
            "initial_root": initial_root,
            "group_mode": group_mode,
            "sort_mode": sort_mode,
        },
    )

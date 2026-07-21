from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from figureviewer.browsing import get_panel_configs
from figureviewer.figures import (
    PanelConfig,
    common_stems,
    list_figures,
    stem_lookup,
)


@dataclass
class ViewportSnapshot:
    panels: List[PanelConfig]
    figure_paths: List[Optional[Path]]
    current_label: str
    columns_per_row: int
    index: int = 0
    total: int = 1


def _panel_figure_lists(session_state) -> Tuple[List[PanelConfig], List[List[Path]]]:
    panels = get_panel_configs()
    valid_panels = [p for p in panels if p.directory.exists() and p.directory.is_dir()]
    if not valid_panels:
        return [], []
    recursive = session_state.get("recursive", False)
    figure_lists = [list_figures(p.directory, recursive=recursive) for p in valid_panels]
    if not any(figure_lists):
        return valid_panels, []
    return valid_panels, figure_lists


def export_index_labels(session_state) -> List[str]:
    """Labels for every figure index that batch export would walk."""
    valid_panels, figure_lists = _panel_figure_lists(session_state)
    if not valid_panels or not figure_lists:
        return []

    sync_mode = session_state.get("sync_mode", True)
    match_by = session_state.get("match_by", "position")

    if sync_mode and match_by == "filename stem":
        return common_stems(figure_lists)

    max_len = max(len(figs) for figs in figure_lists)
    return [str(i + 1) for i in range(max_len)]


def get_viewport_snapshot(
    session_state,
    *,
    index: Optional[int] = None,
) -> Optional[ViewportSnapshot]:
    """Resolve figures for the current (or given) navigation index."""
    valid_panels, figure_lists = _panel_figure_lists(session_state)
    if not valid_panels or not figure_lists:
        return None

    sync_mode = session_state.get("sync_mode", True)
    match_by = session_state.get("match_by", "position")
    columns_per_row = session_state.get("columns_per_row", 2)
    labels = export_index_labels(session_state)
    if not labels:
        return None

    total = len(labels)
    use_explicit_index = index is not None
    if index is None:
        index = int(session_state.get("current_index", 0))
    index = max(0, min(index, total - 1))
    current_label = labels[index]

    figure_paths: List[Optional[Path]] = []
    for panel, figures in zip(valid_panels, figure_lists):
        chosen: Optional[Path] = None
        if sync_mode and match_by == "filename stem":
            chosen = stem_lookup(figures).get(current_label)
        elif sync_mode or use_explicit_index:
            if index < len(figures):
                chosen = figures[index]
        else:
            local_key = f"local_idx_{panel.label}_{panel.directory}"
            local_idx = session_state.get(local_key, 0)
            if local_idx < len(figures):
                chosen = figures[local_idx]
        figure_paths.append(chosen)

    return ViewportSnapshot(
        panels=valid_panels,
        figure_paths=figure_paths,
        current_label=current_label,
        columns_per_row=columns_per_row,
        index=index,
        total=total,
    )


def iter_viewport_snapshots(session_state) -> Iterator[ViewportSnapshot]:
    """Yield a snapshot for every exportable index (sync position or stem list)."""
    labels = export_index_labels(session_state)
    for i in range(len(labels)):
        snapshot = get_viewport_snapshot(session_state, index=i)
        if snapshot is not None:
            yield snapshot

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from figureviewer.figures import (
    PanelConfig,
    common_stems,
    list_figures,
    panels_from_directories,
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


@dataclass(frozen=True)
class _PanelIndex:
    """Cached directory listings + sync labels for the current panel setup."""

    key: tuple
    panels: Tuple[PanelConfig, ...]
    figure_lists: Tuple[Tuple[Path, ...], ...]
    labels: Tuple[str, ...]
    stem_lookups: Tuple[Dict[str, Path], ...]


_PANEL_INDEX: _PanelIndex | None = None


def invalidate_panel_index_cache() -> None:
    """Drop cached listings (e.g. after panels change on disk outside state keys)."""
    global _PANEL_INDEX
    _PANEL_INDEX = None


def _panel_index_key(session_state) -> tuple:
    raw = session_state.get("panel_directories", [])
    paths = tuple(str(Path(p).expanduser()) for p in raw) if isinstance(raw, list) else ()
    return (
        paths,
        bool(session_state.get("recursive", False)),
        bool(session_state.get("sync_mode", True)),
        str(session_state.get("match_by", "position")),
    )


def _build_labels(
    figure_lists: Sequence[Sequence[Path]],
    *,
    sync_mode: bool,
    match_by: str,
) -> Tuple[str, ...]:
    if not any(figure_lists):
        return ()
    if sync_mode and match_by == "filename stem":
        return tuple(common_stems([list(figs) for figs in figure_lists]))
    max_len = max(len(figs) for figs in figure_lists)
    return tuple(str(i + 1) for i in range(max_len))


def resolve_panel_index(session_state) -> _PanelIndex | None:
    """Return cached panel listings/labels, rebuilding only when the setup changes."""
    global _PANEL_INDEX
    key = _panel_index_key(session_state)
    if _PANEL_INDEX is not None and _PANEL_INDEX.key == key:
        return _PANEL_INDEX

    raw = session_state.get("panel_directories", [])
    paths = [Path(p) for p in raw] if isinstance(raw, list) else []
    panels = panels_from_directories(paths)
    valid_panels = [p for p in panels if p.directory.exists() and p.directory.is_dir()]
    if not valid_panels:
        _PANEL_INDEX = None
        return None

    recursive = bool(session_state.get("recursive", False))
    figure_lists = [tuple(list_figures(p.directory, recursive=recursive)) for p in valid_panels]
    if not any(figure_lists):
        _PANEL_INDEX = None
        return None

    sync_mode = bool(session_state.get("sync_mode", True))
    match_by = str(session_state.get("match_by", "position"))
    labels = _build_labels(figure_lists, sync_mode=sync_mode, match_by=match_by)
    if not labels:
        _PANEL_INDEX = None
        return None

    stem_lookups: Tuple[Dict[str, Path], ...]
    if sync_mode and match_by == "filename stem":
        stem_lookups = tuple(stem_lookup(list(figs)) for figs in figure_lists)
    else:
        stem_lookups = tuple({} for _ in figure_lists)

    _PANEL_INDEX = _PanelIndex(
        key=key,
        panels=tuple(valid_panels),
        figure_lists=tuple(figure_lists),
        labels=labels,
        stem_lookups=stem_lookups,
    )
    return _PANEL_INDEX


def _figure_paths_for_index(
    index_data: _PanelIndex,
    session_state,
    *,
    index: int,
    use_explicit_index: bool,
) -> List[Optional[Path]]:
    sync_mode = bool(session_state.get("sync_mode", True))
    match_by = str(session_state.get("match_by", "position"))
    current_label = index_data.labels[index]
    figure_paths: List[Optional[Path]] = []
    for panel, figures, stems in zip(
        index_data.panels, index_data.figure_lists, index_data.stem_lookups
    ):
        chosen: Optional[Path] = None
        if sync_mode and match_by == "filename stem":
            chosen = stems.get(current_label)
        elif sync_mode or use_explicit_index:
            if index < len(figures):
                chosen = figures[index]
        else:
            local_key = f"local_idx_{panel.label}_{panel.directory.resolve()}"
            local_idx = int(session_state.get(local_key, 0))
            if local_idx < len(figures):
                chosen = figures[local_idx]
        figure_paths.append(chosen)
    return figure_paths


def export_index_labels(session_state) -> List[str]:
    """Labels for every figure index that batch export would walk."""
    index_data = resolve_panel_index(session_state)
    if index_data is None:
        return []
    return list(index_data.labels)


def get_viewport_snapshot(
    session_state,
    *,
    index: Optional[int] = None,
) -> Optional[ViewportSnapshot]:
    """Resolve figures for the current (or given) navigation index."""
    index_data = resolve_panel_index(session_state)
    if index_data is None:
        return None

    columns_per_row = int(session_state.get("columns_per_row", 2))
    total = len(index_data.labels)
    use_explicit_index = index is not None
    if index is None:
        index = int(session_state.get("current_index", 0))
    index = max(0, min(index, total - 1))
    current_label = index_data.labels[index]
    figure_paths = _figure_paths_for_index(
        index_data,
        session_state,
        index=index,
        use_explicit_index=use_explicit_index,
    )

    return ViewportSnapshot(
        panels=list(index_data.panels),
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

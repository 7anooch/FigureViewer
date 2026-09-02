from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from figurecommon.sort import natural_key

from figuregallery.models import Category, FigureRef, GroupMode, SortMode


def build_playlist(
    categories: dict[str, Category],
    selected_keys: set[str],
    sort_mode: SortMode,
    *,
    group_mode: GroupMode,
) -> list[FigureRef]:
    if not selected_keys:
        return []

    keys = sorted(selected_keys, key=natural_key)
    if sort_mode == SortMode.CATEGORY_THEN_PATH:
        return _category_then_path(categories, keys)
    return _path_then_category(categories, keys, group_mode)


def _displayable(categories: dict[str, Category], key: str) -> list[FigureRef]:
    cat = categories.get(key)
    if cat is None:
        return []
    return cat.displayable_refs


def _category_then_path(categories: dict[str, Category], keys: list[str]) -> list[FigureRef]:
    out: list[FigureRef] = []
    for key in keys:
        refs = sorted(_displayable(categories, key), key=lambda r: natural_key(str(r.relative_path)))
        out.extend(refs)
    return out


def _path_then_category(
    categories: dict[str, Category],
    keys: list[str],
    group_mode: GroupMode,
) -> list[FigureRef]:
    pool: list[FigureRef] = []
    for key in keys:
        pool.extend(_displayable(categories, key))

    by_dir: dict[Path, list[FigureRef]] = defaultdict(list)
    for ref in pool:
        by_dir[ref.parent_relative].append(ref)

    dirs = sorted(by_dir.keys(), key=lambda p: natural_key(str(p)))
    out: list[FigureRef] = []
    for directory in dirs:
        refs_in_dir = by_dir[directory]
        if group_mode == GroupMode.FILENAME:
            by_key = {r.filename: r for r in refs_in_dir}
        else:
            by_key = {r.stem: r for r in refs_in_dir}
        for key in keys:
            ref = by_key.get(key)
            if ref is not None:
                out.append(ref)
    return out


def index_of_ref(playlist: list[FigureRef], ref: FigureRef) -> int | None:
    try:
        return playlist.index(ref)
    except ValueError:
        return None


def preserve_position(
    old_playlist: list[FigureRef],
    old_index: int,
    new_playlist: list[FigureRef],
) -> int:
    if not new_playlist:
        return 0
    if not old_playlist or old_index < 0 or old_index >= len(old_playlist):
        return 0
    current = old_playlist[old_index]
    new_index = index_of_ref(new_playlist, current)
    return new_index if new_index is not None else 0


def category_position(ref: FigureRef, playlist: list[FigureRef], *, group_mode: GroupMode) -> tuple[int, int]:
    key = ref.category_key(group_mode)
    same = [r for r in playlist if r.category_key(group_mode) == key]
    if not same:
        same = [r for r in playlist if r.absolute_path == ref.absolute_path]
    try:
        pos = same.index(ref) + 1
    except ValueError:
        pos = 1
    return pos, len(same)


def filter_by_path_prefix(playlist: list[FigureRef], prefix: Path | None) -> list[FigureRef]:
    """Keep figures whose relative path lies under prefix (directory segments only)."""
    if prefix is None or not prefix.parts:
        return list(playlist)
    prefix_parts = prefix.parts
    return [ref for ref in playlist if _path_has_prefix(ref.relative_path, prefix_parts)]


def _path_has_prefix(relative_path: Path, prefix_parts: tuple[str, ...]) -> bool:
    rel_parts = relative_path.parts
    if len(rel_parts) < len(prefix_parts):
        return False
    return rel_parts[: len(prefix_parts)] == prefix_parts

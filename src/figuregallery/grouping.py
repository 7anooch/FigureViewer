from __future__ import annotations

from figuregallery.models import Category, FigureRef, GroupMode, ScanIndex


def group_refs(refs: list[FigureRef], mode: GroupMode) -> dict[str, Category]:
    categories: dict[str, Category] = {}
    for ref in refs:
        key = ref.category_key(mode)
        if key not in categories:
            categories[key] = Category(key=key)
        categories[key].refs.append(ref)
    return categories


def group_index(index: ScanIndex, mode: GroupMode) -> dict[str, Category]:
    return group_refs(index.refs, mode)


def remap_selection(
    selected: set[str],
    old_mode: GroupMode,
    new_mode: GroupMode,
    index: ScanIndex,
) -> set[str]:
    if old_mode == new_mode:
        return set(selected)

    if old_mode == GroupMode.STEM and new_mode == GroupMode.FILENAME:
        out: set[str] = set()
        for ref in index.refs:
            if ref.stem in selected:
                out.add(ref.filename)
        return out

    out = set()
    for ref in index.refs:
        if ref.filename in selected:
            out.add(ref.stem)
    return out

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from figurecommon.sort import natural_key

from figuregallery.models import FigureRef
from figuregallery.playlist import _path_has_prefix


class FilterNodeKind(Enum):
    EXPANDED = "expanded"
    FAN_VARIANT = "fan_variant"
    SHARED = "shared"


@dataclass
class DirNode:
    name: str
    prefix: Path
    figure_count: int = 0
    children: dict[str, DirNode] = field(default_factory=dict)


@dataclass
class FilterNode:
    name: str
    kind: FilterNodeKind
    figure_count: int
    exclusion_prefixes: frozenset[Path]
    children: list[FilterNode] = field(default_factory=list)
    fan_variants: list[FilterNode] = field(default_factory=list)


def build_directory_tree(refs: list[FigureRef]) -> DirNode:
    root = DirNode(name="", prefix=Path())
    for ref in refs:
        parts = ref.relative_path.parts[:-1]
        node = root
        for index, part in enumerate(parts):
            prefix = Path(*parts[: index + 1])
            if part not in node.children:
                node.children[part] = DirNode(name=part, prefix=prefix)
            node = node.children[part]
            node.figure_count += 1
    return root


def build_filter_display_tree(refs: list[FigureRef]) -> list[FilterNode]:
    all_paths = _all_directory_prefixes(refs)
    if not all_paths:
        return []
    return _fold_variants([()], all_paths, refs)


def _all_directory_prefixes(refs: list[FigureRef]) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    for ref in refs:
        parts = ref.relative_path.parts[:-1]
        for depth in range(len(parts)):
            paths.add(tuple(parts[: depth + 1]))
    return paths


def _structure_key(paths: set[tuple[str, ...]]) -> tuple:
    if not paths:
        return ("leaf",)
    by_first: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    has_leaf = False
    for path in paths:
        if not path:
            has_leaf = True
            continue
        first, *rest = path
        by_first[first].add(tuple(rest))
    if not by_first:
        return ("leaf",) if has_leaf else ("empty",)
    if len(by_first) == 1:
        only = next(iter(by_first.values()))
        return ("chain", _structure_key(only))
    child_keys = tuple(_structure_key(remains) for remains in by_first.values())
    if len(set(child_keys)) == 1:
        return ("fan", tuple(sorted(by_first.keys(), key=natural_key)), child_keys[0])
    return (
        "split",
        tuple(
            (name, _structure_key(remains))
            for name, remains in sorted(by_first.items(), key=lambda item: natural_key(item[0]))
        ),
    )


def _segments_below(
    variant_roots: list[tuple[str, ...]],
    all_paths: set[tuple[str, ...]],
) -> set[str]:
    segments: set[str] = set()
    for root in variant_roots:
        depth = len(root)
        for path in all_paths:
            if len(path) > depth and path[:depth] == root:
                segments.add(path[depth])
    return segments


def _below_signature(
    segment: str,
    variant_roots: list[tuple[str, ...]],
    all_paths: set[tuple[str, ...]],
) -> tuple:
    below: set[tuple[str, ...]] = set()
    for root in variant_roots:
        depth = len(root)
        for path in all_paths:
            if len(path) < depth + 1 or path[:depth] != root or path[depth] != segment:
                continue
            below.add(path[depth + 1 :])
    return _structure_key(below)


def _fold_variants(
    variant_roots: list[tuple[str, ...]],
    all_paths: set[tuple[str, ...]],
    refs: list[FigureRef],
) -> list[FilterNode]:
    segments = _segments_below(variant_roots, all_paths)
    if not segments:
        return []

    sig_groups: dict[tuple, list[str]] = defaultdict(list)
    for segment in segments:
        sig_groups[_below_signature(segment, variant_roots, all_paths)].append(segment)

    nodes: list[FilterNode] = []
    for sig in sorted(sig_groups.keys(), key=str):
        grouped = sorted(sig_groups[sig], key=natural_key)
        if len(grouped) >= 2:
            nodes.append(_make_fan_group(variant_roots, grouped, all_paths, refs))
            continue
        for segment in grouped:
            nodes.append(_make_single_segment_node(segment, variant_roots, all_paths, refs))
    return nodes


def _make_fan_group(
    variant_roots: list[tuple[str, ...]],
    segments: list[str],
    all_paths: set[tuple[str, ...]],
    refs: list[FigureRef],
) -> FilterNode:
    variants = [
        FilterNode(
            name=segment,
            kind=FilterNodeKind.FAN_VARIANT,
            figure_count=sum(
                _count_under(refs, Path(*(root + (segment,)))) for root in variant_roots
            ),
            exclusion_prefixes=frozenset(
                Path(*(root + (segment,))) for root in variant_roots
            ),
            children=[],
        )
        for segment in segments
    ]
    combined_roots = [root + (segment,) for root in variant_roots for segment in segments]
    return FilterNode(
        name="",
        kind=FilterNodeKind.EXPANDED,
        figure_count=sum(v.figure_count for v in variants),
        exclusion_prefixes=frozenset(),
        fan_variants=variants,
        children=_fold_variants(combined_roots, all_paths, refs),
    )


def _make_single_segment_node(
    segment: str,
    variant_roots: list[tuple[str, ...]],
    all_paths: set[tuple[str, ...]],
    refs: list[FigureRef],
) -> FilterNode:
    new_roots = [root + (segment,) for root in variant_roots]
    prefix_paths = frozenset(Path(*root) for root in new_roots)
    kind = FilterNodeKind.SHARED if len(variant_roots) >= 2 else FilterNodeKind.EXPANDED
    return FilterNode(
        name=segment,
        kind=kind,
        figure_count=sum(_count_under(refs, prefix) for prefix in prefix_paths),
        exclusion_prefixes=prefix_paths,
        children=_fold_variants(new_roots, all_paths, refs),
    )


def _count_under(refs: list[FigureRef], prefix: Path) -> int:
    return sum(1 for ref in refs if _path_has_prefix(ref.relative_path, prefix.parts))


def collect_directory_filter(
    nodes: list[FilterNode], checked: dict[int, bool]
) -> tuple[set[Path], set[Path]]:
    """Return ``(excluded, included)`` from checkbox state.

    Unchecking a directory excludes it and its descendants. Checking a
    descendant under an excluded ancestor re-includes that subtree (and its
    children), which can itself be re-excluded deeper down.
    """
    excluded: set[Path] = set()
    included: set[Path] = set()

    def walk(node_list: list[FilterNode], parent_included: bool) -> None:
        for node in node_list:
            if node.fan_variants:
                if parent_included:
                    any_active = False
                    for variant in node.fan_variants:
                        # Default follow parent: missing means included here.
                        if checked.get(id(variant), True):
                            any_active = True
                        else:
                            excluded.update(variant.exclusion_prefixes)
                    walk(node.children, any_active)
                else:
                    any_active = False
                    for variant in node.fan_variants:
                        # Under an exclusion, missing means still excluded.
                        if checked.get(id(variant), False):
                            any_active = True
                            included.update(variant.exclusion_prefixes)
                    walk(node.children, any_active)
                continue

            # Missing checkbox follows parent (include under include, exclude under exclude).
            node_checked = checked.get(id(node), parent_included)
            if parent_included:
                if node_checked:
                    walk(node.children, True)
                else:
                    excluded.update(node.exclusion_prefixes)
                    walk(node.children, False)
            elif node_checked:
                included.update(node.exclusion_prefixes)
                walk(node.children, True)
            else:
                walk(node.children, False)

    walk(nodes, True)
    return _prune_filter_rules(excluded, included)


def collect_exclusions(nodes: list[FilterNode], checked: dict[int, bool]) -> set[Path]:
    excluded, _included = collect_directory_filter(nodes, checked)
    return excluded


def _prune_redundant_exclusions(excluded: set[Path]) -> set[Path]:
    """Drop child exclusions whose parent is also excluded (no include exceptions)."""
    return _prune_redundant_paths(excluded, opposing=set())


def _prune_redundant_paths(paths: set[Path], *, opposing: set[Path]) -> set[Path]:
    """Drop a path when an ancestor is in ``paths`` and no ``opposing`` path intervenes."""
    pruned = set(paths)
    for path in sorted(paths, key=lambda item: len(item.parts)):
        parts = path.parts
        for depth in range(1, len(parts)):
            ancestor = Path(*parts[:depth])
            if ancestor not in pruned:
                continue
            if _has_intervening_path(ancestor, path, opposing):
                continue
            pruned.discard(path)
            break
    return pruned


def _has_intervening_path(ancestor: Path, descendant: Path, others: set[Path]) -> bool:
    for other in others:
        if other == ancestor or other == descendant:
            continue
        if _path_has_prefix(other, ancestor.parts) and _path_has_prefix(descendant, other.parts):
            return True
    return False


def _prune_filter_rules(
    excluded: set[Path], included: set[Path]
) -> tuple[set[Path], set[Path]]:
    # Inclusions only matter under an exclusion.
    included = {
        path
        for path in included
        if any(path != exc and _path_has_prefix(path, exc.parts) for exc in excluded)
    }
    excluded = _prune_redundant_paths(excluded, opposing=included)
    included = {
        path
        for path in included
        if any(path != exc and _path_has_prefix(path, exc.parts) for exc in excluded)
    }
    included = _prune_redundant_paths(included, opposing=excluded)
    return excluded, included


def initial_checked_state(
    nodes: list[FilterNode],
    excluded: set[Path],
    included: set[Path] | None = None,
) -> dict[int, bool]:
    included = set() if included is None else set(included)
    checked: dict[int, bool] = {}

    def walk(node_list: list[FilterNode]) -> None:
        for node in node_list:
            for variant in node.fan_variants:
                checked[id(variant)] = _prefixes_included(
                    variant.exclusion_prefixes, excluded, included
                )
            if node.exclusion_prefixes:
                checked[id(node)] = _prefixes_included(
                    node.exclusion_prefixes, excluded, included
                )
            walk(node.children)

    walk(nodes)
    return checked


def _prefixes_included(
    prefixes: frozenset[Path],
    excluded: set[Path],
    included: set[Path],
) -> bool:
    return all(_path_effectively_included(prefix, excluded, included) for prefix in prefixes)


def _path_effectively_included(
    path: Path,
    excluded: set[Path],
    included: set[Path],
) -> bool:
    """Whether directory ``path`` itself is included (checkbox checked)."""
    best_depth = -1
    is_included = True
    for exc in excluded:
        if path == exc or _path_has_prefix(path, exc.parts):
            depth = len(exc.parts)
            if depth > best_depth:
                best_depth = depth
                is_included = False
    for inc in included:
        if path == inc or _path_has_prefix(path, inc.parts):
            depth = len(inc.parts)
            if depth > best_depth:
                best_depth = depth
                is_included = True
    return is_included


def filter_by_directory_exclusions(
    playlist: list[FigureRef],
    excluded: set[Path],
    included: set[Path] | None = None,
) -> list[FigureRef]:
    if not excluded:
        return list(playlist)
    included_set = set() if included is None else set(included)
    return [
        ref
        for ref in playlist
        if not is_under_excluded_directory(ref, excluded, included_set)
    ]


def is_under_excluded_directory(
    ref: FigureRef,
    excluded: set[Path],
    included: set[Path] | None = None,
) -> bool:
    """True when the figure should be hidden by directory filter rules.

    Most-specific matching path wins: an inclusion under an exclusion re-shows
    that subtree; a deeper exclusion can hide part of a re-included tree.
    """
    if not excluded:
        return False
    included_set = set() if included is None else set(included)
    rel = ref.relative_path
    best_depth = -1
    hide = False
    for prefix in excluded:
        if _path_has_prefix(rel, prefix.parts):
            depth = len(prefix.parts)
            if depth > best_depth:
                best_depth = depth
                hide = True
    for prefix in included_set:
        if _path_has_prefix(rel, prefix.parts):
            depth = len(prefix.parts)
            if depth > best_depth:
                best_depth = depth
                hide = False
    return hide


def directory_prefixes_in_refs(refs: list[FigureRef]) -> set[Path]:
    """Relative directory prefixes present in ``refs`` (parents of figure files)."""
    return {Path(*parts) for parts in _all_directory_prefixes(refs)}


def prune_directory_exclusions(
    excluded: set[Path],
    refs: list[FigureRef],
) -> set[Path]:
    """Drop exclusions that no longer exist in the current figure set."""
    excluded, _included = prune_directory_filter(excluded, set(), refs)
    return excluded


def prune_directory_filter(
    excluded: set[Path],
    included: set[Path],
    refs: list[FigureRef],
) -> tuple[set[Path], set[Path]]:
    """Drop filter paths that no longer exist in the current figure set."""
    if not excluded and not included:
        return set(), set()
    valid = directory_prefixes_in_refs(refs)
    if not valid:
        return set(), set()
    pruned_excluded = {path for path in excluded if path in valid}
    pruned_included = {path for path in included if path in valid}
    return _prune_filter_rules(pruned_excluded, pruned_included)


def maximal_exclusions(checked: dict[Path, bool]) -> set[Path]:
    excluded: set[Path] = set()
    paths = sorted((path for path in checked if path.parts), key=lambda path: len(path.parts))
    for path in paths:
        if checked.get(path, True):
            continue
        parent = Path(*path.parts[:-1]) if len(path.parts) > 1 else Path()
        if checked.get(parent, True):
            excluded.add(path)
    return excluded


def iter_dir_nodes(node: DirNode) -> list[DirNode]:
    out = [node]
    for child in sorted(node.children.values(), key=lambda n: natural_key(n.name)):
        out.extend(iter_dir_nodes(child))
    return out

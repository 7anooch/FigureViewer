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


def collect_exclusions(nodes: list[FilterNode], checked: dict[int, bool]) -> set[Path]:
    excluded: set[Path] = set()

    def walk(node_list: list[FilterNode], parent_active: bool) -> None:
        for node in node_list:
            if node.fan_variants:
                any_active = False
                for variant in node.fan_variants:
                    if parent_active and checked.get(id(variant), True):
                        any_active = True
                    elif parent_active:
                        excluded.update(variant.exclusion_prefixes)
                walk(node.children, any_active)
                continue

            active = parent_active and checked.get(id(node), True)
            if parent_active and not checked.get(id(node), True):
                excluded.update(node.exclusion_prefixes)
            walk(node.children, active)

    walk(nodes, True)
    return _prune_redundant_exclusions(excluded)


def _prune_redundant_exclusions(excluded: set[Path]) -> set[Path]:
    pruned = set(excluded)
    for path in sorted(excluded, key=lambda item: len(item.parts)):
        parts = path.parts
        for depth in range(1, len(parts)):
            if Path(*parts[:depth]) in pruned:
                pruned.discard(path)
                break
    return pruned


def initial_checked_state(nodes: list[FilterNode], excluded: set[Path]) -> dict[int, bool]:
    checked: dict[int, bool] = {}

    def walk(node_list: list[FilterNode]) -> None:
        for node in node_list:
            for variant in node.fan_variants:
                checked[id(variant)] = _prefixes_included(variant.exclusion_prefixes, excluded)
            if node.exclusion_prefixes:
                checked[id(node)] = _prefixes_included(node.exclusion_prefixes, excluded)
            walk(node.children)

    walk(nodes)
    return checked


def _prefixes_included(prefixes: frozenset[Path], excluded: set[Path]) -> bool:
    for prefix in prefixes:
        if prefix in excluded:
            return False
        for exc in excluded:
            if _path_has_prefix(prefix, exc.parts):
                return False
    return True


def filter_by_directory_exclusions(
    playlist: list[FigureRef],
    excluded: set[Path],
) -> list[FigureRef]:
    if not excluded:
        return list(playlist)
    return [ref for ref in playlist if not is_under_excluded_directory(ref, excluded)]


def is_under_excluded_directory(ref: FigureRef, excluded: set[Path]) -> bool:
    rel = ref.relative_path
    for prefix in excluded:
        if _path_has_prefix(rel, prefix.parts):
            return True
    return False


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

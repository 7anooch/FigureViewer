from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

FIGURE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".pdf"}


@dataclass
class PanelConfig:
    label: str
    directory: Path
    enabled: bool = True


def natural_key(s: str):
    """Sort file names in human order: fig2 before fig10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def list_figures(directory: Path, recursive: bool = False) -> List[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    files = [p for p in iterator if p.is_file() and p.suffix.lower() in FIGURE_EXTS]
    return sorted(files, key=lambda p: natural_key(str(p.relative_to(directory))))


def common_stems(figure_lists: List[List[Path]]) -> List[str]:
    sets = [{p.stem for p in figs} for figs in figure_lists if figs]
    if not sets:
        return []
    common = set.intersection(*sets)
    return sorted(common, key=natural_key)


def stem_lookup(figures: List[Path]) -> Dict[str, Path]:
    """Map stem to first matching figure. If duplicates exist, keep first natural-sorted one."""
    out: Dict[str, Path] = {}
    for p in figures:
        out.setdefault(p.stem, p)
    return out


def panel_display_labels(directories: List[Path]) -> List[str]:
    """Shortest distinguishing path suffix per directory; climbs parents when leaf names collide."""
    if not directories:
        return []
    resolved = [d.expanduser().resolve() for d in directories]
    if len(resolved) == 1:
        return [resolved[0].name or str(resolved[0])]

    max_parts = max(len(p.parts) for p in resolved)
    labels: List[str] = []
    for depth in range(1, max_parts + 1):
        labels = []
        for path in resolved:
            parts = path.parts
            if depth >= len(parts):
                labels.append(str(path))
            else:
                labels.append("/".join(parts[-depth:]))
        if len(set(labels)) == len(labels):
            break
    else:
        labels = [str(p) for p in resolved]

    split_labels = [label.split("/") for label in labels]
    while split_labels and all(len(parts) > 1 for parts in split_labels):
        trailing = [parts[-1] for parts in split_labels]
        if len(set(trailing)) != 1:
            break
        split_labels = [parts[:-1] for parts in split_labels]

    return ["/".join(parts) for parts in split_labels]


def parse_panels(panel_text: str) -> List[PanelConfig]:
    panels: List[PanelConfig] = []
    for i, line in enumerate(panel_text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            label, path = line.split("=", 1)
            label = label.strip() or f"Panel {i}"
            path = path.strip()
        else:
            p = Path(os.path.expanduser(line))
            label = p.name or f"Panel {i}"
            path = line
        panels.append(PanelConfig(label=label, directory=Path(os.path.expanduser(path))))
    return panels

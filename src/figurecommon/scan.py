from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from figurecommon.exts import is_figure_path

DEFAULT_SKIP_DIR_NAMES = frozenset({
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".eggs",
})


@dataclass(frozen=True)
class ScanOptions:
    follow_gitignore: bool = True
    include_pdf: bool = True


def _load_gitignore_patterns(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return []
    patterns: list[str] = []
    for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line.rstrip("/"))
    return patterns


def _gitignore_skip(relative_posix: str, patterns: list[str]) -> bool:
    name = relative_posix.split("/")[-1]
    for pattern in patterns:
        if pattern.endswith("/"):
            if fnmatch.fnmatch(relative_posix, pattern[:-1] + "*"):
                return True
            continue
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relative_posix, pattern):
            return True
    return False


def should_skip_dir(path: Path, options: ScanOptions) -> bool:
    if path.name.startswith("."):
        return True
    if path.name in DEFAULT_SKIP_DIR_NAMES:
        return True
    return False


def walk_figures(root: Path, options: ScanOptions | None = None) -> Iterator[Path]:
    """Yield absolute paths to figure files under root."""
    options = options or ScanOptions()
    root = root.expanduser().resolve()
    if not root.is_dir():
        return

    gitignore_patterns = _load_gitignore_patterns(root) if options.follow_gitignore else []

    def walk(current: Path) -> Iterator[Path]:
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue
            rel = entry.relative_to(root).as_posix()
            if gitignore_patterns and _gitignore_skip(rel, gitignore_patterns):
                continue

            if entry.is_dir():
                if should_skip_dir(entry, options):
                    continue
                yield from walk(entry)
            elif entry.is_file() and is_figure_path(entry, include_pdf=options.include_pdf):
                yield entry.resolve()

    yield from walk(root)

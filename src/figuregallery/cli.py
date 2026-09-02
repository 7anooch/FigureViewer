from __future__ import annotations

import argparse
import sys
from pathlib import Path

from figuregallery.models import GroupMode, SortMode
from figuregallery.ui.app import run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="figuregallery",
        description="Browse figures across a directory tree grouped by filename.",
    )
    parser.add_argument("root", nargs="?", type=Path, help="Root directory to scan")
    parser.add_argument(
        "--group-by",
        choices=["stem", "filename"],
        default="stem",
        help="Group categories by stem (default) or full filename",
    )
    parser.add_argument(
        "--sort",
        choices=["category-then-path", "path-then-category"],
        default="category-then-path",
        help="Playlist sort order",
    )
    return parser.parse_args(argv)


def _group_mode(value: str) -> GroupMode:
    return GroupMode.FILENAME if value == "filename" else GroupMode.STEM


def _sort_mode(value: str) -> SortMode:
    if value == "path-then-category":
        return SortMode.PATH_THEN_CATEGORY
    return SortMode.CATEGORY_THEN_PATH


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    initial_root: Path | None = None
    if args.root is not None:
        resolved = args.root.expanduser().resolve()
        if not resolved.is_dir():
            print(f"error: not a directory: {resolved}", file=sys.stderr)
            raise SystemExit(1)
        initial_root = resolved

    raise SystemExit(
        run(
            initial_root=initial_root,
            group_mode=_group_mode(args.group_by),
            sort_mode=_sort_mode(args.sort),
        )
    )


if __name__ == "__main__":
    main()

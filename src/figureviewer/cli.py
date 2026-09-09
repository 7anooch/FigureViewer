from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from figureviewer.desktop.modes import AppMode


def parse_launch_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="figureviewer",
        description=(
            "Compare corresponding figures across multiple directories, or browse "
            "a directory tree in Gallery mode. Default launch is Streamlit; "
            "use --desktop for the native PyQt6 app."
        ),
    )
    parser.add_argument(
        "-d",
        "--desktop",
        action="store_true",
        help="Launch the native PyQt6 desktop app instead of Streamlit.",
    )
    parser.add_argument(
        "--mode",
        choices=["compare", "browse"],
        default=None,
        help=(
            "Desktop mode: multi-panel Compare or Gallery Browse "
            "(default: last used, else compare). Implies --desktop."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Browse-mode scan root (also accepted as a trailing path with --desktop).",
    )
    args, rest = parser.parse_known_args(argv)
    if args.mode is not None:
        args.desktop = True
    # Allow: figureviewer --mode browse /path/to/tree
    if args.desktop and args.root is None and rest and not str(rest[0]).startswith("-"):
        args.root = Path(rest[0])
        rest = rest[1:]
    args.streamlit_args = rest
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_launch_args(argv)
    if args.desktop:
        from figureviewer.desktop.app import run

        initial_root: Path | None = None
        if args.root is not None:
            resolved = args.root.expanduser().resolve()
            if not resolved.is_dir():
                print(f"error: not a directory: {resolved}", file=sys.stderr)
                raise SystemExit(1)
            initial_root = resolved

        mode = AppMode.parse(args.mode) if args.mode else None
        raise SystemExit(run(mode=mode, initial_root=initial_root))

    app_path = Path(__file__).resolve().parent / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), *args.streamlit_args]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_launch_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="figureviewer",
        description=(
            "Compare corresponding figures across multiple directories. "
            "Default launch is Streamlit; use --desktop for the native PyQt6 app."
        ),
    )
    parser.add_argument(
        "-d",
        "--desktop",
        action="store_true",
        help="Launch the native PyQt6 desktop app instead of Streamlit.",
    )
    args, rest = parser.parse_known_args(argv)
    args.streamlit_args = rest
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_launch_args(argv)
    if args.desktop:
        from figureviewer.desktop.app import run

        raise SystemExit(run())

    app_path = Path(__file__).resolve().parent / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), *args.streamlit_args]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

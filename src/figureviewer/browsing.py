from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import streamlit as st

from figureviewer.figures import PanelConfig, natural_key, panel_display_labels
from figureviewer.settings import load_default_browse_root


def resolve_path(path_str: str) -> Path:
    return Path(os.path.expanduser(path_str.strip())).resolve()


def path_widget_key(prefix: str, path: Path) -> str:
    digest = hashlib.md5(str(path.resolve()).encode(), usedforsecurity=False).hexdigest()[:12]
    return f"{prefix}_{digest}"


def column_widget_key(prefix: str, column_index: int, path: Path) -> str:
    digest = hashlib.md5(str(path.resolve()).encode(), usedforsecurity=False).hexdigest()[:10]
    return f"{prefix}_c{column_index}_{digest}"


def list_child_dirs(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    children = [p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")]
    return sorted(children, key=lambda p: natural_key(p.name))


def pick_directory_dialog(initial: Optional[str] = None) -> Optional[str]:
    """Open a native folder picker in a subprocess (safe with Streamlit threads)."""
    initial_path = initial if initial and Path(initial).exists() else str(Path.home())

    if sys.platform == "darwin":
        # AppleScript runs outside Python; avoids tkinter main-thread crash on macOS.
        script = 'POSIX path of (choose folder with prompt "Select folder")'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None  # cancelled or failed
        chosen = result.stdout.strip()
        return str(Path(chosen).resolve()) if chosen else None

    if sys.platform.startswith("linux"):
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=Select folder"],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        chosen = result.stdout.strip()
        return str(Path(chosen).resolve()) if chosen else None

    if os.name == "nt":
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$dialog.SelectedPath = '{initial_path.replace(chr(39), chr(39) + chr(39))}'; "
            "if ($dialog.ShowDialog() -eq 'OK') { Write-Output $dialog.SelectedPath }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        chosen = result.stdout.strip()
        return str(Path(chosen).resolve()) if chosen else None

    return None


def folder_dialog_available() -> bool:
    if sys.platform == "darwin":
        return True
    if sys.platform.startswith("linux"):
        from shutil import which
        return which("zenity") is not None
    if os.name == "nt":
        return True
    return False


def folder_dialog_hint() -> str:
    if sys.platform == "darwin":
        return "Opens the macOS folder picker."
    if sys.platform.startswith("linux"):
        return "Requires `zenity` (install if Browse is disabled)."
    if os.name == "nt":
        return "Opens the Windows folder picker."
    return "Not available on this platform; type a path instead."


def get_panel_configs() -> List[PanelConfig]:
    raw = st.session_state.get("panel_directories", [])
    paths: List[str] = [str(p) for p in raw] if isinstance(raw, list) else []
    directories = [Path(p) for p in paths]
    labels = panel_display_labels(directories)
    panels: List[PanelConfig] = []
    for i, (directory, label) in enumerate(zip(directories, labels), start=1):
        panels.append(PanelConfig(label=label or f"Panel {i}", directory=directory))
    return panels


def add_panel_directory(path: Path) -> None:
    resolved = str(path.resolve())
    dirs: List[str] = list(st.session_state.get("panel_directories", []))
    if resolved not in dirs:
        dirs.append(resolved)
        st.session_state.panel_directories = dirs


def remove_panel_directory(path: Path) -> None:
    resolved = str(path.resolve())
    dirs: List[str] = list(st.session_state.get("panel_directories", []))
    st.session_state.panel_directories = [d for d in dirs if d != resolved]


def clear_panel_directories() -> None:
    st.session_state.panel_directories = []


def get_tree_stack() -> List[str]:
    stack = st.session_state.get("tree_stack")
    if isinstance(stack, list) and stack:
        return [str(p) for p in stack]
    root = st.session_state.get("browse_root", str(Path.home()))
    return [root]


def current_tree_path() -> Path:
    return Path(get_tree_stack()[-1])


def reset_tree_to_root(root: Path) -> None:
    resolved = str(root.resolve())
    st.session_state.browse_root = resolved
    st.session_state.tree_stack = [resolved]


def navigate_tree(column_index: int, path: Path) -> None:
    """Finder-style: truncate stack at column and descend into path."""
    stack = get_tree_stack()
    resolved = str(path.resolve())
    new_stack = stack[: column_index + 1]
    if column_index + 1 < len(new_stack):
        new_stack[column_index + 1] = resolved
    else:
        new_stack.append(resolved)
    st.session_state.tree_stack = new_stack


def tree_column_levels(tree_stack: List[str]) -> List[tuple[Path, Optional[Path], List[Path]]]:
    """For each column: parent folder, highlighted child, children to list."""
    levels: List[tuple[Path, Optional[Path], List[Path]]] = []
    for i, parent_str in enumerate(tree_stack):
        parent = Path(parent_str)
        selected = Path(tree_stack[i + 1]) if i + 1 < len(tree_stack) else None
        levels.append((parent, selected, list_child_dirs(parent)))
    return levels


def format_breadcrumb(tree_stack: List[str]) -> str:
    labels = [Path(p).name or str(Path(p)) for p in tree_stack]
    return " › ".join(labels)


def apply_pending_browse_pick() -> None:
    picked = st.session_state.pop("_pending_browse_pick", None)
    if not picked:
        return
    st.session_state.browse_root_input = picked
    reset_tree_to_root(Path(picked))


def init_browse_state() -> None:
    home = str(Path.home())
    default_root = load_default_browse_root()
    initial_root = default_root or home
    if "panel_directories" not in st.session_state:
        st.session_state.panel_directories = []
    if "browse_root" not in st.session_state:
        st.session_state.browse_root = initial_root
    if "browse_root_input" not in st.session_state:
        st.session_state.browse_root_input = st.session_state.browse_root
    if "tree_stack" not in st.session_state:
        st.session_state.tree_stack = [st.session_state.browse_root]
    # Migrate legacy state from older builds.
    if "browse_cwd" in st.session_state:
        cwd = st.session_state.pop("browse_cwd")
        if cwd:
            st.session_state.tree_stack = [str(Path(cwd).resolve())]

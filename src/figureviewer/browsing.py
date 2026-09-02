from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import List, Optional

import streamlit as st

from figurecommon.paths import resolve_path
from figurecommon.sort import natural_key
from figureviewer.figures import PanelConfig, panel_display_labels
from figureviewer.settings import load_default_browse_root

__all__ = [
    "apply_pending_browse_pick",
    "clear_panel_directories",
    "column_widget_key",
    "current_tree_path",
    "folder_dialog_available",
    "folder_dialog_hint",
    "format_breadcrumb",
    "get_panel_configs",
    "get_tree_stack",
    "init_browse_state",
    "list_child_dirs",
    "navigate_tree",
    "path_widget_key",
    "pick_directory_dialog",
    "reset_tree_to_root",
    "resolve_path",
    "tree_column_levels",
]

from figurecommon.paths import (  # noqa: E402  re-export for callers
    folder_dialog_available,
    folder_dialog_hint,
    pick_directory_dialog,
)


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
    if "browse_cwd" in st.session_state:
        cwd = st.session_state.pop("browse_cwd")
        if cwd:
            st.session_state.tree_stack = [str(Path(cwd).resolve())]

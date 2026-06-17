from __future__ import annotations

from pathlib import Path

import streamlit as st

from figureviewer.browsing import (
    add_panel_directory,
    apply_pending_browse_pick,
    clear_panel_directories,
    column_widget_key,
    current_tree_path,
    folder_dialog_available,
    folder_dialog_hint,
    format_breadcrumb,
    get_panel_configs,
    get_tree_stack,
    init_browse_state,
    navigate_tree,
    path_widget_key,
    pick_directory_dialog,
    remove_panel_directory,
    reset_tree_to_root,
    resolve_path,
    tree_column_levels,
)
from figureviewer.settings import (
    clear_default_browse_root,
    load_default_browse_root,
    save_default_browse_root,
)

_COLUMN_BROWSER_CSS = """
<style>
.column-browser-panel [data-testid="stHorizontalBlock"] {
  overflow-x: auto;
  flex-wrap: nowrap !important;
  align-items: stretch;
  gap: 0;
  margin: 0.15rem 0 0.35rem 0;
  border-top: 1px solid rgba(128, 128, 128, 0.28);
  border-bottom: 1px solid rgba(128, 128, 128, 0.28);
}
.column-browser-panel [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  min-width: 9.5rem;
  max-width: 9.5rem;
  flex: 0 0 9.5rem;
  border-right: 1px solid rgba(128, 128, 128, 0.22);
  padding: 0.2rem 0.15rem 0.25rem 0.15rem;
}
.column-browser-panel [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
  border-right: none;
}
.column-browser-panel [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {
  max-height: 10.5rem;
  overflow-y: auto;
  gap: 0.05rem !important;
}
.column-browser-col-title {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  opacity: 0.55;
  margin: 0 0 0.15rem 0;
  padding: 0 0.15rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.column-browser-panel .stButton > button {
  padding: 0.1rem 0.35rem !important;
  min-height: 1.45rem !important;
  font-size: 0.8rem !important;
  line-height: 1.2 !important;
  border-radius: 0.2rem !important;
}
.column-browser-panel .stButton > button p {
  font-size: 0.8rem !important;
}
.column-browser-panel [data-testid="column"] .stButton > button {
  border: none !important;
  box-shadow: none !important;
}
.column-browser-panel button[kind="primary"] {
  background-color: rgba(28, 131, 225, 0.12) !important;
  color: inherit !important;
  border: 1px solid rgba(28, 131, 225, 0.3) !important;
}
.column-browser-toolbar {
  margin-bottom: 0.15rem;
}
.column-browser-toolbar [data-testid="stHorizontalBlock"] {
  gap: 0.35rem;
  align-items: center;
}
.column-browser-footer {
  font-size: 0.8rem;
  opacity: 0.85;
  margin-top: 0.15rem;
}
</style>
"""


def _toggle_default_browse_root() -> None:
    if st.session_state.use_default_browse_root:
        save_default_browse_root(st.session_state.browse_root_input)
    else:
        clear_default_browse_root()


def _init_default_browse_root_checkbox() -> None:
    if "use_default_browse_root" in st.session_state:
        return
    saved = load_default_browse_root()
    if not saved:
        st.session_state.use_default_browse_root = False
        return
    try:
        current = resolve_path(st.session_state.browse_root_input)
        st.session_state.use_default_browse_root = str(current) == saved
    except Exception:
        st.session_state.use_default_browse_root = False


def _apply_manual_paths() -> None:
    text = st.session_state.get("panel_text_manual", "")
    panels = parse_panels(text)
    st.session_state.panel_directories = [str(p.directory.resolve()) for p in panels]


def _inject_column_browser_css() -> None:
    if st.session_state.get("_column_browser_css"):
        return
    st.session_state._column_browser_css = True
    st.markdown(_COLUMN_BROWSER_CSS, unsafe_allow_html=True)


def _folder_button_type(is_selected: bool) -> str:
    return "primary" if is_selected else "tertiary"


def _render_tree_column(
    column_index: int,
    parent: Path,
    selected: Path | None,
    children: list[Path],
    panel_paths: set[str],
) -> None:
    title = parent.name or str(parent)
    st.markdown(f'<div class="column-browser-col-title">{title}</div>', unsafe_allow_html=True)

    if not children:
        st.caption("(empty)")
        return

    for child in children:
        is_selected = selected is not None and child.resolve() == selected.resolve()
        is_panel = str(child.resolve()) in panel_paths
        mark = "✓ " if is_panel else ""
        label = f"{mark}{child.name}"

        pick_col, add_col = st.columns([6, 1], gap="small")
        with pick_col:
            if st.button(
                label,
                key=column_widget_key("tree", column_index, child),
                use_container_width=True,
                type=_folder_button_type(is_selected),
            ):
                navigate_tree(column_index, child)
                st.rerun()
        with add_col:
            if st.button(
                "−" if is_panel else "+",
                key=column_widget_key("panel", column_index, child),
                help="Remove panel" if is_panel else "Add as panel",
                type="tertiary",
            ):
                if is_panel:
                    remove_panel_directory(child)
                else:
                    add_panel_directory(child)
                st.rerun()


def render_column_browser() -> None:
    """Finder-style column directory browser in the main panel (needs horizontal space)."""
    _inject_column_browser_css()
    init_browse_state()
    apply_pending_browse_pick()

    st.markdown('<div class="column-browser-toolbar">', unsafe_allow_html=True)
    head_a, head_b = st.columns([1, 2])
    with head_a:
        st.markdown("**Directories**")
    with head_b:
        try:
            tree_stack = get_tree_stack()
            st.caption(f"`{format_breadcrumb(tree_stack)}`")
        except Exception:
            pass

    root_col, browse_col, default_col, open_col = st.columns([6, 1, 1, 1])
    with root_col:
        st.text_input(
            "Root directory",
            key="browse_root_input",
            label_visibility="collapsed",
            placeholder="Root directory…",
        )
    with browse_col:
        if st.button(
            "Browse…",
            key="browse_root_dialog",
            use_container_width=True,
            disabled=not folder_dialog_available(),
            help=folder_dialog_hint(),
            type="tertiary",
        ):
            picked = pick_directory_dialog(st.session_state.get("browse_root"))
            if picked:
                st.session_state._pending_browse_pick = picked
                if st.session_state.get("use_default_browse_root"):
                    save_default_browse_root(picked)
                st.rerun()
    with default_col:
        _init_default_browse_root_checkbox()
        st.checkbox(
            "Default",
            key="use_default_browse_root",
            on_change=_toggle_default_browse_root,
            help="Remember this root directory when FigureViewer starts.",
        )
    with open_col:
        if st.button("Open", key="open_browse_root", use_container_width=True, type="tertiary"):
            try:
                root_path = resolve_path(st.session_state.browse_root_input)
                if root_path.is_dir():
                    reset_tree_to_root(root_path)
                    if st.session_state.get("use_default_browse_root"):
                        save_default_browse_root(str(root_path))
                else:
                    st.warning("Root path is not a directory.")
            except Exception as exc:
                st.warning(f"Invalid path: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)

    try:
        tree_stack = get_tree_stack()
        root_path = resolve_path(st.session_state.browse_root)
        if str(Path(tree_stack[0]).resolve()) != str(root_path.resolve()):
            reset_tree_to_root(root_path)
            tree_stack = get_tree_stack()
    except Exception:
        reset_tree_to_root(Path.home())
        tree_stack = get_tree_stack()

    panel_paths = {str(Path(p).resolve()) for p in st.session_state.get("panel_directories", [])}
    levels = tree_column_levels(tree_stack)

    st.markdown('<div class="column-browser-panel">', unsafe_allow_html=True)
    if not levels:
        st.caption("Set a root directory and click **Open**.")
    elif len(levels) == 1 and not levels[0][2]:
        st.caption("No subfolders in this directory.")
    else:
        cols = st.columns(len(levels), gap="small")
        for column_index, (parent, selected, children) in enumerate(levels):
            with cols[column_index]:
                _render_tree_column(column_index, parent, selected, children, panel_paths)
    st.markdown("</div>", unsafe_allow_html=True)

    current = current_tree_path()
    current_is_panel = str(current.resolve()) in panel_paths

    foot_col1, foot_col2 = st.columns([1, 2])
    with foot_col1:
        if st.button(
            f"{'−' if current_is_panel else '+'} {current.name}",
            key="add_current_tree_panel",
            help="Toggle current folder as panel",
            type="tertiary",
        ):
            if current_is_panel:
                remove_panel_directory(current)
            else:
                add_panel_directory(current)
            st.rerun()
    with foot_col2:
        panels = get_panel_configs()
        if panels:
            labels = " · ".join(f"`{p.label}`" for p in panels)
            st.markdown(f'<div class="column-browser-footer">Panels: {labels}</div>', unsafe_allow_html=True)

    with st.expander("Enter paths manually", expanded=False):
        st.text_area(
            "One directory per line",
            value="",
            height=80,
            key="panel_text_manual",
        )
        if st.button("Apply manual paths", key="apply_manual_paths", type="tertiary"):
            _apply_manual_paths()
            st.rerun()


def render_selected_panels_sidebar() -> None:
    """Compact selected-panel list for the sidebar."""
    st.markdown("**Selected panels**")
    panels = get_panel_configs()
    if not panels:
        if st.session_state.get("show_directory_browser", True):
            st.caption("Use the directory browser above the figures.")
        else:
            st.caption("Turn on **Show directory browser** to add or change folders.")
        return
    for panel in panels:
        row_col, rm_col = st.columns([5, 1])
        with row_col:
            st.text(panel.label)
        with rm_col:
            if st.button("×", key=path_widget_key("rm", panel.directory), help="Remove panel", type="tertiary"):
                remove_panel_directory(panel.directory)
    if st.button("Clear all panels", key="clear_panels", use_container_width=True, type="tertiary"):
        clear_panel_directories()

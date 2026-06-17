from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import streamlit as st

from figureviewer.browsing import get_panel_configs
from figureviewer.figures import (
    PanelConfig,
    common_stems,
    list_figures,
    stem_lookup,
)
from figureviewer.keynav import listen_keyboard
from figureviewer.metadata import render_metadata_editor
from figureviewer.navigation import (
    clamp_index,
    go_first,
    go_last,
    next_image,
    on_nav_index_change,
    sync_nav_index,
)
from figureviewer.render import render_figure, resolve_display_width


@st.fragment
def render_figure_viewport() -> None:
    recursive = st.session_state.get("recursive", False)
    sync_mode = st.session_state.get("sync_mode", True)
    match_by = st.session_state.get("match_by", "position")
    show_metadata = st.session_state.get("show_metadata", False)
    columns_per_row = st.session_state.get("columns_per_row", 2)
    display_mode = st.session_state.get("display_mode", "Fill panel")
    custom_width = st.session_state.get("custom_width", 700)
    pdf_mode = st.session_state.get("pdf_mode", "Rasterize")
    pdf_dpi = st.session_state.get("pdf_dpi", 200)
    pdf_embed_height = st.session_state.get("pdf_embed_height", 700)
    display_width = resolve_display_width(display_mode, custom_width)

    action = listen_keyboard()
    if action == "prev":
        next_image(-1)
    elif action == "next":
        next_image(1)
    elif action == "first":
        go_first()
    elif action == "last":
        go_last()

    if "nav_index" not in st.session_state:
        st.session_state.nav_index = st.session_state.current_index

    panels = get_panel_configs()
    valid_panels = [p for p in panels if p.directory.exists() and p.directory.is_dir()]
    invalid = [p for p in panels if p not in valid_panels]
    for p in invalid:
        st.warning(f"Not found or not a directory: {p.label} → {p.directory}")

    if not valid_panels:
        st.info("Select one or more directories in the sidebar browser to begin.")
        return

    figure_lists = [list_figures(p.directory, recursive=recursive) for p in valid_panels]
    if not any(figure_lists):
        st.warning("No figures found in the selected directories.")
        return

    if sync_mode and match_by == "filename stem":
        names = common_stems(figure_lists)
        if not names:
            st.error("No common filename stems found across the selected directories.")
            return
        st.session_state.max_index = len(names) - 1
        clamp_index()
        sync_nav_index()
        selected_name = names[st.session_state.current_index]
        current_label = selected_name
    else:
        max_len = max(len(figs) for figs in figure_lists)
        st.session_state.max_index = max_len - 1
        clamp_index()
        sync_nav_index()
        selected_name = None
        current_label = f"{st.session_state.current_index + 1} / {max_len}"

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        st.button(
            "⟵ Previous",
            on_click=next_image,
            args=(-1,),
            key="nav_prev",
            use_container_width=True,
        )
    with nav2:
        st.slider(
            "Index",
            0,
            st.session_state.max_index,
            key="nav_index",
            on_change=on_nav_index_change,
        )
    with nav3:
        st.button(
            "Next ⟶",
            on_click=next_image,
            args=(1,),
            key="nav_next",
            use_container_width=True,
        )
    st.markdown(f"**Current:** `{current_label}`")

    rows: List[List[Tuple[PanelConfig, List[Path]]]] = []
    for i in range(0, len(valid_panels), columns_per_row):
        rows.append(list(zip(valid_panels, figure_lists))[i : i + columns_per_row])

    for row in rows:
        cols = st.columns(len(row))
        for col, (panel, figures) in zip(cols, row):
            with col:
                chosen: Optional[Path] = None
                if sync_mode and match_by == "filename stem" and selected_name is not None:
                    chosen = stem_lookup(figures).get(selected_name)
                elif sync_mode:
                    if st.session_state.current_index < len(figures):
                        chosen = figures[st.session_state.current_index]
                else:
                    local_key = f"local_idx_{panel.label}_{panel.directory}"
                    if local_key not in st.session_state:
                        st.session_state[local_key] = min(
                            st.session_state.current_index,
                            max(len(figures) - 1, 0),
                        )
                    local_idx = st.slider(
                        f"Index for {panel.label}",
                        0,
                        max(len(figures) - 1, 0),
                        key=local_key,
                    )
                    chosen = figures[local_idx] if figures else None

                if chosen is None:
                    st.markdown(f"**{panel.label}**")
                    st.error("No matching figure in this panel.")
                    continue

                rel = chosen.relative_to(panel.directory)
                st.markdown(f"**{panel.label}** · `{rel.name}`")
                with st.expander("Directory path", expanded=False):
                    st.text(str(panel.directory))
                if show_metadata:
                    render_metadata_editor(
                        panel,
                        key_prefix=f"meta_{panel.label}_{panel.directory}",
                    )
                render_figure(
                    chosen,
                    display_width=display_width,
                    pdf_dpi=pdf_dpi,
                    pdf_mode=pdf_mode,
                    pdf_embed_height=pdf_embed_height,
                )

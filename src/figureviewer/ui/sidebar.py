from __future__ import annotations

import streamlit as st

from figureviewer.browsing import init_browse_state
from figureviewer.navigation import go_first, go_last
from figureviewer.ui.column_browser import render_selected_panels_sidebar


def render_sidebar() -> None:
    init_browse_state()

    st.header("Panels")
    st.checkbox(
        "Show directory browser",
        value=True,
        help="Hide after choosing folders to give figures more screen space.",
        key="show_directory_browser",
    )

    render_selected_panels_sidebar()

    st.divider()

    st.checkbox(
        "Include figures in subfolders",
        value=False,
        key="recursive",
    )
    st.checkbox(
        "Sync panels",
        value=True,
        help="When on, all panels show the same file index or same filename stem.",
        key="sync_mode",
    )
    st.radio(
        "Sync by",
        ["position", "filename stem"],
        index=0,
        disabled=not st.session_state.sync_mode,
        key="match_by",
    )
    if st.session_state.match_by == "filename stem":
        st.caption(
            "Stem sync matches extensions (e.g. `fig1.png` ↔ `fig1.pdf`). "
            "Duplicate stems use the first file in natural sort order."
        )
    st.checkbox("Show metadata editors", value=False, key="show_metadata")
    st.checkbox("Compact UI", value=True, key="compact_ui")
    st.slider("Panels per row", min_value=1, max_value=4, value=2, key="columns_per_row")

    st.header("Display")
    st.radio(
        "Display size",
        ["Fill panel", "Natural size", "Custom width"],
        index=0,
        help="Fill panel uses full column width. Natural size shows native pixels up to the column width.",
        key="display_mode",
    )
    if st.session_state.display_mode == "Custom width":
        st.slider(
            "Custom width (px)",
            min_value=250,
            max_value=2400,
            value=700,
            step=50,
            key="custom_width",
        )

    st.radio("PDF display", ["Rasterize", "Embedded viewer"], index=0, key="pdf_mode")
    if st.session_state.pdf_mode == "Rasterize":
        st.slider("PDF raster DPI", min_value=100, max_value=400, value=200, step=25, key="pdf_dpi")
    else:
        st.slider(
            "PDF viewer height (px)",
            min_value=300,
            max_value=1200,
            value=700,
            step=50,
            key="pdf_embed_height",
        )

    st.header("Navigation")
    st.caption("Shortcuts (figure area only): ← previous · → next · Home first · End last")
    col_first, col_last = st.columns(2)
    with col_first:
        if st.button("First", key="sidebar_first", use_container_width=True):
            go_first()
    with col_last:
        if st.button("Last", key="sidebar_last", use_container_width=True):
            go_last()

from __future__ import annotations

import streamlit as st

from figureviewer.ui import render_column_browser, render_figure_viewport, render_sidebar


def main() -> None:
    st.set_page_config(page_title="Multi-panel Figure Compare", layout="wide")
    st.markdown(
        """<style>
          .block-container { padding-top: 1rem; padding-bottom: 0.5rem; }
        </style>""",
        unsafe_allow_html=True,
    )

    if "current_index" not in st.session_state:
        st.session_state.current_index = 0

    with st.sidebar:
        render_sidebar()

    if not st.session_state.get("compact_ui", True):
        st.title("Multi-panel Figure Compare")
        st.caption(
            "Compare corresponding figures across directories, with optional synchronized navigation."
        )

    if st.session_state.get("show_directory_browser", True):
        render_column_browser()
    render_figure_viewport()


if __name__ == "__main__":
    main()

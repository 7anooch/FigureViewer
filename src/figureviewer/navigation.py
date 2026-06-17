from __future__ import annotations

import streamlit as st


def clamp_index() -> None:
    max_index = max(st.session_state.get("max_index", 0), 0)
    st.session_state.current_index = max(0, min(st.session_state.get("current_index", 0), max_index))


def sync_nav_index() -> None:
    st.session_state.nav_index = st.session_state.current_index


def next_image(delta: int) -> None:
    st.session_state.current_index = st.session_state.get("current_index", 0) + delta
    clamp_index()
    sync_nav_index()


def go_first() -> None:
    st.session_state.current_index = 0
    sync_nav_index()


def go_last() -> None:
    st.session_state.current_index = st.session_state.get("max_index", 0)
    sync_nav_index()


def on_nav_index_change() -> None:
    st.session_state.current_index = st.session_state.nav_index
    clamp_index()
    sync_nav_index()

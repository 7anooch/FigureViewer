from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import streamlit as st
import streamlit.components.v1 as components

_COMPONENT_PATH = Path(__file__).parent
_keynav = components.declare_component("figure_keynav", path=str(_COMPONENT_PATH))

_LAST_EVENT_KEY = "__figure_keynav_last_event__"
_CSS_FLAG = "__figure_keynav_css__"


def _inject_css() -> None:
    if st.session_state.get(_CSS_FLAG):
        return
    st.session_state[_CSS_FLAG] = True
    st.markdown(
        """
<style>
.st-key-figure_keynav,
.st-key-figure_keynav > div {
  margin:0 !important; padding:0 !important;
  height:0 !important; min-height:0 !important;
  border:0 !important; overflow:hidden !important;
}
.st-key-figure_keynav iframe {
  width:0 !important; height:0 !important; border:0 !important;
  position:absolute !important; opacity:0 !important; pointer-events:none !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def listen_keyboard(*, armed: bool = True) -> Optional[str]:
    """Return 'prev', 'next', 'first', or 'last' once per key press outside the sidebar."""
    _inject_css()
    event: Any = _keynav(armed=armed, key="figure_keynav", default=None)
    if not event or not isinstance(event, dict):
        return None
    action = event.get("id")
    if not action:
        return None
    token = (action, event.get("ts"))
    if st.session_state.get(_LAST_EVENT_KEY) == token:
        return None
    st.session_state[_LAST_EVENT_KEY] = token
    return str(action)

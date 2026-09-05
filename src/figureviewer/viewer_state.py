from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator


VIEWER_STATE_DEFAULTS: dict[str, Any] = {
    "panel_directories": [],
    "recursive": False,
    "sync_mode": True,
    "match_by": "position",
    "show_metadata": False,
    "show_directory_browser": True,
    "columns_per_row": 2,
    "display_mode": "Fill panel",
    "custom_width": 700,
    "pdf_mode": "Rasterize",
    "pdf_dpi": 200,
    "pdf_embed_height": 700,
    "trim_whitespace": False,
    "current_index": 0,
    "max_index": 0,
    "export_output_dir": "",
    "export_output_dir_user_set": False,
    "export_choose_dir_on_save": False,
    "export_use_custom_titles": False,
    "export_custom_titles_text": "",
    "export_pdf_dpi": 300,
    "export_preserve_native": True,
    "export_min_panel_width": 1200,
    "browse_root": "",
    "tree_stack": [],
}


class ViewerState:
    """Dict-like settings store compatible with display_state.get_viewport_snapshot."""

    def __init__(self, **overrides: Any) -> None:
        self._data: dict[str, Any] = dict(VIEWER_STATE_DEFAULTS)
        self._data.update(overrides)
        if not self._data.get("browse_root"):
            home = str(Path.home())
            self._data["browse_root"] = home
            self._data["tree_stack"] = [home]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def keys(self) -> Iterator[str]:
        return iter(self._data)

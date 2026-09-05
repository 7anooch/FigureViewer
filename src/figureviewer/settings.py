from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path.home() / ".config" / "figureviewer"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

# Persisted across launches (beyond browse root).
_STICKY_KEYS = (
    "display_mode",
    "pdf_dpi",
    "custom_width",
    "trim_whitespace",
    "columns_per_row",
    "export_output_dir",
    "export_pdf_dpi",
)


def _load_settings() -> dict:
    if not _CONFIG_FILE.is_file():
        return {}
    try:
        return json.loads(_CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_settings(data: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")


def load_default_browse_root() -> str | None:
    path = _load_settings().get("default_browse_root")
    if not path:
        return None
    resolved = Path(path).expanduser().resolve()
    if resolved.is_dir():
        return str(resolved)
    return None


def save_default_browse_root(path: str) -> None:
    resolved = str(Path(path).expanduser().resolve())
    data = _load_settings()
    data["default_browse_root"] = resolved
    _save_settings(data)


def clear_default_browse_root() -> None:
    data = _load_settings()
    if "default_browse_root" not in data:
        return
    data.pop("default_browse_root")
    _save_settings(data)


def load_sticky_prefs() -> dict[str, Any]:
    """Return persisted display/export prefs that should seed ViewerState."""
    data = _load_settings()
    prefs: dict[str, Any] = {}
    for key in _STICKY_KEYS:
        if key not in data:
            continue
        value = data[key]
        if key == "export_output_dir":
            if not value:
                continue
            path = Path(str(value)).expanduser()
            if path.is_dir():
                prefs[key] = str(path.resolve())
                prefs["export_output_dir_user_set"] = True
            continue
        prefs[key] = value
    return prefs


def save_sticky_prefs(**updates: Any) -> None:
    """Merge sticky display/export prefs into settings.json."""
    data = _load_settings()
    changed = False
    for key, value in updates.items():
        if key not in _STICKY_KEYS:
            continue
        if key == "export_output_dir" and value:
            value = str(Path(str(value)).expanduser().resolve())
        if data.get(key) != value:
            data[key] = value
            changed = True
    if changed:
        _save_settings(data)

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "figureviewer"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"


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

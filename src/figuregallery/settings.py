from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "figuregallery"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

_RECENT_ROOTS_MAX = 8


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


def _resolved_dir(path: Path | str) -> Path | None:
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return None
    if resolved.is_dir():
        return resolved
    return None


def load_last_root() -> Path | None:
    path = _load_settings().get("last_root")
    if not path:
        return None
    return _resolved_dir(path)


def load_recent_roots() -> list[Path]:
    raw = _load_settings().get("recent_roots")
    if not isinstance(raw, list):
        return []
    roots: list[Path] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        resolved = _resolved_dir(item)
        if resolved is None:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)
        if len(roots) >= _RECENT_ROOTS_MAX:
            break
    return roots


def save_last_root(path: Path) -> None:
    """Set last_root and push path to the front of recent_roots (MRU, max 8)."""
    resolved = _resolved_dir(path)
    if resolved is None:
        return
    key = str(resolved)
    data = _load_settings()
    data["last_root"] = key
    existing = data.get("recent_roots")
    recent: list[str] = []
    if isinstance(existing, list):
        for item in existing:
            if isinstance(item, str) and item != key:
                recent.append(item)
    recent.insert(0, key)
    data["recent_roots"] = recent[:_RECENT_ROOTS_MAX]
    _save_settings(data)

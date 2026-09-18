from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path.home() / ".config" / "figureviewer"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"
_SAVE_WARNED = False

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


def _fallback_config_dirs() -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []
    if sys.platform == "darwin":
        dirs.append(home / "Library" / "Application Support" / "FigureViewer")
    dirs.append(home / ".figureviewer")
    return dirs


def _settings_candidates() -> list[Path]:
    """Primary settings path first, then fallbacks (deduped)."""
    seen: set[Path] = set()
    out: list[Path] = []
    for directory in [_CONFIG_DIR, *_fallback_config_dirs()]:
        path = directory / "settings.json"
        key = path
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _load_settings() -> dict:
    for path in _settings_candidates():
        if not path.is_file():
            continue
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def _warn_save_failure(detail: str) -> None:
    global _SAVE_WARNED
    if _SAVE_WARNED:
        return
    _SAVE_WARNED = True
    warnings.warn(
        f"Could not save Figure Viewer settings ({detail}). "
        "The app will run, but preferences may not persist. "
        "Check ownership/permissions on ~/.config/figureviewer "
        "(e.g. created by a different user or with sudo).",
        UserWarning,
        stacklevel=3,
    )


def _save_settings(data: dict) -> None:
    """Write settings.json; never raise — launch must not die on config permissions."""
    global _CONFIG_DIR, _CONFIG_FILE
    payload = json.dumps(data, indent=2) + "\n"
    attempts: list[tuple[Path, Path]] = [(_CONFIG_DIR, _CONFIG_FILE)]
    for directory in _fallback_config_dirs():
        attempts.append((directory, directory / "settings.json"))

    errors: list[str] = []
    for directory, path in attempts:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(payload)
            _CONFIG_DIR = directory
            _CONFIG_FILE = path
            return
        except OSError as exc:
            errors.append(f"{path}: {exc}")
            continue
    _warn_save_failure("; ".join(errors) if errors else "no writable location")


def _resolved_dir(path: Path | str) -> Path | None:
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return None
    if resolved.is_dir():
        return resolved
    return None


def load_default_browse_root() -> str | None:
    path = _load_settings().get("default_browse_root")
    if not path:
        return None
    resolved = _resolved_dir(path)
    return str(resolved) if resolved is not None else None


def save_default_browse_root(path: str) -> None:
    resolved = _resolved_dir(path)
    if resolved is None:
        return
    data = _load_settings()
    data["default_browse_root"] = str(resolved)
    _save_settings(data)


def clear_default_browse_root() -> None:
    data = _load_settings()
    if "default_browse_root" not in data:
        return
    data.pop("default_browse_root")
    _save_settings(data)


_RECENT_ROOTS_MAX = 8


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


def remember_recent_root(path: Path | str) -> None:
    """Push a directory to the front of recent_roots (MRU, max 8)."""
    resolved = _resolved_dir(path)
    if resolved is None:
        return
    key = str(resolved)
    data = _load_settings()
    existing = data.get("recent_roots")
    recent: list[str] = []
    if isinstance(existing, list):
        for item in existing:
            if isinstance(item, str) and item != key:
                recent.append(item)
    recent.insert(0, key)
    data["recent_roots"] = recent[:_RECENT_ROOTS_MAX]
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


def load_desktop_mode() -> str | None:
    """Last unified-desktop mode: ``compare`` or ``browse``."""
    value = _load_settings().get("desktop_mode")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None


def save_desktop_mode(mode: str) -> None:
    key = str(mode).strip().lower()
    if key not in {"compare", "browse"}:
        return
    data = _load_settings()
    if data.get("desktop_mode") == key:
        return
    data["desktop_mode"] = key
    _save_settings(data)

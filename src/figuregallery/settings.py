from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "figuregallery"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"
_SAVE_WARNED = False

_RECENT_ROOTS_MAX = 8


def _fallback_config_dirs() -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []
    if sys.platform == "darwin":
        dirs.append(home / "Library" / "Application Support" / "FigureGallery")
    dirs.append(home / ".figuregallery")
    return dirs


def _settings_candidates() -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for directory in [_CONFIG_DIR, *_fallback_config_dirs()]:
        path = directory / "settings.json"
        if path in seen:
            continue
        seen.add(path)
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
        f"Could not save Figure Gallery settings ({detail}). "
        "The app will run, but preferences may not persist. "
        "Check ownership/permissions on ~/.config/figuregallery "
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


def load_hide_unavailable_categories() -> bool:
    return bool(_load_settings().get("hide_unavailable_categories", False))


def save_hide_unavailable_categories(hide: bool) -> None:
    data = _load_settings()
    value = bool(hide)
    if data.get("hide_unavailable_categories") == value:
        return
    data["hide_unavailable_categories"] = value
    _save_settings(data)

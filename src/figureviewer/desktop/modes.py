"""Desktop app modes: Compare (multi-panel) vs Browse (gallery)."""

from __future__ import annotations

from enum import Enum


class AppMode(str, Enum):
    COMPARE = "compare"
    BROWSE = "browse"

    @classmethod
    def parse(cls, value: str | None, *, default: AppMode | None = None) -> AppMode:
        if value is None:
            if default is not None:
                return default
            raise ValueError("mode is required")
        key = str(value).strip().lower()
        try:
            return cls(key)
        except ValueError as exc:
            raise ValueError(f"unknown mode: {value!r} (expected compare|browse)") from exc

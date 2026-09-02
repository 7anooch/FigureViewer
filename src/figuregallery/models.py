from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from figurecommon.exts import is_displayable_path


class GroupMode(Enum):
    STEM = "stem"
    FILENAME = "filename"


class SortMode(Enum):
    CATEGORY_THEN_PATH = "category_then_path"
    PATH_THEN_CATEGORY = "path_then_category"


@dataclass(frozen=True)
class FigureRef:
    absolute_path: Path
    relative_path: Path
    filename: str
    stem: str

    @property
    def parent_relative(self) -> Path:
        return self.relative_path.parent

    @property
    def is_displayable(self) -> bool:
        return is_displayable_path(self.absolute_path)

    def category_key(self, mode: GroupMode) -> str:
        return self.stem if mode == GroupMode.STEM else self.filename


@dataclass
class Category:
    key: str
    refs: list[FigureRef] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.refs)

    @property
    def displayable_refs(self) -> list[FigureRef]:
        return [r for r in self.refs if r.is_displayable]

    @property
    def pdf_count(self) -> int:
        return sum(1 for r in self.refs if not r.is_displayable)

    @property
    def is_selectable(self) -> bool:
        return bool(self.displayable_refs)

    def label(self) -> str:
        if self.pdf_count and self.is_selectable:
            return f"{self.key} ({len(self.displayable_refs)} + {self.pdf_count} pdf)"
        if self.pdf_count and not self.is_selectable:
            return f"{self.key} ({self.pdf_count} pdf)"
        return f"{self.key} ({self.count})"


@dataclass
class ScanIndex:
    root: Path
    refs: list[FigureRef]
    scanned_at: float
